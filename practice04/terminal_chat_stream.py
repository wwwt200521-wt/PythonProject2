import json
from pathlib import Path
from urllib import request, error

from history_compress import compress_history, should_compress


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


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    env_data = load_env(project_root / ".env")

    base_url = env_data.get("OPENAI_BASE_URL")
    model = env_data.get("OPENAI_MODEL")
    api_key = env_data.get("OPENAI_API_KEY", "")

    if not base_url or not model:
        raise ValueError("OPENAI_BASE_URL and OPENAI_MODEL are required in .env")

    messages = [
        {"role": "system", "content": "你是一个有帮助的助手，请用中文回答。"}
    ]

    print("进入终端聊天模式（自动压缩历史记录），按 Ctrl+C 退出。")
    while True:
        try:
            user_text = input("你: ").strip()
            if not user_text:
                continue
            messages.append({"role": "user", "content": user_text})

            if should_compress(messages):
                print("正在压缩历史记录...")
                messages = compress_history(
                    messages,
                    lambda transcript: summarize_history(base_url, api_key, model, transcript),
                )

            payload = build_payload(model, messages)
            print("助手: ", end="", flush=True)
            assistant_text = stream_chat(base_url, api_key, payload)
            if assistant_text:
                messages.append({"role": "assistant", "content": assistant_text})
        except KeyboardInterrupt:
            print("\n已退出。")
            break
        except Exception as exc:
            print(f"发生错误: {exc}")


if __name__ == "__main__":
    main()

