"""AE kutish animatsiyasi."""
from pathlib import Path
import asyncio
import contextlib
import logging

from aiogram.types import FSInputFile
import texts

log = logging.getLogger(__name__)

GIF_PATH = Path(__file__).resolve().with_name("AE_logo_rotate.gif")
GIF_CACHE = {}

PHASES = (
    "O‘",
    "O‘yl",
    "O‘ylay",
    "O‘ylayap",
    "O‘ylayapman",
    "O‘ylayapman.",
    "O‘ylayapman..",
    "O‘ylayapman…",
    "O‘ylayapman",
    "O‘ylayap",
    "O‘ylay",
    "O‘yl",
    "O‘",
)


class ThinkingSpinner:
    def __init__(self, msg, label, markup=None):
        self.msg = msg
        self.label = label
        self.markup = markup
        self._task = None
        self._gif = None

    def start(self):
        self._task = asyncio.create_task(self._run())
        return self

    async def _run(self):
        from core import edit

        thinking = self.label in (
            "O‘ylayapman",
            "O'ylayapman",
        )

        try:
            if thinking and GIF_PATH.is_file():
                try:
                    source = GIF_CACHE.get(self.msg.bot.id)

                    if source is None:
                        source = FSInputFile(GIF_PATH)

                    self._gif = await self.msg.bot.send_animation(
                        chat_id=self.msg.chat.id,
                        animation=source,
                        message_thread_id=getattr(
                            self.msg,
                            "message_thread_id",
                            None,
                        ),
                        disable_notification=True,
                    )

                    if self._gif.animation:
                        GIF_CACHE[self.msg.bot.id] = (
                            self._gif.animation.file_id
                        )

                except Exception:
                    log.warning(
                        "AE GIF yuborilmadi",
                        exc_info=True,
                    )

            tick = 0

            while True:
                if thinking:
                    text = PHASES[tick % len(PHASES)]
                else:
                    text = texts.spin_text(
                        self.label,
                        tick,
                        tick,
                    )

                await edit(
                    self.msg,
                    text,
                    html=not thinking,
                    markup=self.markup,
                )

                tick += 1
                await asyncio.sleep(1.2)

        finally:
            if self._gif is not None:
                try:
                    await self._gif.delete()
                except Exception:
                    log.warning(
                        "AE GIF o‘chirilmadi",
                        exc_info=True,
                    )

                self._gif = None

    async def stop(self):
        if self._task is None:
            return

        task, self._task = self._task, None
        task.cancel()

        with contextlib.suppress(
            asyncio.CancelledError,
            Exception,
        ):
            await task
