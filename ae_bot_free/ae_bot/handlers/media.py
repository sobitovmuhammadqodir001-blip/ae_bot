"""Ovoz, rasm, fayl va rasm yaratish bilan bog'liq ishlar (handlerlar chat.py da chaqiradi)."""
from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
import os
from io import BytesIO

from aiogram.enums import ParseMode
from aiogram.types import BufferedInputFile, Message
from openai import BadRequestError

import core
import docs
import texts
from ai import AI
from config import Settings
from db import Database, run

log = logging.getLogger("ae.media")
HTML = ParseMode.HTML


async def _download(message: Message, file_obj) -> bytes:
    buf = BytesIO()
    await message.bot.download(file_obj, destination=buf)
    return buf.getvalue()


# ------------------------------------------------------------------ OVOZ
@core.serialized
async def handle_voice(message: Message, *, db: Database, ai: AI, cfg: Settings) -> None:
    uid = message.from_user.id
    voice = message.voice
    if voice.duration > cfg.max_voice_seconds:
        await message.answer(texts.VOICE_TOO_LONG.format(sec=cfg.max_voice_seconds))
        return
    if voice.file_size and voice.file_size > cfg.max_file_mb * 1024 * 1024:
        await message.answer(texts.FILE_TOO_BIG.format(mb=cfg.max_file_mb))
        return
    for kind in ("voice", "requests"):
        blocked = await core.limit_reached(db, cfg, uid, kind)
        if blocked:
            await message.answer(blocked)
            return

    if not core._is_admin(cfg, uid):
        usage = await run(db.get_usage, uid)
        if usage["voice_seconds"] + voice.duration > cfg.daily_voice_seconds:
            await message.answer(texts.LIMIT_VOICE)
            return

    status = await message.answer(texts.spin_text("Ovozni eshityapman", 0, 0), parse_mode=HTML)
    spinner = core.Spinner(status, "Ovozni eshityapman").start()
    text = ""
    try:
        data = await _download(message, voice)
        text = await ai.transcribe(data, "voice.ogg")
    except Exception as exc:
        log.exception("Ovozni matnga aylantirishda xato")
        await spinner.stop()
        await core.edit(status, texts.ERROR)
        await core.notify_admin(message, cfg, exc)
        return
    finally:
        await spinner.stop()

    if not text:
        await core.edit(status, texts.VOICE_FAIL)
        return

    await run(db.add_usage, uid, voice_seconds=int(voice.duration))
    await core.edit(status, f"🎙 <i>«{texts.e(text)}»</i>", html=True, fallback=f"🎙 «{text}»")

    user = await run(db.get_user, uid)
    await core.run_answer(
        message, db=db, ai=ai, cfg=cfg,
        stored=text, api_content=text, speak=bool(user["voice_reply"]),
    )


# ------------------------------------------------------------------ RASM (tahlil)
@core.serialized
async def handle_photo(message: Message, *, db: Database, ai: AI, cfg: Settings) -> None:
    uid = message.from_user.id
    photo = message.photo[-1]
    if photo.file_size and photo.file_size > cfg.max_file_mb * 1024 * 1024:
        await message.answer(texts.FILE_TOO_BIG.format(mb=cfg.max_file_mb))
        return
    try:
        data = await _download(message, photo)
    except Exception:
        log.exception("Rasmni yuklab olishda xato")
        await message.answer(texts.ERROR)
        return
    await _answer_with_image(message, data, "image/jpeg", db=db, ai=ai, cfg=cfg)


async def _answer_with_image(message: Message, data: bytes, mime: str, *, db: Database, ai: AI, cfg: Settings):
    caption = (message.caption or "").strip() or texts.DEFAULT_PHOTO_PROMPT
    b64 = base64.b64encode(data).decode()
    content = [
        {"type": "text", "text": caption},
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
    ]
    await core.run_answer(
        message, db=db, ai=ai, cfg=cfg,
        stored=f"🖼 [Rasm yuborildi] {caption}", api_content=content,
    )


