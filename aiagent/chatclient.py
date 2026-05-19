from __future__ import annotations

from pathlib import Path

from aiagent.env import load_runtime_config
from aiagent.history_compress import compress_history, context_length, count_rounds, should_compress
from aiagent.notice import enforce_notice_skill_defaults
from aiagent.routing import (
    build_chained_user_request,
    is_search_trigger,
    normalize_search_query,
    should_force_list_anythingllm_files,
    should_force_list_workspace_files,
    should_force_search,
    should_force_skills_check,
    should_route_for_tools,
)
from aiagent.tooling import build_tool_schema_map
from aiagent.web_summary import auto_finalize_web_summary_to_file, build_web_summary_request
from aiagent.workflow import build_tools, build_transcript, executechainedtoolcall, extract_key_facts, summarize_history
from aiagent.tools.history import append_log_entries


def main() -> None:
    config = load_runtime_config(Path(__file__).resolve().parents[1])
    tool_call_log_path = config.tool_call_log_path if config.enable_tool_call_audit else None

    system_prompt = (
        "你是用户的AI助手。"
        "对于内容创作类任务（文章、通知、读后感、公众号稿子等），必须先调用 list_skills 查看可用技能，"
        "再调用 read_skill 获取对应写作规范，最后按规范完成。"
        "涉及知识库和文档查询时，优先使用 AnythingLLM 相关工具和 search_history。"
    )

    messages = [{"role": "system", "content": system_prompt}]
    raw_messages = list(messages)
    last_extracted_index = 0
    tools = build_tools()
    tool_schema_map = build_tool_schema_map(tools)
    last_compress_rounds = 0
    last_compress_chars = 0

    print("进入终端聊天模式（自动压缩历史记录），按 Ctrl+C 退出。")
    while True:
        try:
            user_text = input("你: ").strip()
            if not user_text:
                continue

            web_summary_request = build_web_summary_request(user_text, config.project_root)
            effective_user_text = web_summary_request or user_text
            if is_search_trigger(user_text):
                user_text = normalize_search_query(user_text)
                force_search = True
            elif should_force_search(user_text):
                force_search = True
            else:
                force_search = False

            user_message = {"role": "user", "content": effective_user_text}
            messages.append(user_message)
            raw_messages.append(user_message)

            current_rounds = count_rounds(messages)
            current_chars = context_length(messages)
            should_recompress = should_compress(messages) and (
                current_rounds > last_compress_rounds or current_chars > last_compress_chars
            )
            if should_recompress:
                print("正在压缩历史记录...")
                transcript = build_transcript(raw_messages, last_extracted_index)
                if transcript:
                    facts = extract_key_facts(config.base_url, config.api_key, config.model, transcript)
                    if facts:
                        append_log_entries(facts)
                    last_extracted_index = len(raw_messages)
                messages = compress_history(
                    messages,
                    lambda transcript: summarize_history(config.base_url, config.api_key, config.model, transcript),
                )
                last_compress_rounds = count_rounds(messages)
                last_compress_chars = context_length(messages)

            if web_summary_request:
                print("助手: ", end="", flush=True)
                streamed_chunks: list[str] = []

                def on_token(token: str) -> None:
                    print(token, end="", flush=True)
                    streamed_chunks.append(token)

                assistant_text = auto_finalize_web_summary_to_file(
                    userrequest=web_summary_request,
                    executed_steps=[],
                    base_url=config.base_url,
                    api_key=config.api_key,
                    model=config.model,
                    max_tokens=config.max_tokens,
                    on_token=on_token,
                )
                print()
                if assistant_text:
                    assistant_message = {"role": "assistant", "content": assistant_text}
                    messages.append(assistant_message)
                    raw_messages.append(assistant_message)
                    continue

            force_anythingllm_files = should_force_list_anythingllm_files(effective_user_text)
            force_workspace_files = should_force_list_workspace_files(effective_user_text)
            force_skills = should_force_skills_check(effective_user_text)

            if force_skills:
                from aiagent.tools.clock import get_system_datetime as _dt
                _now = _dt()
                effective_user_text += (
                    f"\n\n【当前系统时间】\n"
                    f"日期：{_now['date']}（{_now['weekday']}）\n"
                    f"时间：{_now['time']}"
                )

            if not should_route_for_tools(effective_user_text):
                continue

            chained_user_request = build_chained_user_request(
                user_text=effective_user_text,
                project_root=config.project_root,
                force_search=force_search,
                force_workspace_files=force_workspace_files,
                force_anythingllm_files=force_anythingllm_files,
                force_skills=force_skills,
            )
            print("助手: ", end="", flush=True)
            streamed_chunks: list[str] = []

            def on_token(token: str) -> None:
                print(token, end="", flush=True)
                streamed_chunks.append(token)

            assistant_text = executechainedtoolcall(
                userrequest=chained_user_request,
                systemprompt=system_prompt,
                tools=tools,
                base_url=config.base_url,
                api_key=config.api_key,
                model=config.model,
                max_tokens=config.max_tokens,
                anythingllm_key=config.anythingllm_key,
                anythingllm_url=config.anythingllm_url,
                maxiterations=config.max_tool_iterations,
                tool_schema_map=tool_schema_map,
                project_root=config.project_root,
                restrict_filesystem_to_workspace=config.restrict_filesystem_to_workspace,
                tool_call_log_path=tool_call_log_path,
                on_token=on_token,
            )
            print()
            if assistant_text == "已达到最大迭代次数，但任务尚未完成。":
                from aiagent.llm_client import call_llm as _clm
                _fallback_payload = {
                    "model": config.model,
                    "messages": [{"role": "user", "content": effective_user_text}],
                    "stream": False,
                    "max_tokens": config.max_tokens,
                }
                _resp = _clm(config.base_url, config.api_key, _fallback_payload)
                _fb_choice = _resp.get("choices", [{}])[0]
                _fb_msg = _fb_choice.get("message", _fb_choice)
                assistant_text = _fb_msg.get("content") or _fb_msg.get("reasoning_content") or ""
                print("助手: " + assistant_text)

            assistant_text = enforce_notice_skill_defaults(user_text, assistant_text)

            if assistant_text:
                assistant_message = {"role": "assistant", "content": assistant_text}
                messages.append(assistant_message)
                raw_messages.append(assistant_message)
        except KeyboardInterrupt:
            print("\n已退出。")
            break
        except Exception as exc:
            print(f"发生错误: {exc}")


if __name__ == "__main__":
    main()
