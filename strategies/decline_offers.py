import asyncio
import logging
from datetime import datetime, timezone

from bootstrap.settings import Settings
from pool.account import Role
from pool.pool import AccountPool
from services.activities import ActivitiesService
from services.offers import OffersService
from state.balance import BalanceTracker
from state.offers_book import OffersBook

log = logging.getLogger("mrkt.strategy.decline_offers")


class DeclineOffersStrategy:
    """Two jobs in one:

    1. Sync own-offer state from activities into OffersBook.
    2. Decline incoming foreign offers on our listed gifts.
    3. Cancel own offers that have been open longer than `offer_expire_minutes`.
    """

    def __init__(
        self,
        pool: AccountPool,
        offers_book: OffersBook,
        balance: BalanceTracker,
        settings: Settings,
    ) -> None:
        self._pool = pool
        self._offers_book = offers_book
        self._balance = balance
        self._settings = settings

    async def run(self) -> None:
        log.info("Decline-offers strategy started")
        while True:
            try:
                await self._cycle()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Decline-offers cycle failed")
            await asyncio.sleep(5)

    async def _cycle(self) -> None:
        # Sync activities
        async with self._pool.acquire(Role.WALLET) as client:
            snapshot = await ActivitiesService(client).fetch_all()

        # Decline foreign offers
        if snapshot.foreign_offer_ids:
            async with self._pool.acquire(Role.OFFERER) as client:
                svc = OffersService(client)
                for oid in snapshot.foreign_offer_ids:
                    await svc.decline_offer(oid)

        # Update offers book from activities
        offers_dict = {
            o.id: (o.created_at, o.price_nano)
            for o in snapshot.own_offers
        }
        await self._offers_book.replace_all(offers_dict)

        # Cancel expired own offers
        now = datetime.now(timezone.utc)
        expired = self._offers_book.expired(now, self._settings.offer_expire_minutes)
        if expired:
            log.info("Cancelling %d expired offers", len(expired))
            async with self._pool.acquire(Role.OFFERER) as client:
                svc = OffersService(client)
                for oid in expired:
                    price = await self._offers_book.remove(oid)
                    await svc.cancel_offer(oid)
                    if price:
                        await self._balance.credit(price)
                        log.info("Cancelled offer %s, credited %.3f TON", oid, price / 1e9)
