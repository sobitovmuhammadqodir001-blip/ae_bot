"""AE Yordamchi: Telegram mavzulari uchun qo'shimcha."""
from contextvars import ContextVar
import asyncio
import logging
import threading
import time

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.exceptions import TelegramBadRequest

from db import run
import core
import keyboards
import texts

_scope = ContextVar("ae_telegram_topic", default=None)
log = logging.getLogger(__name__)


class TopicDB:
    """Har bir mavzu uchun alohida suhbat xotirasi."""

    def __init__(self, db, uid, topic_id):
        self.db = db
        self.uid = uid
        self.topic_id = topic_id

    def __getattr__(self, name):
        return getattr(self.db, name)

    def current_topic(self, uid):
        if uid == self.uid:
            return self.topic_id
        return self.db.current_topic(uid)


class TopicStore:
    """Telegram mavzusini bazadagi suhbat bilan bog'laydi."""

    def __init__(self, db):
        self.db = db
        self.lock = threading.Lock()

        db._exec("""
            CREATE TABLE IF NOT EXISTS telegram_topic_links (
                user_id BIGINT NOT NULL,
                thread_id BIGINT NOT NULL,
                topic_id BIGINT NOT NULL,
                PRIMARY KEY(user_id, thread_id)
            )
        """)

    def bind(self, uid, thread, title="Yangi suhbat"):
        with self.lock:
            row = self.db._one(
                """
                SELECT topic_id FROM telegram_topic_links
                WHERE user_id=? AND thread_id=?
                """,
                (uid, thread),
            )

            if row:
                tid = int(row["topic_id"])
                exists = self.db._one(
                    "SELECT id FROM topics WHERE id=? AND user_id=?",
                    (tid, uid),
                )
                if exists:
                    return tid

            self.db.ensure_user(uid, "")

            tid = self.db._insert(
                """
                INSERT INTO topics(user_id, title, created_at)
                VALUES(?,?,?)
                """,
                (uid, title, self.db._now()),
            )

            self.db._exec(
                """
                INSERT INTO telegram_topic_links(
                    user_id, thread_id, topic_id
                )
                VALUES(?,?,?)
                ON CONFLICT(user_id, thread_id)
                DO UPDATE SET topic_id=excluded.topic_id
                """,
                (uid, thread, tid),
            )
            return tid


class TopicSending:
    """Matn, rasm va ovozni tegishli mavzuga yuboradi."""

    async def __call__(self, make_request, bot, method):
        scope = _scope.get()

        if (
            scope
            and getattr(method, "chat_id", None) == scope[0]
            and "message_thread_id" in type(method).model_fields
            and getattr(method, "message_thread_id", None) is None
        ):
            method = method.model_copy(
                update={"message_thread_id": scope[1]}
            )

        return await make_request(bot, method)


