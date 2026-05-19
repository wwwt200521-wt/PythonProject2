import json
from pathlib import Path

from aiagent.workflow import buildanalysisprompt, executechainedtoolcall


def test_executechainedtoolcall_handles_tool_calls(monkeypatch) -> None:
    responses = iter(
        [
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "id": "call-1",
                                    "type": "function",
                                    "function": {"name": "get_system_datetime", "arguments": "{}"},
                                }
                            ],
                        }
                    }
                ]
            },
            {"choices": [{"message": {"role": "assistant", "content": "最终结果"}}]},
        ]
    )

    def fake_call_llm(_base_url: str, _api_key: str, _payload: dict) -> dict:
        return next(responses)

    def fake_run_tool_call(_call: dict, *_args) -> tuple[str, str]:
        return "get_system_datetime", json.dumps({"date": "2026-01-01"}, ensure_ascii=False)

    monkeypatch.setattr("aiagent.workflow.call_llm_with_retry", fake_call_llm)
    monkeypatch.setattr("aiagent.workflow.run_tool_call", fake_run_tool_call)

    result = executechainedtoolcall(
        userrequest="现在是什么日期",
        systemprompt="你是助手",
        tools=[],
        base_url="http://example.com/v1",
        api_key="",
        model="test-model",
        max_tokens=256,
        anythingllm_key="",
        anythingllm_url="http://localhost:3001",
        maxiterations=3,
    )
    assert result == "最终结果"


def test_executechainedtoolcall_handles_json_finish(monkeypatch) -> None:
    def fake_call_llm(_base_url: str, _api_key: str, _payload: dict) -> dict:
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": '{"done": true, "answer": "任务完成"}',
                    }
                }
            ]
        }

    monkeypatch.setattr("aiagent.workflow.call_llm_with_retry", fake_call_llm)

    def fail_run_tool_call(*_args):
        raise AssertionError("run_tool_call should not be called")

    monkeypatch.setattr("aiagent.workflow.run_tool_call", fail_run_tool_call)

    result = executechainedtoolcall(
        userrequest="直接给出总结",
        systemprompt="你是助手",
        tools=[],
        base_url="http://example.com/v1",
        api_key="",
        model="test-model",
        max_tokens=256,
        anythingllm_key="",
        anythingllm_url="http://localhost:3001",
        maxiterations=3,
    )
    assert result == "任务完成"


def test_executechainedtoolcall_handles_json_tool_call(monkeypatch) -> None:
    responses = iter(
        [
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": '{"done": false, "tool_call": {"name": "get_system_datetime", "arguments": {}}}',
                        }
                    }
                ]
            },
            {"choices": [{"message": {"role": "assistant", "content": '{"done": true, "answer": "处理完成"}'}}]},
        ]
    )

    def fake_call_llm(_base_url: str, _api_key: str, _payload: dict) -> dict:
        return next(responses)

    def fake_run_tool_call(_call: dict, *_args) -> tuple[str, str]:
        return "get_system_datetime", json.dumps({"date": "2026-01-01"}, ensure_ascii=False)

    monkeypatch.setattr("aiagent.workflow.call_llm_with_retry", fake_call_llm)
    monkeypatch.setattr("aiagent.workflow.run_tool_call", fake_run_tool_call)

    result = executechainedtoolcall(
        userrequest="请告诉我当前日期",
        systemprompt="你是助手",
        tools=[],
        base_url="http://example.com/v1",
        api_key="",
        model="test-model",
        max_tokens=256,
        anythingllm_key="",
        anythingllm_url="http://localhost:3001",
        maxiterations=3,
    )
    assert result == "处理完成"


def test_buildanalysisprompt_contains_required_sections() -> None:
    prompt = buildanalysisprompt(
        userrequest="请帮我查今天日期并总结",
        executed_steps=[
            {
                "tool_name": "get_system_datetime",
                "arguments": {},
                "result": '{"date":"2026-04-28"}',
            }
        ],
    )
    assert "用户原始请求" in prompt
    assert "请帮我查今天日期并总结" in prompt
    assert "已执行的工具调用历史" in prompt
    assert "tool_name=get_system_datetime" in prompt
    assert 'arguments={}' in prompt
    assert '{"date":"2026-04-28"}' in prompt
    assert "决策规则" in prompt
    assert "输出要求" in prompt
    assert '{"done": true, "answer": "最终回答内容"}' in prompt
    assert '{"done": false, "tool_call": {"name": "工具名称", "arguments": {"参数名": "参数值"}}}' in prompt


