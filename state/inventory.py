import asyncio
import logging
from typing import Dict, List

log = logging.getLogger("mrkt.state.inventory")


class InventoryStore:
    """Tracks gifts we currently own, indexed by collection."""

    def __init__(self) -> None:
        self._counts: Dict[str, int] = {}
        self._lock = asyncio.Lock()

    async def update_from_container(self, gifts: List[dict]) -> None:
        counts: Dict[str, int] = {}
        for gift in gifts:
            col = gift.get("collectionName") or gift.get("collection")
            if col:
                counts[col] = counts.get(col, 0) + 1
        async with self._lock:
            self._counts = counts
        log.debug("Inventory updated: %d collections", len(counts))

    def count(self, collection: str) -> int:
        return self._counts.get(collection, 0)

    def snapshot(self) -> Dict[str, int]:
        return dict(self._counts)
