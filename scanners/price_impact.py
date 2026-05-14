"""Price-Impact / Floor-Pump Analyzer.

Simulates buying N cheapest listings and computes the profit from
selling them at the new floor price (after the buyout).

Usage:
    from scanners.price_impact import PriceImpactAnalyzer
    analyzer = PriceImpactAnalyzer(client, portals_client=portals)
    results = await analyzer.analyze(max_price_ton=20, max_budget_ton=400)
"""

import asyncio
import logging
from typing import Dict, List, Optional, Tuple

from domain.money import nano_to_ton, ton_to_nano
from integrations.portals import PortalsClient
from services.collections import CollectionsService
from services.feed import FeedService
from transport.client import MarketClient

log = logging.getLogger("mrkt.scanner.price_impact")


class PriceImpactAnalyzer:
    def __init__(
        self,
        client: MarketClient,
        portals: Optional[PortalsClient] = None,
    ) -> None:
        self._client = client
        self._portals = portals

    async def analyze(
        self,
        delay: float = 1.0,
        sell_discount: float = 0.04,
        max_price_ton: float = 20.0,
        top_n: int = 5,
        max_budget_ton: float = 400.0,
        max_items: int = 19,
        collections_filter: Optional[List[str]] = None,
    ) -> Dict[str, dict]:
        all_cols = await CollectionsService(self._client).get_collections()

        collections = (
            [c for c in all_cols if c in collections_filter]
            if collections_filter
            else list(all_cols.keys())
        )

        portals_floors: Dict[str, float] = {}
        if self._portals:
            try:
                raw = await self._portals.get_collections()
                portals_floors = {k: round(nano_to_ton(v), 3) for k, v in raw.items()}
            except Exception:
                log.warning("Portals unavailable for price-impact analysis")

        result: Dict[str, dict] = {}
        feed_svc = FeedService(self._client)

        for i, name in enumerate(collections, 1):
            floor_nano = all_cols.get(name, 0)
            if max_price_ton and nano_to_ton(floor_nano) > max_price_ton:
                continue

            log.info("[%d/%d] %s", i, len(collections), name)
            items: List[dict] = []
            cursor = ""
            need = max_items + 1

            while len(items) < need:
                data = await feed_svc.get_saling_gifts(name, cursor)
                if not data:
                    break
                gifts = data.get("gifts", [])
                if not gifts:
                    break
                items.extend(gifts)
                cursor = data.get("cursor", "")
                if not cursor:
                    break
                await asyncio.sleep(delay)

            if not items:
                continue

            opt = self._find_optimal(items, sell_discount, max_price_ton, top_n, max_budget_ton, max_items)
            result[name] = {
                "current_floor_ton": nano_to_ton(items[0].get("salePrice", 0)),
                "portals_floor_ton": portals_floors.get(name),
                "items_available": len(items),
                "optimal": opt,
            }
            await asyncio.sleep(delay)

        self._print_summary(result, top_n)
        return result

    def _calc_impact(
        self,
        items: list,
        buy_count: int,
        sell_discount: float,
        max_price_ton: Optional[float],
    ) -> Optional[dict]:
        filtered = items
        if max_price_ton:
            max_nano = ton_to_nano(max_price_ton)
            filtered = [g for g in items if g.get("salePrice", 0) <= max_nano]

        if len(filtered) <= buy_count:
            return None

        current_floor = filtered[0].get("salePrice", 0)
        to_buy = filtered[:buy_count]
        total_spend = sum(g.get("salePrice", 0) for g in to_buy)
        new_floor = filtered[buy_count].get("salePrice", 0)

        floor_change = new_floor - current_floor
        floor_change_pct = floor_change / current_floor * 100 if current_floor else None
        sell_price = new_floor * (1 - sell_discount)
        total_revenue = sell_price * buy_count
        profit = total_revenue - total_spend
        avg_buy = total_spend / buy_count

        return {
            "floor_change_ton": round(nano_to_ton(floor_change), 3),
            "floor_change_pct": round(floor_change_pct, 2) if floor_change_pct is not None else None,
            "total_spend_ton": round(nano_to_ton(total_spend), 3),
            "new_floor_ton": round(nano_to_ton(new_floor), 3),
            "sell_price_ton": round(nano_to_ton(sell_price), 3),
            "total_revenue_ton": round(nano_to_ton(total_revenue), 3),
            "profit_ton": round(nano_to_ton(profit), 3),
            "profit_no_discount_ton": round(nano_to_ton(total_revenue / (1 - sell_discount) - total_spend), 3),
            "avg_buy_price_ton": round(nano_to_ton(avg_buy), 3),
        }

    def _find_optimal(
        self,
        items: list,
        sell_discount: float,
        max_price_ton: Optional[float],
        top_n: int,
        max_budget_ton: Optional[float],
        max_items: Optional[int],
    ) -> dict:
        all_impacts: List[Tuple[int, dict]] = []
        limit = min(len(items), (max_items or len(items)) + 1)

        for count in range(1, limit):
            imp = self._calc_impact(items, count, sell_discount, max_price_ton)
            if imp is None:
                continue
            if max_budget_ton and imp["total_spend_ton"] > max_budget_ton:
                break
            all_impacts.append((count, imp))

        if not all_impacts:
            return {"best": None, "best_count": None, "top": [], "all_impacts": []}

        best_count, best = max(all_impacts, key=lambda x: x[1]["profit_ton"])
        top_sorted = sorted(all_impacts, key=lambda x: x[1]["profit_ton"], reverse=True)[:top_n]

        return {
            "best": best,
            "best_count": best_count,
            "top": [{"count": c, **imp} for c, imp in top_sorted],
            "all_impacts": all_impacts,
        }

    def _print_summary(self, result: Dict[str, dict], top_n: int) -> None:
        top: List[dict] = []
        for name, info in result.items():
            best = info["optimal"]["best"]
            if best:
                top.append({"collection": name, "count": info["optimal"]["best_count"], **best})

        top.sort(key=lambda x: x["profit_ton"], reverse=True)

        sep = "=" * 60
        print(f"\n{sep}")
        print(f"{'TOP-20 COLLECTIONS BY PROFIT':^60}")
        print(sep)
        for rank, entry in enumerate(top[:20], 1):
            sign = "+" if entry["profit_ton"] >= 0 else ""
            print(
                f"\n  {rank}. {entry['collection']}\n"
                f"     Buyout   : {entry['count']} items\n"
                f"     Spend    : {entry['total_spend_ton']} TON\n"
                f"     Profit   : {sign}{entry['profit_ton']} TON"
            )
        print(f"\n{sep}")
