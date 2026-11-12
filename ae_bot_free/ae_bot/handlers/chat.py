"""Oddiy xabarlar: matn, ovoz, rasm, fayl. (Buyruqlar commands.py da.)"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.types import Message

import core
import texts
from ai import AI
from config import Settings
from db import Database
from handlers import media

HTML = ParseMode.HTML
router = Router()
router.message.filter(F.chat.type == "private")


@router.message(F.voice)
async def on_voice(message: Message, db: Database, ai: AI, cfg: Settings):
    core.IMAGE_PENDING.discard(message.from_user.id)
    await media.handle_voice(message, db=db, ai=ai, cfg=cfg)


@router.message(F.photo)
async def on_photo(message: Message, db: Database, ai: AI, cfg: Settings):
    core.IMAGE_PENDING.discard(message.from_user.id)
    await media.handle_photo(message, db=db, ai=ai, cfg=cfg)


@router.message(F.document)
async def on_document(message: Message, db: Database, ai: AI, cfg: Settings):
    core.IMAGE_PENDING.discard(message.from_user.id)
    await media.handle_document(message, db=db, ai=ai, cfg=cfg)


@router.message(F.text)
async def on_text(message: Message, db: Database, ai: AI, cfg: Settings):
    uid = message.from_user.id
    text = message.text.strip()
    if not text:
        return
    if len(text) > 8000:
        await message.answer(texts.TOO_LONG)
        return

    # "🎨 Rasm yaratish" bosilgan bo'lsa, bu xabar rasm tavsifi
    if uid in core.IMAGE_PENDING:
        core.IMAGE_PENDING.discard(uid)
        await media.make_image(message, text, db=db, ai=ai, cfg=cfg)
        return

    await core.run_answer(message, db=db, ai=ai, cfg=cfg, stored=text, api_content=text)


@router.message()
async def on_other(message: Message):
    await message.answer(texts.UNSUPPORTED)
