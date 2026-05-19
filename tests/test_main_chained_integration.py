from pathlib import Path

from aiagent.chatclient import main
from aiagent.env import RuntimeConfig
from aiagent.routing import build_chained_user_request
from aiagent.web_summary import build_web_summary_request


def _fake_runtime_config() -> RuntimeConfig:
    project_root = Path(r"C:\Users\Administrator\PycharmProjects\PythonProject2")
    return RuntimeConfig(
        project_root=project_root,
        base_url="http://example.com/v1",
        model="test-model",
        api_key="",
        max_tokens=256,
        anythingllm_key="",
        anythingllm_url="http://localhost:3001",
        max_tool_iterations=8,
        restrict_filesystem_to_workspace=True,
        enable_tool_call_audit=True,
        tool_call_log_path=project_root / "Log" / "tool_calls.jsonl",
    )


def test_build_chained_user_request_contains_constraints() -> None:
    chained = build_chained_user_request(
        user_text="请帮我查历史",
        project_root=Path(r"C:\Users\Administrator\PycharmProjects\PythonProject2"),
        force_search=True,
        force_workspace_files=True,
        force_anythingllm_files=True,
    )
    assert "执行约束" in chained
    assert "list_anythingllm_workspace_files" in chained
    assert "list_dir" in chained
    assert "search_history" in chained
    assert '"query": "请帮我查历史"' in chained


def test_build_chained_user_request_includes_write_file_constraint() -> None:
    chained = build_chained_user_request(
        user_text=(
            "请访问 https://example.com 并总结，然后写入本地文件 "
            r"C:\Users\Administrator\PycharmProjects\PythonProject2\output\summary.txt"
        ),
        project_root=Path(r"C:\Users\Administrator\PycharmProjects\PythonProject2"),
    )
    assert "write_file" in chained
    assert r'"filename": "summary.txt"' in chained
    assert r'"dir_path": "C:\\Users\\Administrator\\PycharmProjects\\PythonProject2\\output"' in chained


def test_build_web_summary_request_appends_default_path_when_missing() -> None:
    project_root = Path(r"C:\Users\Administrator\PycharmProjects\PythonProject2")
    request = build_web_summary_request(
        "请访问 https://example.com 并总结后写入本地文件",
        project_root=project_root,
    )
    assert request.endswith(r"C:\Users\Administrator\PycharmProjects\PythonProject2\output\web_summaries\example_summary.md")


def test_build_web_summary_request_keeps_explicit_path() -> None:
    project_root = Path(r"C:\Users\Administrator\PycharmProjects\PythonProject2")
    source = (
        "请访问 https://example.com 并总结后写入本地文件 "
        r"C:\Users\Administrator\PycharmProjects\PythonProject2\output\summary.txt"
    )
    request = build_web_summary_request(source, project_root=project_root)
    assert request == source


def test_build_web_summary_request_triggers_without_write_keyword() -> None:
    project_root = Path(r"C:\Users\Administrator\PycharmProjects\PythonProject2")
    request = build_web_summary_request(
        "读取https://peps.python.org/pep-0008 并且用中文总结成10点摘要",
        project_root=project_root,
    )
    assert request.endswith(r"C:\Users\Administrator\PycharmProjects\PythonProject2\output\web_summaries\pep-0008_summary.md")


def test_main_uses_executechainedtoolcall(monkeypatch, capsys) -> None:
    called = {}
    inputs = iter(["现在几点了"])

    def fake_input(_prompt: str) -> str:
        try:
            return next(inputs)
        except StopIteration:
            raise KeyboardInterrupt

    def fake_executechainedtoolcall(**kwargs) -> str:
        called["userrequest"] = kwargs.get("userrequest")
        on_token = kwargs.get("on_token")
        if on_token:
            on_token("链式结果")
        return "链式结果"

    monkeypatch.setattr("aiagent.chatclient.load_runtime_config", lambda _project_root: _fake_runtime_config())
    monkeypatch.setattr("aiagent.chatclient.executechainedtoolcall", fake_executechainedtoolcall)
    monkeypatch.setattr("aiagent.chatclient.should_compress", lambda *_args, **_kwargs: False)
    monkeypatch.setattr("builtins.input", fake_input)

    main()

    output = capsys.readouterr().out
    assert called["userrequest"] == "现在几点了"
    assert "链式结果" in output


def test_main_prefers_direct_web_summary_flow(monkeypatch, capsys) -> None:
    inputs = iter(["请访问 https://example.com 并总结后写入本地文件"])

    def fake_input(_prompt: str) -> str:
        try:
            return next(inputs)
        except StopIteration:
            raise KeyboardInterrupt

    def fail_executechainedtoolcall(**_kwargs):
        raise AssertionError("executechainedtoolcall should not be called in direct web summary flow")

    def fake_auto_finalize_web_summary_to_file(**kwargs):
        on_token = kwargs.get("on_token")
        content = "已完成总结并写入本地文件：X"
        if on_token:
            for char in content:
                on_token(char)
        return content

    monkeypatch.setattr("aiagent.chatclient.load_runtime_config", lambda _project_root: _fake_runtime_config())
    monkeypatch.setattr("aiagent.chatclient.executechainedtoolcall", fail_executechainedtoolcall)
    monkeypatch.setattr("aiagent.chatclient.should_compress", lambda *_args, **_kwargs: False)
    monkeypatch.setattr("aiagent.chatclient.auto_finalize_web_summary_to_file", fake_auto_finalize_web_summary_to_file)
    monkeypatch.setattr("builtins.input", fake_input)

    main()

    output = capsys.readouterr().out
    assert "助手: 已完成总结并写入本地文件：X" in output


def test_main_prefers_direct_web_summary_flow_without_write_keyword(monkeypatch, capsys) -> None:
    inputs = iter(["读取https://peps.python.org/pep-0008 并且用中文总结成10点摘要"])

    def fake_input(_prompt: str) -> str:
        try:
            return next(inputs)
        except StopIteration:
            raise KeyboardInterrupt

    def fail_executechainedtoolcall(**_kwargs):
        raise AssertionError("executechainedtoolcall should not be called in direct web summary flow")

    def fake_auto_finalize_web_summary_to_file(**kwargs):
        on_token = kwargs.get("on_token")
        content = "已完成总结并写入本地文件：Y"
        if on_token:
            for char in content:
                on_token(char)
        return content

    monkeypatch.setattr("aiagent.chatclient.load_runtime_config", lambda _project_root: _fake_runtime_config())
    monkeypatch.setattr("aiagent.chatclient.executechainedtoolcall", fail_executechainedtoolcall)
    monkeypatch.setattr("aiagent.chatclient.should_compress", lambda *_args, **_kwargs: False)
    monkeypatch.setattr("aiagent.chatclient.auto_finalize_web_summary_to_file", fake_auto_finalize_web_summary_to_file)
    monkeypatch.setattr("builtins.input", fake_input)

    main()

    output = capsys.readouterr().out
    assert "助手: 已完成总结并写入本地文件：Y" in output
