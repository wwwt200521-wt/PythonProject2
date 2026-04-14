# Practice 04

This module adds automatic chat history compression and 5W fact logging using the same OpenAI-compatible API.

- When the history exceeds 5 rounds or 3k characters, it summarizes older messages.
- The oldest ~75% of messages are summarized, and the newest ~30% are kept verbatim.
- Key facts are extracted into `Log/log.txt` using the 5W format (who/what/when/where/why).
- Use `/search <query>` to search the log with an extra LLM call.

## Run

```powershell
python practice04\terminal_chat_stream.py
```

## Log file

```
Log/log.txt
```

## Test

```powershell
python practice04\test_history_log.py
```
