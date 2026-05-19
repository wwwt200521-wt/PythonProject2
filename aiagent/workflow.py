from __future__ import annotations

import json
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from aiagent.llm_client import call_llm_with_retry
from aiagent.response_parser import (
    extract_tool_calls,
    looks_like_decision_json_text,
    parse_json_final_answer,
    parse_tool_call_arguments,
    _extract_json_object,
)
from aiagent.tooling import (
    enforce_workspace_scope_for_fs,
    execute_with_tool_audit,
    validate_tool_arguments,
)
from aiagent.tools.anythingllm import anythingllmquery, list_anythingllm_workspace_files, list_files_tool_spec, tool_spec as anythingllm_tool_spec
from aiagent.tools.clock import get_system_datetime, tool_spec as datetime_tool_spec
from aiagent.tools.filesystem import format_tool_result as format_fs_result, tool_dispatch as fs_dispatch, tool_specs as fs_tool_specs
from aiagent.tools.history import append_log_entries, format_tool_result as format_history_result, read_log_text, tool_specs as history_tool_specs
from aiagent.tools.skills import format_tool_result as format_skills_result, tool_dispatch as skills_dispatch, tool_specs as skills_tool_specs
from aiagent.tools.weather import format_tool_result as format_weather_result, tool_dispatch as weather_dispatch, tool_specs as weather_tool_specs
from aiagent.tools.web import format_tool_result as format_web_result, tool_dispatch as web_dispatch, tool_specs as web_tool_specs
from aiagent.web_summary import auto_finalize_web_summary_to_file, extract_windows_file_path, request_mentions_file_write


def buildanalysisprompt(userrequest: str, executed_steps: list[dict[str, Any]]) -> str:
    history_lines: list[str] = []
    if not executed_steps:
        history_lines.append("无（尚未执行任何工具）")
    else:
        for index, step in enumerate(executed_steps, start=1):
            tool_name = step.get("tool_name", "")
            arguments = step.get("arguments", {})
            result = step.get("result", "")
            history_lines.append(
                f"{index}. tool_name={tool_name}\n"
                f"   arguments={json.dumps(arguments, ensure_ascii=False)}\n"
                f"   result={result}"
            )

    history_block = "\n".join(history_lines)
    return (
        "你是链式工具调用决策助手，请严格依据上下文决策下一步。\n\n"
        f"【用户原始请求】\n{userrequest}\n\n"
        f"【已执行的工具调用历史（工具名、参数、结果）】\n{history_block}\n\n"
        "【决策规则】\n"
        "1. 首先判断用户输入的性质：\n"
        "   - 若为闲聊、感叹、情绪表达、或没有明确任务指令的含糊发言 → 直接结束并给出自然回复，严禁调用任何工具。\n"
        "   - 若用户指代不明（如「这个」「那个」），直接反问澄清，不要调用工具去猜测。\n"
        "2. 若当前信息足够回答用户，直接结束并给出最终答案。\n"
        "3. 仅在用户有明确任务需求且当前信息不足时，才选择最合适的工具继续调用；参数必须完整且准确。\n"
        "4. 不要虚构工具结果；只能依据已有工具结果与上下文推理。\n"
        "5. 优先复用已获得信息，避免无意义重复调用同一工具。\n"
        "6. 获取到网页内容后应尽快总结并在需要时调用 write_file 落盘，不要反复抓取同一 URL。\n\n"
        "【输出要求】\n"
        "优先使用原生 tool_calls；若无法使用 tool_calls，则只输出单个 JSON 对象。\n"
        "不要输出任何前缀文字、解释或 Markdown 标记，直接输出纯 JSON。\n"
        "JSON 格式必须严格为以下之一：\n"
        '{"done": true, "answer": "最终回答内容"}\n'
        '{"done": false, "tool_call": {"name": "工具名称", "arguments": {"参数名": "参数值"}}}'
    )


