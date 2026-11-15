"""Admin tasdiqlaydigan umumiy xabarnoma. Avtomatik qayta tarqatish yo'q."""
from __future__ import annotations

import asyncio
import contextlib
import logging
import secrets
import time

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from db import run

router = Router(name='ae_broadcast')
router.message.filter(F.chat.type == 'private')
log = logging.getLogger(__name__)
RUNNING = {}
PACE = 0.12
HELP = ('📣 Umumiy xabar yuborish\n\n'
        'Matn: /broadcast Yangi imkoniyatlar qo‘shildi!\n'
        'Rasm, video yoki fayl: kerakli xabarga reply qilib /broadcast yozing.\n\n'
        'Avval namuna chiqadi. “Yuborish” bosilgandan keyin tarqatiladi.\n'
        '/broadcast_status — oxirgi tarqatish holati.\n'
        '/broadcast_stop — joriy tarqatishni to‘xtatish.')


def allowed(cfg, uid):
    return bool(cfg.admin_id) and uid == cfg.admin_id


def buttons(rows):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=text, callback_data=data) for text, data in row]
        for row in rows])


class Store:
    def __init__(self, db):
        self.db = db
        db._exec('''CREATE TABLE IF NOT EXISTS ae_broadcast_jobs (
            id TEXT PRIMARY KEY, admin_id BIGINT NOT NULL,
            source_chat BIGINT NOT NULL, source_message BIGINT NOT NULL,
            state TEXT NOT NULL, owner TEXT NOT NULL, created DOUBLE PRECISION NOT NULL
        )''')
        db._exec('''CREATE TABLE IF NOT EXISTS ae_broadcast_targets (
            job_id TEXT NOT NULL, user_id BIGINT NOT NULL, state TEXT NOT NULL,
            PRIMARY KEY(job_id, user_id)
        )''')

    def draft(self, admin, chat, message):
        token = secrets.token_hex(8)
        self.db._exec('UPDATE ae_broadcast_jobs SET state=? WHERE admin_id=? AND state=?',
                      ('cancelled', admin, 'draft'))
        self.db._exec('INSERT INTO ae_broadcast_jobs(id,admin_id,source_chat,source_message,state,owner,created) VALUES(?,?,?,?,?,?,?)',
                      (token, admin, chat, message, 'draft', '', time.time()))
        self.db._exec('INSERT INTO ae_broadcast_targets(job_id,user_id,state) SELECT ?,user_id,? FROM users WHERE user_id > 0',
                      (token, 'pending'))
        return token

    def get(self, token, admin):
        row = self.db._one('SELECT * FROM ae_broadcast_jobs WHERE id=? AND admin_id=?', (token, admin))
        return dict(row) if row else None

    def latest(self, admin):
        row = self.db._one('SELECT * FROM ae_broadcast_jobs WHERE admin_id=? ORDER BY created DESC LIMIT 1', (admin,))
        return dict(row) if row else None

    def claim(self, token, admin):
        job = self.get(token, admin)
        if not job or job['state'] != 'draft' or time.time() - job['created'] > 600:
            return None
        owner = secrets.token_hex(12)
        self.db._exec('UPDATE ae_broadcast_jobs SET state=?,owner=? WHERE id=? AND admin_id=? AND state=?',
                      ('running', owner, token, admin, 'draft'))
        job = self.get(token, admin)
        return job if job and job['owner'] == owner else None

    def state(self, token, state):
        self.db._exec('UPDATE ae_broadcast_jobs SET state=? WHERE id=?', (state, token))

    def cancel_draft(self, token, admin):
        self.db._exec('UPDATE ae_broadcast_jobs SET state=? WHERE id=? AND admin_id=? AND state=?',
                      ('cancelled', token, admin, 'draft'))

    def batch(self, token):
        return [int(r['user_id']) for r in self.db._all(
            'SELECT user_id FROM ae_broadcast_targets WHERE job_id=? AND state=? ORDER BY user_id LIMIT 100',
            (token, 'pending'))]

    def target(self, token, uid, state):
        self.db._exec('UPDATE ae_broadcast_targets SET state=? WHERE job_id=? AND user_id=?', (state, token, uid))

    def counts(self, token):
        result = {key: 0 for key in ('pending', 'sending', 'sent', 'failed', 'unknown')}
        for row in self.db._all('SELECT state,COUNT(*) AS n FROM ae_broadcast_targets WHERE job_id=? GROUP BY state', (token,)):
            result[row['state']] = int(row['n'])
        return result