def test_executechainedtoolcall_autofinalizes_web_summary_to_file(monkeypatch) -> None:
    written = {}

    def fake_call_llm(_base_url: str, _api_key: str, payload: dict) -> dict:
        if "tools" in payload:
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "id": "call-fetch",
                                    "type": "function",
                                    "function": {
                                        "name": "fetch_web_content",
                                        "arguments": '{"url":"https://example.com"}',
                                    },
                                }
                            ],
                        }
                    }
                ]
            }
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "1. 要点A\n2. 要点B\n3. 要点C\n4. 要点D\n5. 要点E\n6. 要点F\n7. 要点G\n8. 要点H\n9. 要点I\n10. 要点J",
                    }
                }
            ]
        }

    def fake_stream_llm_call(_base_url: str, _api_key: str, payload: dict, *, on_token=None) -> str:
        content = "1. 要点A\n2. 要点B\n3. 要点C\n4. 要点D\n5. 要点E\n6. 要点F\n7. 要点G\n8. 要点H\n9. 要点I\n10. 要点J"
        if on_token:
            for char in content:
                on_token(char)
        return content

    def fake_run_tool_call(_call: dict, *_args) -> tuple[str, str]:
        return "fetch_web_content", json.dumps(
            {
                "url": "https://example.com",
                "title": "Example",
                "content": "Example long content for summary.",
            },
            ensure_ascii=False,
        )

    def fake_write_file(*, dir_path: str, filename: str, content: str, append: bool = False) -> dict:
        written["dir_path"] = dir_path
        written["filename"] = filename
        written["content"] = content
        written["append"] = append
        return {"path": f"{dir_path}\\{filename}"}

    monkeypatch.setattr("aiagent.workflow.call_llm_with_retry", fake_call_llm)
    monkeypatch.setattr("aiagent.workflow.run_tool_call", fake_run_tool_call)
    monkeypatch.setattr("aiagent.web_summary.stream_llm_call", fake_stream_llm_call)
    monkeypatch.setattr("aiagent.web_summary.fs_dispatch", lambda: {"write_file": fake_write_file})

    result = executechainedtoolcall(
        userrequest=(
            "请访问 https://example.com 并总结后写入本地文件\n"
            r"C:\Users\Administrator\PycharmProjects\PythonProject2\output\summary.txt"
        ),
        systemprompt="你是助手",
        tools=[{"type": "function", "function": {"name": "fetch_web_content"}}],
        base_url="http://example.com/v1",
        api_key="",
        model="test-model",
        max_tokens=256,
        anythingllm_key="",
        anythingllm_url="http://localhost:3001",
        maxiterations=1,
    )

    assert result.startswith("已完成总结并写入本地文件：")
    assert written["filename"] == "summary.txt"
    assert written["append"] is False
    assert "1. 要点A" in written["content"]


def test_executechainedtoolcall_waits_for_output_file_before_done(monkeypatch, tmp_path: Path) -> None:
    target_file = tmp_path / "summary.txt"
    write_instruction = json.dumps(
        {
            "done": False,
            "tool_call": {
                "name": "write_file",
                "arguments": {
                    "dir_path": str(tmp_path),
                    "filename": "summary.txt",
                    "content": "ok",
                    "append": False,
                },
            },
        },
        ensure_ascii=False,
    )
    responses = iter(
        [
            {"choices": [{"message": {"role": "assistant", "content": '{"done": true, "answer": "已完成"}'}}]},
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": write_instruction,
                        }
                    }
                ]
            },
            {"choices": [{"message": {"role": "assistant", "content": '{"done": true, "answer": "已完成"}'}}]},
        ]
    )

    def fake_call_llm(_base_url: str, _api_key: str, _payload: dict) -> dict:
        return next(responses)

    def fake_run_tool_call(call: dict, *_args) -> tuple[str, str]:
        name = call.get("function", {}).get("name")
        arguments = json.loads(call.get("function", {}).get("arguments", "{}"))
        if name == "write_file":
            Path(arguments["dir_path"]).mkdir(parents=True, exist_ok=True)
            (Path(arguments["dir_path"]) / arguments["filename"]).write_text(arguments["content"], encoding="utf-8")
            return "write_file", json.dumps({"path": str(Path(arguments["dir_path"]) / arguments["filename"])}, ensure_ascii=False)
        return name or "", "{}"

    monkeypatch.setattr("aiagent.workflow.call_llm_with_retry", fake_call_llm)
    monkeypatch.setattr("aiagent.workflow.run_tool_call", fake_run_tool_call)

    result = executechainedtoolcall(
        userrequest=f"请写入本地文件 {target_file}",
        systemprompt="你是助手",
        tools=[],
        base_url="http://example.com/v1",
        api_key="",
        model="test-model",
        max_tokens=256,
        anythingllm_key="",
        anythingllm_url="http://localhost:3001",
        maxiterations=3,
    )

    assert result == "已完成"
    assert target_file.exists()


