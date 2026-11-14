"""Javobni faqat tugma bosilganda audio qilish; SQLite/PostgreSQL xotirasi."""
import asyncio
import contextlib
import json
import logging
import re

from eleven_tts import ElevenTTSError, cache_key, generate

from aiogram import F, Router
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup
from db import run
from formatting import plain_text

log = logging.getLogger(__name__)
router = Router(name='ae_voice_buttons')
BUSY = set()
TTS_SLOTS = asyncio.Semaphore(2)


def init_store(db):
    db._exec('''CREATE TABLE IF NOT EXISTS ae_audio_answers (
        chat_id BIGINT NOT NULL,
        message_id BIGINT NOT NULL,
        user_id BIGINT NOT NULL,
        body TEXT NOT NULL,
        audio_ids TEXT NOT NULL DEFAULT '[]',
        voice_key TEXT NOT NULL DEFAULT '',
        PRIMARY KEY(chat_id, message_id)
    )''')


def save_answer(db, chat_id, message_id, uid, text):
    init_store(db)
    db._exec('''INSERT INTO ae_audio_answers(chat_id,message_id,user_id,body)
        VALUES(?,?,?,?) ON CONFLICT(chat_id,message_id) DO UPDATE SET
        body=excluded.body, audio_ids='[]', voice_key='' ''',
        (chat_id, message_id, uid, text))


async def attach_listen(message, text, db, uid):
    """Har bir yakunlangan javob bo'lagining o'z tugmasi bor."""
    try:
        await run(save_answer, db, message.chat.id, message.message_id, uid, text)
        await message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(
                text='🔊 Ovozda tinglash', callback_data='ae:listen')]]))
    except Exception:
        log.exception('Ovoz tugmasini qo‘shib bo‘lmadi')


def spoken_parts(md, limit=1200):
    # Nusxalash uchun berilgan blokdagi matn ham o'qiladi.
    text = re.sub(r'^\s*```[^\n]*\n?', '', md, flags=re.M)
    text = plain_text(text, max_chars=max(1, len(text) * 2)).strip()
    if not text:
        return []
    parts = []
    while text:
        if len(text) <= limit:
            parts.append(text)
            break
        cut = max(text.rfind('\n', 0, limit), text.rfind('. ', 0, limit),
                  text.rfind(' ', 0, limit))
        if cut < limit // 2:
            cut = limit
        parts.append(text[:cut].strip())
        text = text[cut:].strip()
    return parts


@router.callback_query(F.data == 'ae:listen')
async def listen(cb, db, ai, cfg):
    msg = cb.message
    if msg is None or msg.chat.type != 'private':
        await cb.answer('Bu tugma shaxsiy chatda ishlaydi.', show_alert=True)
        return
    if cb.from_user.id in BUSY:
        await cb.answer('Oldingi audio tayyorlanyapti…')
        return
    # Birinchi awaitdan oldin band qilinadi.
    BUSY.add(cb.from_user.id)
    status = None
    try:
        await cb.answer('🔊 Audio tayyorlanmoqda…')
        await run(init_store, db)
        row = await run(db._one, '''SELECT * FROM ae_audio_answers
            WHERE chat_id=? AND message_id=? AND user_id=?''',
            (msg.chat.id, msg.message_id, cb.from_user.id))
        if row is None:
            await msg.answer('Bu eski javob uchun audio saqlanmagan. Yangi savol yuboring.')
            return
        if cfg.tts_provider not in ('edge', 'elevenlabs'):
            await msg.answer('Render’da TTS_PROVIDER=elevenlabs yoki edge sozlamasini qo‘ying.')
            return
        parts = spoken_parts(row['body'], max(200, min(cfg.tts_max_chars, 2000)))
        if not parts:
            await msg.answer('Bu javobda o‘qiladigan matn yo‘q.')
            return
        key = cache_key() if cfg.tts_provider == 'elevenlabs' else 'edge:' + cfg.tts_voice
        ids = json.loads(row['audio_ids']) if row['voice_key'] == key else []
        status = await msg.answer('🔊 Ovoz tayyorlanmoqda…')
        async with TTS_SLOTS:
            for index, part in enumerate(parts):
                if index < len(ids):
                    source = ids[index]
                else:
                    provider = generate if cfg.tts_provider == 'elevenlabs' else ai.tts
                    audio, filename = await asyncio.wait_for(provider(part), timeout=90)
                    if not filename.lower().endswith(('.mp3', '.m4a')):
                        raise ValueError('Audio player uchun MP3 yoki M4A kerak')
                    source = BufferedInputFile(audio, filename='AE_Yordamchi.mp3')
                title = 'AE Yordamchi'
                if len(parts) > 1:
                    title += f' · {index + 1}/{len(parts)}'
                sent = await msg.bot.send_audio(
                    chat_id=msg.chat.id,
                    audio=source,
                    title=title,
                    performer='AE Corporation',
                    caption='🔊 Javobning ovozli shakli',
                    message_thread_id=getattr(msg, 'message_thread_id', None),
                )
                if index >= len(ids) and sent.audio:
                    ids.append(sent.audio.file_id)
                    await run(db._exec, '''UPDATE ae_audio_answers SET audio_ids=?, voice_key=?
                        WHERE chat_id=? AND message_id=? AND user_id=?''',
                        (json.dumps(ids), key, msg.chat.id, msg.message_id, cb.from_user.id))
    except ElevenTTSError as exc:
        with contextlib.suppress(Exception):
            await msg.answer(str(exc))
    except Exception:
        log.exception('Javobni audio qilishda xato')
        with contextlib.suppress(Exception):
            await msg.answer('Ovozni tayyorlab bo‘lmadi. Birozdan keyin tugmani qayta bosing.')
    finally:
        BUSY.discard(cb.from_user.id)
        if status is not None:
            with contextlib.suppress(Exception):
                await status.delete()
