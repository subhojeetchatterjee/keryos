"""Simple in-memory TTL cache for expensive API results (catalog, NDVI stats)."""
import functools
import hashlib
import json
import logging
import time
from collections.abc import Callable
from typing import Any, TypeVar

_log = logging.getLogger(__name__)

T = TypeVar("T")


class _TTLCache:
    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = ttl_seconds
        self._store: dict[str, tuple[Any, float]] = {}

    def _make_key(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> str:
        raw = json.dumps({"a": args, "k": kwargs}, sort_keys=True, default=str)
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, key: str) -> tuple[bool, Any]:
        entry = self._store.get(key)
        if entry and time.monotonic() < entry[1]:
            return True, entry[0]
        self._store.pop(key, None)
        return False, None

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (value, time.monotonic() + self._ttl)

    def invalidate(self) -> None:
        self._store.clear()


def ttl_cached(ttl_seconds: int = 300) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator: cache the return value of a function for ttl_seconds."""
    cache = _TTLCache(ttl_seconds)

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            key = cache._make_key(args, kwargs)
            hit, value = cache.get(key)
            if hit:
                _log.debug("Cache hit: %s", fn.__qualname__)
                return value  # type: ignore[return-value]
            result = fn(*args, **kwargs)
            cache.set(key, result)
            return result

        return wrapper

    return decorator
