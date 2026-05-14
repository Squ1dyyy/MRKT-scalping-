import logging
from typing import TYPE_CHECKING, List, Tuple

from domain.events import HistoryEvent, parse_history_events
from transport import urls

if TYPE_CHECKING:
    from transport.client import MarketClient

log = logging.getLogger("mrkt.services.wallet")


class WalletService:
    def __init__(self, client: "MarketClient") -> None:
        self._client = client

    async def get_balance(self) -> Tuple[int, int]:
        """Returns (hard_balance_nano, hard_locked_nano)."""
        raw = await self._client.get(urls.BALANCE)
        return raw["hard"], raw.get("hardLocked", 0)

    async def get_history(self, limit: int = 20) -> List[HistoryEvent]:
        raw = await self._client.get(urls.HISTORY, params={"limit": limit})
        return parse_history_events(raw)
