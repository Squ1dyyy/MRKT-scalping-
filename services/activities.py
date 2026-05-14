import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Dict, List

from dateutil import parser as dateutil_parser

from transport import urls

if TYPE_CHECKING:
    from transport.client import MarketClient

log = logging.getLogger("mrkt.services.activities")


@dataclass
class ActiveOffer:
    id: str
    created_at: datetime
    price_nano: int


@dataclass
class ActivitiesSnapshot:
    orders: Dict[str, Dict[str, int]] = field(default_factory=dict)
    # collection_name → {order_id: priceMaxNanoTONs}
    own_offers: List[ActiveOffer] = field(default_factory=list)
    foreign_offer_ids: List[str] = field(default_factory=list)


class ActivitiesService:
    def __init__(self, client: "MarketClient") -> None:
        self._client = client

    async def fetch_all(self, is_active: bool = True) -> ActivitiesSnapshot:
        """Paginates through all activities and returns a structured snapshot."""
        snapshot = ActivitiesSnapshot()
        offset = 0
        while True:
            count = await self._fetch_page(snapshot, offset=offset, is_active=is_active)
            if count == 0:
                break
            offset += 20
        return snapshot

    async def _fetch_page(
        self,
        snapshot: ActivitiesSnapshot,
        offset: int,
        is_active: bool,
    ) -> int:
        raw = await self._client.get(
            urls.ACTIVITIES,
            params={"offset": offset, "count": 20, "isActive": str(is_active).lower()},
        )

        count = 0
        for item in raw:
            t = item.get("type")
            if t == "order":
                order = item["order"]
                coll = order["collectionName"]
                oid = order["id"]
                snapshot.orders.setdefault(coll, {})[oid] = order["priceMaxNanoTONs"]
                count += 1

            elif t == "offer_activity":
                offer = item.get("offer", {})
                if offer.get("isMine"):
                    snapshot.own_offers.append(
                        ActiveOffer(
                            id=offer["id"],
                            created_at=dateutil_parser.isoparse(offer["createdAt"]),
                            price_nano=offer["priceNanoTONs"],
                        )
                    )
                else:
                    snapshot.foreign_offer_ids.append(offer["id"])

        return count
