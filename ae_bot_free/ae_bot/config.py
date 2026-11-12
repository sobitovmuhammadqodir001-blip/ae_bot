"""Sozlamalar. Barcha maxfiy narsalar (token, kalit) muhit o'zgaruvchilaridan olinadi.

Renderda ular Dashboard -> Environment bo'limida turadi, kodda YO'Q.
Kompyuterda sinaganda .env fayldan o'qiladi (python-dotenv).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # dotenv bo'lmasa ham ishlayveradi
    pass


def _str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    bot_token: str
    openai_key: str
    admin_id: int
    db_path: str

    chat_model: str
    reasoning: str          # "low" / "none" / "" (bo'sh = yubormaslik)
    stt_model: str
    stt_languages: list     # masalan ["uz", "ru"]; bo'sh = avtomatik aniqlash
    image_model: str
    image_size: str

    tts_provider: str       # "edge" yoki "openai"
    tts_voice: str
    tts_openai_model: str
    tts_max_chars: int

    history_messages: int
    history_chars: int
    daily_requests: int
    daily_images: int
    daily_voice_seconds: int
    max_voice_seconds: int
    max_file_mb: int
    max_doc_chars: int


def load_settings() -> Settings:
    token = _str("TELEGRAM_BOT_TOKEN")
    key = _str("OPENAI_API_KEY")
    missing = [n for n, v in (("TELEGRAM_BOT_TOKEN", token), ("OPENAI_API_KEY", key)) if not v]
    if missing:
        raise SystemExit(
            "XATO: quyidagi muhit o'zgaruvchilari kiritilmagan: "
            + ", ".join(missing)
            + "\nRenderda: Dashboard -> servis -> Environment bo'limiga qo'shing."
        )

    langs = [x.strip() for x in _str("STT_LANGUAGES").split(",") if x.strip()]
    provider = _str("TTS_PROVIDER", "edge").lower()
    default_voice = "uz-UZ-MadinaNeural" if provider == "edge" else "alloy"

    return Settings(
        bot_token=token,
        openai_key=key,
        admin_id=_int("ADMIN_ID", 0),
        db_path=_str("DB_PATH", "./data/bot.db"),
        chat_model=_str("OPENAI_MODEL", "gpt-6-luna"),
        reasoning=_str("OPENAI_REASONING", "low"),
        stt_model=_str("STT_MODEL", "gpt-transcribe"),
        stt_languages=langs,
        image_model=_str("IMAGE_MODEL", "gpt-image-2"),
        image_size=_str("IMAGE_SIZE", "1024x1024"),
        tts_provider=provider,
        tts_voice=_str("TTS_VOICE", default_voice),
        tts_openai_model=_str("TTS_OPENAI_MODEL", "gpt-4o-mini-tts"),
        tts_max_chars=_int("TTS_MAX_CHARS", 1200),
        history_messages=_int("HISTORY_MESSAGES", 24),
        history_chars=_int("HISTORY_CHARS", 30000),
        daily_requests=_int("DAILY_REQUESTS", 100),
        daily_images=_int("DAILY_IMAGES", 5),
        daily_voice_seconds=_int("DAILY_VOICE_SECONDS", 600),
        max_voice_seconds=_int("MAX_VOICE_SECONDS", 120),
        max_file_mb=_int("MAX_FILE_MB", 15),
        max_doc_chars=_int("MAX_DOC_CHARS", 30000),
    )
