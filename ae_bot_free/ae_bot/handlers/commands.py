"""Buyruqlar (/start, /new, /topics ...), pastki menyu tugmalari va inline tugmalar."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

import core
import keyboards
import texts
from ai import AI
from config import Settings
from db import Database, run
from handlers import media

HTML = ParseMode.HTML
router = Router()
router.message.filter(F.chat.type == "private")


# ------------------------------------------------------------------ /start, /help
@router.message(Command("start"))
async def cmd_start(message: Message, db: Database):
    u = message.from_user
    await run(db.ensure_user, u.id, u.full_name or "")
    core.IMAGE_PENDING.discard(u.id)
    await message.answer(texts.welcome(u.first_name or "do'st"), parse_mode=HTML, reply_markup=keyboards.main_menu())


@router.message(Command("help"))
@router.message(F.text == texts.BTN_HELP)
async def cmd_help(message: Message):
    core.IMAGE_PENDING.discard(message.from_user.id)
    await message.answer(texts.HELP, parse_mode=HTML, reply_markup=keyboards.main_menu())


# ------------------------------------------------------------------ suhbatlar
@router.message(Command("new"))
@router.message(F.text == texts.BTN_NEW)
async def cmd_new(message: Message, db: Database):
    core.IMAGE_PENDING.discard(message.from_user.id)
    await run(db.new_topic, message.from_user.id)
    await message.answer(texts.NEW_TOPIC, parse_mode=HTML, reply_markup=keyboards.main_menu())


async def _topics_view(db: Database, user_id: int):
    current = await run(db.current_topic, user_id)   # kerak bo'lsa, yangi suhbat ochadi
    topics = await run(db.list_topics, user_id)
    return texts.topics_header(), keyboards.topics_kb(topics, current)


@router.message(Command("topics"))
@router.message(F.text == texts.BTN_TOPICS)
async def cmd_topics(message: Message, db: Database):
    core.IMAGE_PENDING.discard(message.from_user.id)
    text, kb = await _topics_view(db, message.from_user.id)
    await message.answer(text, parse_mode=HTML, reply_markup=kb)


@router.callback_query(F.data.startswith("topic:"))
async def cb_topic(cb: CallbackQuery, db: Database):
    tid = int(cb.data.split(":", 1)[1])
    ok = await run(db.switch_topic, cb.from_user.id, tid)
    await cb.answer("✅ Suhbat tanlandi" if ok else "Topilmadi")
    text, kb = await _topics_view(db, cb.from_user.id)
    try:
        await cb.message.edit_text(text, parse_mode=HTML, reply_markup=kb)
    except TelegramBadRequest:
        pass


@router.callback_query(F.data.startswith("deltopic:"))
async def cb_delete_topic(cb: CallbackQuery, db: Database):
    tid = int(cb.data.split(":", 1)[1])
    await run(db.delete_topic, cb.from_user.id, tid)
    await cb.answer("🗑 O'chirildi")
    text, kb = await _topics_view(db, cb.from_user.id)
    try:
        await cb.message.edit_text(text, parse_mode=HTML, reply_markup=kb)
    except TelegramBadRequest:
        pass


@router.callback_query(F.data == "newtopic")
async def cb_new_topic(cb: CallbackQuery, db: Database):
    await run(db.new_topic, cb.from_user.id)
    await cb.answer("🆕 Yangi suhbat")
    text, kb = await _topics_view(db, cb.from_user.id)
    try:
        await cb.message.edit_text(text, parse_mode=HTML, reply_markup=kb)
    except TelegramBadRequest:
        pass


# ------------------------------------------------------------------ to'xtatish
@router.message(Command("stop"))
async def cmd_stop(message: Message):
    if core.request_stop(message.from_user.id):
        return
    await message.answer(texts.NOTHING_TO_STOP)


@router.callback_query(F.data == "stop")
async def cb_stop(cb: CallbackQuery):
    if core.request_stop(cb.from_user.id):
        await cb.answer("⏹ To'xtatilmoqda…")
    else:
        await cb.answer("Allaqachon tugagan")


# ------------------------------------------------------------------ sozlamalar
async def _settings_view(db: Database, cfg: Settings, user_id: int):
    user = await run(db.get_user, user_id)
    usage = await run(db.get_usage, user_id)
    on = bool(user["voice_reply"])
    return texts.settings_text(on, usage, cfg), keyboards.settings_kb(on)


@router.message(Command("settings"))
@router.message(F.text == texts.BTN_SETTINGS)
async def cmd_settings(message: Message, db: Database, cfg: Settings):
    core.IMAGE_PENDING.discard(message.from_user.id)
    text, kb = await _settings_view(db, cfg, message.from_user.id)
    await message.answer(text, parse_mode=HTML, reply_markup=kb)


@router.callback_query(F.data == "toggle_voice")
async def cb_toggle_voice(cb: CallbackQuery, db: Database, cfg: Settings):
    user = await run(db.get_user, cb.from_user.id)
    new_state = not bool(user["voice_reply"])
    await run(db.set_voice_reply, cb.from_user.id, new_state)
    await cb.answer("🔊 Yoqildi" if new_state else "🔇 O'chirildi")
    text, kb = await _settings_view(db, cfg, cb.from_user.id)
    try:
        await cb.message.edit_text(text, parse_mode=HTML, reply_markup=kb)
    except TelegramBadRequest:
        pass


# ------------------------------------------------------------------ rasm yaratish
@router.message(Command("image"))
async def cmd_image(message: Message, command: CommandObject, db: Database, ai: AI, cfg: Settings):
    prompt = (command.args or "").strip()
    if prompt:
        await media.make_image(message, prompt, db=db, ai=ai, cfg=cfg)
        return
    core.IMAGE_PENDING.add(message.from_user.id)
    await message.answer(texts.IMAGE_ASK, parse_mode=HTML)


@router.message(F.text == texts.BTN_IMAGE)
async def btn_image(message: Message):
    core.IMAGE_PENDING.add(message.from_user.id)
    await message.answer(texts.IMAGE_ASK, parse_mode=HTML)


# ------------------------------------------------------------------ admin
@router.message(Command("stats"))
async def cmd_stats(message: Message, db: Database, cfg: Settings):
    if not cfg.admin_id or message.from_user.id != cfg.admin_id:
        return
    stats = await run(db.stats)
    await message.answer(texts.stats_text(stats), parse_mode=HTML)
