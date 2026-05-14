import asyncio
import logging
from typing import Dict, List

log = logging.getLogger("mrkt.state.orders")


class OrdersBook:
    """Thread-safe store of active buy orders.

    Structure: {collection_name: {order_id: priceMaxNanoTONs}}
    """

    def __init__(self) -> None:
        self._orders: Dict[str, Dict[str, int]] = {}
        self._lock = asyncio.Lock()

    async def replace_all(self, snapshot: Dict[str, Dict[str, int]]) -> None:
        async with self._lock:
            self._orders = {k: dict(v) for k, v in snapshot.items()}

    async def add(self, collection: str, order_id: str, price: int) -> None:
        async with self._lock:
            self._orders.setdefault(collection, {})[order_id] = price

    async def remove(self, collection: str, order_id: str) -> None:
        async with self._lock:
            if collection in self._orders:
                self._orders[collection].pop(order_id, None)
                if not self._orders[collection]:
                    del self._orders[collection]

    async def remove_collection(self, collection: str) -> None:
        async with self._lock:
            self._orders.pop(collection, None)

    def snapshot(self) -> Dict[str, Dict[str, int]]:
        return {k: dict(v) for k, v in self._orders.items()}

    def get_collection(self, collection: str) -> Dict[str, int]:
        return dict(self._orders.get(collection, {}))

    def collections(self) -> List[str]:
        return list(self._orders.keys())
