"""JSON Parser Tool - JSON parsing and transformation.

Provides operations for parsing JSON from text, JSONPath queries,
schema validation, and JSON transformation.
"""

from __future__ import annotations

import json
import re
from typing import Any

import structlog

from leagent.tools.base import SyncTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)


class JsonParserTool(SyncTool):
    """Parse, query, and transform JSON data.

    Features:
    - Parse JSON from text (with extraction from markdown/mixed content)
    - JSONPath-like queries
    - JSON Schema validation
    - Transform/reshape JSON structures
    - Merge and diff JSON objects
    - Flatten and unflatten nested structures
    """

    name = "json_parser"
    description = (
        "Parse JSON from text, query with JSONPath expressions, validate against schemas, "
        "and transform JSON structures."
    )
    category = ToolCategory.UTIL
    version = "1.0.0"
    timeout_sec = 60
    aliases = ["json", "jsonpath", "json_query"]
    search_hint = "JSON parse query JSONPath validate schema transform structure"
    is_concurrency_safe = True
    is_read_only = True
    interrupt_behavior = "cancel"
    max_result_size_chars = 200_000

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        op = (params or {}).get("operation", "parse")
        return f"Processing JSON ({op})"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "parse",
                        "query",
                        "validate",
                        "transform",
                        "merge",
                        "diff",
                        "flatten",
                        "unflatten",
                        "stringify",
                        "extract",
                    ],
                    "description": "JSON operation to perform.",
                },
                "text": {
                    "type": "string",
                    "description": "Text containing JSON to parse.",
                },
                "data": {
                    "description": "JSON data object to operate on.",
                },
                "path": {
                    "type": "string",
                    "description": "JSONPath expression for query (e.g., '$.store.book[0].title').",
                },
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Multiple JSONPath expressions.",
                },
                "schema": {
                    "type": "object",
                    "description": "JSON Schema for validation.",
                },
                "transform_spec": {
                    "type": "object",
                    "description": "Transformation specification (field mappings).",
                },
                "data2": {
                    "description": "Second JSON object for merge/diff operations.",
                },
                "merge_strategy": {
                    "type": "string",
                    "enum": ["shallow", "deep", "replace", "concat_arrays"],
                    "description": "Strategy for merging objects.",
                    "default": "deep",
                },
                "separator": {
                    "type": "string",
                    "description": "Separator for flatten/unflatten (default: '.').",
                    "default": ".",
                },
                "indent": {
                    "type": "integer",
                    "description": "Indentation for stringify output.",
                    "default": 2,
                },
                "strict": {
                    "type": "boolean",
                    "description": "Strict mode for parsing (fail on errors).",
                    "default": False,
                },
            },
            "required": ["operation"],
            "additionalProperties": False,
        }

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Execute JSON operation.

        Args:
            params: Tool parameters including operation and data.
            context: Execution context.

        Returns:
            Dictionary containing operation result.

        Raises:
            ValueError: If parameters are invalid.
            json.JSONDecodeError: If JSON parsing fails.
        """
        operation = params["operation"]

        logger.info("Executing JSON operation", operation=operation)

        operations = {
            "parse": self._parse_json,
            "query": self._query_json,
            "validate": self._validate_json,
            "transform": self._transform_json,
            "merge": self._merge_json,
            "diff": self._diff_json,
            "flatten": self._flatten_json,
            "unflatten": self._unflatten_json,
            "stringify": self._stringify_json,
            "extract": self._extract_json,
        }

        if operation not in operations:
            raise ValueError(f"Unknown operation: {operation}")

        result = operations[operation](params)

        logger.info("JSON operation complete", operation=operation)
        return result

    def _parse_json(self, params: dict[str, Any]) -> dict[str, Any]:
        """Parse JSON from text."""
        text = params.get("text", "")
        strict = params.get("strict", False)

        if not text:
            if params.get("data") is not None:
                return {"data": params["data"], "source": "provided"}
            raise ValueError("Text is required for parse operation")

        text = text.strip()

        try:
            data = json.loads(text)
            return {
                "data": data,
                "valid": True,
                "type": type(data).__name__,
            }
        except json.JSONDecodeError as e:
            if strict:
                raise

            extracted = self._try_extract_json(text)
            if extracted is not None:
                return {
                    "data": extracted,
                    "valid": True,
                    "extracted": True,
                    "type": type(extracted).__name__,
                }

            return {
                "data": None,
                "valid": False,
                "error": str(e),
                "error_position": e.pos,
            }

    def _try_extract_json(self, text: str) -> Any | None:
        """Try to extract JSON from mixed content."""
        code_block = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if code_block:
            try:
                return json.loads(code_block.group(1).strip())
            except json.JSONDecodeError:
                pass

        for start, end in [("{", "}"), ("[", "]")]:
            first = text.find(start)
            if first != -1:
                depth = 0
                for i, char in enumerate(text[first:], first):
                    if char == start:
                        depth += 1
                    elif char == end:
                        depth -= 1
                        if depth == 0:
                            try:
                                return json.loads(text[first : i + 1])
                            except json.JSONDecodeError:
                                break

        return None

    def _query_json(self, params: dict[str, Any]) -> dict[str, Any]:
        """Query JSON with JSONPath-like expression."""
        data = params.get("data")
        path = params.get("path")
        paths = params.get("paths", [])

        if data is None:
            text = params.get("text")
            if text:
                parsed = self._parse_json({"text": text})
                data = parsed.get("data")
            else:
                raise ValueError("Data or text is required for query operation")

        if path:
            result = self._evaluate_path(data, path)
            return {
                "path": path,
                "result": result,
                "found": result is not None,
            }

        if paths:
            results = {}
            for p in paths:
                results[p] = self._evaluate_path(data, p)
            return {
                "results": results,
                "found_count": sum(1 for v in results.values() if v is not None),
            }

        raise ValueError("Path or paths is required for query operation")

    def _evaluate_path(self, data: Any, path: str) -> Any:
        """Evaluate a JSONPath-like expression."""
        if path.startswith("$"):
            path = path[1:]
        if path.startswith("."):
            path = path[1:]

        if not path:
            return data

        current = data
        parts = self._parse_path(path)

        for part in parts:
            if current is None:
                return None

            if part.startswith("[") and part.endswith("]"):
                inner = part[1:-1]
                if inner == "*":
                    if isinstance(current, list):
                        return current
                    elif isinstance(current, dict):
                        return list(current.values())
                elif ":" in inner:
                    if isinstance(current, list):
                        slice_parts = inner.split(":")
                        start = int(slice_parts[0]) if slice_parts[0] else None
                        end = int(slice_parts[1]) if len(slice_parts) > 1 and slice_parts[1] else None
                        return current[start:end]
                else:
                    try:
                        idx = int(inner)
                        if isinstance(current, list) and -len(current) <= idx < len(current):
                            current = current[idx]
                        else:
                            return None
                    except ValueError:
                        key = inner.strip("'\"")
                        if isinstance(current, dict):
                            current = current.get(key)
                        else:
                            return None
            else:
                if isinstance(current, dict):
                    current = current.get(part)
                else:
                    return None

        return current

    def _parse_path(self, path: str) -> list[str]:
        """Parse JSONPath into parts."""
        parts: list[str] = []
        current = ""
        in_bracket = False
        depth = 0

        for char in path:
            if char == "[":
                if current:
                    parts.append(current)
                    current = ""
                in_bracket = True
                depth += 1
                current += char
            elif char == "]":
                current += char
                depth -= 1
                if depth == 0:
                    parts.append(current)
                    current = ""
                    in_bracket = False
            elif char == "." and not in_bracket:
                if current:
                    parts.append(current)
                    current = ""
            else:
                current += char

        if current:
            parts.append(current)

        return parts

    def _validate_json(self, params: dict[str, Any]) -> dict[str, Any]:
        """Validate JSON against a schema."""
        data = params.get("data")
        schema = params.get("schema")

        if data is None:
            text = params.get("text")
            if text:
                parsed = self._parse_json({"text": text})
                data = parsed.get("data")

        if schema is None:
            raise ValueError("Schema is required for validate operation")

        try:
            import jsonschema
            jsonschema.validate(instance=data, schema=schema)
            return {
                "valid": True,
                "data": data,
                "errors": [],
            }
        except ImportError:
            return self._simple_validate(data, schema)
        except jsonschema.ValidationError as e:
            return {
                "valid": False,
                "data": data,
                "errors": [
                    {
                        "message": e.message,
                        "path": list(e.path),
                        "schema_path": list(e.schema_path),
                    }
                ],
            }
        except jsonschema.SchemaError as e:
            return {
                "valid": False,
                "schema_error": str(e),
                "errors": [{"message": f"Invalid schema: {e.message}"}],
            }

    def _simple_validate(self, data: Any, schema: dict[str, Any]) -> dict[str, Any]:
        """Simple validation without jsonschema library."""
        errors: list[dict[str, Any]] = []

        def validate_type(value: Any, expected: str, path: str) -> None:
            type_map = {
                "string": str,
                "number": (int, float),
                "integer": int,
                "boolean": bool,
                "array": list,
                "object": dict,
                "null": type(None),
            }
            if expected in type_map:
                if not isinstance(value, type_map[expected]):
                    errors.append({
                        "message": f"Expected {expected}, got {type(value).__name__}",
                        "path": path,
                    })

        def validate_object(obj: Any, obj_schema: dict[str, Any], path: str) -> None:
            if "type" in obj_schema:
                validate_type(obj, obj_schema["type"], path)

            if isinstance(obj, dict) and "properties" in obj_schema:
                for prop, prop_schema in obj_schema["properties"].items():
                    if prop in obj:
                        validate_object(obj[prop], prop_schema, f"{path}.{prop}")

                required = obj_schema.get("required", [])
                for req in required:
                    if req not in obj:
                        errors.append({
                            "message": f"Missing required property: {req}",
                            "path": path,
                        })

            if isinstance(obj, list) and "items" in obj_schema:
                for i, item in enumerate(obj):
                    validate_object(item, obj_schema["items"], f"{path}[{i}]")

        validate_object(data, schema, "$")

        return {
            "valid": len(errors) == 0,
            "data": data,
            "errors": errors,
        }

    def _transform_json(self, params: dict[str, Any]) -> dict[str, Any]:
        """Transform JSON using a specification."""
        data = params.get("data")
        spec = params.get("transform_spec", {})

        if data is None:
            raise ValueError("Data is required for transform operation")

        if not spec:
            return {"data": data, "transformed": False}

        result = {}

        for target_field, source_spec in spec.items():
            if isinstance(source_spec, str):
                value = self._evaluate_path(data, source_spec)
            elif isinstance(source_spec, dict):
                source_path = source_spec.get("source", source_spec.get("path"))
                default = source_spec.get("default")
                transform = source_spec.get("transform")

                value = self._evaluate_path(data, source_path) if source_path else None
                if value is None:
                    value = default

                if transform and value is not None:
                    value = self._apply_transform(value, transform)
            else:
                value = source_spec

            self._set_nested(result, target_field, value)

        return {
            "original": data,
            "data": result,
            "transformed": True,
        }

    def _apply_transform(self, value: Any, transform: str) -> Any:
        """Apply a simple transform to a value."""
        transforms: dict[str, Any] = {
            "upper": lambda v: v.upper() if isinstance(v, str) else v,
            "lower": lambda v: v.lower() if isinstance(v, str) else v,
            "trim": lambda v: v.strip() if isinstance(v, str) else v,
            "string": str,
            "int": lambda v: int(v) if v is not None else None,
            "float": lambda v: float(v) if v is not None else None,
            "bool": bool,
            "keys": lambda v: list(v.keys()) if isinstance(v, dict) else None,
            "values": lambda v: list(v.values()) if isinstance(v, dict) else None,
            "length": len,
            "first": lambda v: v[0] if isinstance(v, (list, str)) and v else None,
            "last": lambda v: v[-1] if isinstance(v, (list, str)) and v else None,
        }

        if transform in transforms:
            try:
                return transforms[transform](value)
            except (ValueError, TypeError):
                return value
        return value

    def _set_nested(self, obj: dict[str, Any], path: str, value: Any) -> None:
        """Set a nested value using dot notation."""
        parts = path.split(".")
        current = obj

        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]

        current[parts[-1]] = value

    def _merge_json(self, params: dict[str, Any]) -> dict[str, Any]:
        """Merge two JSON objects."""
        data1 = params.get("data")
        data2 = params.get("data2")
        strategy = params.get("merge_strategy", "deep")

        if data1 is None or data2 is None:
            raise ValueError("Both data and data2 are required for merge operation")

        if strategy == "replace":
            return {"data": data2}
        elif strategy == "shallow":
            if isinstance(data1, dict) and isinstance(data2, dict):
                return {"data": {**data1, **data2}}
            return {"data": data2}
        elif strategy == "concat_arrays":
            result = self._deep_merge(data1, data2, concat_arrays=True)
            return {"data": result}
        else:
            result = self._deep_merge(data1, data2)
            return {"data": result}

    def _deep_merge(self, obj1: Any, obj2: Any, concat_arrays: bool = False) -> Any:
        """Deep merge two objects."""
        if isinstance(obj1, dict) and isinstance(obj2, dict):
            result = obj1.copy()
            for key, value in obj2.items():
                if key in result:
                    result[key] = self._deep_merge(result[key], value, concat_arrays)
                else:
                    result[key] = value
            return result
        elif isinstance(obj1, list) and isinstance(obj2, list) and concat_arrays:
            return obj1 + obj2
        return obj2

    def _diff_json(self, params: dict[str, Any]) -> dict[str, Any]:
        """Calculate difference between two JSON objects."""
        data1 = params.get("data")
        data2 = params.get("data2")

        if data1 is None or data2 is None:
            raise ValueError("Both data and data2 are required for diff operation")

        added: list[dict[str, Any]] = []
        removed: list[dict[str, Any]] = []
        changed: list[dict[str, Any]] = []

        def compare(path: str, v1: Any, v2: Any) -> None:
            if type(v1) != type(v2):
                changed.append({"path": path, "old": v1, "new": v2})
            elif isinstance(v1, dict):
                all_keys = set(v1.keys()) | set(v2.keys())
                for key in all_keys:
                    new_path = f"{path}.{key}" if path else key
                    if key not in v1:
                        added.append({"path": new_path, "value": v2[key]})
                    elif key not in v2:
                        removed.append({"path": new_path, "value": v1[key]})
                    else:
                        compare(new_path, v1[key], v2[key])
            elif isinstance(v1, list):
                if len(v1) != len(v2):
                    changed.append({"path": path, "old": v1, "new": v2})
                else:
                    for i, (item1, item2) in enumerate(zip(v1, v2)):
                        compare(f"{path}[{i}]", item1, item2)
            elif v1 != v2:
                changed.append({"path": path, "old": v1, "new": v2})

        compare("", data1, data2)

        return {
            "added": added,
            "removed": removed,
            "changed": changed,
            "has_differences": bool(added or removed or changed),
            "summary": {
                "added_count": len(added),
                "removed_count": len(removed),
                "changed_count": len(changed),
            },
        }

    def _flatten_json(self, params: dict[str, Any]) -> dict[str, Any]:
        """Flatten nested JSON to single-level object."""
        data = params.get("data")
        separator = params.get("separator", ".")

        if data is None:
            raise ValueError("Data is required for flatten operation")

        result: dict[str, Any] = {}

        def flatten(obj: Any, prefix: str = "") -> None:
            if isinstance(obj, dict):
                for key, value in obj.items():
                    new_key = f"{prefix}{separator}{key}" if prefix else key
                    flatten(value, new_key)
            elif isinstance(obj, list):
                for i, item in enumerate(obj):
                    new_key = f"{prefix}[{i}]"
                    flatten(item, new_key)
            else:
                result[prefix] = obj

        flatten(data)

        return {
            "original": data,
            "data": result,
            "key_count": len(result),
        }

    def _unflatten_json(self, params: dict[str, Any]) -> dict[str, Any]:
        """Unflatten single-level object to nested JSON."""
        data = params.get("data")
        separator = params.get("separator", ".")

        if data is None or not isinstance(data, dict):
            raise ValueError("Data (dict) is required for unflatten operation")

        result: dict[str, Any] = {}

        for key, value in data.items():
            parts = self._split_key(key, separator)
            current = result

            for i, part in enumerate(parts[:-1]):
                next_part = parts[i + 1]
                is_next_array = next_part.isdigit()

                if part.isdigit():
                    part_idx = int(part)
                    while len(current) <= part_idx:
                        current.append([] if is_next_array else {})
                    current = current[part_idx]
                else:
                    if part not in current:
                        current[part] = [] if is_next_array else {}
                    current = current[part]

            last_part = parts[-1]
            if last_part.isdigit():
                idx = int(last_part)
                while len(current) <= idx:
                    current.append(None)
                current[idx] = value
            else:
                current[last_part] = value

        return {
            "original": data,
            "data": result,
        }

    def _split_key(self, key: str, separator: str) -> list[str]:
        """Split flattened key into parts."""
        parts: list[str] = []
        current = ""

        i = 0
        while i < len(key):
            if key[i] == "[":
                if current:
                    parts.append(current)
                    current = ""
                end = key.index("]", i)
                parts.append(key[i + 1 : end])
                i = end + 1
            elif key[i : i + len(separator)] == separator:
                if current:
                    parts.append(current)
                    current = ""
                i += len(separator)
            else:
                current += key[i]
                i += 1

        if current:
            parts.append(current)

        return parts

    def _stringify_json(self, params: dict[str, Any]) -> dict[str, Any]:
        """Convert data to JSON string."""
        data = params.get("data")
        indent = params.get("indent", 2)

        if data is None:
            raise ValueError("Data is required for stringify operation")

        result = json.dumps(data, indent=indent, ensure_ascii=False, default=str)

        return {
            "json": result,
            "length": len(result),
        }

    def _extract_json(self, params: dict[str, Any]) -> dict[str, Any]:
        """Extract all JSON objects from text."""
        text = params.get("text", "")

        if not text:
            raise ValueError("Text is required for extract operation")

        extracted: list[dict[str, Any]] = []

        code_blocks = re.findall(r"```(?:json)?\s*([\s\S]*?)```", text)
        for block in code_blocks:
            try:
                data = json.loads(block.strip())
                extracted.append({
                    "data": data,
                    "source": "code_block",
                    "type": type(data).__name__,
                })
            except json.JSONDecodeError:
                pass

        for pattern in [r"\{[^{}]*\}", r"\[[^\[\]]*\]"]:
            for match in re.finditer(pattern, text):
                try:
                    data = json.loads(match.group())
                    is_duplicate = any(e["data"] == data for e in extracted)
                    if not is_duplicate:
                        extracted.append({
                            "data": data,
                            "source": "inline",
                            "type": type(data).__name__,
                            "position": match.start(),
                        })
                except json.JSONDecodeError:
                    pass

        return {
            "extracted": extracted,
            "count": len(extracted),
        }