def _build_missing_file_followup(target_path: str) -> str:
    target = Path(target_path)
    args = json.dumps(
        {"dir_path": str(target.parent), "filename": target.name},
        ensure_ascii=False,
    )
    return (
        "目标文件尚未生成。"
        f"你必须调用 write_file 将最终结果写入该文件（dir_path/filename 必须与下述一致）：{args}。"
        "写入成功后再返回 done=true。"
    )


def _build_invalid_decision_followup() -> str:
    return (
        "你上一条决策输出不可执行（JSON 无效或缺少必须字段）。"
        "请只输出一个合法 JSON 对象，严格使用以下格式之一：\n"
        '{"done": true, "answer": "最终回答内容"}\n'
        '{"done": false, "tool_call": {"name": "工具名称", "arguments": {"参数名": "参数值"}}}'
    )


def executechainedtoolcall(
    userrequest: str,
    systemprompt: str,
    tools: list[dict[str, Any]],
    base_url: str,
    api_key: str,
    model: str,
    max_tokens: int,
    anythingllm_key: str,
    anythingllm_url: str,
    maxiterations: int = 8,
    tool_schema_map: dict[str, dict[str, Any]] | None = None,
    project_root: Path | None = None,
    restrict_filesystem_to_workspace: bool = False,
    tool_call_log_path: Path | None = None,
    *,
    on_token: Callable[[str], None] | None = None,
    on_tool_call: Callable[[dict[str, Any]], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> str:
    messages: list[dict[str, Any]] = [{"role": "system", "content": systemprompt}]
    executed_steps: list[dict[str, Any]] = []
    expected_output_path = extract_windows_file_path(userrequest)
    requires_output_file = bool(expected_output_path) and request_mentions_file_write(userrequest)

    if maxiterations < 1:
        raise ValueError("maxiterations must be >= 1")

    for iteration in range(1, maxiterations + 1):
        if cancel_event and cancel_event.is_set():
            return "生成已被用户中断。"

        analysis_prompt = buildanalysisprompt(userrequest, executed_steps)
        messages.append({"role": "user", "content": analysis_prompt})

        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0.1,
            "max_tokens": max_tokens,
        }
        response = call_llm_with_retry(base_url, api_key, payload)
        message = response.get("choices", [{}])[0].get("message", {})

        tool_calls = extract_tool_calls(message)

        if tool_calls:
            if isinstance(message.get("tool_calls"), list):
                messages.append(message)
            else:
                messages.append({"role": "assistant", "content": message.get("content", ""), "tool_calls": tool_calls})

            for call_index, call in enumerate(tool_calls, start=1):
                call_arguments = parse_tool_call_arguments(call)
                tool_name, tool_result = run_tool_call(
                    call,
                    base_url, api_key, model,
                    anythingllm_key, anythingllm_url,
                    tool_schema_map, project_root,
                    restrict_filesystem_to_workspace, tool_call_log_path,
                )
                executed_steps.append({
                    "iteration": iteration,
                    "tool_name": tool_name,
                    "arguments": call_arguments,
                    "tool_call_id": call.get("id", f"chain-tool-{iteration}-{call_index}"),
                    "result": tool_result,
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": call.get("id", f"chain-tool-{iteration}-{call_index}"),
                    "name": tool_name,
                    "content": tool_result,
                })
                if on_tool_call:
                    on_tool_call({
                        "tool_name": tool_name,
                        "arguments": call_arguments,
                        "result": tool_result,
                        "iteration": iteration,
                    })
            continue

        json_payload = _extract_json_object(message.get("content") or message.get("reasoning_content") or "")
        if isinstance(json_payload, dict):
            final_answer = parse_json_final_answer(json_payload)
            done_flag = json_payload.get("done") is True or str(json_payload.get("action", "")).lower() in {
                "done", "finish", "final", "complete", "completed",
            }
            if final_answer:
                if requires_output_file and expected_output_path and not Path(expected_output_path).is_file():
                    messages.append({"role": "user", "content": _build_missing_file_followup(expected_output_path)})
                    continue
                if on_token:
                    on_token(final_answer)
                return final_answer
            if done_flag:
                if requires_output_file and expected_output_path and not Path(expected_output_path).is_file():
                    messages.append({"role": "user", "content": _build_missing_file_followup(expected_output_path)})
                    continue
                if on_token:
                    on_token("任务已完成。")
                return "任务已完成。"
            if json_payload.get("done") is False:
                messages.append({"role": "user", "content": _build_invalid_decision_followup()})
                continue

        assistant_text = message.get("content") or message.get("reasoning_content") or ""
        if isinstance(assistant_text, str) and assistant_text.strip():
            if looks_like_decision_json_text(assistant_text):
                messages.append({"role": "user", "content": _build_invalid_decision_followup()})
                continue
            if requires_output_file and expected_output_path and not Path(expected_output_path).is_file():
                messages.append({"role": "user", "content": _build_missing_file_followup(expected_output_path)})
                continue
            if on_token:
                on_token(assistant_text.strip())
            return assistant_text.strip()

    autofinalized = auto_finalize_web_summary_to_file(
        userrequest=userrequest, executed_steps=executed_steps,
        base_url=base_url, api_key=api_key, model=model, max_tokens=max_tokens,
    )
    if autofinalized:
        if on_token:
            on_token(autofinalized)
        return autofinalized
    if requires_output_file and expected_output_path and Path(expected_output_path).is_file():
        msg = f"任务已完成，文件已写入：{expected_output_path}"
        if on_token:
            on_token(msg)
        return msg
    msg = "已达到最大迭代次数，但任务尚未完成。"
    if on_token:
        on_token(msg)
    return msg


def summarize_history(base_url: str, api_key: str, model: str, transcript: str) -> str:
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一个对话总结助手，请提炼关键事实、用户偏好和待办事项。"},
            {"role": "user", "content": f"请总结以下对话内容，要求简洁清晰:\n\n{transcript}"},
        ],
        "temperature": 0.2,
    }
    response = call_llm_with_retry(base_url, api_key, payload)
    message = response.get("choices", [{}])[0].get("message", {})
    return message.get("content", "")


