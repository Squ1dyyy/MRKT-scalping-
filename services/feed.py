import logging
from typing import TYPE_CHECKING, Dict, List, Optional, Set

from transport import urls

if TYPE_CHECKING:
    from transport.client import MarketClient

log = logging.getLogger("mrkt.services.feed")

_DEFAULT_TYPES = ["Sale", "Listing", "ChangePrice"]


class FeedService:
    def __init__(self, client: "MarketClient") -> None:
        self._client = client

    async def get_feed(
        self,
        min_price: int,
        max_price: int,
        types: Optional[List[str]] = None,
    ) -> Dict[str, List[dict]]:
        """Returns {collection_name: [gift_dict, ...]} from the live feed."""
        payload = {
            "count": 20,
            "cursor": "",
            "collectionNames": [],
            "modelNames": [],
            "backdropNames": [],
            "number": None,
            "type": types or _DEFAULT_TYPES,
            "minPrice": min_price,
            "maxPrice": max_price,
            "ordering": "Latest",
            "lowToHigh": False,
            "query": None,
        }
        raw = await self._client.post(urls.FEED, json=payload)
        return _parse_feed(raw)

    async def get_saling_gifts(
        self, collection_name: str, cursor: str = ""
    ) -> Optional[dict]:
        """Returns raw saling-gifts page (gifts + next cursor)."""
        payload = {
            "count": 20,
            "cursor": cursor,
            "collectionNames": [collection_name],
            "modelNames": [],
            "backdropNames": [],
            "symbolNames": [],
            "craftable": None,
            "giftType": None,
            "isCrafted": None,
            "isNew": None,
            "isPremarket": None,
            "isTransferable": None,
            "lowToHigh": True,
            "luckyBuy": None,
            "maxPrice": None,
            "minPrice": None,
            "number": None,
            "ordering": "Price",
            "query": None,
            "removeSelfSales": None,
            "tgCanBeCraftedFrom": None,
        }
        try:
            return await self._client.post(urls.SALING_GIFTS, json=payload)
        except Exception:
            log.exception("get_saling_gifts failed for %s", collection_name)
            return None


def _parse_feed(raw: dict) -> Dict[str, List[dict]]:
    data: Dict[str, List[dict]] = {}
    seen_types: Dict[str, Set[str]] = {}

    for item in raw.get("items", []):
        _type = item.get("type")
        price = item.get("amount")
        _gift = item.get("gift", {})

        name = _gift.get("collectionName")
        _id = _gift.get("id")

        if _id not in seen_types:
            seen_types[_id] = set()

        if _type == "sale" and {"listing", "change_price"} & seen_types[_id]:
            continue
        seen_types[_id].add(_type)
        if _type == "sale":
            continue

        mr = _gift.get("modelRarityPerMille")
        sr = _gift.get("symbolRarityPerMille")
        br = _gift.get("backdropRarityPerMille")

        if name not in data:
            data[name] = []

        data[name].append({
            "id": _id,
            "amount": price,
            "type": _type,
            "name": name,
            "modelName": _gift.get("modelName"),
            "modelRarityPerMille": mr / 10 if mr is not None else _gift.get("modelRarityName"),
            "backdropName": _gift.get("backdropName"),
            "backdropRarityPerMille": br / 10 if br is not None else None,
            "symbolName": _gift.get("symbolName"),
            "symbolRarityPerMille": sr / 10 if sr is not None else _gift.get("symbolRarityName", "-"),
        })

    return data
