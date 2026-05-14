import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict, List

log = logging.getLogger("mrkt.bus")

Handler = Callable[[Any], Awaitable[None]]


class EventBus:
    """Simple asyncio pub/sub bus.

    Handlers are launched as fire-and-forget tasks so publish() never blocks.
    Exceptions in handlers are logged and swallowed.
    """

    def __init__(self) -> None:
        self._handlers: Dict[str, List[Handler]] = {}

    def subscribe(self, event_type: str, handler: Handler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    async def publish(self, event_type: str, payload: Any = None) -> None:
        for handler in self._handlers.get(event_type, []):
            asyncio.create_task(self._safe_call(handler, payload))

    async def _safe_call(self, handler: Handler, payload: Any) -> None:
        try:
            await handler(payload)
        except Exception:
            log.exception("Unhandled error in bus handler %s", handler)