def extract_key_facts(base_url: str, api_key: str, model: str, transcript: str) -> list[dict[str, Any]]:
    if not transcript.strip():
        return []
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是信息抽取助手，只输出 JSON 数组。字段: who, what, when, where, why。没有就空字符串。"},
            {"role": "user", "content": "请按 5W 规则从对话中提取多条关键信息:\n\n" + transcript},
        ],
        "temperature": 0.1,
    }
    response = call_llm_with_retry(base_url, api_key, payload)
    message = response.get("choices", [{}])[0].get("message", {})
    content = message.get("content", "")
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def search_history_with_llm(base_url: str, api_key: str, model: str, log_text: str, query: str) -> dict[str, str]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是聊天历史检索助手，只根据提供的日志查找相关内容。"},
            {"role": "user", "content": "日志如下:\n" + log_text + "\n\n请查找与以下问题相关的内容，并给出要点:\n" + query},
        ],
        "temperature": 0.2,
    }
    response = call_llm_with_retry(base_url, api_key, payload)
    message = response.get("choices", [{}])[0].get("message", {})
    return {"query": query, "result": message.get("content", "")}


def build_transcript(messages: list[dict[str, Any]], start_index: int) -> str:
    lines: list[str] = []
    for message in messages[start_index:]:
        role = message.get("role")
        if role not in {"user", "assistant"}:
            continue
        content = message.get("content", "")
        if not content:
            continue
        prefix = "User" if role == "user" else "Assistant"
        lines.append(f"{prefix}: {content}")
    return "\n".join(lines)


def build_tools() -> list[dict[str, Any]]:
    return (
        history_tool_specs()
        + [anythingllm_tool_spec(), list_files_tool_spec(), datetime_tool_spec()]
        + fs_tool_specs()
        + weather_tool_specs()
        + skills_tool_specs()
        + web_tool_specs()
    )


