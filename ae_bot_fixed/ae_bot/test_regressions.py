"""Tashqi kalitlarsiz: python -m unittest -v test_regressions"""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
import core
from handlers import media

class RegressionTests(unittest.IsolatedAsyncioTestCase):
    def message(self):
        return SimpleNamespace(from_user=SimpleNamespace(id=123), answer=AsyncMock())

    async def test_parallel_and_nested(self):
        entered, release = asyncio.Event(), asyncio.Event()
        calls = []
        @core.serialized
        async def inner(message):
            calls.append('inner')
        @core.serialized
        async def job(message):
            entered.set()
            await release.wait()
            await inner(message)
        m = self.message()
        first = asyncio.create_task(job(m))
        await entered.wait()
        await job(m)
        self.assertEqual(m.answer.await_count, 1)
        release.set()
        await first
        self.assertEqual(calls, ['inner'])
        self.assertNotIn(123, core.ACTIVE)

    async def test_stop_cancels_provider(self):
        stop = asyncio.Event()
        cleaned = asyncio.Event()
        async def provider():
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()
        task = asyncio.create_task(core.until_stopped(provider(), stop))
        await asyncio.sleep(0)
        stop.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(cleaned.is_set())

    async def test_voice_remaining_budget(self):
        m = self.message()
        m.voice = SimpleNamespace(duration=120, file_size=100)
        cfg = SimpleNamespace(admin_id=0, max_voice_seconds=120, max_file_mb=15,
            daily_requests=100, daily_voice_seconds=600)
        db = SimpleNamespace(get_usage=lambda uid: dict(requests=0, images=0, voice_seconds=590))
        ai = SimpleNamespace(transcribe=AsyncMock())
        await media.handle_voice(m, db=db, ai=ai, cfg=cfg)
        ai.transcribe.assert_not_awaited()
        self.assertEqual(m.answer.await_args.args[0], core.texts.LIMIT_VOICE)
        self.assertNotIn(123, core.ACTIVE)

    async def test_image_stop(self):
        m = self.message()
        status = SimpleNamespace(edit_text=AsyncMock())
        m.answer.return_value = status
        cfg = SimpleNamespace(admin_id=0, daily_images=5)
        db = SimpleNamespace(get_usage=lambda uid: dict(requests=0, images=0, voice_seconds=0))
        started = asyncio.Event()
        async def improve(prompt):
            started.set()
            await asyncio.Event().wait()
        ai = SimpleNamespace(improve_image_prompt=improve, generate_image=AsyncMock())
        task = asyncio.create_task(media.make_image(m, 'tog', db=db, ai=ai, cfg=cfg))
        await started.wait()
        self.assertTrue(core.request_stop(123))
        await task
        ai.generate_image.assert_not_awaited()
        self.assertNotIn(123, core.ACTIVE)
        self.assertEqual(status.edit_text.await_args.args[0], core.texts.STOPPED)

    async def test_image_bad_parameter_is_not_policy(self):
        from openai import BadRequestError
        import httpx
        m = self.message()
        status = SimpleNamespace(edit_text=AsyncMock())
        m.answer.return_value = status
        cfg = SimpleNamespace(admin_id=0, daily_images=5)
        db = SimpleNamespace(get_usage=lambda uid: dict(requests=0, images=0, voice_seconds=0))
        error = BadRequestError("Invalid size", response=httpx.Response(400,
            request=httpx.Request('POST', 'https://example.com')), body={"code": "invalid_value"})
        ai = SimpleNamespace(improve_image_prompt=AsyncMock(return_value='mountain'),
            generate_image=AsyncMock(side_effect=error))
        with self.assertLogs('ae.media', level='ERROR'):
            await media.make_image(m, 'tog', db=db, ai=ai, cfg=cfg)
        self.assertEqual(status.edit_text.await_args.args[0], core.texts.ERROR)
        self.assertNotIn(123, core.ACTIVE)

if __name__ == '__main__':
    unittest.main()
