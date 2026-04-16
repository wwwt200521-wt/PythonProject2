from aiagent.history_compress import compress_history, should_compress


def fake_summarizer(_: str) -> str:
    return "SUMMARY"


def build_messages(rounds: int) -> list[dict]:
    messages = [{"role": "system", "content": "sys"}]
    for idx in range(rounds):
        messages.append({"role": "user", "content": f"question {idx}"})
        messages.append({"role": "assistant", "content": f"answer {idx}"})
    return messages


def test_round_limit() -> None:
    messages = build_messages(6)
    assert should_compress(messages)
    compressed = compress_history(messages, fake_summarizer)
    assert compressed[0]["role"] == "system"
    assert compressed[1]["role"] == "system"
    assert "SUMMARY" in compressed[1]["content"]
    assert compressed[-4:] == messages[-4:]


def test_length_limit() -> None:
    messages = [{"role": "system", "content": "sys"}]
    messages.append({"role": "user", "content": "x" * 4000})
    assert should_compress(messages)

