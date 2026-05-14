import asyncio
import logging

log = logging.getLogger("mrkt.state.balance")


class BalanceTracker:
    """Thread-safe balance tracker.

    Holds an optimistic in-memory balance that strategies can debit locally
    (to avoid over-spending before the API confirms). The authoritative
    balance is refreshed periodically via update().
    """

    def __init__(self, initial: int = 0) -> None:
        self._balance = initial
        self._locked = 0
        self._lock = asyncio.Lock()

    @property
    def current(self) -> int:
        return self._balance

    @property
    def locked(self) -> int:
        return self._locked

    async def update(self, balance: int, locked: int = 0) -> None:
        async with self._lock:
            self._balance = balance
            self._locked = locked
            log.info("Balance updated: %.3f TON (locked %.3f)", balance / 1e9, locked / 1e9)

    async def debit(self, amount: int) -> bool:
        """Optimistically debit amount. Returns False if insufficient balance."""
        async with self._lock:
            if self._balance < amount:
                return False
            self._balance -= amount
            return True

    async def credit(self, amount: int) -> None:
        async with self._lock:
            self._balance += amount