def test_executechainedtoolcall_autofetches_web_content_when_model_skips_tools(monkeypatch, tmp_path: Path) -> None:
    target_file = tmp_path / "summary.txt"
    written = {}
    calls = {"llm": 0}

    def fake_call_llm(_base_url: str, _api_key: str, _payload: dict) -> dict:
        calls["llm"] += 1
        if calls["llm"] == 1:
            return {"choices": [{"message": {"role": "assistant", "content": '{"done": true, "answer": "已完成"}'}}]}
        return {"choices": [{"message": {"role": "assistant", "content": "1. A\n2. B\n3. C\n4. D\n5. E\n6. F\n7. G\n8. H\n9. I\n10. J"}}]}

    def fake_stream_llm_call(_base_url: str, _api_key: str, _payload: dict, *, on_token=None) -> str:
        calls["llm"] += 1
        if calls["llm"] == 1:
            content = '{"done": true, "answer": "已完成"}'
        else:
            content = "1. A\n2. B\n3. C\n4. D\n5. E\n6. F\n7. G\n8. H\n9. I\n10. J"
        if on_token:
            for char in content:
                on_token(char)
        return content

    def fake_fetch_web_content(*, url: str, max_chars: int = 12000) -> dict:
        assert url == "https://example.com"
        assert max_chars == 12000
        return {"url": url, "title": "Example", "content": "Example long content."}

    def fake_write_file(*, dir_path: str, filename: str, content: str, append: bool = False) -> dict:
        written["dir_path"] = dir_path
        written["filename"] = filename
        written["content"] = content
        written["append"] = append
        return {"path": f"{dir_path}\\{filename}"}

    monkeypatch.setattr("aiagent.workflow.call_llm_with_retry", fake_call_llm)
    monkeypatch.setattr("aiagent.web_summary.stream_llm_call", fake_stream_llm_call)
    monkeypatch.setattr("aiagent.web_summary.web_dispatch", lambda: {"fetch_web_content": fake_fetch_web_content})
    monkeypatch.setattr("aiagent.web_summary.fs_dispatch", lambda: {"write_file": fake_write_file})

    result = executechainedtoolcall(
        userrequest=f"请访问 https://example.com 并总结后写入本地文件 {target_file}",
        systemprompt="你是助手",
        tools=[],
        base_url="http://example.com/v1",
        api_key="",
        model="test-model",
        max_tokens=256,
        anythingllm_key="",
        anythingllm_url="http://localhost:3001",
        maxiterations=1,
    )

    assert result.startswith("已完成总结并写入本地文件：")
    assert written["filename"] == "summary.txt"
    assert "1. A" in written["content"]


def test_executechainedtoolcall_retries_when_decision_json_is_invalid(monkeypatch) -> None:
    responses = iter(
        [
            {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": '{"done": false, "tool_call": {"name": "write_file", "arguments": {"dir_path": ".", "filename": "x.txt"',
                        }
                    }
                ]
            },
            {"choices": [{"message": {"role": "assistant", "content": '{"done": true, "answer": "最终答案"}'}}]},
        ]
    )

    def fake_call_llm(_base_url: str, _api_key: str, _payload: dict) -> dict:
        return next(responses)

    def fail_run_tool_call(*_args):
        raise AssertionError("run_tool_call should not be called for invalid JSON text")

    monkeypatch.setattr("aiagent.workflow.call_llm_with_retry", fake_call_llm)
    monkeypatch.setattr("aiagent.workflow.run_tool_call", fail_run_tool_call)

    result = executechainedtoolcall(
        userrequest="读取 https://peps.python.org/pep-0008 并总结",
        systemprompt="你是助手",
        tools=[],
        base_url="http://example.com/v1",
        api_key="",
        model="test-model",
        max_tokens=256,
        anythingllm_key="",
        anythingllm_url="http://localhost:3001",
        maxiterations=3,
    )

    assert result == "最终答案"

