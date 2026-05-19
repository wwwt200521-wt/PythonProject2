from __future__ import annotations

import functools
import time
import urllib.error
from collections.abc import Callable
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

DEFAULT_RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    urllib.error.URLError,
    ConnectionError,
    TimeoutError,
    OSError,
)


def _is_retryable_http_error(exc: urllib.error.HTTPError) -> bool:
    return 500 <= exc.code < 600


def retry_on_failure(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    retryable_exceptions: tuple[type[BaseException], ...] = DEFAULT_RETRYABLE_EXCEPTIONS,
) -> Callable[[F], F]:
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            delay = initial_delay
            last_exception: Exception | None = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except urllib.error.HTTPError as exc:
                    if not _is_retryable_http_error(exc):
                        raise
                    last_exception = exc
                    if attempt < max_attempts:
                        time.sleep(delay)
                        delay *= backoff_factor
                except retryable_exceptions as exc:
                    last_exception = exc
                    if attempt < max_attempts:
                        time.sleep(delay)
                        delay *= backoff_factor
                except Exception:
                    raise

            raise last_exception  # type: ignore[misc]

        return wrapper  # type: ignore[return-value]

    return decorator
