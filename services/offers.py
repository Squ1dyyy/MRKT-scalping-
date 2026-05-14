import logging
from typing import TYPE_CHECKING, Optional

from transport import urls

if TYPE_CHECKING:
    from transport.client import MarketClient

log = logging.getLogger("mrkt.services.offers")


class OffersService:
    def __init__(self, client: "MarketClient") -> None:
        self._client = client

    async def send_offer(self, gift_sale_id: str, price: int, gift: Optional[dict] = None) -> None:
        payload = {"giftSaleId": gift_sale_id, "price": price}
        try:
            await self._client.post(urls.OFFER_CREATE, json=payload)
            _desc = _gift_desc(gift) if gift else gift_sale_id
            log.info("[OFFER SENT] %s price=%d", _desc, price)
        except Exception:
            _desc = _gift_desc(gift) if gift else gift_sale_id
            log.exception("[OFFER FAILED] %s price=%d", _desc, price)

    async def cancel_offer(self, offer_id: str) -> None:
        headers_extra = {"Content-Type": "application/x-www-form-urlencoded"}
        try:
            await self._client.post(
                f"{urls.OFFER_CANCEL}?offerId={offer_id}",
                headers=headers_extra,
            )
            log.info("[OFFER CANCEL] id=%s", offer_id)
        except Exception:
            log.exception("[OFFER CANCEL FAILED] id=%s", offer_id)

    async def decline_offer(self, offer_id: str) -> None:
        headers_extra = {"Content-Type": "application/x-www-form-urlencoded"}
        try:
            await self._client.post(
                f"{urls.OFFER_DECLINE}?offerId={offer_id}",
                headers=headers_extra,
            )
            log.info("[OFFER DECLINE] id=%s", offer_id)
        except Exception:
            log.exception("[OFFER DECLINE FAILED] id=%s", offer_id)


def _gift_desc(gift: dict) -> str:
    return (
        f"M:{gift.get('name')} "
        f"N:{gift.get('modelName')} "
        f"B:{gift.get('backdropName')} "
        f"S:{gift.get('symbolName')}"
    )
