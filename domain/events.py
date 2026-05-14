from datetime import datetime
from typing import List, Literal, Optional, Union
from pydantic import BaseModel, ValidationError

from domain.models import Gift, OrderActivity


class OrderEvent(BaseModel):
    type: Literal["order"]
    order: OrderActivity
    date: datetime


class SellEvent(BaseModel):
    type: Literal["sell"]
    gift: Gift
    price: int
    date: datetime


class BuyEvent(BaseModel):
    type: Literal["buy"]
    gift: Gift
    price: int
    date: datetime


class IncomeEvent(BaseModel):
    type: Literal["income"]
    amount: int
    date: datetime


class WithdrawEvent(BaseModel):
    type: Literal["withdraw"]
    amount: int
    date: datetime
    status: str
    historyId: str


class CashbackEvent(BaseModel):
    type: Literal["cashback"]
    amount: int
    date: datetime


class DeclineOfferEvent(BaseModel):
    type: Literal["decline_offer"]
    gift: Gift
    price: int
    date: datetime


HistoryEvent = Union[
    OrderEvent,
    SellEvent,
    BuyEvent,
    IncomeEvent,
    WithdrawEvent,
    CashbackEvent,
    DeclineOfferEvent,
]

_EVENT_MAP = {
    "order": OrderEvent,
    "sell": SellEvent,
    "buy": BuyEvent,
    "income": IncomeEvent,
    "withdraw": WithdrawEvent,
    "cashback": CashbackEvent,
    "decline_offer": DeclineOfferEvent,
}


def parse_history_events(raw: list) -> List[HistoryEvent]:
    import logging
    log = logging.getLogger("mrkt.domain.events")
    events: List[HistoryEvent] = []
    for item in raw:
        event_type = item.get("type")
        cls = _EVENT_MAP.get(event_type)
        if cls is None:
            log.debug("Unknown event type: %s", event_type)
            continue
        try:
            events.append(cls(**item))
        except ValidationError:
            log.warning("Failed to parse %s event", event_type, exc_info=True)
    return events
