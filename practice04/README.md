# Practice 04

This module adds automatic chat history compression using the same OpenAI-compatible API.

- When the history exceeds 5 rounds or 3k characters, it summarizes older messages.
- The oldest ~75% of messages are summarized, and the newest ~30% are kept verbatim.

## Run

```powershell
python practice04\terminal_chat_stream.py
```

## Test

```powershell
python practice04\test_history_compress.py
```

