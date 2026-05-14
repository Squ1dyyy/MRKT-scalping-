import asyncio
import logging
from typing import TYPE_CHECKING, List, Optional

from domain.models import OrdersResponse
from transport import urls
from transport.errors import AuthError

if TYPE_CHECKING:
    from transport.client import MarketClient

log = logging.getLogger("mrkt.services.orders")


class OrdersService:
    def __init__(self, client: "MarketClient") -> None:
        self._client = client

    async def get_top_order(self, collection_name: str) -> Optional[int]:
        """Returns priceMaxNanoTONs of the highest buy order, or None."""
        raw = await self._client.get(
            urls.ORDER_TOP, params={"collectionName": collection_name}
        )
        if not raw or raw[0]["id"] is None:
            return None
        return raw[0]["priceMaxNanoTONs"]

    async def get_all_orders(self, collection_name: str) -> List[dict]:
        """Paginates through all buy orders for a collection."""
        all_orders: List[dict] = []
        cursor = ""
        while True:
            raw = await self._client.post(
                urls.ORDERS,
                json={"collectionName": collection_name, "cursor": cursor, "count": 20},
            )
            model = OrdersResponse(**raw)
            all_orders.extend(o.model_dump() for o in model.orders)
            if not model.cursor:
                break
            cursor = model.cursor
            await asyncio.sleep(0.1)
        return all_orders

    async def create_order(
        self,
        collection_name: str,
        price: int,
        quantity: int = 3,
        *,
        model_name: Optional[str] = None,
        backdrop_name: Optional[str] = None,
        symbol_name: Optional[str] = None,
    ) -> None:
        from domain.money import ton_to_nano
        if price > ton_to_nano(80):
            quantity = 1
        payload = {
            "collectionName": collection_name,
            "modelName": model_name,
            "backdropName": backdrop_name,
            "symbolName": symbol_name,
            "priceMinNanoTONs": 500_000_000,
            "priceMaxNanoTONs": price,
            "quantity": quantity,
        }
        try:
            await self._client.post(urls.ORDER_CREATE, json=payload)
            log.info("[CREATE ORDER] %s @ %d", collection_name, price)
        except AuthError:
            raise
        except Exception:
            log.exception("[CREATE ORDER FAILED] %s @ %d", collection_name, price)

    async def cancel_order(self, order_id: str, collection_name: str = "") -> None:
        try:
            await self._client.post(urls.ORDER_CANCEL + order_id)
            log.info("[CANCEL ORDER] %s id=%s", collection_name, order_id)
        except Exception:
            log.exception("[CANCEL ORDER FAILED] id=%s", order_id)
