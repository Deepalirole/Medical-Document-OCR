from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    warnings: list[dict[str, str]]


class DynamicValidator:
    def validate(self, definition: dict[str, Any], data: dict[str, Any]) -> ValidationResult:
        warnings: list[dict[str, str]] = []
        for section in definition["sections"]:
            self._validate_node(section, data.get(section["key"]), section["key"], warnings)
        return ValidationResult(not warnings, warnings)

    def _validate_node(
        self, node: dict[str, Any], value: Any, path: str, warnings: list[dict[str, str]]
    ) -> None:
        if value is None:
            if node.get("required"):
                warnings.append({"path": path, "code": "REQUIRED_VALUE_MISSING"})
            return
        field_type = node["type"]
        if field_type == "object":
            if not isinstance(value, dict):
                warnings.append({"path": path, "code": "TYPE_MISMATCH"})
                return
            for child in node["fields"]:
                self._validate_node(
                    child, value.get(child["key"]), f"{path}.{child['key']}", warnings
                )
        elif field_type in {"array", "medicine_list"}:
            if not isinstance(value, list):
                warnings.append({"path": path, "code": "TYPE_MISMATCH"})
                return
            if node.get("required") and not value:
                warnings.append({"path": path, "code": "REQUIRED_VALUE_MISSING"})
            for index, item in enumerate(value):
                if "type" in node["item_schema"]:
                    self._validate_node(
                        {"key": "item", **node["item_schema"]},
                        item,
                        f"{path}[{index}]",
                        warnings,
                    )
                    continue
                if not isinstance(item, dict):
                    warnings.append({"path": f"{path}[{index}]", "code": "TYPE_MISMATCH"})
                    continue
                for key, definition in node["item_schema"].items():
                    self._validate_node(
                        {"key": key, **definition},
                        item.get(key),
                        f"{path}[{index}].{key}",
                        warnings,
                    )
        elif not self._is_scalar_valid(node, value):
            warnings.append({"path": path, "code": "TYPE_MISMATCH"})

    @staticmethod
    def _is_scalar_valid(node: dict[str, Any], value: Any) -> bool:
        field_type = node["type"]
        if field_type in {"string", "free_text"}:
            return isinstance(value, str)
        if field_type == "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if field_type == "boolean":
            return isinstance(value, bool)
        if field_type == "date":
            if not isinstance(value, str):
                return False
            try:
                date.fromisoformat(value)
                return True
            except ValueError:
                return False
        if field_type == "enum":
            return value in node.get("options", [])
        if field_type == "key_value":
            return isinstance(value, dict)
        return True
