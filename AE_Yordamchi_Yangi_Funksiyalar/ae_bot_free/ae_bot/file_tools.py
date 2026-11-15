"""Matn/kod/rasm -> fayl va internetdan surat izlash routeri."""
from __future__ import annotations
import asyncio
import base64
import contextlib
import io
import logging
import re
from pathlib import Path
from aiogram import Router
from aiogram.types import BufferedInputFile
import core
import docs
from db import run
from file_builder import FORMATS, TEXT_FORMATS, build_file, clean_image
from internet_images import search_image

router = Router(name='ae_file_tools')
router.message.filter(lambda m: m.chat.type == 'private')
log = logging.getLogger(__name__)
HELP = ('📎 Fayl tayyorlash:\n/file pdf Matningiz\n/file pptx Quyosh tizimi haqida 5 slayd\n'
        '/file html Kalkulyator sahifasini yoz\nRasmni “PDF qil” izohi bilan yuboring yoki unga reply qiling.\n'
        'Oldingi javobga reply qilib “Word fayl qil” deyishingiz ham mumkin.\n'
        '🌐 Haqiqiy surat: /photo Lamine Yamal\n'
        'Formatlar: PDF, DOCX, PPTX, TXT, TEX, HTML, PY, JS, CSS, JSON, CSV, MD, XML, YAML, SQL, SVG, TS.')


def requested_format(text):
    s = text.lower().strip()
    s = re.sub(r'\bpython\b', 'py', s)
    s = re.sub(r'\bjavascript\b', 'js', s)
    s = re.sub(r'\btypescript\b', 'ts', s)
    s = re.sub(r'\blatex\b', 'tex', s)
    command = re.match(r'^/file(?:@\w+)?\s+(\w+)', s)
    if command:
        return command.group(1) if command.group(1) in FORMATS else None
    for fmt, pattern in [('pptx', r'\b(power\s*point|powerpoint|pptx|prezentatsiya|taqdimot|slayd)\b'),
                         ('docx', r'\b(word|docx)\b'), ('pdf', r'\bpdf\b')]:
        if re.search(pattern, s) and re.search(r'qil|tayyor|yarat|ber|tuz|aylantir|saqla|format|fayl', s):
            return fmt
    for fmt in sorted(TEXT_FORMATS, key=len, reverse=True):
        if re.search(r'(?<!\w)\.?'+fmt+r'(?!\w)', s) and re.search(r'fayl|format|saqla|kod.*yoz|yoz.*kod', s):
            return fmt
    return None


def image_request(text):
    if re.match(r'^/photo(?:@\w+)?(?:\s|$)', text, re.I):
        return True
    return bool(re.search(r'rasm|surat|foto', text, re.I) and
                re.search(r'top|tashla|yubor|internetdan|qidir|ko.rsat', text, re.I) and
                not re.search(r'chiz|yarat|generatsiya|tahlil|o.qi', text, re.I))


def candidate(message):
    text = message.text or message.caption or ''
    if re.match(r'^/(file|photo)(?:@\w+)?(?:\s|$)', text, re.I):
        return True
    if text.startswith('/') or message.from_user.id in core.IMAGE_PENDING:
        return False
    return bool(requested_format(text) or image_request(text))


async def download(message, item, cfg):
    limit = min(cfg.max_file_mb, 15) * 1024 * 1024
    if (item.file_size or 0) > limit:
        raise ValueError(f'Fayl {min(cfg.max_file_mb, 15)} MB dan kichik bo‘lsin.')
    buffer = io.BytesIO()
    await message.bot.download(item, destination=buffer)
    if buffer.tell() > limit:
        raise ValueError('Fayl hajmi katta.')
    return buffer.getvalue()


async def source_content(message, cfg, db):
    source = message if message.photo or message.document else message.reply_to_message
    images, text = [], ''
    if source:
        if source.photo:
            images.append(await download(message, source.photo[-1], cfg))
        elif source.document:
            item = source.document
            data = await download(message, item, cfg)
            ext = Path(item.file_name or '').suffix.lower()
            if (item.mime_type or '').startswith('image/'):
                images.append(data)
            else:
                text = await asyncio.to_thread(docs.extract_text, data, ext, cfg.max_doc_chars)
        else:
            text = source.text or source.caption or ''
    instruction = message.text or message.caption or ''
    if not source and re.search(r'shuni|shu javob|oldingi|buni', instruction, re.I):
        topic = await run(db.current_topic, message.from_user.id)
        history = await run(db.get_history, topic, cfg.history_messages, cfg.history_chars)
        text = next((m['content'] for m in reversed(history) if m['role'] == 'assistant'), '')
        if not text:
            raise ValueError('Qaysi matn yoki rasm? Unga reply qilib formatni yozing.')
    return text, images


async def collect(ai, messages):
    parts, size = [], 0
    async for part in ai.stream_chat(messages):
        size += len(part)
        if size > 60000:
            raise ValueError('Natija juda uzun. Vazifani qismlarga ajrating.')
        parts.append(part)
    result = ''.join(parts).strip()
    if not result:
        raise ValueError('Bo‘sh javob qaytdi. Yana urinib ko‘ring.')
    return result


