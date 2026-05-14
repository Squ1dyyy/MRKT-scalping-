import asyncio
import logging
from typing import Dict, List

from bootstrap.settings import Settings
from domain.money import nano_to_ton, ton_to_nano
from integrations.telegram import TelegramNotifier
from pool.account import Role
from pool.pool import AccountPool
from services.feed import FeedService
from services.orders import OrdersService
from services.trading import TradingService
from state.balance import BalanceTracker
from state.inventory import InventoryStore

log = logging.getLogger("mrkt.strategy.feed_sniper")


def _format_gift(gift: dict, session: int) -> str:
    col = gift.get("name", "Unknown")
    return (
        f"SESSION #{session}\n"
        f"🎁 Gift #{gift.get('id', '?')}\n"
        f"Модель: {gift.get('modelName')} ({gift.get('modelRarityPerMille')}%)\n"
        f"Коллекция: {col}\n"
        f"Фон: {gift.get('backdropName')} ({gift.get('backdropRarityPerMille')}%)"
        f" | Символ: {gift.get('symbolName')} ({gift.get('symbolRarityPerMille')}%)\n"
        f"Цена покупки: {nano_to_ton(gift.get('amount', 0))} TON"
    )


class FeedSniperStrategy:
    """Watches live feed and instantly buys gifts trading below the best order price.

    Distinct from the order strategy — this is event-driven instant buying
    from the feed, not order-book management.
    """

    def __init__(
        self,
        pool: AccountPool,
        balance: BalanceTracker,
        inventory: InventoryStore,
        settings: Settings,
        notifier: TelegramNotifier,
        session_num: int = 0,
    ) -> None:
        self._pool = pool
        self._balance = balance
        self._inventory = inventory
        self._settings = settings
        self._notifier = notifier
        self._session_num = session_num

    async def run(self) -> None:
        log.info("Feed sniper started")
        scale = 1 - self._settings.profit_percent

        while True:
            try:
                await self._cycle(scale)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Feed sniper cycle failed")
            await asyncio.sleep(2)

    async def _cycle(self, scale: float) -> None:
        min_nano = ton_to_nano(self._settings.min_price_ton)
        max_nano = min(
            ton_to_nano(self._settings.max_price_ton),
            self._balance.current,
        )

        async with self._pool.acquire(Role.SCANNER) as client:
            feed = await FeedService(client).get_feed(min_price=min_nano, max_price=max_nano)

        # Build proposed orders map for all feed collections
        proposed_orders: Dict[str, int] = {}
        for name in feed:
            if name.strip().isdigit():
                continue
            try:
                async with self._pool.acquire(Role.SCANNER, key=name) as client:
                    price = await OrdersService(client).get_top_order(name)
                if price:
                    proposed_orders[name] = price
            except Exception:
                pass

        buy_queue: List[dict] = []

        for name, gifts in feed.items():
            if name.strip().isdigit():
                continue

            max_order = proposed_orders.get(name, 0)
            if max_order == 0:
                continue

            for gift in gifts:
                if gift["amount"] <= max_order * scale:
                    diff = max_order - gift["amount"]
                    diff_pct = diff / max_order * 100 if max_order else 0
                    log.info(
                        "✅ %s id=%s price=%.3f diff=%.3f (%.2f%%)",
                        name,
                        gift.get("id"),
                        nano_to_ton(gift["amount"]),
                        nano_to_ton(diff),
                        diff_pct,
                        extra={"collection": name},
                    )
                    buy_queue.append(gift)

        if not buy_queue:
            return

        log.info("Feed sniper: %d gifts to buy", len(buy_queue))

        tasks = []
        for gift in buy_queue:
            gid = gift.get("id")
            amt = gift.get("amount")
            if gid is None or amt is None:
                continue
            tasks.append(self._buy(gift))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for gift, result in zip(buy_queue, results):
            if isinstance(result, Exception):
                log.error("Buy failed for %s: %s", gift.get("id"), result)
            elif result:
                text = _format_gift(gift, self._session_num)
                await self._notifier.send(text)

    async def _buy(self, gift: dict) -> bool:
        gid = gift["id"]
        amt = gift["amount"]
        if not await self._balance.debit(amt):
            log.warning("Insufficient balance for id=%s amt=%.3f", gid, nano_to_ton(amt))
            return False
        async with self._pool.acquire(Role.BUYER) as client:
            result = await TradingService(client).buy_gift(gid, amt)
        if result:
            return True
        await self._balance.credit(amt)  # refund on failure
        return False
