"""Tugmalar: pastki menyu va xabar ostidagi (inline) tugmalar."""
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

import texts


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=texts.BTN_NEW), KeyboardButton(text=texts.BTN_TOPICS)],
            [KeyboardButton(text=texts.BTN_IMAGE), KeyboardButton(text=texts.BTN_SETTINGS)],
            [KeyboardButton(text=texts.BTN_HELP)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Savolingizni yozing yoki ovoz yuboring…",
    )


def stop_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⏹ To'xtatish", callback_data="stop")]]
    )


def topics_kb(topics: list, current_id: int) -> InlineKeyboardMarkup:
    rows = []
    for t in topics:
        mark = "✅ " if t["id"] == current_id else "💬 "
        title = t["title"] if len(t["title"]) <= 28 else t["title"][:27] + "…"
        rows.append(
            [
                InlineKeyboardButton(text=mark + title, callback_data=f"topic:{t['id']}"),
                InlineKeyboardButton(text="🗑", callback_data=f"deltopic:{t['id']}"),
            ]
        )
    rows.append([InlineKeyboardButton(text="➕ Yangi suhbat", callback_data="newtopic")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def settings_kb(voice_on: bool) -> InlineKeyboardMarkup:
    label = "🔊 Ovozli javob: ✅ yoqilgan" if voice_on else "🔊 Ovozli javob: ⛔ o'chiq"
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=label, callback_data="toggle_voice")]]
    )
