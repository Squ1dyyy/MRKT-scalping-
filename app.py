import asyncio
import logging
import time
from datetime import timedelta
from typing import List, Optional

from bootstrap.accounts import load_accounts
from bootstrap.logging import setup_logging
from bootstrap.settings import Settings
from integrations.portals import PortalsClient
from integrations.telegram import TelegramNotifier
from pool.account import Role
from pool.pool import AccountPool
from services.wallet import WalletService
from state.balance import BalanceTracker
from state.inventory import InventoryStore
from state.offers_book import OffersBook
from state.orders_book import OrdersBook
from strategies.decline_offers import DeclineOffersStrategy
from strategies.feed_sniper import FeedSniperStrategy
from strategies.offers import OfferStrategy
from strategies.orders import OrderStrategy

log = logging.getLogger("mrkt.app")


class Application:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._tasks: List[asyncio.Task] = []
        self._is_running = False
        self._start_time: float = 0.0

        # Shared state
        self._balance = BalanceTracker()
        self._orders_book = OrdersBook()
        self._offers_book = OffersBook()
        self._inventory = InventoryStore()

        self._pool: Optional[AccountPool] = None
        self._portals: Optional[PortalsClient] = None
        self._notifier: Optional[TelegramNotifier] = None
        self._session_num = settings.current_session()

    async def run(self) -> None:
        setup_logging(self._settings.log_level, self._settings.log_file)
        log.info("Starting MRKT bot (session #%d)", self._session_num)

        accounts = load_accounts(self._settings.accounts_file)
        self._pool = AccountPool(accounts)
        await self._pool.start()

        if not self._settings.skip_portals:
            self._portals = PortalsClient(auth=self._settings.auth_portals or None)
            await self._portals.start()
            await self._portals.init()
            if not self._settings.auth_portals:
                log.info("Portals running in read-only mode (no AUTH_PORTALS)")

        self._notifier = TelegramNotifier(
            token=self._settings.bot_token,
            chat_id=self._settings.bot_chat_id,
            channel=self._settings.bot_channel,
            start_cb=self._start_strategies,
            stop_cb=self._stop_strategies,
        )
        await self._notifier.start()

        # Initial balance fetch
        async with self._pool.acquire(Role.WALLET) as client:
            hard, locked = await WalletService(client).get_balance()
        await self._balance.update(hard, locked)

        await self._notifier.send(f"Session #{self._session_num} started")

        try:
            await self._start_strategies()
            await self._notifier.dp.start_polling()
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await self._shutdown()

    async def _start_strategies(self) -> List[asyncio.Task]:
        if self._is_running:
            log.warning("Strategies already running")
            return self._tasks

        assert self._pool is not None
        assert self._notifier is not None

        self._start_time = time.perf_counter()
        self._is_running = True

        balance_task = asyncio.create_task(self._balance_loop(), name="balance_loop")

        order_strategy = OrderStrategy(
            pool=self._pool,
            orders_book=self._orders_book,
            balance=self._balance,
            inventory=self._inventory,
            portals=self._portals,
            settings=self._settings,
            notifier=self._notifier,
            session_num=self._session_num,
        )
        offer_strategy = OfferStrategy(
            pool=self._pool,
            balance=self._balance,
            portals=self._portals,
            settings=self._settings,
        )
        feed_strategy = FeedSniperStrategy(
            pool=self._pool,
            balance=self._balance,
            inventory=self._inventory,
            settings=self._settings,
            notifier=self._notifier,
            session_num=self._session_num,
        )
        decline_strategy = DeclineOffersStrategy(
            pool=self._pool,
            offers_book=self._offers_book,
            balance=self._balance,
            settings=self._settings,
        )

        self._tasks = [
            balance_task,
            asyncio.create_task(order_strategy.run(), name="order_strategy"),
            asyncio.create_task(offer_strategy.run(), name="offer_strategy"),
            asyncio.create_task(feed_strategy.run(), name="feed_sniper"),
            asyncio.create_task(decline_strategy.run(), name="decline_offers"),
        ]

        log.info("All strategies started (%d tasks)", len(self._tasks))
        return self._tasks

    async def _stop_strategies(self) -> None:
        if not self._is_running:
            return
        for task in self._tasks:
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks = []
        self._is_running = False

        await self._report_session()
        log.info("All strategies stopped")

    async def _shutdown(self) -> None:
        await self._stop_strategies()
        if self._pool:
            await self._pool.close()
        if self._portals:
            await self._portals.close()
        if self._notifier:
            await self._notifier.stop()
        log.info("Application shut down")

    async def _balance_loop(self) -> None:
        assert self._pool is not None
        while True:
            try:
                async with self._pool.acquire(Role.WALLET) as client:
                    hard, locked = await WalletService(client).get_balance()
                await self._balance.update(hard, locked)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Balance update failed")
            await asyncio.sleep(10)

    async def _report_session(self) -> None:
        assert self._notifier is not None
        elapsed_s = time.perf_counter() - self._start_time
        elapsed = timedelta(seconds=int(elapsed_s))
        h, rem = divmod(int(elapsed.total_seconds()), 3600)
        m, s = divmod(rem, 60)
        time_str = f"{h:02}:{m:02}:{s:02}"

        self._settings.increment_session()
        await self._notifier.send(
            f"SESSION #{self._session_num} ended\n"
            f"TIME: {time_str}\n"
            f"Balance: {self._balance.current / 1e9:.3f} TON"
        )
