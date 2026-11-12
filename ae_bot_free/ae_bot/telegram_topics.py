"""AE Yordamchi: Telegram mavzulari uchun qo'shimcha."""
from contextvars import ContextVar
import asyncio
import logging
import threading

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery
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

    async def get_store(self):
        async with self.init_lock:
            if self.store is None:
                self.store = await run(TopicStore, self.db)
        return self.store

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
                return await handler(event, data)

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
                    "Yangi suhbat uchun /new buyrug‘ini yuboring."
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
