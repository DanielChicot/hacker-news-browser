"""A single-value TTL cache that serves stale data if a refresh fails."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Generic, TypeVar

T = TypeVar("T")
log = logging.getLogger(__name__)


class TtlCache(Generic[T]):
    def __init__(self, ttl_seconds: float, clock: Callable[[], float] = time.monotonic):
        self._ttl = ttl_seconds
        self._clock = clock
        self._value: T | None = None
        self._loaded_at: float | None = None
        self._lock = asyncio.Lock()

    def _fresh(self) -> bool:
        return self._loaded_at is not None and self._clock() - self._loaded_at < self._ttl

    async def get(self, loader: Callable[[], Awaitable[T]]) -> T:
        if self._fresh():
            return self._value  # type: ignore[return-value]
        async with self._lock:
            if self._fresh():
                return self._value  # type: ignore[return-value]
            try:
                self._value = await loader()
                self._loaded_at = self._clock()
            except Exception:
                if self._loaded_at is None:
                    raise
                log.exception("refresh failed, serving stale value")
            return self._value  # type: ignore[return-value]
