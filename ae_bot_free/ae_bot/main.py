"""AE Yordamchi — Telegram boti. Ishga tushirish: python main.py"""
from __future__ import annotations

import asyncio
import logging
import sys
import os
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from logging.handlers import RotatingFileHandler

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand

from ai import AI
from config import load_settings
from db import Database
from handlers import chat, commands
from telegram_topics import install_topics


def setup_logging() -> None:
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)
    try:
        file = RotatingFileHandler(
            "bot.log",
            maxBytes=1_000_000,
            backupCount=2,
            encoding="utf-8",
        )
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
    db = await asyncio.to_thread(
        Database,
        os.getenv("DATABASE_URL", "").strip() or cfg.db_path,
    )
    ai = AI(cfg)

    dp = Dispatcher(db=db, ai=ai, cfg=cfg)
    install_topics(dp, bot, db)

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

    mode = os.getenv("BOT_MODE", "webhook").strip().lower()

    try:
        me = await bot.get_me()

        if mode == "polling":
            await bot.delete_webhook(drop_pending_updates=False)
            log.info("Bot ishga tushdi: @%s | polling", me.username)

            await dp.start_polling(
                bot,
                allowed_updates=dp.resolve_used_update_types(),
            )

        elif mode == "webhook":
            base = (
                os.getenv("WEBHOOK_BASE_URL")
                or os.getenv("RENDER_EXTERNAL_URL")
                or ""
            ).rstrip("/")

            secret = os.getenv("WEBHOOK_SECRET", "").strip()

            if not base.startswith("https://") or len(secret) < 32:
                raise RuntimeError(
                    "WEBHOOK_BASE_URL HTTPS bo'lishi va WEBHOOK_SECRET "
                    "kamida 32 belgidan iborat bo'lishi kerak."
                )

            if not all(
                c.isascii() and (c.isalnum() or c in "_-")
                for c in secret
            ):
                raise RuntimeError(
                    "WEBHOOK_SECRET faqat A-Z, a-z, 0-9, _ va - "
                    "belgilaridan iborat bo'lsin."
                )

            if not os.getenv("DATABASE_URL", "").strip():
                raise RuntimeError(
                    "Bepul hostingda xotira uchun DATABASE_URL kiriting "
                    "(tashqi PostgreSQL)."
                )

            app = web.Application(client_max_size=1024 * 1024)

            async def health(request):
                return web.Response(text="AE Yordamchi: OK")

            app.router.add_get("/", health)
            app.router.add_get("/health", health)

            SimpleRequestHandler(
                dp,
                bot,
                secret_token=secret,
                handle_in_background=True,
            ).register(app, path="/telegram/webhook")

            setup_application(app, dp, bot=bot)

            runner = web.AppRunner(app)
            await runner.setup()

            try:
                await web.TCPSite(
                    runner,
                    "0.0.0.0",
                    int(os.getenv("PORT", "10000")),
                ).start()

                await bot.set_webhook(
                    base + "/telegram/webhook",
                    secret_token=secret,
                    drop_pending_updates=False,
                    allowed_updates=dp.resolve_used_update_types(),
                )

                log.info(
                    "Bot ishga tushdi: @%s | webhook",
                    me.username,
                )

                await asyncio.Event().wait()

            finally:
                await runner.cleanup()

        else:
            raise RuntimeError(
                "BOT_MODE faqat webhook yoki polling bo'lishi mumkin."
            )

    finally:
        await ai.client.close()
        await bot.session.close()
        await asyncio.to_thread(db.close)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
