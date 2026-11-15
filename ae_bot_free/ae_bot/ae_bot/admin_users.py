"""Admin uchun foydalanuvchilar ro'yxati. SQLite/PostgreSQL bilan ishlaydi."""
from __future__ import annotations

import logging
from datetime import timedelta
from html import escape

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from db import run, today
from bot_activity import activity_text

router = Router(name='ae_admin_users')
router.message.filter(F.chat.type == 'private')
log = logging.getLogger(__name__)
PAGE_SIZE = 8
ACTIVE_SQL = '(requests > 0 OR images > 0 OR voice_seconds > 0)'


def is_admin(cfg, uid):
    return bool(cfg.admin_id) and uid == cfg.admin_id


def admin_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='👥 Foydalanuvchilar', callback_data='au:users:0')],
        [InlineKeyboardButton(text='📊 Statistikani yangilash', callback_data='au:home')],
    ])


def summary(db):
    from datetime import date
    day = today()
    start = (date.fromisoformat(day) - timedelta(days=29)).isoformat()
    total = db._one('SELECT COUNT(*) AS n FROM users')['n']
    joined = db._one('SELECT COUNT(*) AS n FROM users WHERE created_at >= ? AND created_at < ?',
                     (day, (date.fromisoformat(day) + timedelta(days=1)).isoformat()))['n']
    active_today = db._one('SELECT COUNT(DISTINCT user_id) AS n FROM usage WHERE day = ? AND ' + ACTIVE_SQL,
                           (day,))['n']
    active_month = db._one('SELECT COUNT(DISTINCT user_id) AS n FROM usage WHERE day >= ? AND day <= ? AND ' + ACTIVE_SQL,
                           (start, day))['n']
    return {'total': int(total), 'joined': int(joined), 'today': int(active_today),
            'month': int(active_month), 'day': day}


def read_page(db, page):
    stats = summary(db)
    pages = max(1, (stats['total'] + PAGE_SIZE - 1) // PAGE_SIZE)
    page = min(max(0, page), pages - 1)
    rows = db._all('''
        SELECT u.user_id, u.name, u.created_at,
            (SELECT MAX(day) FROM usage a WHERE a.user_id = u.user_id
             AND (a.requests > 0 OR a.images > 0 OR a.voice_seconds > 0)) AS last_day
        FROM users u ORDER BY u.created_at DESC, u.user_id DESC LIMIT ? OFFSET ?
    ''', (PAGE_SIZE, page * PAGE_SIZE))
    return stats, [dict(row) for row in rows], page, pages


def header(stats):
    return ('👥 <b>Foydalanuvchilar</b>\n\n'
            f'👤 Jami: <b>{stats["total"]:,}</b>\n'
            f'🆕 Bugun qo‘shilgan: <b>{stats["joined"]:,}</b>\n'
            f'🟢 Bugun foydalangan: <b>{stats["today"]:,}</b>\n'
            f'📅 Oxirgi 30 kunda foydalangan: <b>{stats["month"]:,}</b>\n'
            f'🕒 Sana: {stats["day"]} — Toshkent vaqti\n'
            '<i>Faollik bazadagi AI so‘rovi, rasm yoki ovoz ishlatilishiga asoslanadi.</i>')


def page_view(db, page):
    stats, users, page, pages = read_page(db, page)
    parts = [header(stats), f'\n📋 <b>Ro‘yxat — {page + 1}/{pages}</b>']
    for index, user in enumerate(users, start=page * PAGE_SIZE + 1):
        name = escape((user['name'] or 'Ismi saqlanmagan')[:70])
        created = escape(str(user['created_at'])[:10])
        last = escape(str(user['last_day'] or 'Faollik qayd etilmagan'))
        parts.append(f'\n<b>{index}. {name}</b>\n'
                     f'🆔 <code>{int(user["user_id"])}</code>\n'
                     f'📥 Qo‘shilgan: {created}\n'
                     f'🗓 Oxirgi foydalanish: {last}')
    if not users:
        parts.append('\nHozircha foydalanuvchilar yo‘q.')
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text='⬅️ Oldingi', callback_data=f'au:users:{page-1}'))
    if page + 1 < pages:
        nav.append(InlineKeyboardButton(text='Keyingi ➡️', callback_data=f'au:users:{page+1}'))
    rows = [nav] if nav else []
    rows += [[InlineKeyboardButton(text='🔄 Yangilash', callback_data=f'au:users:{page}')],
             [InlineKeyboardButton(text='⚙️ Admin panel', callback_data='au:home')]]
    return '\n'.join(parts), InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command('admin'))
async def cmd_admin(message, db, cfg):
    if not is_admin(cfg, message.from_user.id):
        await message.answer('🔒 Bu bo‘lim faqat administrator uchun.')
        return
    stats = await run(summary, db)
    await message.answer('⚙️ <b>Admin panel</b>\n\n' + activity_text() + '\n\n' + header(stats),
                         parse_mode=ParseMode.HTML, reply_markup=admin_keyboard())


@router.message(Command('activity'))
async def cmd_activity(message, cfg):
    # Eski buyruq faqat admin uchun; umumiy menyuda ko'rsatilmaydi.
    if is_admin(cfg, message.from_user.id):
        await message.answer(activity_text())


@router.message(Command('users'))
@router.message(F.text == '👥 Foydalanuvchilar')
async def cmd_users(message, db, cfg):
    if not is_admin(cfg, message.from_user.id):
        await message.answer('🔒 Bu bo‘lim faqat administrator uchun.')
        return
    body, keyboard = await run(page_view, db, 0)
    await message.answer(body, parse_mode=ParseMode.HTML, reply_markup=keyboard)


@router.callback_query(F.data.startswith('au:'))
async def cb_admin(call, db, cfg):
    message = call.message
    if not is_admin(cfg, call.from_user.id) or not message or message.chat.type != 'private':
        await call.answer('🔒 Bu bo‘lim faqat administrator uchun.', show_alert=True)
        return
    await call.answer()
    try:
        if call.data == 'au:home':
            stats = await run(summary, db)
            body = '⚙️ <b>Admin panel</b>\n\n' + activity_text() + '\n\n' + header(stats)
            keyboard = admin_keyboard()
        elif call.data.startswith('au:users:'):
            value = call.data.rsplit(':', 1)[-1]
            if not value.isdecimal() or len(value) > 8:
                return
            body, keyboard = await run(page_view, db, int(value))
        else:
            return
        await message.edit_text(body, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    except TelegramBadRequest as exc:
        if 'not modified' not in str(exc).lower():
            log.warning('Admin panel tahrirlash xatosi: %s', exc)