def _build_dispatch_map() -> dict[str, Any]:
    dispatch: dict[str, Any] = {}
    dispatch.update(fs_dispatch())
    dispatch.update(weather_dispatch())
    dispatch.update(web_dispatch())
    dispatch.update(skills_dispatch())
    return dispatch


def run_tool_call(
    call: dict[str, Any],
    base_url: str,
    api_key: str,
    model: str,
    anythingllm_key: str,
    anythingllm_url: str,
    tool_schema_map: dict[str, dict[str, Any]] | None = None,
    project_root: Path | None = None,
    restrict_filesystem_to_workspace: bool = False,
    tool_call_log_path: Path | None = None,
) -> tuple[str, str]:
    name = call.get("function", {}).get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Tool call missing function name")
    name = name.strip()
    raw_args = call.get("function", {}).get("arguments", "{}")
    try:
        args: dict[str, Any] = json.loads(raw_args) if raw_args else {}
    except json.JSONDecodeError:
        args = {}
    if not isinstance(args, dict):
        args = {}

    if isinstance(tool_schema_map, dict):
        args = validate_tool_arguments(name, args, tool_schema_map)
    if restrict_filesystem_to_workspace and project_root:
        enforce_workspace_scope_for_fs(name, args, project_root)

    dispatch_map = _build_dispatch_map()

    def _execute() -> str:
        if name == "search_history":
            query = str(args.get("query", "")).strip()
            log_text = read_log_text()
            result = search_history_with_llm(base_url, api_key, model, log_text, query)
            return format_history_result(result)
        if name == "anythingllmquery":
            msg = str(args.get("message", "")).strip()
            result = anythingllmquery(msg, anythingllm_key, anythingllm_url)
            return format_history_result(result)
        if name == "list_anythingllm_workspace_files":
            workspace = str(args.get("workspace", "ai"))
            result = list_anythingllm_workspace_files(anythingllm_key, anythingllm_url, workspace)
            return format_history_result(result)
        if name == "get_system_datetime":
            result = get_system_datetime()
            return format_history_result(result)

        if name in dispatch_map:
            result = dispatch_map[name](**args)
            return _format_result_for_tool(name, result)

        raise ValueError(f"Unknown tool requested: {name}")

    formatted_result = execute_with_tool_audit(
        _execute,
        project_root=project_root,
        tool_call_log_path=tool_call_log_path,
        tool_name=name,
        arguments=args,
    )
    return name, formatted_result


def _format_result_for_tool(name: str, result: dict[str, Any]) -> str:
    if name in fs_dispatch():
        return format_fs_result(result)
    if name in weather_dispatch():
        return format_weather_result(result)
    if name in web_dispatch():
        return format_web_result(result)
    if name in skills_dispatch():
        return format_skills_result(result)
    return json.dumps(result, ensure_ascii=False)


def complete_after_tool_results(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    base_url: str,
    api_key: str,
    model: str,
    max_tokens: int,
    anythingllm_key: str,
    anythingllm_url: str,
    tool_schema_map: dict[str, dict[str, Any]] | None = None,
    project_root: Path | None = None,
    restrict_filesystem_to_workspace: bool = False,
    tool_call_log_path: Path | None = None,
) -> str:
    for _ in range(3):
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }
        response = call_llm_with_retry(base_url, api_key, payload)
        message = response.get("choices", [{}])[0].get("message", {})
        next_calls = extract_tool_calls(message)
        if not next_calls:
            return message.get("content", "")

        if isinstance(message.get("tool_calls"), list):
            messages.append(message)
        else:
            messages.append({"role": "assistant", "content": "", "tool_calls": next_calls})

        for call in next_calls:
            tool_name, tool_result = run_tool_call(
                call, base_url, api_key, model,
                anythingllm_key, anythingllm_url,
                tool_schema_map, project_root,
                restrict_filesystem_to_workspace, tool_call_log_path,
            )
            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id", ""),
                "name": tool_name,
                "content": tool_result,
            })

    return "我已执行工具，但模型未返回最终文本答案，请重试。"
