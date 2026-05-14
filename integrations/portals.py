import asyncio
import logging
from typing import Dict, Optional

from curl_cffi.requests import AsyncSession
from curl_cffi.requests.exceptions import HTTPError

from domain.money import ton_to_nano
from transport.urls import PORTALS_COLLECTIONS, PORTALS_ORDERS

log = logging.getLogger("mrkt.portals")

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/137.0.0.0 Safari/537.36"
)


class PortalsClient:
    """Read-only client for portal-market.com.

    Uses its own session (separate auth / no impersonation needed).
    """

    def __init__(self, auth: Optional[str] = None, proxy: Optional[str] = None) -> None:
        self._auth = auth or ""
        self._proxy = proxy
        self._headers = {
            "User-Agent": _DEFAULT_UA,
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://portal-market.com/collection-list",
            "Origin": "https://portal-market.com",
            "Accept-Language": "ru,en;q=0.9",
        }
        if self._auth:
            self._headers["Authorization"] = self._auth
        self._session: Optional[AsyncSession] = None
        self._name_to_id: Dict[str, str] = {}
        self.current_floor_collections: Dict[str, int] = {}

    async def start(self) -> None:
        proxies = {"https": self._proxy} if self._proxy else None
        self._session = AsyncSession(impersonate="chrome", proxies=proxies, timeout=30)

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    async def init(self) -> None:
        """Pre-load collection names → IDs (needed for get_order)."""
        await self._load_collections(fetch_names=True)

    async def get_collections(self) -> Dict[str, int]:
        """Returns {collection_name: floorPriceNanoTons}."""
        return await self._load_collections(fetch_names=False)

    async def get_order(self, collection_name: str, all_orders: bool = False):
        collection_id = self._name_to_id.get(collection_name)
        if collection_id is None:
            await self.init()
            collection_id = self._name_to_id.get(collection_name)
        if collection_id is None:
            raise KeyError(f"Collection not found in Portals: {collection_name}")

        assert self._session is not None
        resp = await self._session.get(
            f"{PORTALS_ORDERS}{collection_id}/all",
            headers=self._headers,
        )
        resp.raise_for_status()
        data = resp.json()
        if all_orders:
            return data
        return ton_to_nano(float(data[0]["amount"]))

    async def _load_collections(self, fetch_names: bool) -> Dict[str, int]:
        assert self._session is not None, "Call await portals.start() first"

        resp = None
        for attempt in range(3):
            try:
                resp = await self._session.get(PORTALS_COLLECTIONS, headers=self._headers)
                resp.raise_for_status()
                break
            except HTTPError as exc:
                if hasattr(exc, "response") and exc.response.status_code == 429:
                    log.warning("Portals 429, retrying in %ds", attempt + 1)
                    await asyncio.sleep(attempt + 1)
                else:
                    log.exception("Portals collections fetch failed")
                    raise
        else:
            raise RuntimeError("Portals collections: exceeded retries")

        assert resp is not None
        data = resp.json()

        if fetch_names:
            for col in data.get("collections", []):
                self._name_to_id[col["name"]] = col["id"]
            return {}

        result: Dict[str, int] = {}
        for col in data.get("collections", []):
            try:
                result[col["name"]] = ton_to_nano(float(col["floor_price"]))
            except (KeyError, ValueError):
                pass
        self.current_floor_collections = result
        return result
