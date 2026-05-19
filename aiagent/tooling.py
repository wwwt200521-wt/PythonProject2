from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any


_TYPE_MAP: dict[str, tuple[type, ...]] = {
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "object": (dict,),
}

_FILESYSTEM_TOOL_NAMES = {
    "list_dir",
    "rename_file",
    "delete_file",
    "write_file",
    "read_file",
    "create_dir",
}


def build_tool_schema_map(tools: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    schema_map: dict[str, dict] = {}
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        function_meta = tool.get("function")
        if not isinstance(function_meta, dict):
            continue
        name = function_meta.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        parameters = function_meta.get("parameters")
        if isinstance(parameters, dict):
            schema_map[name.strip()] = parameters
    return schema_map


def validate_tool_arguments(name: str, arguments: dict[str, Any], schema_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if not isinstance(arguments, dict):
        raise ValueError(f"Tool '{name}' arguments must be a JSON object")

    schema = schema_map.get(name)
    if not isinstance(schema, dict):
        return arguments

    properties = schema.get("properties", {})
    required = schema.get("required", [])
    if not isinstance(properties, dict):
        properties = {}
    if not isinstance(required, list):
        required = []

    missing = [field for field in required if field not in arguments]
    if missing:
        raise ValueError(f"Tool '{name}' missing required arguments: {', '.join(sorted(missing))}")

    unknown = [key for key in arguments if key not in properties]
    if unknown:
        raise ValueError(f"Tool '{name}' received unsupported arguments: {', '.join(sorted(unknown))}")

    for key, value in arguments.items():
        field_schema = properties.get(key)
        if not isinstance(field_schema, dict):
            continue
        expected = field_schema.get("type")
        if not isinstance(expected, str):
            continue
        expected_types = _TYPE_MAP.get(expected)
        if not expected_types:
            continue
        if expected == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"Tool '{name}' argument '{key}' must be integer")
            continue
        if not isinstance(value, expected_types):
            raise ValueError(f"Tool '{name}' argument '{key}' must be {expected}")
    return arguments


def enforce_workspace_scope_for_fs(tool_name: str, arguments: dict[str, Any], project_root: Path) -> None:
    if tool_name not in _FILESYSTEM_TOOL_NAMES:
        return
    raw_dir_path = arguments.get("dir_path")
    if not isinstance(raw_dir_path, str) or not raw_dir_path.strip():
        raise ValueError(f"Tool '{tool_name}' requires dir_path within workspace")

    workspace = project_root.expanduser().resolve()
    candidate = Path(raw_dir_path).expanduser().resolve()
    try:
        candidate.relative_to(workspace)
    except ValueError as exc:
        raise ValueError(f"Tool '{tool_name}' dir_path escapes workspace: {raw_dir_path}") from exc


def execute_with_tool_audit(
    executor: Callable[[], Any],
    *,
    project_root: Path | None,
    tool_call_log_path: Path | None,
    tool_name: str,
    arguments: dict[str, Any],
) -> Any:
    started = perf_counter()
    success = False
    error = ""
    result: Any = None
    try:
        result = executor()
        success = True
        return result
    except Exception as exc:
        error = str(exc)
        raise
    finally:
        if project_root and tool_call_log_path:
            duration_ms = int((perf_counter() - started) * 1000)
            append_tool_audit_log(
                project_root=project_root,
                log_path=tool_call_log_path,
                event={
                    "time": datetime.now(timezone.utc).isoformat(),
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "success": success,
                    "duration_ms": duration_ms,
                    "error": error,
                },
            )


def append_tool_audit_log(project_root: Path, log_path: Path, event: dict[str, Any]) -> None:
    root = project_root.expanduser().resolve()
    target = log_path.expanduser().resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Tool audit log path escapes workspace: {target}") from exc

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")
