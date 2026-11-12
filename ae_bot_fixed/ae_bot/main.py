"""AE Yordamchi — Telegram boti. Ishga tushirish: python main.py"""
from __future__ import annotations

import asyncio
import logging
import sys
from logging.handlers import RotatingFileHandler

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand

from ai import AI
from config import load_settings
from db import Database
from handlers import chat, commands


def setup_logging() -> None:
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    console = logging.StreamHandler(sys.stdout)   # Render shu yerdan loglarni ko'rsatadi
    console.setFormatter(fmt)
    root.addHandler(console)
    try:
        file = RotatingFileHandler("bot.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8")
        file.setFormatter(fmt)
        root.addHandler(file)
    except OSError:
        pass
    logging.getLogger("aiogram").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def main() -> None:
    setup_logging()
    log = logging.getLogger("ae.main")
    cfg = load_settings()

    bot = Bot(token=cfg.bot_token)
    db = Database(cfg.db_path)
    ai = AI(cfg)

    dp = Dispatcher(db=db, ai=ai, cfg=cfg)   # handlerlar shularni nomi bo'yicha oladi
    dp.include_router(commands.router)
    dp.include_router(chat.router)

    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Boshlash"),
            BotCommand(command="new", description="Yangi suhbat"),
            BotCommand(command="topics", description="Suhbatlarim"),
            BotCommand(command="image", description="Rasm yaratish"),
            BotCommand(command="settings", description="Sozlamalar"),
            BotCommand(command="stop", description="Javobni to'xtatish"),
            BotCommand(command="help", description="Yordam"),
        ]
    )
    await bot.delete_webhook(drop_pending_updates=True)

    me = await bot.get_me()
    log.info("Bot ishga tushdi: @%s | model=%s | tts=%s | db=%s", me.username, cfg.chat_model, cfg.tts_provider, cfg.db_path)
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
