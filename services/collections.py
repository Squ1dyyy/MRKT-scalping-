import logging
from typing import TYPE_CHECKING, Dict, Optional, Set

from domain.models import CollectionItem
from transport import urls

if TYPE_CHECKING:
    from transport.client import MarketClient

log = logging.getLogger("mrkt.services.collections")


class CollectionsService:
    def __init__(self, client: "MarketClient") -> None:
        self._client = client

    async def get_collections(
        self,
        black_list: Optional[Set[str]] = None,
    ) -> Dict[str, int]:
        """Returns {collection_name: floorPriceNanoTons} filtered by black_list."""
        raw = await self._client.get(urls.COLLECTIONS)
        result: Dict[str, int] = {}
        for item in raw:
            if item.get("floorPriceNanoTons") is None:
                continue
            col = CollectionItem(**item)
            if col.isNew:
                continue
            if black_list and col.name.lower() in black_list:
                log.debug("[BLACK LIST] %s", col.name)
                continue
            result[col.name] = col.floorPriceNanoTons
        return result
