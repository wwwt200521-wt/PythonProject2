import json
from pathlib import Path
from urllib import request, error

from tools_fs import format_tool_result, tool_dispatch, tool_specs


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


def run_tool_call(call: dict, tools: dict) -> tuple[str, str]:
    name = call.get("function", {}).get("name")
    raw_args = call.get("function", {}).get("arguments", "{}")
    if not name or name not in tools:
        raise ValueError("Unknown tool requested")
    try:
        args = json.loads(raw_args) if raw_args else {}
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid tool arguments") from exc
    result = tools[name](**args)
    return name, format_tool_result(result)


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    env_data = load_env(project_root / ".env")

    base_url = env_data.get("OPENAI_BASE_URL")
    model = env_data.get("OPENAI_MODEL")
    api_key = env_data.get("OPENAI_API_KEY", "")

    if not base_url or not model:
        raise ValueError("OPENAI_BASE_URL and OPENAI_MODEL are required in .env")

    system_prompt = (
        "你是一个支持工具调用的助手。"
        "当用户需要处理本地文件或目录时，优先使用工具。"
        "工具可用时，先调用工具，再根据工具结果回答用户。"
        "如果问题不需要工具，直接回答。"
    )

    messages = [{"role": "system", "content": system_prompt}]
    tools = tool_specs()
    dispatch = tool_dispatch()

    print("进入工具调用聊天模式，按 Ctrl+C 退出。")
    while True:
        try:
            user_text = input("你: ").strip()
            if not user_text:
                continue
            messages.append({"role": "user", "content": user_text})

            payload = {
                "model": model,
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
                "temperature": 0.4,
            }

            response = call_llm(base_url, api_key, payload)
            message = response.get("choices", [{}])[0].get("message", {})
            tool_calls = extract_tool_calls(message)

            if tool_calls:
                messages.append(message)
                for call in tool_calls:
                    tool_name, tool_result = run_tool_call(call, dispatch)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.get("id", ""),
                            "name": tool_name,
                            "content": tool_result,
                        }
                    )

                followup_payload = {
                    "model": model,
                    "messages": messages,
                    "temperature": 0.4,
                }
                followup = call_llm(base_url, api_key, followup_payload)
                assistant = followup.get("choices", [{}])[0].get("message", {})
                content = assistant.get("content") or ""
            else:
                content = message.get("content") or ""

            print(f"助手: {content}")
            if content:
                messages.append({"role": "assistant", "content": content})
        except KeyboardInterrupt:
            print("\n已退出。")
            break
        except Exception as exc:
            print(f"发生错误: {exc}")


if __name__ == "__main__":
    main()

