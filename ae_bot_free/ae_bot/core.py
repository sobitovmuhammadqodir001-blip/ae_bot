"""AE Yordamchi: javob yozish, animatsiya va xotira."""
from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from functools import wraps
from contextvars import ContextVar

from aiogram.enums import ChatAction, ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter
from aiogram.types import BufferedInputFile, Message
from openai import AuthenticationError, PermissionDeniedError, RateLimitError

import keyboards
import texts
from ai import AI
from config import Settings
from db import Database, run
from formatting import md_to_html, plain_text, split_markdown
from thinking_animation import ThinkingSpinner as Spinner

log = logging.getLogger("ae.core")
HTML = ParseMode.HTML

EDIT_INTERVAL = 1.1
PREVIEW_LIMIT = 3500

ACTIVE: dict[int, asyncio.Event] = {}
IMAGE_PENDING: set[int] = set()

_last_admin_alert = 0.0
_OPERATION = ContextVar("ae_operation", default=None)


def is_busy(user_id: int) -> bool:
    return user_id in ACTIVE


def request_stop(user_id: int) -> bool:
    event = ACTIVE.get(user_id)

    if event is None:
        return False

    event.set()
    return True


def serialized(fn):
    @wraps(fn)
    async def wrapper(message, *args, **kwargs):
        uid = message.from_user.id
        current = _OPERATION.get()

        if current is not None and current == (
            uid,
            asyncio.current_task(),
        ):
            return await fn(message, *args, **kwargs)

        if uid in ACTIVE:
            await message.answer(
                texts.BUSY,
                parse_mode=HTML,
            )
            return

        ACTIVE[uid] = asyncio.Event()
        token = _OPERATION.set((uid, asyncio.current_task()))

        try:
            return await fn(message, *args, **kwargs)
        finally:
            _OPERATION.reset(token)
            ACTIVE.pop(uid, None)

    return wrapper


async def until_stopped(awaitable, stop):
    work = asyncio.create_task(awaitable)
    signal = asyncio.create_task(stop.wait())

    try:
        done, _ = await asyncio.wait(
            {work, signal},
            return_when=asyncio.FIRST_COMPLETED,
        )

        if signal in done:
            raise asyncio.CancelledError

        return await work

    finally:
        for task in (work, signal):
            if not task.done():
                task.cancel()

        await asyncio.gather(
            work,
            signal,
            return_exceptions=True,
        )


async def edit(
    msg: Message,
    text: str,
    *,
    html: bool = False,
    fallback: str | None = None,
    markup=None,
) -> bool:
    for attempt in range(2):
        try:
            await msg.edit_text(
                text,
                parse_mode=HTML if html else None,
                reply_markup=markup,
            )
            return True

        except TelegramRetryAfter as exc:
            await asyncio.sleep(min(exc.retry_after, 5))
            continue

        except TelegramBadRequest as exc:
            low = str(exc).lower()

            if "not modified" in low:
                return True

            if html and "parse" in low and fallback is not None:
                html, text = False, fallback
                continue

            log.warning("edit_text xatosi: %s", exc)
            return False

        except Exception:
            log.exception("edit_text kutilmagan xato")
            return False

    return False


async def send_md(
    message: Message,
    md_chunk: str,
) -> Message | None:
    try:
        return await message.answer(
            md_to_html(md_chunk),
            parse_mode=HTML,
        )

    except TelegramBadRequest:
        try:
            return await message.answer(
                md_chunk,
                parse_mode=None,
            )
        except Exception:
            log.exception("send_md muvaffaqiyatsiz")
            return None


def _is_admin(cfg: Settings, user_id: int) -> bool:
    return bool(cfg.admin_id) and user_id == cfg.admin_id


async def limit_reached(
    db: Database,
    cfg: Settings,
    user_id: int,
    kind: str,
) -> str | None:
    if _is_admin(cfg, user_id):
        return None

    usage = await run(db.get_usage, user_id)

    if (
        kind == "requests"
        and usage["requests"] >= cfg.daily_requests
    ):
        return texts.LIMIT_REQUESTS

    if (
        kind == "images"
        and usage["images"] >= cfg.daily_images
    ):
        return texts.LIMIT_IMAGES

    if (
        kind == "voice"
        and usage["voice_seconds"] >= cfg.daily_voice_seconds
    ):
        return texts.LIMIT_VOICE

    return None


async def notify_admin(
    message: Message,
    cfg: Settings,
    exc: Exception,
) -> None:
    global _last_admin_alert

    if not cfg.admin_id:
        return

    if not isinstance(
        exc,
        (
            AuthenticationError,
            PermissionDeniedError,
            RateLimitError,
        ),
    ):
        return

    if time.monotonic() - _last_admin_alert < 600:
        return

    _last_admin_alert = time.monotonic()

    with contextlib.suppress(Exception):
        await message.bot.send_message(
            cfg.admin_id,
            f"⚠️ OpenAI xatosi: <code>{type(exc).__name__}</code>\n"
            "Hisobda mablag' tugagan yoki kalit/limit "
            "muammosi bo'lishi mumkin.",
            parse_mode=HTML,
        )


