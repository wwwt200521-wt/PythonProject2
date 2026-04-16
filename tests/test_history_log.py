from pathlib import Path
from tempfile import TemporaryDirectory

from aiagent.tools.history import append_log_entries, read_log_text


def test_history_log_write_and_read() -> None:
    with TemporaryDirectory() as temp_dir:
        log_path = Path(temp_dir) / "log.txt"
        result = append_log_entries(
            [
                {
                    "who": "用户",
                    "what": "测试写入",
                    "when": "",
                    "where": "",
                    "why": "",
                }
            ],
            log_path=log_path,
        )
        assert result["appended"] == 1
        assert "测试写入" in read_log_text(log_path)

