import re
from dataclasses import asdict, dataclass
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class MappedField:
    field_path: str
    field_type: str
    array_item_id: str | None
    original_value: Any
    current_value: Any
    review_status: str
    confidence: float | None
    evidence: list[dict[str, Any]]
    validation: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class DynamicFieldMapper:
    def map(
        self,
        definition: dict[str, Any],
        structured_output: dict[str, Any],
        evidence: list[dict[str, Any]],
    ) -> list[MappedField]:
        fields: list[MappedField] = []
        for section in definition["sections"]:
            value = structured_output.get(section["key"])
            self._map_node(section, value, section["key"], evidence, fields, None)
        return fields

    def _map_node(
        self,
        node: dict[str, Any],
        value: Any,
        path: str,
        evidence: list[dict[str, Any]],
        output: list[MappedField],
        array_item_id: str | None,
    ) -> None:
        field_type = node["type"]
        if field_type == "object":
            values = value if isinstance(value, dict) else {}
            for child in node["fields"]:
                self._map_node(
                    child,
                    values.get(child["key"]),
                    f"{path}.{child['key']}",
                    evidence,
                    output,
                    array_item_id,
                )
            return
        if field_type in {"array", "medicine_list"}:
            items = value if isinstance(value, list) else []
            valid_items = [
                item
                for item in items
                if not (isinstance(item, dict) and all(v in (None, "", []) for v in item.values()))
            ]
            if not valid_items:
                output.append(self._make_field(node, [], path, evidence, None))
                return
            for index, item in enumerate(valid_items):
                item_id = str(uuid4())
                if "type" in node["item_schema"]:
                    child = {"key": "item", **node["item_schema"]}
                    self._map_node(
                        child,
                        item,
                        f"{path}[{index}]",
                        evidence,
                        output,
                        item_id,
                    )
                    continue
                item_values = item if isinstance(item, dict) else {}
                for key, child_definition in node["item_schema"].items():
                    child = {"key": key, **child_definition}
                    self._map_node(
                        child,
                        item_values.get(key),
                        f"{path}[{index}].{key}",
                        evidence,
                        output,
                        item_id,
                    )
        if value in (None, "", []):
            if node.get("required"):
                output.append(self._make_field(node, value, path, evidence, array_item_id))
            return
        output.append(self._make_field(node, value, path, evidence, array_item_id))

    def _make_field(
        self,
        node: dict[str, Any],
        value: Any,
        path: str,
        evidence: list[dict[str, Any]],
        array_item_id: str | None,
    ) -> MappedField:
        matches = self._find_evidence(value, evidence)
        confidences = [item["confidence"] for item in matches if item.get("confidence") is not None]
        confidence = sum(confidences) / len(confidences) if confidences else None
        required_missing = bool(
            node.get("required") and (value is None or value == "" or value == [])
        )
        unsupported = value not in (None, "", []) and not matches
        validation = {
            "valid": not required_missing and not unsupported,
            "warnings": [
                *(["REQUIRED_VALUE_MISSING"] if required_missing else []),
                *(["VALUE_HAS_NO_MATCHING_EVIDENCE"] if unsupported else []),
            ],
        }
        if required_missing or unsupported:
            review_status = "REVIEW_REQUIRED"
        elif value in (None, "", []):
            review_status = "LOW"
        elif confidence is None:
            review_status = "MEDIUM"
        elif confidence >= 0.85:
            review_status = "HIGH"
        elif confidence >= 0.7:
            review_status = "MEDIUM"
        else:
            review_status = "LOW"
        return MappedField(
            field_path=path,
            field_type=node["type"],
            array_item_id=array_item_id,
            original_value=value,
            current_value=value,
            review_status=review_status,
            confidence=confidence,
            evidence=matches,
            validation=validation,
        )

    @staticmethod
    def _find_evidence(value: Any, evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if value is None or isinstance(value, (dict, list, bool)):
            return []
        needle = re.sub(r"\s+", " ", str(value).strip().casefold())
        if not needle:
            return []
        matches = []
        for item in evidence:
            haystack = re.sub(r"\s+", " ", str(item.get("text", "")).strip().casefold())
            if needle in haystack or (len(needle) >= 3 and haystack in needle):
                matches.append(item)
        return matches


PATH_PART = re.compile(r"([^.[\]]+)|\[(\d+)\]")


def build_structured_json(fields: list[dict[str, Any]]) -> dict[str, Any]:
    root: dict[str, Any] = {}
    for field in sorted(fields, key=lambda item: item["field_path"]):
        if field["field_type"] in {"array", "medicine_list"} and field["field_path"].find("[") < 0:
            root.setdefault(field["field_path"], field.get("current_value") or [])
            continue
        parts: list[str | int] = []
        for match in PATH_PART.finditer(field["field_path"]):
            parts.append(int(match.group(2)) if match.group(2) is not None else match.group(1))
        _set_value(root, parts, field.get("current_value"))
    return _remove_empty_array_rows(root)


def _set_value(root: dict[str, Any], parts: list[str | int], value: Any) -> None:
    current: Any = root
    for index, part in enumerate(parts):
        last = index == len(parts) - 1
        next_part = parts[index + 1] if not last else None
        if isinstance(part, str):
            if last:
                current[part] = value
            else:
                current.setdefault(part, [] if isinstance(next_part, int) else {})
                current = current[part]
        else:
            while len(current) <= part:
                current.append({} if not isinstance(next_part, int) else [])
            if last:
                current[part] = value
            else:
                current = current[part]


def _remove_empty_array_rows(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _remove_empty_array_rows(child) for key, child in value.items()}
    if isinstance(value, list):
        cleaned = [_remove_empty_array_rows(child) for child in value]
        return [
            child
            for child in cleaned
            if not (isinstance(child, dict) and all(item is None for item in child.values()))
        ]
    return value
