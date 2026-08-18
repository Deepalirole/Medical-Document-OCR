"""Mapping from the approved prescription contract to the Medikunj HMIS schema.

The approved ``data`` object is dynamic and defined by the pinned schema version, while
the destination tables (``patients``, ``prescriptions``, ``prescription_items``) are fixed.
This module bridges the two with an explicit, configurable path mapping so that a new
prescription schema needs a mapping entry rather than a code change, and so that nothing
is inferred from field names the reviewer never approved.
"""

from dataclasses import dataclass, field
from typing import Any

from app.core.errors import AppError
from app.services.integrations.base import HMISDocument

SOURCE_NAMESPACE = "pse"
MEDICINE_SECTION_TYPES = {"medicine_list"}
MEDICINE_KEY_CANDIDATES = ("medicines", "medications", "drugs", "rx")


@dataclass(frozen=True)
class MedikunjFieldMapping:
    """Destination column -> ordered candidate paths in the approved ``data`` object."""

    patient: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: {
            "full_name": ("patient.name", "patient.full_name", "patient_name"),
            "age_at_reg": ("patient.age", "patient_age"),
            "gender": ("patient.gender", "patient_gender", "patient.sex"),
            "mobile_number": ("patient.mobile", "patient.phone", "patient.contact"),
            "address": ("patient.address",),
        }
    )
    prescription: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: {
            "notes": ("notes", "advice", "remarks", "instructions"),
        }
    )
    prescription_item: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: {
            "drug_name": ("medicine_name", "drug_name", "name"),
            "dosage": ("strength", "dose", "dosage"),
            "frequency": ("frequency", "timing"),
            "duration": ("duration",),
            "quantity": ("quantity", "qty"),
            "instructions": ("instructions", "note", "remarks"),
        }
    )
    integer_columns: frozenset[str] = frozenset({"age_at_reg", "quantity"})


class MedikunjMapper:
    """Translates one approved integration payload into Medikunj records."""

    def __init__(self, mapping: MedikunjFieldMapping | None = None) -> None:
        self.mapping = mapping or MedikunjFieldMapping()

    @property
    def name(self) -> str:
        return "medikunj"

    def map(
        self,
        payload: dict[str, Any],
        schema_definition: dict[str, Any] | None = None,
    ) -> HMISDocument:
        contract_version = str(payload.get("contract_version", ""))
        if contract_version != "1.0":
            raise AppError(
                "HMIS_CONTRACT_UNSUPPORTED",
                "The approved payload uses an unsupported integration contract version.",
                409,
                {"contract_version": contract_version},
            )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise AppError(
                "HMIS_PAYLOAD_INVALID",
                "The approved payload carries no structured object to map.",
                409,
            )

        prescription_id = str(payload["prescription_id"])
        approved_version = int(payload["approved_version"])
        source_id = f"{SOURCE_NAMESPACE}:{prescription_id}:v{approved_version}"

        consumed: set[str] = set()
        rejected: list[str] = []
        medicine_key = self._medicine_key(data, schema_definition)

        patient = self._map_object(data, self.mapping.patient, consumed, rejected)
        prescription = self._map_object(data, self.mapping.prescription, consumed, rejected)
        items = self._map_items(data, medicine_key, consumed, rejected)

        patient["source_id"] = source_id
        prescription["source_id"] = source_id

        unmapped = sorted(set(self._leaf_paths(data)) - consumed)
        return HMISDocument(
            contract_version=contract_version,
            source_id=source_id,
            prescription_id=prescription_id,
            organization_id=str(payload["organization_id"]),
            approved_version=approved_version,
            patient=patient,
            prescription=prescription,
            prescription_items=items,
            source_data=payload,
            unmapped=unmapped + sorted(rejected),
        )

    def _medicine_key(
        self, data: dict[str, Any], schema_definition: dict[str, Any] | None
    ) -> str | None:
        for section in (schema_definition or {}).get("sections", []):
            if isinstance(section, dict) and section.get("type") in MEDICINE_SECTION_TYPES:
                key = section.get("key")
                if isinstance(key, str):
                    return key
        for candidate in MEDICINE_KEY_CANDIDATES:
            if isinstance(data.get(candidate), list):
                return candidate
        return None

    def _map_object(
        self,
        data: dict[str, Any],
        columns: dict[str, tuple[str, ...]],
        consumed: set[str],
        rejected: list[str],
    ) -> dict[str, Any]:
        mapped: dict[str, Any] = {}
        for column, candidates in columns.items():
            for path in candidates:
                value = self._resolve(data, path)
                if value is None:
                    continue
                coerced = self._coerce(column, value)
                if coerced is None:
                    rejected.append(f"{path}:not-coercible")
                    consumed.add(path)
                    break
                mapped[column] = coerced
                consumed.add(path)
                break
        return mapped

    def _map_items(
        self,
        data: dict[str, Any],
        medicine_key: str | None,
        consumed: set[str],
        rejected: list[str],
    ) -> list[dict[str, Any]]:
        if not medicine_key:
            return []
        rows = data.get(medicine_key)
        if not isinstance(rows, list):
            return []
        items: list[dict[str, Any]] = []
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                rejected.append(f"{medicine_key}[{index}]:not-an-object")
                continue
            mapped: dict[str, Any] = {}
            for column, candidates in self.mapping.prescription_item.items():
                for key in candidates:
                    value = row.get(key)
                    if value is None:
                        continue
                    coerced = self._coerce(column, value)
                    if coerced is None:
                        rejected.append(f"{medicine_key}[].{key}:not-coercible")
                        consumed.add(f"{medicine_key}[].{key}")
                        break
                    mapped[column] = coerced
                    consumed.add(f"{medicine_key}[].{key}")
                    break
            if not mapped.get("drug_name"):
                raise AppError(
                    "HMIS_MEDICINE_UNMAPPABLE",
                    "An approved medicine row has no mappable drug name; dispatch was refused.",
                    409,
                    {"row_index": index},
                )
            items.append(mapped)
        return items

    def _coerce(self, column: str, value: Any) -> Any:
        if column in self.mapping.integer_columns:
            if isinstance(value, bool):
                return None
            if isinstance(value, int):
                return value
            try:
                return int(float(str(value).strip()))
            except (TypeError, ValueError):
                return None
        if isinstance(value, str):
            trimmed = value.strip()
            return trimmed or None
        if isinstance(value, (int, float, bool)):
            return str(value)
        return None

    @staticmethod
    def _resolve(data: dict[str, Any], path: str) -> Any:
        current: Any = data
        for part in path.split("."):
            if not isinstance(current, dict):
                return None
            current = current.get(part)
        return current

    @classmethod
    def _leaf_paths(cls, value: Any, prefix: str = "") -> list[str]:
        if isinstance(value, dict):
            paths: list[str] = []
            for key, child in value.items():
                paths.extend(cls._leaf_paths(child, f"{prefix}.{key}" if prefix else key))
            return paths
        if isinstance(value, list):
            paths = []
            for item in value:
                paths.extend(cls._leaf_paths(item, f"{prefix}[]"))
            return sorted(set(paths))
        return [prefix] if prefix else []
