import logging
from typing import TYPE_CHECKING, List, Optional, Tuple

from transport import urls

if TYPE_CHECKING:
    from transport.client import MarketClient

log = logging.getLogger("mrkt.services.trading")


class TradingService:
    def __init__(self, client: "MarketClient") -> None:
        self._client = client

    async def buy_gift(self, gift_id: str, price: int) -> Optional[dict]:
        payload = {"ids": [gift_id], "prices": {gift_id: price}}
        try:
            result = await self._client.post(urls.BUY_GIFT, json=payload)
            log.info("[BUY] id=%s price=%d", gift_id, price)
            return result
        except Exception:
            log.exception("[BUY FAILED] id=%s price=%d", gift_id, price)
            return None

    async def sell_gift(self, gift_id: str, price: int) -> Optional[dict]:
        payload = {"ids": [gift_id], "price": price}
        try:
            result = await self._client.post(urls.SALE_GIFT, json=payload)
            log.info("[SELL] id=%s price=%d", gift_id, price)
            return result
        except Exception:
            log.exception("[SELL FAILED] id=%s price=%d", gift_id, price)
            return None

    async def fetch_container(
        self,
        is_listed: bool = False,
        cursor: str = "",
    ) -> Tuple[List[dict], Optional[str]]:
        """Returns (gifts_list, next_cursor)."""
        payload = {
            "isListed": is_listed,
            "count": 20,
            "cursor": cursor,
            "collectionNames": [],
            "modelNames": [],
            "backdropNames": [],
            "symbolNames": [],
            "number": None,
            "isNew": None,
            "isPremarket": None,
            "luckyBuy": None,
            "giftType": None,
            "craftable": None,
            "removeSelfSales": None,
            "isTransferable": None,
            "minPrice": None,
            "maxPrice": None,
            "ordering": "None",
            "lowToHigh": False,
            "query": None,
        }
        raw = await self._client.post(urls.CONTAINER, json=payload)
        gifts = raw.get("gifts", [])
        next_cursor = raw.get("cursor")
        return gifts, next_cursor

    async def fetch_all_container(self, is_listed: bool = False) -> List[dict]:
        all_gifts: List[dict] = []
        cursor = ""
        while True:
            gifts, next_cursor = await self.fetch_container(is_listed, cursor)
            if not gifts:
                break
            all_gifts.extend(gifts)
            if not next_cursor:
                break
            cursor = next_cursor
        return all_gifts
