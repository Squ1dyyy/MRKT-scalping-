import asyncio
import time
from typing import Optional


class TokenBucket:
    """Async token-bucket rate limiter."""

    def __init__(self, rate: float, burst: Optional[float] = None):
        self._rate = rate
        self._burst = burst if burst is not None else rate * 2
        self._tokens = self._burst
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._last = now
            self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
            if self._tokens < 1:
                sleep_for = (1 - self._tokens) / self._rate
                await asyncio.sleep(sleep_for)
                self._tokens = 0
            else:
                self._tokens -= 1