class TopicIncoming(BaseMiddleware):
    def __init__(self, db):
        self.db = db
        self.store = None
        self.init_lock = asyncio.Lock()
        self.rename_pending = {}

    async def get_store(self):
        async with self.init_lock:
            if self.store is None:
                self.store = await run(TopicStore, self.db)
        return self.store

    async def _set_name(self, msg, uid, thread, tid, title):
        title = " ".join(title.split())
        if not title or len(title) > 128:
            await msg.answer("Nom 1–128 belgidan iborat bo‘lsin. Qayta yozing yoki /cancel bosing.")
            return False
        try:
            await msg.bot.edit_forum_topic(
                chat_id=msg.chat.id, message_thread_id=thread, name=title)
        except TelegramBadRequest as exc:
            if "not modified" not in str(exc).lower():
                log.warning("Mavzu nomi o‘zgarmadi: %s", exc)
                await msg.answer("Nom o‘zgarmadi. Keyinroq /rename bilan urinib ko‘ring.")
                return False
        except Exception:
            log.exception("Mavzu nomini Telegram’da saqlashda xato")
            await msg.answer("Telegram bilan ulanishda muammo. Keyinroq /rename bilan urinib ko‘ring.")
            return False
        await run(self.db._exec,
                  "UPDATE topics SET title=? WHERE id=? AND user_id=?",
                  (title, tid, uid))
        return True

    async def _forward(self, handler, event, data, msg, uid, thread, tid):
        if not thread or tid is None:
            return await handler(event, data)
        before = await run(self.db.topic_title, tid)
        result = await handler(event, data)
        after = await run(self.db.topic_title, tid)
        if before == "Yangi suhbat" and after != before:
            try:
                await msg.bot.edit_forum_topic(
                    chat_id=msg.chat.id, message_thread_id=thread, name=after[:128])
            except Exception:
                log.warning("Avtomatik mavzu nomi yangilanmadi", exc_info=True)
        return result

    async def __call__(self, handler, event, data):
        callback = isinstance(event, CallbackQuery)
        msg = event.message if callback else event

        if not msg or msg.chat.type != "private":
            return await handler(event, data)

        uid = event.from_user.id
        thread = getattr(msg, "message_thread_id", None)
        token = _scope.set(
            (msg.chat.id, thread) if thread else None
        )

        tid = None
        try:
            if thread:
                store = await self.get_store()
                created = getattr(msg, "forum_topic_created", None)
                title = created.name if created else "Yangi suhbat"

                tid = await run(store.bind, uid, thread, title)
                data["db"] = TopicDB(self.db, uid, tid)

                edited = getattr(msg, "forum_topic_edited", None)

                if edited and edited.name:
                    await run(
                        self.db._exec,
                        "UPDATE topics SET title=? WHERE id=?",
                        (edited.name, tid),
                    )

                service_message = (
                    created
                    or edited
                    or getattr(msg, "forum_topic_closed", None)
                    or getattr(msg, "forum_topic_reopened", None)
                )
                if not callback and service_message:
                    return

            text = (getattr(msg, "text", None) or "").strip()
            command = (
                text.split(maxsplit=1)[0].split("@")[0]
                if text else ""
            )

            pending_key = (uid, msg.chat.id, thread)
            expires = self.rename_pending.get(pending_key, 0)
            pending = expires > time.monotonic()
            if expires and not pending:
                self.rename_pending.pop(pending_key, None)
            rename = (event.data == "ae:rename") if callback else command == "/rename"
            if not callback and command == "/cancel" and pending:
                self.rename_pending.pop(pending_key, None)
                await msg.answer("Nom o‘zgartirish bekor qilindi.")
                return
            if rename:
                if callback:
                    await event.answer()
                if not thread:
                    await msg.answer("Avval chap paneldan kerakli mavzuni oching.")
                    return
                core.IMAGE_PENDING.discard(uid)
                pieces = text.split(maxsplit=1)
                args = pieces[1] if not callback and len(pieces) > 1 else ""
                if args:
                    if await self._set_name(msg, uid, thread, tid, args):
                        self.rename_pending.pop(pending_key, None)
                        await msg.answer("✅ Mavzu nomi o‘zgartirildi.")
                else:
                    self.rename_pending[pending_key] = time.monotonic() + 300
                    await msg.answer("✏️ Shu mavzuning yangi nomini yozing.\nBekor qilish: /cancel")
                return
            if pending and not callback and text and not text.startswith("/") and text not in texts.MENU_BUTTONS:
                if await self._set_name(msg, uid, thread, tid, text):
                    self.rename_pending.pop(pending_key, None)
                    await msg.answer("✅ Mavzu nomi o‘zgartirildi.")
                return
            if not callback and (text in texts.MENU_BUTTONS or text.startswith("/")):
                self.rename_pending.pop(pending_key, None)

            if callback:
                new = event.data == "newtopic"
                listing = (event.data or "").startswith(
                    ("topic:", "deltopic:")
                )
            else:
                new = command == "/new" or text == texts.BTN_NEW
                listing = (
                    command == "/topics"
                    or text == texts.BTN_TOPICS
                )

            if not (new or listing):
                return await self._forward(handler, event, data, msg, uid, thread, tid)

            enabled = bool(thread)
            if not enabled:
                me = await msg.bot.get_me()
                enabled = bool(
                    getattr(me, "has_topics_enabled", False)
                )

            if not enabled:
                return await handler(event, data)

            if callback:
                await event.answer()

            if listing:
                await msg.answer(
                    "📚 Suhbatlaringiz Telegram mavzular panelida.\n\n"
                    "Kerakli mavzuni ochib yozishni davom ettiring.\n"
                    "Yangi suhbat uchun /new buyrug‘ini yuboring.\n"
                    "Nomini o‘zgartirish: /rename Yangi nom",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="✏️ Nomini o‘zgartirish", callback_data="ae:rename")],
                        [InlineKeyboardButton(text="🆕 Yangi suhbat", callback_data="newtopic")],
                    ])
                )
                return

            if core.is_busy(uid):
                await msg.answer(texts.BUSY)
                return

            core.IMAGE_PENDING.discard(uid)

            try:
                topic = await msg.bot.create_forum_topic(
                    chat_id=msg.chat.id,
                    name="Yangi suhbat",
                )
            except TelegramBadRequest:
                log.exception("Telegram mavzusini ochib bo‘lmadi")
                await msg.answer(
                    "Mavzu ochilmadi. BotFather’dagi "
                    "Topics sozlamasini tekshiring."
                )
                return

            store = await self.get_store()
            await run(store.bind, uid, topic.message_thread_id)

            await msg.bot.send_message(
                chat_id=msg.chat.id,
                text="✨ Yangi suhbat ochildi. Savolingizni yozing.",
                message_thread_id=topic.message_thread_id,
                reply_markup=keyboards.main_menu(),
            )

        finally:
            _scope.reset(token)


def install_topics(dp, bot, db):
    middleware = TopicIncoming(db)
    dp.message.outer_middleware(middleware)
    dp.callback_query.outer_middleware(middleware)
    bot.session.middleware(TopicSending())
