"""OpenAI bilan ishlash: suhbat (oqimli), ovozni matnga, matnni ovozga, rasm yaratish."""
from __future__ import annotations

import base64
import io
import logging
from typing import AsyncIterator

import aiohttp
from openai import AsyncOpenAI, BadRequestError

from config import Settings

log = logging.getLogger("ae.ai")


class AI:
    def __init__(self, cfg: Settings):
        self.cfg = cfg
        self.client = AsyncOpenAI(api_key=cfg.openai_key, timeout=120, max_retries=2)

    # ---------- suhbat ----------
    async def stream_chat(self, messages: list) -> AsyncIterator[str]:
        """Javobni bo'lak-bo'lak (so'z-so'z) qaytaradi."""
        kwargs = dict(model=self.cfg.chat_model, messages=messages, stream=True)
        effort = self.cfg.reasoning
        if effort:
            kwargs["reasoning_effort"] = effort
        try:
            stream = await self.client.chat.completions.create(**kwargs)
        except BadRequestError as exc:
            # Model reasoning_effort ni tanimasa - usiz qayta uramiz
            if effort and "reasoning" in str(exc).lower():
                log.warning("Model reasoning_effort ni qabul qilmadi, usiz urinaman: %s", exc)
                kwargs.pop("reasoning_effort", None)
                stream = await self.client.chat.completions.create(**kwargs)
            else:
                raise
        try:
            async for chunk in stream:
                if not chunk.choices:
                    continue
                piece = chunk.choices[0].delta.content
                if piece:
                    yield piece
        finally:
            try:
                await stream.close()
            except Exception:
                pass

    async def complete(self, system: str, user: str) -> str:
        """Oddiy (oqimsiz) qisqa so'rov."""
        kwargs = dict(
            model=self.cfg.chat_model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        if self.cfg.reasoning:  # qisqa vazifa uchun fikrlashsiz - tez va arzon
            kwargs["reasoning_effort"] = "none"
        try:
            resp = await self.client.chat.completions.create(**kwargs)
        except BadRequestError:
            kwargs.pop("reasoning_effort", None)
            resp = await self.client.chat.completions.create(**kwargs)
        return (resp.choices[0].message.content or "").strip()

    # ---------- ovoz -> matn ----------
    async def transcribe(self, audio: bytes, filename: str = "voice.ogg") -> str:
        buf = io.BytesIO(audio)
        buf.name = filename
        kwargs = dict(model=self.cfg.stt_model, file=buf)
        if self.cfg.stt_languages:
            if self.cfg.stt_model.startswith("gpt-transcribe"):
                kwargs["extra_body"] = {"languages": self.cfg.stt_languages}
            else:  # eski modellar (whisper-1 va h.k.) bitta `language` oladi
                kwargs["language"] = self.cfg.stt_languages[0]
        result = await self.client.audio.transcriptions.create(**kwargs)
        return (getattr(result, "text", "") or "").strip()

    # ---------- matn -> ovoz ----------
    async def tts(self, text: str) -> tuple[bytes, str]:
        """(audio baytlari, fayl nomi) qaytaradi. Telegram ovozli xabar sifatida mp3/ogg qabul qiladi."""
        if self.cfg.tts_provider == "openai":
            resp = await self.client.audio.speech.create(
                model=self.cfg.tts_openai_model,
                voice=self.cfg.tts_voice,
                input=text,
                response_format="opus",
            )
            return resp.content, "javob.ogg"

        import edge_tts  # bepul, o'zbekcha ovozlari bor

        comm = edge_tts.Communicate(text, self.cfg.tts_voice)
        out = bytearray()
        async for chunk in comm.stream():
            if chunk.get("type") == "audio":
                out += chunk["data"]
        if not out:
            raise RuntimeError("edge-tts bo'sh javob qaytardi")
        return bytes(out), "javob.mp3"

    # ---------- rasm ----------
    async def improve_image_prompt(self, user_text: str) -> str:
        """O'zbekcha tasvirni rasm modeli uchun batafsil inglizcha promptga aylantiradi."""
        try:
            out = await self.complete(
                "Foydalanuvchi tasvirini rasm yaratish modeli uchun batafsil, chiroyli INGLIZCHA promptga "
                "aylantir (uslub, yorug'lik, kompozitsiya). Faqat promptning o'zini yoz, izohsiz.",
                user_text,
            )
            return out or user_text
        except Exception:
            log.exception("Prompt yaxshilashda xato; asl matn ishlatiladi")
            return user_text

    async def generate_image(self, prompt: str) -> bytes:
        resp = await self.client.images.generate(
            model=self.cfg.image_model,
            prompt=prompt,
            size=self.cfg.image_size,
        )
        item = resp.data[0]
        if getattr(item, "b64_json", None):
            return base64.b64decode(item.b64_json)
        if getattr(item, "url", None):
            async with aiohttp.ClientSession() as session:
                async with session.get(item.url) as r:
                    r.raise_for_status()
                    return await r.read()
        raise RuntimeError("Rasm modeli rasm qaytarmadi")