@serialized
async def run_answer(
    message: Message,
    *,
    db: Database,
    ai: AI,
    cfg: Settings,
    stored: str,
    api_content,
    speak: bool = False,
) -> None:
    uid = message.from_user.id

    blocked = await limit_reached(
        db,
        cfg,
        uid,
        "requests",
    )

    if blocked:
        await message.answer(blocked)
        return

    stop = ACTIVE[uid]
    topic_id = await run(db.current_topic, uid)

    await run(
        db.add_message,
        topic_id,
        "user",
        stored,
    )

    await run(
        db.set_title_if_default,
        topic_id,
        stored,
    )

    history = await run(
        db.get_history,
        topic_id,
        cfg.history_messages,
        cfg.history_chars,
    )

    api_messages = (
        [{"role": "system", "content": texts.SYSTEM_PROMPT}]
        + history[:-1]
        + [{"role": "user", "content": api_content}]
    )

    result = await _generate(
        message,
        ai,
        cfg,
        api_messages,
        stop,
    )

    if result is None:
        return

    full, stopped = result

    if full:
        await run(
            db.add_message,
            topic_id,
            "assistant",
            full,
        )

    await run(db.add_usage, uid, requests=1)

    if speak and full and not stopped:
        await _send_voice(message, ai, cfg, full)


async def _generate(
    message: Message,
    ai: AI,
    cfg: Settings,
    api_messages: list,
    stop: asyncio.Event,
):
    live = await message.answer(
        "O‘ylayapman…",
        parse_mode=HTML,
        reply_markup=keyboards.stop_kb(),
    )

    spinner = Spinner(
        live,
        "O'ylayapman",
        keyboards.stop_kb(),
    ).start()

    state = {
        "full": "",
        "last_edit": 0.0,
    }

    gen = ai.stream_chat(api_messages)

    async def consume() -> None:
        async for piece in gen:
            if not piece:
                continue

            if not state["full"]:
                await spinner.stop()

            state["full"] += piece
            now = time.monotonic()

            if now - state["last_edit"] >= EDIT_INTERVAL:
                state["last_edit"] = now
                full = state["full"]

                shown = (
                    full
                    if len(full) <= PREVIEW_LIMIT
                    else "…" + full[-PREVIEW_LIMIT:]
                )

                await edit(
                    live,
                    shown,
                    markup=keyboards.stop_kb(),
                )

    consume_task = asyncio.create_task(consume())
    stop_task = asyncio.create_task(stop.wait())
    stopped = False

    try:
        done, _ = await asyncio.wait(
            {consume_task, stop_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        if consume_task in done:
            stop_task.cancel()
            consume_task.result()

        else:
            stopped = True
            consume_task.cancel()

            with contextlib.suppress(
                asyncio.CancelledError,
                Exception,
            ):
                await consume_task

    except Exception as exc:
        log.exception("Javob yaratishda xato")

        await spinner.stop()
        stop_task.cancel()

        with contextlib.suppress(Exception):
            await gen.aclose()

        await edit(live, texts.ERROR)
        await notify_admin(message, cfg, exc)
        return None

    finally:
        for task in (consume_task, stop_task):
            if not task.done():
                task.cancel()

        await asyncio.gather(
            consume_task,
            stop_task,
            return_exceptions=True,
        )

        await spinner.stop()

        with contextlib.suppress(Exception):
            await gen.aclose()

    full = state["full"].strip()
    footer = "\n\n" + texts.STOPPED if stopped else ""

    if not full:
        await edit(
            live,
            texts.STOPPED if stopped else texts.ERROR,
            html=True,
        )
        return ("", stopped)

    chunks = split_markdown(full)
    first_html = md_to_html(chunks[0])

    if len(chunks) == 1:
        first_html += footer

    await edit(
        live,
        first_html,
        html=True,
        fallback=chunks[0],
    )

    for index, chunk in enumerate(chunks[1:], start=2):
        sent = await send_md(message, chunk)

        if sent is None:
            break

        if index == len(chunks) and stopped:
            await edit(
                sent,
                md_to_html(chunk) + footer,
                html=True,
                fallback=chunk,
            )

    return (full, stopped)


async def _send_voice(
    message: Message,
    ai: AI,
    cfg: Settings,
    full: str,
) -> None:
    text = plain_text(full, cfg.tts_max_chars)

    if not text:
        return

    try:
        await message.bot.send_chat_action(
            message.chat.id,
            ChatAction.RECORD_VOICE,
        )

        audio, name = await ai.tts(text)

        await message.answer_voice(
            BufferedInputFile(
                audio,
                filename=name,
            )
        )

    except Exception:
        log.exception(
            "Ovozli javob yuborilmadi; matn yuborilgan."
        )
