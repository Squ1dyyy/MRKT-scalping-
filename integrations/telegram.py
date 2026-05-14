import asyncio
import logging
from typing import Awaitable, Callable, List, Optional

from aiogram import Bot, Dispatcher, types

log = logging.getLogger("mrkt.tg")

StartCallback = Callable[[], Awaitable[List[asyncio.Task]]]
StopCallback = Callable[[], Awaitable[None]]


class TelegramNotifier:
    """Single-instance Telegram bot with a message queue to prevent flood bans.

    Messages are enqueued via send() and drained by a background task with
    a small inter-message delay.
    """

    def __init__(
        self,
        token: str,
        chat_id: int,
        channel: str,
        *,
        start_cb: Optional[StartCallback] = None,
        stop_cb: Optional[StopCallback] = None,
    ) -> None:
        self._chat_id = chat_id
        self._channel = channel
        self._start_cb = start_cb
        self._stop_cb = stop_cb
        self._queue: "asyncio.Queue[str]" = asyncio.Queue()
        self._drain_task: Optional[asyncio.Task] = None

        self.bot = Bot(token=token)
        self.dp = Dispatcher(self.bot)
        self._register_handlers()

    def _register_handlers(self) -> None:
        @self.dp.message_handler(commands=["start"])
        async def cmd_start(message: types.Message) -> None:
            if message.chat.id != self._chat_id:
                return
            if self._start_cb is None:
                await message.answer("No start callback registered.")
                return
            try:
                await self._start_cb()
                await message.answer("Started")
            except Exception:
                log.exception("Start callback failed")
                await message.answer("Failed to start")

        @self.dp.message_handler(commands=["stop"])
        async def cmd_stop(message: types.Message) -> None:
            if message.chat.id != self._chat_id:
                return
            if self._stop_cb is None:
                await message.answer("No stop callback registered.")
                return
            try:
                await self._stop_cb()
                await message.answer("Stopped. Cancelling orders...")
            except Exception:
                log.exception("Stop callback failed")
                await message.answer("Failed to stop")

        @self.dp.message_handler(commands=["balance"])
        async def cmd_balance(message: types.Message) -> None:
            if message.chat.id != self._chat_id:
                return
            await message.answer("Use /start to run the bot first.")

    async def start(self) -> None:
        self._drain_task = asyncio.create_task(self._drain_loop())
        log.info("TelegramNotifier started (chat_id=%d)", self._chat_id)

    async def stop(self) -> None:
        if self._drain_task:
            self._drain_task.cancel()
            try:
                await self._drain_task
            except asyncio.CancelledError:
                pass
        session = await self.bot.get_session()
        if session:
            await session.close()
        log.info("TelegramNotifier stopped")

    async def send(self, text: str) -> None:
        await self._queue.put(text)

    async def _drain_loop(self) -> None:
        while True:
            text = await self._queue.get()
            try:
                await self.bot.send_message(self._chat_id, text)
                if self._channel:
                    await self.bot.send_message(self._channel, text)
            except Exception:
                log.exception("Failed to send TG message")
            finally:
                self._queue.task_done()
            await asyncio.sleep(0.05)
