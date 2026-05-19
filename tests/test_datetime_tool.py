from datetime import datetime

from aiagent.notice import (
    enforce_notice_skill_defaults,
    has_department_in_request,
    is_notice_request,
)
from aiagent.routing import (
    should_force_list_anythingllm_files,
    should_force_list_workspace_files,
    should_route_for_tools,
)
from aiagent.workflow import extract_tool_calls
from aiagent.tools.clock import get_system_datetime


def test_get_system_datetime_shape() -> None:
    result = get_system_datetime()
    assert "iso" in result
    assert "date" in result
    assert "time" in result
    assert "weekday" in result
    assert "timezone" in result
    assert "timestamp" in result
    assert isinstance(result["timestamp"], int)
    datetime.fromisoformat(result["iso"])


def test_datetime_query_routes_to_tools() -> None:
    assert should_route_for_tools("今天是几月几日")
    assert should_route_for_tools("现在几点了")
    assert should_route_for_tools("帮我写一个学工部通知")
    assert should_route_for_tools("请访问 https://example.com 并总结")


def test_extract_textual_tool_call_fallback() -> None:
    message = {
        "role": "assistant",
        "content": '<tool_call>{"name":"read_skill","arguments":{"skill_name":"notice"}}</tool_call>',
    }
    calls = extract_tool_calls(message)
    assert len(calls) == 1
    assert calls[0]["function"]["name"] == "read_skill"


def test_notice_helpers() -> None:
    assert is_notice_request("帮我写一份通知")
    assert is_notice_request("Write a notice")
    assert has_department_in_request("帮我写一个学工部通知")
    assert not has_department_in_request("帮我写通知")


def test_enforce_notice_default_dept() -> None:
    user_text = "帮我写一份通知，内容是明天全体不上课"
    assistant_text = "**销售部通知**\n\n各位同学：\n\n明天全体不上课。\n\n---\n销售部\n2026年4月23日"
    fixed = enforce_notice_skill_defaults(user_text, assistant_text)
    assert "xx部通知" in fixed
    assert "销售部通知" not in fixed
    assert "\nxx部\n" in fixed


def test_force_list_workspace_files_trigger() -> None:
    assert should_force_list_workspace_files("列出本地项目工作区中所有的文件")
    assert should_force_list_workspace_files("请查看本地workspace全部file")
    assert not should_force_list_workspace_files("列出天气信息")


def test_force_list_anythingllm_files_trigger() -> None:
    assert should_force_list_anythingllm_files("列出AnythingLLM工作区的所有文件名")
    assert should_force_list_anythingllm_files("查看知识库workspace全部文档")
    assert not should_force_list_anythingllm_files("列出本地项目工作区所有文件")

