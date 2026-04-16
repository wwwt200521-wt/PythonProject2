# PythonProject2

Unified AI terminal agent package: `aiagent`.

## Setup

1. Create and activate virtual environment.
2. Copy `.env.example` to `.env` and fill values.
3. Run the CLI.

## Quick start (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
notepad .env
python -m aiagent.cli
```

## Main modules

- `aiagent/chatclient.py`: unified terminal chat flow (history compression, tool routing, streaming output).
- `aiagent/history_compress.py`: history compression and summary logic.
- `aiagent/tools/filesystem.py`: filesystem tools (list/read/write/delete/rename/create_dir).
- `aiagent/tools/weather.py`: weather tool wrapper for wttr.in.
- `aiagent/tools/anythingllm.py`: AnythingLLM tool wrapper.
- `aiagent/tools/history.py`: 5W history log append/search helpers.

## Tests

```powershell
python -m pip install pytest
python -m pytest -q
```

## Notes

- Reads `.env` from project root.
- Sends OpenAI-compatible requests to `{OPENAI_BASE_URL}/chat/completions`.
- Uses `ANYTHINGLLMAPIKEY` for AnythingLLM authentication.
