import asyncio
import logging
from typing import Dict, List, Optional, Tuple

from bootstrap.settings import Settings
from domain.money import nano_to_ton, ton_to_nano
from integrations.portals import PortalsClient
from integrations.telegram import TelegramNotifier
from pool.account import Role
from pool.pool import AccountPool
from services.activities import ActivitiesService
from services.collections import CollectionsService
from services.orders import OrdersService
from services.trading import TradingService
from state.balance import BalanceTracker
from state.inventory import InventoryStore
from state.orders_book import OrdersBook

log = logging.getLogger("mrkt.strategy.orders")


class OrderStrategy:
    def __init__(
        self,
        pool: AccountPool,
        orders_book: OrdersBook,
        balance: BalanceTracker,
        inventory: InventoryStore,
        portals: Optional[PortalsClient],
        settings: Settings,
        notifier: TelegramNotifier,
        session_num: int = 0,
    ) -> None:
        self._pool = pool
        self._orders_book = orders_book
        self._balance = balance
        self._inventory = inventory
        self._portals = portals
        self._settings = settings
        self._notifier = notifier
        self._session_num = session_num

    async def run(self) -> None:
        log.info("Order strategy started (session #%d)", self._session_num)
        while True:
            try:
                await self._cycle()
            except asyncio.CancelledError:
                log.info("Order strategy cancelled, cleaning up...")
                await self._cancel_all_orders()
                raise
            except Exception:
                log.exception("Order strategy cycle failed")
            log.info("Sleeping %ds...", self._settings.time_sleep)
            await asyncio.sleep(self._settings.time_sleep)

    async def _cycle(self) -> None:
        # 1. Sync activities → orders book
        async with self._pool.acquire(Role.WALLET) as client:
            snapshot = await ActivitiesService(client).fetch_all()
        await self._orders_book.replace_all(snapshot.orders)

        # 2. Update inventory
        async with self._pool.acquire(Role.SCANNER) as client:
            gifts = await TradingService(client).fetch_all_container()
        await self._inventory.update_from_container(gifts)

        # Notify newly acquired gifts
        if gifts:
            async with self._pool.acquire(Role.SCANNER) as client:
                floor_cols = await CollectionsService(client).get_collections()
            await self._notify_new_gifts(gifts, floor_cols)

        # 3. Get collection floors
        async with self._pool.acquire(Role.SCANNER) as client:
            mrkt_cols = await CollectionsService(client).get_collections(
                black_list=set(self._settings.black_list)
            )

        portal_cols = mrkt_cols
        if self._portals:
            try:
                portal_cols = await self._portals.get_collections()
            except Exception:
                log.warning("Portals unavailable, using MRKT floors as fallback")

        # 4. Find profitable orders
        profitable = await self._find_profitable(mrkt_cols, portal_cols)

        # 5. Sync orders
        await self._sync_orders(profitable)

    async def _find_profitable(
        self,
        mrkt_cols: Dict[str, int],
        portal_cols: Dict[str, int],
    ) -> Dict[str, int]:
        min_nano = ton_to_nano(self._settings.min_price_ton)
        max_nano = min(
            ton_to_nano(self._settings.max_price_ton),
            self._balance.current,
        )

        candidates = {
            name: floor
            for name, floor in mrkt_cols.items()
            if (
                min_nano < floor < max_nano
                and not name.strip().isdigit()
                and self._inventory.count(name) < self._settings.max_collection_stock
            )
        }

        profitable: Dict[str, int] = {}
        batch_size = 5

        names = list(candidates.items())
        for i in range(0, len(names), batch_size):
            batch = names[i : i + batch_size]
            tasks = [
                self._evaluate_collection(name, floor, portal_cols.get(name))
                for name, floor in batch
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    log.error("Collection evaluation error: %s", result)
                    continue
                if result is not None:
                    col_name, price = result
                    profitable[col_name] = price

        log.info("Found %d profitable collections", len(profitable))
        return profitable

    async def _evaluate_collection(
        self,
        name: str,
        mrkt_floor: int,
        portal_floor: Optional[int],
    ) -> Optional[Tuple[str, int]]:
        async with self._pool.acquire(Role.ORDERER, key=name) as client:
            top_order = await OrdersService(client).get_top_order(name)

        if top_order is None:
            common_floor = min(portal_floor or mrkt_floor, mrkt_floor)
            top_order = _calc_order_price(common_floor)

        portal_floor = portal_floor or mrkt_floor
        mrkt_profit = mrkt_floor * 1.0 - top_order - ton_to_nano(0.02)
        portal_profit = portal_floor * self._settings.portals_commission - top_order - ton_to_nano(0.02)

        if top_order == 0:
            return None

        profit_pct = mrkt_profit / top_order
        if profit_pct > self._settings.profit_percent and portal_profit > 0:
            log.info(
                "%s: +%.3f TON (%.2f%%)",
                name,
                nano_to_ton(mrkt_profit),
                profit_pct * 100,
                extra={"collection": name},
            )
            return name, top_order
        return None

    async def _sync_orders(self, profitable: Dict[str, int]) -> None:
        current = self._orders_book.snapshot()
        up_price = self._settings.order_up_price_nano

        # Cancel orders for collections no longer profitable
        for name in list(current):
            if name not in profitable:
                for order_id in current[name]:
                    async with self._pool.acquire(Role.ORDERER, key=name) as client:
                        await OrdersService(client).cancel_order(order_id, name)
                await self._orders_book.remove_collection(name)
                log.info("[DELETE] %s", name)

        # Create / update orders
        for name, new_price in profitable.items():
            curr_orders = self._orders_book.get_collection(name)

            if not curr_orders:
                async with self._pool.acquire(Role.ORDERER, key=name) as client:
                    await OrdersService(client).create_order(name, new_price + up_price)
                log.info("[CREATE] %s → %.3f TON", name, nano_to_ton(new_price + up_price))
                continue

            order_id, curr_price = next(iter(curr_orders.items()))
            if new_price > curr_price or new_price < curr_price - up_price:
                async with self._pool.acquire(Role.ORDERER, key=name) as client:
                    svc = OrdersService(client)
                    await svc.cancel_order(order_id, name)
                    await svc.create_order(name, new_price + up_price)
                log.info(
                    "[UPDATE] %s: %.3f → %.3f TON",
                    name,
                    nano_to_ton(curr_price),
                    nano_to_ton(new_price + up_price),
                )

    async def _cancel_all_orders(self) -> None:
        for name, orders in self._orders_book.snapshot().items():
            for order_id in orders:
                async with self._pool.acquire(Role.ORDERER, key=name) as client:
                    await OrdersService(client).cancel_order(order_id, name)

    async def _notify_new_gifts(self, gifts: List[dict], floor_cols: Dict[str, int]) -> None:
        for gift in gifts:
            col = gift.get("collectionName") or gift.get("collection")
            if col:
                log.debug("Inventory: %s count=%d", col, self._inventory.count(col))


def _calc_order_price(floor_price: int) -> int:
    return int(floor_price / 0.95 - floor_price * 0.1)
