import json
from pathlib import Path
from urllib import request, error

from history_compress import compress_history, context_length, count_rounds, should_compress
from tools_anythingllm import DEFAULT_BASE_URL, anythingllmquery, tool_spec as anythingllm_tool_spec
from tools_history import append_log_entries, format_tool_result, read_log_text, tool_specs as history_tool_specs


def load_env(env_path: Path) -> dict:
    env_data = {}
    if not env_path.exists():
        raise FileNotFoundError(f"Missing .env file at: {env_path}")

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, sep, value = stripped.partition("=")
        if not sep:
            continue
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        env_data[key] = value
    return env_data


def build_payload(model: str, messages: list[dict]) -> dict:
    return {
        "model": model,
        "messages": messages,
        "stream": True,
        "temperature": 0.7,
        "max_tokens": 512,
        "stop": ["\n——\n⚠️ 重要提醒", "\n\n——\n⚠️ 重要提醒"],
    }


def iter_sse_lines(response) -> str:
    for raw in response:
        line = raw.decode("utf-8", errors="ignore").strip()
        if not line:
            continue
        if line.startswith("data:"):
            yield line[5:].strip()


def stream_chat(base_url: str, api_key: str, payload: dict) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = request.Request(url, data=body, headers=headers, method="POST")

    try:
        with request.urlopen(req, timeout=120) as resp:
            chunks = []
            for data in iter_sse_lines(resp):
                if data == "[DONE]":
                    break
                try:
                    event = json.loads(data)
                except json.JSONDecodeError:
                    continue
                delta = event.get("choices", [{}])[0].get("delta", {})
                content = delta.get("content")
                if content:
                    print(content, end="", flush=True)
                    chunks.append(content)
            print("")
            return "".join(chunks)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def call_llm(base_url: str, api_key: str, payload: dict) -> dict:
    url = base_url.rstrip("/") + "/chat/completions"
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = request.Request(url, data=body, headers=headers, method="POST")

    try:
        with request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def extract_tool_calls(message: dict) -> list[dict]:
    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list):
        return []
    return tool_calls


def is_search_trigger(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith("/search") or "查找聊天历史" in stripped or "搜索聊天历史" in stripped


def should_route_for_tools(text: str) -> bool:
    keywords = (
        "历史",
        "回顾",
        "查找",
        "搜索",
        "名字",
        "姓名",
        "叫啥",
        "我是谁",
        "身份",
        "知识库",
        "文档",
        "资料",
        "AnythingLLM",
        "workspace",
    )
    return any(keyword in text for keyword in keywords)


def should_force_search(text: str) -> bool:
    keywords = ("名字", "姓名", "叫啥", "我是谁", "身份")
    return any(keyword in text for keyword in keywords)


def normalize_search_query(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("/search"):
        return stripped[len("/search") :].strip() or "查找聊天历史"
    return stripped


def build_tool_call(query: str, call_id: str = "manual-search") -> dict:
    return {
        "type": "function",
        "id": call_id,
        "function": {
            "name": "search_history",
            "arguments": json.dumps({"query": query}, ensure_ascii=False),
        },
    }


def summarize_history(base_url: str, api_key: str, model: str, transcript: str) -> str:
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "你是一个对话总结助手，请提炼关键事实、用户偏好和待办事项。",
            },
            {
                "role": "user",
                "content": f"请总结以下对话内容，要求简洁清晰:\n\n{transcript}",
            },
        ],
        "temperature": 0.2,
    }
    response = call_llm(base_url, api_key, payload)
    message = response.get("choices", [{}])[0].get("message", {})
    return message.get("content", "")


def extract_key_facts(base_url: str, api_key: str, model: str, transcript: str) -> list[dict]:
    if not transcript.strip():
        return []
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "你是信息抽取助手，只输出 JSON 数组。字段: who, what, when, where, why。没有就空字符串。",
            },
            {
                "role": "user",
                "content": "请按 5W 规则从对话中提取多条关键信息:\n\n" + transcript,
            },
        ],
        "temperature": 0.1,
    }
    response = call_llm(base_url, api_key, payload)
    message = response.get("choices", [{}])[0].get("message", {})
    content = message.get("content", "")
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def search_history_with_llm(base_url: str, api_key: str, model: str, log_text: str, query: str) -> dict:
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "你是聊天历史检索助手，只根据提供的日志查找相关内容。",
            },
            {
                "role": "user",
                "content": "日志如下:\n" + log_text + "\n\n请查找与以下问题相关的内容，并给出要点:\n" + query,
            },
        ],
        "temperature": 0.2,
    }
    response = call_llm(base_url, api_key, payload)
    message = response.get("choices", [{}])[0].get("message", {})
    return {"query": query, "result": message.get("content", "")}


