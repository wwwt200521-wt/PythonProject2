from __future__ import annotations

import urllib.error

import pytest

from aiagent.retry import retry_on_failure, _is_retryable_http_error


class FakeHTTPError(urllib.error.HTTPError):
    def __init__(self, url: str, code: int, msg: str, hdrs, fp) -> None:
        super().__init__(url, code, msg, hdrs, fp)


class TestIsRetryableHTTPError:
    def test_500_is_retryable(self) -> None:
        exc = FakeHTTPError("http://x", 500, "Error", None, None)
        assert _is_retryable_http_error(exc) is True

    def test_503_is_retryable(self) -> None:
        exc = FakeHTTPError("http://x", 503, "Error", None, None)
        assert _is_retryable_http_error(exc) is True

    def test_400_is_not_retryable(self) -> None:
        exc = FakeHTTPError("http://x", 400, "Error", None, None)
        assert _is_retryable_http_error(exc) is False

    def test_404_is_not_retryable(self) -> None:
        exc = FakeHTTPError("http://x", 404, "Error", None, None)
        assert _is_retryable_http_error(exc) is False


class TestRetryOnFailure:
    def test_success_on_first_attempt_returns_immediately(self) -> None:
        call_count = 0

        @retry_on_failure(max_attempts=3)
        def work() -> int:
            nonlocal call_count
            call_count += 1
            return 42

        assert work() == 42
        assert call_count == 1

    def test_retries_on_urlerror_and_succeeds(self) -> None:
        call_count = 0

        @retry_on_failure(max_attempts=3, initial_delay=0.01)
        def work() -> int:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise urllib.error.URLError("timeout")
            return 99

        assert work() == 99
        assert call_count == 3

    def test_retries_on_5xx_and_succeeds(self) -> None:
        call_count = 0

        @retry_on_failure(max_attempts=3, initial_delay=0.01)
        def work() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise FakeHTTPError("http://x", 502, "Bad Gateway", None, None)
            return "ok"

        assert work() == "ok"
        assert call_count == 2

    def test_no_retry_on_4xx(self) -> None:
        call_count = 0

        @retry_on_failure(max_attempts=3)
        def work() -> None:
            nonlocal call_count
            call_count += 1
            raise FakeHTTPError("http://x", 403, "Forbidden", None, None)

        with pytest.raises(FakeHTTPError):
            work()
        assert call_count == 1  # 4xx should not be retried

    def test_gives_up_after_max_attempts(self) -> None:
        call_count = 0

        @retry_on_failure(max_attempts=3, initial_delay=0.01)
        def work() -> None:
            nonlocal call_count
            call_count += 1
            raise urllib.error.URLError("fail")

        with pytest.raises(urllib.error.URLError):
            work()
        assert call_count == 3

    def test_max_attempts_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="max_attempts"):
            retry_on_failure(max_attempts=0)

    def test_non_retryable_exception_raised_immediately(self) -> None:
        call_count = 0

        @retry_on_failure(max_attempts=3)
        def work() -> None:
            nonlocal call_count
            call_count += 1
            raise TypeError("bad type")

        with pytest.raises(TypeError):
            work()
        assert call_count == 1

    def test_connection_error_is_retryable(self) -> None:
        call_count = 0

        @retry_on_failure(max_attempts=3, initial_delay=0.01)
        def work() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("refused")
            return "connected"

        assert work() == "connected"
        assert call_count == 2