def report(job, counts):
    labels = {'draft':'Tasdiq kutilmoqda', 'running':'Yuborilmoqda', 'done':'Tugadi',
              'cancelled':'Bekor qilindi', 'stopped':'To‘xtatildi', 'interrupted':'Uzilib qoldi'}
    total = sum(counts.values())
    return (f'📣 Tarqatish: {labels.get(job["state"], job["state"])}\n\n'
            f'👥 Jami: {total}\n✅ Yuborildi: {counts["sent"]}\n'
            f'🚫 Yuborilmadi: {counts["failed"]}\n'
            f'❔ Natijasi noaniq: {counts["unknown"] + counts["sending"]}\n'
            f'⏳ Qolgan: {counts["pending"]}\n\n'
            'Hisobotdagi “yuborildi” xabar o‘qilganini bildirmaydi.')


async def pause(stop, seconds):
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


async def copy_one(bot, job, uid, stop):
    for attempt in range(3):
        if stop.is_set():
            return 'pending'
        try:
            await bot.copy_message(chat_id=uid, from_chat_id=job['source_chat'],
                                   message_id=job['source_message'],
                                   reply_markup=InlineKeyboardMarkup(inline_keyboard=[]))
            return 'sent'
        except TelegramRetryAfter as exc:
            if attempt == 2:
                return 'failed'
            await pause(stop, exc.retry_after + 0.5)
        except (TelegramForbiddenError, TelegramBadRequest):
            return 'failed'
        except Exception:
            # Tarmoq uzilganda xabar yetgan bo'lishi mumkin: qayta yuborib takrorlamaymiz.
            log.warning('Broadcast natijasi noaniq: job=%s user=%s', job['id'], uid, exc_info=True)
            return 'unknown'
    return 'failed'


async def deliver(bot, store, job, stop):
    token = job['id']
    try:
        while not stop.is_set():
            targets = await run(store.batch, token)
            if not targets:
                break
            for uid in targets:
                if stop.is_set():
                    break
                await run(store.target, token, uid, 'sending')
                state = await copy_one(bot, job, uid, stop)
                await run(store.target, token, uid, state)
                await pause(stop, PACE)
        await run(store.state, token, 'stopped' if stop.is_set() else 'done')
    except asyncio.CancelledError:
        await run(store.state, token, 'interrupted')
        raise
    except Exception:
        log.exception('Broadcast jarayoni uzildi: %s', token)
        await run(store.state, token, 'interrupted')


@router.message(Command('broadcast'))
async def cmd_broadcast(message, command, db, cfg):
    uid = message.from_user.id
    if not allowed(cfg, uid):
        await message.answer('🔒 Bu buyruq faqat administrator uchun.')
        return
    if uid in RUNNING:
        await message.answer('Hozir tarqatish davom etyapti. /broadcast_status yoki /broadcast_stop')
        return
    text = (command.args or '').strip()
    source = message.reply_to_message
    if text and source:
        await message.answer('Matn yoki reply usulidan bittasini tanlang.\n\n' + HELP)
        return
    if not text and not source:
        await message.answer(HELP)
        return
    if source and not any(getattr(source, kind, None) for kind in (
            'text','photo','video','animation','audio','voice','video_note','document','sticker')):
        await message.answer('Matn, rasm, video, ovoz yoki faylga reply qiling. Albomdan faqat tanlangan bitta xabar olinadi.')
        return
    store = await run(Store, db)
    # Namuna alohida nusxa: asl xabar keyin tahrirlansa tarqatish mazmuni o'zgarmaydi.
    try:
        if text:
            preview = await message.answer(text, parse_mode=None)
            preview_id = preview.message_id
        else:
            preview = await message.bot.copy_message(chat_id=message.chat.id,
                from_chat_id=source.chat.id, message_id=source.message_id,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[]))
            preview_id = preview.message_id
    except TelegramBadRequest:
        await message.answer('Bu xabarni nusxalab bo‘lmadi. Himoyalanmagan matn yoki fayl yuboring.')
        return
    token = await run(store.draft, uid, message.chat.id, preview_id)
    count = sum((await run(store.counts, token)).values())
    if not count:
        await run(store.cancel_draft, token, uid)
        await message.answer('Bazada foydalanuvchilar yo‘q.')
        return
    await message.answer(
        f'📣 Yuqoridagi namuna {count} ta foydalanuvchiga yuboriladi.\n'
        'Tasdiq 10 daqiqa amal qiladi. Bloklagan foydalanuvchilarga yetmasligi mumkin.',
        reply_markup=buttons([[('✅ Yuborish', f'bc:send:{token}'),
                               ('❌ Bekor qilish', f'bc:cancel:{token}')]]))