# ------------------------------------------------------------------ FAYL
@core.serialized
async def handle_document(message: Message, *, db: Database, ai: AI, cfg: Settings) -> None:
    uid = message.from_user.id
    doc = message.document
    if doc.file_size and doc.file_size > cfg.max_file_mb * 1024 * 1024:
        await message.answer(texts.FILE_TOO_BIG.format(mb=cfg.max_file_mb))
        return

    mime = (doc.mime_type or "").lower()
    name = doc.file_name or "fayl"
    ext = os.path.splitext(name)[1].lower()

    # Rasm "fayl" qilib yuborilgan bo'lsa (skrinshot) - rasm sifatida tahlil qilamiz
    if mime in ("image/jpeg", "image/png", "image/webp", "image/gif"):
        try:
            data = await _download(message, doc)
        except Exception:
            log.exception("Rasm-faylni yuklab olishda xato")
            await message.answer(texts.ERROR)
            return
        await _answer_with_image(message, data, mime, db=db, ai=ai, cfg=cfg)
        return

    status = await message.answer(texts.spin_text("Faylni o'qiyapman", 0, 0), parse_mode=HTML)
    spinner = core.Spinner(status, "Faylni o'qiyapman").start()
    try:
        data = await _download(message, doc)
        text = await asyncio.to_thread(docs.extract_text, data, ext, cfg.max_doc_chars)
    except docs.FileProblem as problem:
        await spinner.stop()
        msg = {
            "unsupported": texts.FILE_UNSUPPORTED,
            "old": texts.FILE_OLD,
            "empty": texts.FILE_EMPTY,
            "encrypted": texts.FILE_ENCRYPTED,
        }.get(problem.code, texts.FILE_FAIL)
        await core.edit(status, msg)
        return
    except Exception:
        log.exception("Faylni o'qishda xato")
        await spinner.stop()
        await core.edit(status, texts.FILE_FAIL)
        return
    finally:
        await spinner.stop()

    with contextlib.suppress(Exception):
        await status.delete()

    instruction = (message.caption or "").strip() or texts.DEFAULT_DOC_PROMPT
    full = f"{instruction}\n\n📎 Fayl: {name}\n\n{text}"
    await core.run_answer(
        message, db=db, ai=ai, cfg=cfg,
        stored=full, api_content=full,
    )


# ------------------------------------------------------------------ RASM YARATISH
@core.serialized
async def make_image(message: Message, prompt: str, *, db: Database, ai: AI, cfg: Settings) -> None:
    uid = message.from_user.id
    blocked = await core.limit_reached(db, cfg, uid, "images")
    if blocked:
        await message.answer(blocked)
        return

    status = await message.answer(texts.spin_text("Rasm chizyapman", 0, 0), parse_mode=HTML, reply_markup=core.keyboards.stop_kb())
    spinner = core.Spinner(status, "Rasm chizyapman", core.keyboards.stop_kb()).start()
    try:
        stop = core.ACTIVE[uid]
        en_prompt = await core.until_stopped(ai.improve_image_prompt(prompt), stop)
        img = await core.until_stopped(ai.generate_image(en_prompt), stop)
    except asyncio.CancelledError:
        if not core.ACTIVE[uid].is_set():
            raise
        await spinner.stop()
        await core.edit(status, texts.STOPPED, html=True)
        return
    except BadRequestError as exc:
        log.exception("Rasm yaratish so'rovida xato")
        await spinner.stop()
        code = str(getattr(exc, "code", "") or "").lower()
        policy = code in {"content_policy_violation", "moderation_blocked", "safety_violations"}
        await core.edit(status, texts.ERROR_IMAGE_POLICY if policy else texts.ERROR)
        return
    except Exception as exc:
        log.exception("Rasm yaratishda xato")
        await spinner.stop()
        await core.edit(status, texts.ERROR)
        await core.notify_admin(message, cfg, exc)
        return
    finally:
        await spinner.stop()

    caption = f"🎨 <b>Tayyor!</b>\n<i>{texts.e(prompt[:300])}</i>"
    await message.answer_photo(BufferedInputFile(img, filename="rasm.png"), caption=caption, parse_mode=HTML)
    with contextlib.suppress(Exception):
        await status.delete()
    await run(db.add_usage, uid, images=1)
