import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

log = logging.getLogger("mrkt.state.offers")


class OffersBook:
    """Thread-safe store of active sent offers.

    Structure: {offer_id: (created_at, price_nano)}
    """

    def __init__(self) -> None:
        self._offers: Dict[str, Tuple[datetime, int]] = {}
        self._lock = asyncio.Lock()

    async def add(self, offer_id: str, created_at: datetime, price_nano: int) -> None:
        async with self._lock:
            self._offers[offer_id] = (created_at, price_nano)

    async def remove(self, offer_id: str) -> int:
        """Remove offer and return its price so caller can credit balance back."""
        async with self._lock:
            entry = self._offers.pop(offer_id, None)
            return entry[1] if entry else 0

    async def replace_all(self, offers: Dict[str, Tuple[datetime, int]]) -> None:
        async with self._lock:
            self._offers = dict(offers)

    def snapshot(self) -> Dict[str, Tuple[datetime, int]]:
        return dict(self._offers)

    def expired(self, now: datetime, max_age_minutes: int) -> List[str]:
        threshold = timedelta(minutes=max_age_minutes)
        return [
            oid for oid, (created_at, _) in self._offers.items()
            if now - created_at > threshold
        ]
