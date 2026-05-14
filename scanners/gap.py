"""Gap Arbitrage Scanner.

Finds collections where a small number of cheaply-priced listings
are followed by a sharp price gap — buying the cheap items and
selling near the gap target can be profitable.

Usage:
    from scanners.gap import GapScanner
    scanner = GapScanner(client, min_floor_ton=5, max_buyout=3, gap_threshold=1.0)
    entries = await scanner.run()
    scanner.print_top(entries)
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

from domain.money import nano_to_ton, ton_to_nano
from services.collections import CollectionsService
from services.feed import FeedService
from services.orders import OrdersService
from transport.client import MarketClient

log = logging.getLogger("mrkt.scanner.gap")


@dataclass
class BuyoutEntry:
    collection: str
    order_price: int
    buyout_gifts: List[dict]
    target_gift: dict

    def _price(self, g: dict) -> int:
        return g.get("salePrice") or g.get("price") or 0

    @property
    def buyout_prices(self) -> List[int]:
        return [self._price(g) for g in self.buyout_gifts]

    @property
    def target_price(self) -> int:
        return self._price(self.target_gift)

    @property
    def avg_buyout(self) -> float:
        p = self.buyout_prices
        return sum(p) / len(p) if p else 0.0

    @property
    def total_cost(self) -> int:
        return sum(self.buyout_prices)

    @property
    def gap_pct(self) -> float:
        last = self.buyout_prices[-1] if self.buyout_prices else 0
        if not last:
            return 0.0
        return (self.target_price / last - 1.0) * 100.0

    @property
    def proximity_pct(self) -> float:
        if not self.avg_buyout:
            return 0.0
        return (self.order_price / self.avg_buyout) * 100.0

    @property
    def score(self) -> float:
        return self.gap_pct * (self.proximity_pct / 100.0)

    def format(self) -> str:
        prices_str = "  |  ".join(f"{nano_to_ton(p):.3f}" for p in self.buyout_prices)
        order_diff = self.proximity_pct - 100.0
        sign = "+" if order_diff >= 0 else ""
        slug = self.collection.replace(" ", "")
        lines = [
            f"[{self.collection}]  x{len(self.buyout_gifts)}  score={self.score:.2f}",
            f"  order       {nano_to_ton(self.order_price):.3f} TON  ({sign}{order_diff:.1f}% vs avg buyout)",
            f"  buyout      [{prices_str}] TON",
            f"  avg buyout  {nano_to_ton(int(self.avg_buyout)):.3f} TON",
            f"  total cost  {nano_to_ton(self.total_cost):.3f} TON",
            f"  target      {nano_to_ton(self.target_price):.3f} TON",
            f"  gap         +{self.gap_pct:.1f}%",
        ]
        for g in self.buyout_gifts:
            num = g.get("number")
            if num:
                lines.append(f"  -> https://t.me/nft/{slug}-{num}")
        return "\n".join(lines)


class GapScanner:
    def __init__(
        self,
        client: MarketClient,
        min_floor_ton: float = 5.0,
        max_buyout: int = 3,
        gap_threshold: float = 1.0,
        top_n: int = 50,
        delay: float = 0.35,
    ) -> None:
        self._client = client
        self._min_floor_nano = ton_to_nano(min_floor_ton)
        self._max_buyout = max_buyout
        self._gap_threshold = gap_threshold
        self._top_n = top_n
        self._delay = delay

    async def run(self) -> List[BuyoutEntry]:
        cols = await self._fetch_filtered_collections()
        orders = await self._fetch_all_orders(cols)
        entries = await self._scan(orders)
        return entries[: self._top_n]

    def print_top(self, entries: List[BuyoutEntry]) -> None:
        sep = "=" * 70
        print(f"\n{sep}")
        print(f"  TOP-{len(entries)} gap arbitrage")
        print(
            f"  floor >= {nano_to_ton(self._min_floor_nano):.1f} TON | "
            f"max buyout x{self._max_buyout} | "
            f"gap >= {self._gap_threshold:.0f}%"
        )
        print(sep)
        for i, e in enumerate(entries, 1):
            print(f"\n#{i:>3}  {e.format()}")
        print(f"\n{sep}\n")

    async def _fetch_filtered_collections(self) -> Dict[str, int]:
        svc = CollectionsService(self._client)
        all_cols = await svc.get_collections()
        filtered = {
            name: floor
            for name, floor in all_cols.items()
            if floor >= self._min_floor_nano and not name.strip().isdigit()
        }
        log.info("Collections passing filter: %d / %d", len(filtered), len(all_cols))
        return filtered

    async def _fetch_all_orders(self, collections: Dict[str, int]) -> Dict[str, int]:
        svc = OrdersService(self._client)
        order_map: Dict[str, int] = {}
        total = len(collections)
        log.info("Fetching top orders for %d collections...", total)

        for i, name in enumerate(collections, 1):
            try:
                price = await svc.get_top_order(name)
                if price:
                    order_map[name] = price
                    log.debug("[%d/%d] %s → %.3f TON", i, total, name, nano_to_ton(price))
                else:
                    log.debug("[%d/%d] %s → no order", i, total, name)
            except Exception:
                log.warning("[%d/%d] %s → error fetching order", i, total, name)
            await asyncio.sleep(self._delay)

        log.info("Orders collected: %d", len(order_map))
        return order_map

    async def _scan(self, order_map: Dict[str, int]) -> List[BuyoutEntry]:
        svc = FeedService(self._client)
        entries: List[BuyoutEntry] = []
        total = len(order_map)

        for i, (name, order_price) in enumerate(order_map.items(), 1):
            try:
                raw = await svc.get_saling_gifts(name)
                gifts = (raw or {}).get("gifts", [])[: self._max_buyout + 1]
            except Exception:
                log.warning("[%d/%d] %s → failed to fetch listings", i, total, name)
                gifts = []

            await asyncio.sleep(self._delay)
            entry = self._find_buyout(name, gifts, order_price)

            if entry is None:
                reason = "not enough listings" if len(gifts) < 2 else f"gap < {self._gap_threshold:.0f}%"
                log.debug("[%d/%d] %s → %s", i, total, name, reason)
            else:
                log.info(
                    "[%d/%d] %s | x%d | gap=+%.1f%% | score=%.2f",
                    i, total, name,
                    len(entry.buyout_gifts),
                    entry.gap_pct,
                    entry.score,
                )
                entries.append(entry)

        entries.sort(key=lambda e: e.score, reverse=True)
        return entries

    def _find_buyout(
        self, name: str, gifts: List[dict], order_price: int
    ) -> Optional[BuyoutEntry]:
        if len(gifts) < 2:
            return None

        prices = [g.get("salePrice") or g.get("price") or 0 for g in gifts]

        for j in range(1, len(prices)):
            prev, curr = prices[j - 1], prices[j]
            if not prev:
                continue
            gap = (curr / prev - 1.0) * 100.0
            if gap >= self._gap_threshold:
                buyout_gifts = gifts[:j]
                if len(buyout_gifts) > self._max_buyout:
                    return None
                return BuyoutEntry(
                    collection=name,
                    order_price=order_price,
                    buyout_gifts=buyout_gifts,
                    target_gift=gifts[j],
                )
        return None
