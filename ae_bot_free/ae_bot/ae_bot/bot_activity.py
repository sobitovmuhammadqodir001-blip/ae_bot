"""Botning ilk ishga tushish sanasidan faoliyat muddati."""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone

UZ_TZ = timezone(timedelta(hours=5))


def activity_text(started=None, on_day=None):
    """BOT_STARTED_AT=YYYY-MM-DD. Server qayta ishga tushsa muddat nol bo'lmaydi."""
    value = started if started is not None else os.getenv('BOT_STARTED_AT', '2026-11-15')
    now = datetime.now(UZ_TZ)
    current = on_day or now.date()
    try:
        first = date.fromisoformat(value.strip())
    except (ValueError, AttributeError, TypeError):
        return '🟢 AE Yordamchi faol.'
    if first > current:
        return '🟢 AE Yordamchi faol.'
    days = (current - first).days
    months = ((current.year - first.year) * 12 + current.month - first.month
              - int(current.day < first.day))
    if days == 0:
        period = 'Bugundan beri'
    elif months < 1:
        period = f'{days} kundan beri'
    elif months < 12:
        period = f'{months} oydan beri'
    else:
        years, remaining = divmod(months, 12)
        period = f'{years} yil' + (f' {remaining} oy' if remaining else '') + 'dan beri'
    return (f'🟢 AE Yordamchi — {period} faol.\n📅 Ishga tushgan: {first:%d.%m.%Y}'
            f'\n🕒 Toshkent vaqti: {now:%d.%m.%Y %H:%M}')
