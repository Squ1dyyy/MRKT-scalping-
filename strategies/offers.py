import asyncio
import logging
from collections import deque
from typing import Deque, Dict, List, Optional

from bootstrap.settings import Settings
from domain.money import nano_to_ton, ton_to_nano
from integrations.portals import PortalsClient
from pool.account import Role
from pool.pool import AccountPool
from services.feed import FeedService
from services.offers import OffersService
from services.orders import OrdersService
from state.balance import BalanceTracker

log = logging.getLogger("mrkt.strategy.offers")


class OfferStrategy:
    """Sends buy-offers on listed gifts at a discount below the best order price.

    Reads the live feed → for each gift checks if there's an active buy order
    in the collection → offers at min(order_price, gift_price) × scale.
    """

    def __init__(
        self,
        pool: AccountPool,
        balance: BalanceTracker,
        portals: Optional[PortalsClient],
        settings: Settings,
    ) -> None:
        self._pool = pool
        self._balance = balance
        self._portals = portals
        self._settings = settings

    async def run(self) -> None:
        log.info("Offer strategy started")
        max_price_nano = ton_to_nano(self._settings.max_price_offer_ton)
        scale = 1 - self._settings.profit_percent_offer
        min_balance_nano = ton_to_nano(10)

        sent_offers: Deque[str] = deque(maxlen=100)

        while True:
            try:
                if self._balance.current < min_balance_nano:
                    await asyncio.sleep(2)
                    continue

                async with self._pool.acquire(Role.SCANNER) as client:
                    feed = await FeedService(client).get_feed(
                        min_price=ton_to_nano(self._settings.min_price_ton),
                        max_price=min(max_price_nano, self._balance.current),
                    )

                # Refresh portal floors if available
                portal_floors: Dict[str, int] = {}
                if self._portals and not self._settings.skip_portals:
                    try:
                        portal_floors = await self._portals.get_collections()
                    except Exception:
                        log.warning("Portals unavailable for offer strategy")

                # Get proposed orders map once per cycle
                proposed_orders = await self._get_proposed_orders(feed)

                for name, gifts in feed.items():
                    if name.strip().isdigit():
                        continue

                    max_order = proposed_orders.get(name, 0)
                    if max_order == 0:
                        continue

                    if not self._settings.skip_portals:
                        portal_floor = portal_floors.get(name)
                        if portal_floor is None:
                            continue
                        if portal_floor * self._settings.portals_commission < max_order:
                            continue

                    current_scale = scale

                    for gift in gifts:
                        if gift["amount"] > max_price_nano:
                            continue
                        diff_pct = (gift["amount"] - max_order) / max_order * 100 if max_order else 0
                        if diff_pct > 49:
                            continue

                        gift_id = gift["id"]
                        if gift_id in sent_offers:
                            continue

                        price_offer = min(max_order, gift["amount"]) * current_scale
                        if await self._balance.debit(int(price_offer)):
                            async with self._pool.acquire(Role.OFFERER) as client:
                                await OffersService(client).send_offer(
                                    gift_id, int(price_offer), gift=gift
                                )
                            sent_offers.append(gift_id)
                        else:
                            log.info(
                                "Insufficient balance: %.3f TON needed %.3f",
                                nano_to_ton(self._balance.current),
                                nano_to_ton(int(price_offer)),
                            )

            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Offer strategy cycle failed")

            await asyncio.sleep(3)

    async def _get_proposed_orders(self, feed: Dict[str, List[dict]]) -> Dict[str, int]:
        """Returns {collection_name: max_order_price} for collections in the feed."""
        proposed: Dict[str, int] = {}
        for name in feed:
            if name.strip().isdigit():
                continue
            try:
                async with self._pool.acquire(Role.SCANNER, key=name) as client:
                    price = await OrdersService(client).get_top_order(name)
                if price:
                    proposed[name] = price
            except Exception:
                log.debug("get_top_order failed for %s", name)
        return proposed
