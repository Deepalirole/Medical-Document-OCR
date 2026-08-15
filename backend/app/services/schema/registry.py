from copy import deepcopy
from typing import Any

from app.core.errors import AppError


class SchemaRegistry:
    ALLOWED_TYPES = {
        "string",
        "number",
        "date",
        "boolean",
        "enum",
        "object",
        "array",
        "medicine_list",
        "key_value",
        "free_text",
    }

    def validate(self, definition: dict[str, Any]) -> dict[str, Any]:
        sections = definition.get("sections")
        if not isinstance(sections, list) or not sections:
            raise AppError("SCHEMA_INVALID", "A schema must contain at least one section.", 422)
        seen: set[str] = set()
        for section in sections:
            self._validate_node(section, seen, "sections")
        return deepcopy(definition)

    def _validate_node(self, node: Any, seen: set[str], context: str) -> None:
        if not isinstance(node, dict):
            raise AppError("SCHEMA_INVALID", f"{context} entries must be objects.", 422)
        key = node.get("key")
        field_type = node.get("type")
        if not isinstance(key, str) or not key or not key.replace("_", "a").isalnum():
            raise AppError("SCHEMA_INVALID", f"{context} contains an invalid key.", 422)
        qualified = f"{context}.{key}"
        if qualified in seen:
            raise AppError("SCHEMA_INVALID", f"Duplicate schema key: {key}.", 422)
        seen.add(qualified)
        if field_type not in self.ALLOWED_TYPES:
            raise AppError("SCHEMA_INVALID", f"Unsupported field type: {field_type}.", 422)

        if field_type == "object":
            fields = node.get("fields")
            if not isinstance(fields, list) or not fields:
                raise AppError("SCHEMA_INVALID", f"Object {key} requires fields.", 422)
            child_seen: set[str] = set()
            for child in fields:
                self._validate_node(child, child_seen, qualified)
        elif field_type in {"array", "medicine_list"}:
            item_schema = node.get("item_schema")
            if not isinstance(item_schema, dict) or not item_schema:
                raise AppError("SCHEMA_INVALID", f"Array {key} requires item_schema.", 422)
            if "type" in item_schema:
                self._validate_node({"key": "item", **item_schema}, set(), qualified)
            else:
                for child_key, child_definition in item_schema.items():
                    child = {"key": child_key, **child_definition}
                    self._validate_node(child, set(), qualified)
        elif field_type == "enum":
            options = node.get("options") or node.get("validators", {}).get("options")
            if not isinstance(options, list) or not options:
                raise AppError("SCHEMA_INVALID", f"Enum {key} requires options.", 422)

    def to_json_schema(self, definition: dict[str, Any]) -> dict[str, Any]:
        self.validate(definition)
        properties: dict[str, Any] = {}
        for section in definition["sections"]:
            properties[section["key"]] = self._node_to_json_schema(section)
        schema: dict[str, Any] = {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        }
        return schema

    def _node_to_json_schema(self, node: dict[str, Any]) -> dict[str, Any]:
        field_type = node["type"]
        if field_type == "object":
            properties = {
                child["key"]: self._node_to_json_schema(child) for child in node["fields"]
            }
            output: dict[str, Any] = {
                "type": ["object", "null"],
                "properties": properties,
                "required": list(properties),
                "additionalProperties": False,
            }
            return output
        if field_type in {"array", "medicine_list"}:
            if "type" in node["item_schema"]:
                return {
                    "type": ["array", "null"],
                    "items": self._node_to_json_schema(
                        {"key": "item", **node["item_schema"]}
                    ),
                }
            item_properties = {
                key: self._node_to_json_schema({"key": key, **value})
                for key, value in node["item_schema"].items()
            }
            item: dict[str, Any] = {
                "type": "object",
                "properties": item_properties,
                "required": list(item_properties),
                "additionalProperties": False,
            }
            return {"type": ["array", "null"], "items": item}
        mapping: dict[str, Any] = {
            "string": {"type": ["string", "null"]},
            "free_text": {"type": ["string", "null"]},
            "date": {"type": ["string", "null"], "format": "date"},
            "number": {"type": ["number", "null"]},
            "boolean": {"type": ["boolean", "null"]},
            "key_value": {"type": ["object", "null"], "additionalProperties": True},
            "enum": {"type": ["string", "null"], "enum": [*node.get("options", []), None]},
        }
        return mapping[field_type]