@router.message(candidate)
@core.serialized
async def handle_tools(message, db, ai, cfg):
    uid = message.from_user.id
    instruction = (message.text or message.caption or '').strip()
    fmt = requested_format(instruction)
    if re.fullmatch(r'/file(?:@\w+)?', instruction, re.I) or (instruction.startswith('/file') and not fmt):
        await message.answer(HELP)
        return
    blocked = await core.limit_reached(db, cfg, uid, 'requests')
    if blocked:
        await message.answer(blocked)
        return
    status = await message.answer('⏳ Tayyorlayapman…', reply_markup=core.keyboards.stop_kb())
    stop = core.ACTIVE[uid]
    async def work():
        if not fmt:
            query = re.sub(r'^/photo(?:@\w+)?\s*', '', instruction, flags=re.I).strip()
            if not query:
                raise ValueError('Masalan: /photo Lamine Yamal')
            await run(db.add_usage, uid, requests=1)
            query = await ai.complete('Return only a short English Wikimedia Commons photo search query. '
                                      'Keep proper names. No instructions, no quotes.', query)
            result = await search_image(query)
            if not result:
                raise ValueError('Wikimedia Commons’dan mos surat topilmadi. Ism yoki mavzuni aniqroq yozing.')
            data, caption = result
            await message.answer_photo(BufferedInputFile(data, filename='internet_rasm.jpg'), caption=caption)
            summary = caption
        else:
            source, images = await source_content(message, cfg, db)
            # Oddiy konvertatsiyada model matnni o'zgartirmaydi.
            transform = bool(re.search(r'yoz|haqida|yarat|slayd|tahrir|tarjima|xulosa|tuzib|matn.*o.q|matn.*ajrat', instruction, re.I))
            transform = transform or bool(images and fmt in TEXT_FORMATS)
            prompt = re.sub(r'^/file(?:@\w+)?\s+\w+\s*', '', instruction, flags=re.I)
            if source and not transform:
                output = source
            elif images and not source and not transform:
                output = ''
            elif not prompt.strip():
                raise ValueError('Faylga joylash uchun matn yoki rasm yuboring.\n' + HELP)
            else:
                await run(db.add_usage, uid, requests=1)
                system = ('You create file CONTENT ONLY, never explain how to create a file. '
                          'Reply in the user language. Do not invent sources or facts from an unseen image. '
                          'Read attached images accurately; mark unreadable text instead of guessing. '
                          'Keep output under 16000 characters. ')
                if fmt in TEXT_FORMATS:
                    system += f'Output only valid {fmt} source/content, without Markdown fences or commentary. Never execute code.'
                elif fmt == 'pptx':
                    system += ('Write 4-10 slides unless a count is specified (maximum 20). '
                               'Separate slides with a line containing ---. Each slide: short title then '
                               'at most 6 short bullet lines, each under 65 characters.')
                else:
                    system += 'Write a polished document. Use short paragraphs and # headings. No code for making documents.'
                content = prompt + '\n\nManba matni:\n' + source
                if images:
                    content = [{'type': 'text', 'text': content}] + [
                        {'type': 'image_url', 'image_url': {'url': 'data:image/jpeg;base64,' +
                            base64.b64encode(await asyncio.to_thread(clean_image, pic)).decode()}}
                        for pic in images]
                output = await collect(ai, [{'role': 'system', 'content': system},
                                           {'role': 'user', 'content': content}])
                if fmt in TEXT_FORMATS:
                    images = []
            data, filename = await asyncio.to_thread(build_file, fmt, output, images)
            if len(data) > 45 * 1024 * 1024:
                raise ValueError('Natija juda katta. Manbani qisqartiring.')
            if stop.is_set():
                raise asyncio.CancelledError
            await message.answer_document(BufferedInputFile(data, filename=filename), caption='📎 Tayyor!')
            summary = f'📎 {filename}\n' + output[:30000]
        topic = await run(db.current_topic, uid)
        await run(db.add_message, topic, 'user', instruction)
        await run(db.set_title_if_default, topic, instruction)
        await run(db.add_message, topic, 'assistant', summary)
    try:
        await core.until_stopped(work(), stop)
    except asyncio.CancelledError:
        if not stop.is_set():
            raise
        await core.edit(status, '⏹ To‘xtatildi.')
        return
    except (ValueError, docs.FileProblem) as exc:
        await core.edit(status, str(exc) if isinstance(exc, ValueError) else 'Fayldan matnni o‘qib bo‘lmadi. Matn yoki rasm yuboring.')
        return
    except Exception as exc:
        log.exception('Fayl yoki internet rasmi xatosi')
        await core.edit(status, 'Fayl yoki rasmni tayyorlab bo‘lmadi. Keyinroq qayta urinib ko‘ring.')
        await core.notify_admin(message, cfg, exc)
        return
    with contextlib.suppress(Exception):
        await status.delete()
