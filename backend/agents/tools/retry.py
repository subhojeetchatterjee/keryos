"""Shared retry + exponential backoff with jitter for all HTTP callers."""

import logging
import random
import time
from collections.abc import Callable
from typing import TypeVar

import requests

_log = logging.getLogger(__name__)

T = TypeVar("T")

_RETRYABLE_STATUS = (429, 500, 502, 503, 504)


def with_retry(
    fn: Callable[[], T],
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable_status: tuple[int, ...] = _RETRYABLE_STATUS,
) -> T:
    """
    Call fn() retrying on Timeout or retryable HTTP status codes.
    Uses exponential backoff with full-jitter: sleep = rand(0, min(cap, base * 2^attempt)).
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            return fn()
        except requests.exceptions.Timeout as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                delay = min(base_delay * (2**attempt), max_delay) * random.random()
                _log.warning(
                    "Request timed out (attempt %d/%d), retrying in %.1fs", attempt + 1, max_retries, delay
                )
                time.sleep(delay)
        except requests.exceptions.HTTPError as exc:
            last_exc = exc
            if (
                exc.response is not None
                and exc.response.status_code in retryable_status
                and attempt < max_retries - 1
            ):
                delay = min(base_delay * (2**attempt), max_delay) * random.random()
                _log.warning(
                    "HTTP %d (attempt %d/%d), retrying in %.1fs",
                    exc.response.status_code,
                    attempt + 1,
                    max_retries,
                    delay,
                )
                time.sleep(delay)
            else:
                raise
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("with_retry: unreachable")