@router.message(Command('broadcast_stop'))
async def cmd_stop(message, cfg):
    uid = message.from_user.id
    if not allowed(cfg, uid):
        return
    running = RUNNING.get(uid)
    if running:
        running[1].set()
        await message.answer('⏹ To‘xtatilmoqda. Oldin yuborilgan xabarlar o‘chirilmaydi.')
    else:
        await message.answer('Hozir tarqatish yo‘q.')


@router.message(Command('broadcast_status'))
async def cmd_status(message, db, cfg):
    uid = message.from_user.id
    if not allowed(cfg, uid):
        return
    store = await run(Store, db)
    job = await run(store.latest, uid)
    if not job:
        await message.answer('Hali tarqatish tayyorlanmagan. /broadcast')
        return
    if job['state'] == 'running' and uid not in RUNNING:
        await run(store.state, job['id'], 'interrupted')
        job['state'] = 'interrupted'
    await message.answer(report(job, await run(store.counts, job['id'])))


@router.callback_query(F.data.startswith('bc:'))
async def cb_broadcast(call, db, cfg):
    uid = call.from_user.id
    if not allowed(cfg, uid) or not call.message or call.message.chat.type != 'private':
        await call.answer('🔒 Faqat administrator uchun.', show_alert=True)
        return
    parts = (call.data or '').split(':')
    if len(parts) != 3:
        await call.answer()
        return
    _, action, token = parts
    store = await run(Store, db)
    job = await run(store.get, token, uid)
    if not job:
        await call.answer('Tarqatish topilmadi.', show_alert=True)
        return
    if action == 'cancel':
        await run(store.cancel_draft, token, uid)
        await call.answer('Bekor qilindi')
        with contextlib.suppress(TelegramBadRequest):
            await call.message.edit_reply_markup(reply_markup=None)
        return
    if action == 'stop':
        current = RUNNING.get(uid)
        if current and current[0] == token:
            current[1].set()
        await call.answer('To‘xtatilmoqda')
        return
    if action != 'send':
        await call.answer()
        return
    if uid in RUNNING:
        await call.answer('Boshqa tarqatish davom etmoqda.', show_alert=True)
        return
    # Ikki callback bir paytda kelsa ham bir foydalanuvchi uchun bitta jarayon.
    stop = asyncio.Event()
    RUNNING[uid] = (token, stop)
    try:
        job = await run(store.claim, token, uid)
        if not job:
            await call.answer('Bu tasdiq eskirgan yoki ishlatilgan.', show_alert=True)
            return
        await call.answer('Yuborish boshlandi')
        with contextlib.suppress(TelegramBadRequest):
            await call.message.edit_text('📣 Yuborilmoqda…\nHolat: /broadcast_status',
                reply_markup=buttons([[('⏹ To‘xtatish', f'bc:stop:{token}')]]))
        await deliver(call.bot, store, job, stop)
        job = await run(store.get, token, uid)
        body = report(job, await run(store.counts, token))
        try:
            await call.message.edit_text(body, reply_markup=None)
        except TelegramBadRequest:
            await call.message.answer(body)
    finally:
        if RUNNING.get(uid, (None,))[0] == token:
            RUNNING.pop(uid, None)
