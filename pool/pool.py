from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from pool.account import AccountConfig, Role
from transport.client import MarketClient
from transport.errors import NoAccountError

log = logging.getLogger("mrkt.pool")


class AccountPool:
    """Holds one MarketClient per account; routes requests by role.

    acquire(role) — round-robin across accounts that have that role.
    acquire(role, key=collection_name) — sticky: same collection always
    goes to the same account to avoid conflicting order books.
    """

    def __init__(self, accounts: list[AccountConfig]) -> None:
        self._clients: dict[str, MarketClient] = {
            acc.name: MarketClient(acc) for acc in accounts
        }
        self._by_role: dict[Role, list[str]] = {}
        for acc in accounts:
            for role in Role:
                if acc.has_role(role):
                    self._by_role.setdefault(role, []).append(acc.name)

        self._rr_counters: dict[Role, int] = {}
        self._sticky_map: dict[str, str] = {}  # key → account name

        for role, names in self._by_role.items():
            log.info("Role %s → %s", role.name, names)

    async def start(self) -> None:
        for client in self._clients.values():
            await client.start()
        log.info("Pool started (%d accounts)", len(self._clients))

    async def close(self) -> None:
        for client in self._clients.values():
            await client.close()
        log.info("Pool closed")

    @asynccontextmanager
    async def acquire(
        self, role: Role, *, key: Optional[str] = None
    ) -> AsyncIterator[MarketClient]:
        client = self._pick(role, key=key)
        log.debug("Acquired %s for role %s (key=%s)", client.cfg.name, role.name, key)
        yield client

    def client(self, name: str) -> MarketClient:
        return self._clients[name]

    def _pick(self, role: Role, *, key: Optional[str] = None) -> MarketClient:
        names = self._by_role.get(role)
        if not names:
            raise NoAccountError(f"No account configured with role {role.name}")

        if key is not None:
            sticky_key = f"{role.name}:{key}"
            if sticky_key not in self._sticky_map:
                idx = abs(hash(key)) % len(names)
                self._sticky_map[sticky_key] = names[idx]
            return self._clients[self._sticky_map[sticky_key]]

        # round-robin
        idx = self._rr_counters.get(role, 0)
        self._rr_counters[role] = (idx + 1) % len(names)
        return self._clients[names[idx]]
