import json
from pathlib import Path

import pytest

from aiagent.workflow import _extract_json_object, build_tools, run_tool_call
from aiagent.tooling import build_tool_schema_map, validate_tool_arguments


def test_build_tool_schema_map_contains_registered_tools() -> None:
    schema_map = build_tool_schema_map(build_tools())
    assert "write_file" in schema_map
    assert "fetch_web_content" in schema_map
    assert "get_system_datetime" in schema_map


def test_validate_tool_arguments_enforces_required_and_unknown_fields() -> None:
    schema_map = {
        "demo_tool": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
    }
    with pytest.raises(ValueError, match="missing required arguments"):
        validate_tool_arguments("demo_tool", {}, schema_map)

    with pytest.raises(ValueError, match="unsupported arguments"):
        validate_tool_arguments("demo_tool", {"name": "ok", "extra": 1}, schema_map)


def test_run_tool_call_blocks_filesystem_escape(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside"
    outside.mkdir(parents=True, exist_ok=True)

    call = {
        "function": {
            "name": "write_file",
            "arguments": json.dumps(
                {
                    "dir_path": str(outside),
                    "filename": "note.txt",
                    "content": "blocked",
                    "append": False,
                },
                ensure_ascii=False,
            ),
        }
    }

    with pytest.raises(ValueError, match="escapes workspace"):
        run_tool_call(
            call,
            base_url="http://example.com/v1",
            api_key="",
            model="test-model",
            anythingllm_key="",
            anythingllm_url="http://localhost:3001",
            tool_schema_map=build_tool_schema_map(build_tools()),
            project_root=workspace,
            restrict_filesystem_to_workspace=True,
            tool_call_log_path=None,
        )

    assert not (outside / "note.txt").exists()


def test_run_tool_call_records_audit_log(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    target_dir = workspace / "output"
    log_path = workspace / "Log" / "tool_calls.jsonl"

    call = {
        "function": {
            "name": "write_file",
            "arguments": json.dumps(
                {
                    "dir_path": str(target_dir),
                    "filename": "ok.txt",
                    "content": "hello",
                    "append": False,
                },
                ensure_ascii=False,
            ),
        }
    }

    tool_name, _ = run_tool_call(
        call,
        base_url="http://example.com/v1",
        api_key="",
        model="test-model",
        anythingllm_key="",
        anythingllm_url="http://localhost:3001",
        tool_schema_map=build_tool_schema_map(build_tools()),
        project_root=workspace,
        restrict_filesystem_to_workspace=True,
        tool_call_log_path=log_path,
    )

    assert tool_name == "write_file"
    assert (target_dir / "ok.txt").read_text(encoding="utf-8") == "hello"

    lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["tool_name"] == "write_file"
    assert payload["success"] is True
    assert payload["duration_ms"] >= 0


def test_extract_json_object_supports_prefixed_text() -> None:
    payload = _extract_json_object("请按规则处理：{\"done\": true, \"answer\": \"ok\"}")
    assert payload == {"done": True, "answer": "ok"}
