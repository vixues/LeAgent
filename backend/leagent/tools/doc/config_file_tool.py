"""Structured config file operations (JSON, YAML, TOML)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import structlog
import yaml

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef, import-not-found]

from leagent.tools.base import SyncTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)

_FORMATS = ("json", "yaml", "toml")


def _detect_format_from_path(path: Path) -> str | None:
    suf = path.suffix.lower()
    if suf == ".json":
        return "json"
    if suf in (".yaml", ".yml"):
        return "yaml"
    if suf == ".toml":
        return "toml"
    return None


def _parse_json(text: str) -> Any:
    return json.loads(text)


def _parse_yaml(text: str) -> Any:
    return yaml.safe_load(text)


def _parse_toml(text: str) -> Any:
    return tomllib.loads(text)


def _try_parse(text: str, fmt: str) -> Any:
    if fmt == "json":
        return _parse_json(text)
    if fmt == "yaml":
        return _parse_yaml(text)
    if fmt == "toml":
        return _parse_toml(text)
    raise ValueError(f"Unknown format: {fmt}")


def _parse_with_fallback(text: str, hint: str | None) -> tuple[Any, str]:
    if hint:
        try:
            return _try_parse(text, hint), hint
        except Exception:
            pass
    last_err: Exception | None = None
    for fmt in ("json", "yaml", "toml"):
        if fmt == hint:
            continue
        try:
            return _try_parse(text, fmt), fmt
        except Exception as e:
            last_err = e
    raise ValueError(f"Could not parse config (tried {_FORMATS}): {last_err}")


def _recursive_dict_key_count(obj: Any) -> int:
    n = 0
    if isinstance(obj, dict):
        n += len(obj)
        for v in obj.values():
            n += _recursive_dict_key_count(v)
    elif isinstance(obj, list):
        for item in obj:
            n += _recursive_dict_key_count(item)
    return n


def _deep_merge(base: Any, overlay: Any) -> Any:
    if isinstance(base, dict) and isinstance(overlay, dict):
        out = dict(base)
        for k, v in overlay.items():
            if k in out:
                out[k] = _deep_merge(out[k], v)
            else:
                out[k] = v
        return out
    return overlay


def _get_by_path(data: Any, path: str) -> Any:
    if not path:
        return data
    cur = data
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, list) and part.isdigit():
            idx = int(part)
            if -len(cur) <= idx < len(cur):
                cur = cur[idx]
            else:
                return None
        elif isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _manual_toml_dump(obj: dict[str, Any]) -> str:
    lines: list[str] = []

    def esc_key(k: str) -> str:
        if k and all(c.isalnum() or c in "_-" for c in k) and not k[0].isdigit():
            return k
        return '"' + k.replace("\\", "\\\\").replace('"', '\\"') + '"'

    def fmt_scalar(v: Any) -> str:
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, int):
            return str(v)
        if isinstance(v, float):
            return repr(v)
        if isinstance(v, str):
            return '"' + v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
        if isinstance(v, list):
            if not v:
                return "[]"
            if all(isinstance(x, (str, int, float, bool)) or x is None for x in v):
                return "[" + ", ".join(fmt_scalar(x) for x in v) + "]"
            raise ValueError("TOML manual dump: only lists of scalars are supported")
        raise TypeError(f"TOML manual dump: unsupported type {type(v).__name__}")

    def walk(prefix: tuple[str, ...], d: dict[str, Any]) -> None:
        scalars: dict[str, Any] = {}
        children: dict[str, dict[str, Any]] = {}
        for k, v in d.items():
            if isinstance(v, dict):
                children[k] = v
            else:
                scalars[k] = v
        if prefix:
            header = ".".join(esc_key(x) for x in prefix)
            lines.append(f"[{header}]")
        for k in sorted(scalars.keys()):
            lines.append(f"{esc_key(k)} = {fmt_scalar(scalars[k])}")
        for k in sorted(children.keys()):
            walk(prefix + (k,), children[k])

    walk((), obj)
    return "\n".join(lines) + ("\n" if lines else "")


def _dump_toml(data: dict[str, Any]) -> str:
    try:
        import tomli_w

        return tomli_w.dumps(data)
    except ImportError:
        return _manual_toml_dump(data)


def _serialize(data: Any, fmt: str) -> str:
    if fmt == "json":
        return json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n"
    if fmt == "yaml":
        return yaml.safe_dump(data, default_flow_style=False, allow_unicode=True, sort_keys=False)
    if fmt == "toml":
        if not isinstance(data, dict):
            raise ValueError("TOML output requires a mapping at the root")
        return _dump_toml(data)
    raise ValueError(f"Unknown format: {fmt}")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_parsed(path: Path) -> tuple[Any, str]:
    text = _read_text(path)
    hint = _detect_format_from_path(path)
    return _parse_with_fallback(text, hint)


class ConfigFileTool(SyncTool):
    name = "config_file"
    description = (
        "Read, write, query, merge, and convert structured config files "
        "(JSON, YAML, TOML), including ~/.openclaw/openclaw.json for installed skill API keys."
    )
    category = ToolCategory.DOC
    version = "1.0.0"
    timeout_sec = 60
    aliases = ["config", "json_file", "yaml_file", "toml_file"]
    search_hint = "config JSON YAML TOML read write query merge convert structured"
    is_concurrency_safe = True
    is_read_only = False
    interrupt_behavior = "cancel"
    max_result_size_chars = 100_000
    path_params = ()
    output_path_params = ()

    def _enforce_path_sandbox(
        self,
        params: dict[str, Any],
        context: ToolContext,
    ) -> None:
        """Apply read/write path permissions according to the config operation.

        OpenClaw config paths such as ``~/.openclaw/openclaw.json`` are
        authorised by the shared PathSandbox default roots.
        """
        from leagent.tools._sandbox.paths import PathSandbox

        request_id = context.extra.get("request_id", context.session_id or "")

        def resolve_param(key: str, *, allow_create: bool) -> None:
            val = params.get(key)
            if val and isinstance(val, str):
                params[key] = str(PathSandbox.resolve_safe(
                    val,
                    context=context,
                    allow_create=allow_create,
                    tool_name=self.name,
                    request_id=str(request_id),
                ))

        op = params.get("operation")
        if op in {"read", "query", "convert"}:
            resolve_param("file_path", allow_create=False)
        elif op == "write":
            resolve_param("file_path", allow_create=True)
        elif op == "merge":
            resolve_param("base_path", allow_create=False)
            resolve_param("overlay_path", allow_create=False)

        resolve_param("output_path", allow_create=True)

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["read", "write", "query", "merge", "convert"],
                    "description": "Config file operation.",
                },
                "file_path": {
                    "type": "string",
                    "description": (
                        "Path to the config file. For write/merge outputs that "
                        "create or replace a file, use only when the user explicitly "
                        "asked to save or export."
                    ),
                },
                "data": {
                    "type": "object",
                    "description": "Object to write (write operation).",
                },
                "format": {
                    "type": "string",
                    "enum": list(_FORMATS),
                    "description": "Serialization format (optional; inferred from extension).",
                },
                "path": {
                    "type": "string",
                    "description": "Dot path for query (e.g. database.host or servers.0.name).",
                },
                "base_path": {
                    "type": "string",
                    "description": "Base config file path (merge).",
                },
                "overlay_path": {
                    "type": "string",
                    "description": "Overlay config file path (merge).",
                },
                "output_path": {
                    "type": "string",
                    "description": "Optional output file path.",
                },
                "output_format": {
                    "type": "string",
                    "enum": list(_FORMATS),
                    "description": "Target format for convert.",
                },
            },
            "required": ["operation"],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        op = (params or {}).get("operation", "read")
        fmt = (params or {}).get("format", "auto")
        return f"Processing config file ({op}, {fmt})"

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        op = params["operation"]
        logger.info("config_file operation", operation=op)

        if op == "read":
            file_path = params.get("file_path")
            if not file_path:
                raise ValueError("file_path is required for read")
            path = Path(file_path)
            data, fmt = _load_parsed(path)
            return {
                "data": data,
                "format": fmt,
                "key_count": _recursive_dict_key_count(data),
            }

        if op == "write":
            file_path = params.get("file_path")
            data = params.get("data")
            if not file_path:
                raise ValueError("file_path is required for write")
            if data is None:
                raise ValueError("data is required for write")
            path = Path(file_path)
            fmt = params.get("format") or _detect_format_from_path(path)
            if not fmt:
                raise ValueError("format is required when extension does not imply json, yaml, or toml")
            content = _serialize(data, fmt)
            path.write_text(content, encoding="utf-8")
            return {"success": True}

        if op == "query":
            file_path = params.get("file_path")
            qpath = params.get("path")
            if not file_path:
                raise ValueError("file_path is required for query")
            if qpath is None or qpath == "":
                raise ValueError("path is required for query")
            data, _fmt = _load_parsed(Path(file_path))
            return {"value": _get_by_path(data, qpath)}

        if op == "merge":
            base_path = params.get("base_path")
            overlay_path = params.get("overlay_path")
            if not base_path or not overlay_path:
                raise ValueError("base_path and overlay_path are required for merge")
            base_data, _ = _load_parsed(Path(base_path))
            overlay_data, _ = _load_parsed(Path(overlay_path))
            merged = _deep_merge(base_data, overlay_data)
            out = params.get("output_path")
            if out:
                opath = Path(out)
                fmt = _detect_format_from_path(opath) or "json"
                opath.write_text(_serialize(merged, fmt), encoding="utf-8")
            return {"data": merged}

        if op == "convert":
            file_path = params.get("file_path")
            output_format = params.get("output_format")
            if not file_path:
                raise ValueError("file_path is required for convert")
            if not output_format:
                raise ValueError("output_format is required for convert")
            data, _ = _load_parsed(Path(file_path))
            content = _serialize(data, output_format)
            outp = params.get("output_path")
            if outp:
                Path(outp).write_text(content, encoding="utf-8")
            return {"content": content, "output_format": output_format}

        raise ValueError(f"Unknown operation: {op}")
