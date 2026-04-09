import json
from pathlib import Path
from urllib import request, error


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

    print("进入终端聊天模式，按 Ctrl+C 退出。")
    while True:
        try:
            user_text = input("你: ").strip()
            if not user_text:
                continue
            messages.append({"role": "user", "content": user_text})

            payload = build_payload(model, messages)
            print("助手: ", end="", flush=True)
            assistant_text = stream_chat(base_url, api_key, payload)
            if assistant_text:
                messages.append({"role": "assistant", "content": assistant_text})
        except KeyboardInterrupt:
            print("\n已退出。")
            break


if __name__ == "__main__":
    main()

