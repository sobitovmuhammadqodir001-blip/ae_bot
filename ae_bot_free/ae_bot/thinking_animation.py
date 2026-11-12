"""AE GIF avval, kutish matni keyin. Kalitlar bu faylda yo'q."""
from pathlib import Path
import asyncio
import contextlib
import logging
import time

from aiogram.types import FSInputFile
import texts

log = logging.getLogger(__name__)
GIF_PATH = Path(__file__).resolve().with_name("AE_logo_rotate.gif")
GIF_CACHE = {}
PHASES = (
    "O‘", "O‘yl", "O‘ylay", "O‘ylayap", "O‘ylayapman",
    "O‘ylayapman.", "O‘ylayapman..", "O‘ylayapman…",
    "O‘ylayapman", "O‘ylayap", "O‘ylay", "O‘yl", "O‘",
)


class ThinkingSpinner:
    def __init__(self, msg, label, markup=None):
        self.msg, self.label, self.markup = msg, label, markup
        self._task = None
        self._gif = None

    @classmethod
    async def create(cls, message, markup=None):
        """GIF va kutish matnini aynan shu tartibda yuboradi."""
        gif = None
        if GIF_PATH.is_file():
            try:
                source = GIF_CACHE.get(message.bot.id)
                if source is None:
                    source = FSInputFile(GIF_PATH)
                gif = await message.bot.send_animation(
                    chat_id=message.chat.id,
                    animation=source,
                    message_thread_id=getattr(message, "message_thread_id", None),
                    disable_notification=True,
                    request_timeout=15,
                )
                if gif.animation:
                    GIF_CACHE[message.bot.id] = gif.animation.file_id
            except Exception:
                GIF_CACHE.pop(message.bot.id, None)
                log.warning("AE GIF yuborilmadi", exc_info=True)
        else:
            log.warning("AE_logo_rotate.gif topilmadi: %s", GIF_PATH)

        try:
            live = await message.answer("O‘ylayapman…", reply_markup=markup)
        except BaseException:
            if gif is not None:
                with contextlib.suppress(Exception):
                    await gif.delete()
            raise
        spinner = cls(live, "O'ylayapman", markup)
        spinner._gif = gif
        spinner.start()
        return live, spinner

    def start(self):
        if self._task is None:
            self._task = asyncio.create_task(self._run())
        return self

    async def _run(self):
        from core import edit
        tick = 0
        started = time.monotonic()
        thinking = self.label in ("O'ylayapman", "O‘ylayapman")
        while True:
            await asyncio.sleep(1.2)
            text = (PHASES[tick % len(PHASES)] if thinking else
                    texts.spin_text(self.label, tick, int(time.monotonic()-started)))
            await edit(self.msg, text, html=not thinking, markup=self.markup)
            tick += 1

    async def stop(self):
        if self._task is not None:
            task, self._task = self._task, None
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        if self._gif is not None:
            gif, self._gif = self._gif, None
            try:
                await gif.delete()
            except Exception:
                log.warning("AE GIF o‘chirilmadi", exc_info=True)