def build_transcript(messages: list[dict], start_index: int) -> str:
    lines = []
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


def build_tools() -> list[dict]:
    return history_tool_specs() + [anythingllm_tool_spec()]


def run_tool_call(call: dict, base_url: str, api_key: str, model: str, anythingllm_key: str, anythingllm_url: str) -> tuple[str, str]:
    name = call.get("function", {}).get("name")
    raw_args = call.get("function", {}).get("arguments", "{}")
    try:
        args = json.loads(raw_args) if raw_args else {}
    except json.JSONDecodeError:
        args = {}

    if name == "search_history":
        query = args.get("query", "").strip()
        log_text = read_log_text()
        result = search_history_with_llm(base_url, api_key, model, log_text, query)
        return name, format_tool_result(result)
    if name == "anythingllmquery":
        message = args.get("message", "").strip()
        result = anythingllmquery(message, anythingllm_key, anythingllm_url)
        return name, format_tool_result(result)
    raise ValueError("Unknown tool requested")


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    env_data = load_env(project_root / ".env")

    base_url = env_data.get("OPENAI_BASE_URL")
    model = env_data.get("OPENAI_MODEL")
    api_key = env_data.get("OPENAI_API_KEY", "")
    anythingllm_key = env_data.get("ANYTHINGLLMAPIKEY", "")
    anythingllm_url = env_data.get("ANYTHINGLLM_BASE_URL", DEFAULT_BASE_URL)

    if not base_url or not model:
        raise ValueError("OPENAI_BASE_URL and OPENAI_MODEL are required in .env")

    system_prompt = (
        "你是一个支持工具调用的助手。"
        "当用户需要查询聊天历史或找回已记录的 5W 事实时，使用 search_history。"
        "当用户明确需要查询 AnythingLLM 本地知识库/文档/资料时，使用 anythingllmquery。"
        "工具可用时，先调用工具，再根据工具结果回答用户。"
        "如果问题不需要工具，直接回答。"
    )

    messages = [{"role": "system", "content": system_prompt}]
    raw_messages = list(messages)
    last_extracted_index = 0
    tools = build_tools()
    last_compress_rounds = 0
    last_compress_chars = 0

    print("进入终端聊天模式（自动压缩历史记录），按 Ctrl+C 退出。")
    while True:
        try:
            user_text = input("你: ").strip()
            if not user_text:
                continue
            if is_search_trigger(user_text):
                user_text = normalize_search_query(user_text)
                force_search = True
            elif should_force_search(user_text):
                force_search = True
            else:
                force_search = False

            user_message = {"role": "user", "content": user_text}
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
                    facts = extract_key_facts(base_url, api_key, model, transcript)
                    if facts:
                        append_log_entries(facts)
                    last_extracted_index = len(raw_messages)
                messages = compress_history(
                    messages,
                    lambda transcript: summarize_history(base_url, api_key, model, transcript),
                )
                last_compress_rounds = count_rounds(messages)
                last_compress_chars = context_length(messages)

            tool_calls = []
            if force_search:
                tool_calls = [build_tool_call(user_text)]
                messages.append({"role": "assistant", "content": "", "tool_calls": tool_calls})
            elif should_route_for_tools(user_text):
                route_payload = {
                    "model": model,
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": "auto",
                    "temperature": 0.0,
                }
                route_response = call_llm(base_url, api_key, route_payload)
                route_message = route_response.get("choices", [{}])[0].get("message", {})
                tool_calls = extract_tool_calls(route_message)
                if tool_calls:
                    messages.append(route_message)

            if tool_calls:
                for call in tool_calls:
                    tool_name, tool_result = run_tool_call(
                        call,
                        base_url,
                        api_key,
                        model,
                        anythingllm_key,
                        anythingllm_url,
                    )
                    if tool_name == "search_history":
                        print("检索结果:")
                        print(tool_result)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.get("id", ""),
                            "name": tool_name,
                            "content": tool_result,
                        }
                    )

                payload = build_payload(model, messages)
                print("助手: ", end="", flush=True)
                assistant_text = stream_chat(base_url, api_key, payload)
            else:
                payload = build_payload(model, messages)
                print("助手: ", end="", flush=True)
                assistant_text = stream_chat(base_url, api_key, payload)

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

