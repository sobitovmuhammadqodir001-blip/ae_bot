import unittest
from unittest.mock import AsyncMock, patch
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from aiogram import Bot, Dispatcher
from aiogram.webhook.aiohttp_server import SimpleRequestHandler

class WebhookTests(unittest.IsolatedAsyncioTestCase):
    async def test_secret_and_delivery(self):
        bot = Bot('123456:TEST_TOKEN_FOR_LOCAL_VALIDATION')
        dp = Dispatcher()
        app = web.Application()
        SimpleRequestHandler(dp, bot, secret_token='local-test-secret', handle_in_background=False).register(app, path='/telegram/webhook')
        async with TestClient(TestServer(app)) as client:
            response = await client.post('/telegram/webhook', json={'update_id': 1})
            self.assertEqual(response.status, 401)
            with patch.object(dp, 'feed_webhook_update', new=AsyncMock(return_value=None)) as feed:
                response = await client.post('/telegram/webhook', json={'update_id': 2}, headers={'X-Telegram-Bot-Api-Secret-Token':'local-test-secret'})
                self.assertEqual(response.status, 200)
                feed.assert_awaited_once()
        await bot.session.close()

    async def test_sqlite_persistence(self):
        import tempfile
        from db import Database
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            path = str(Path(folder)/'bot.db')
            db = Database(path)
            tid = db.current_topic(1234567890123)
            db.add_message(tid, 'user', 'Salom')
            db.close()
            db = Database(path)
            self.assertEqual(db.get_history(tid, 24, 30000)[0]['content'], 'Salom')
            db.close()
