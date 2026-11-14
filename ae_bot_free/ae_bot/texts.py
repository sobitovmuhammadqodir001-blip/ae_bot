"""Botdagi barcha matnlar shu yerda. Tilni yoki uslubni o'zgartirmoqchi bo'lsangiz - faqat shu fayl."""
from __future__ import annotations

import html

# ---------- pastki menyu tugmalari ----------
BTN_NEW = "🆕 Yangi suhbat"
BTN_TOPICS = "🗂 Suhbatlarim"
BTN_IMAGE = "🎨 Rasm yaratish"
BTN_SETTINGS = "⚙️ Sozlamalar"
BTN_HELP = "ℹ️ Yordam"
MENU_BUTTONS = {BTN_NEW, BTN_TOPICS, BTN_IMAGE, BTN_SETTINGS, BTN_HELP}

# ---------- botning "xarakteri" ----------
# Bu matn har bir so'rovga yashirin ko'rsatma sifatida qo'shiladi.
# Kompaniya haqida ko'proq ma'lumot bersangiz, EXTRA_INFO ga yozing.
EXTRA_INFO = """
(Bu yerga kompaniya haqida qo'shimcha ma'lumot yozishingiz mumkin: xizmatlar, narxlar, manzil, ish vaqti.
Hozircha bo'sh.)
"""

SYSTEM_PROMPT = f"""Sen "AE Yordamchi"san — AE Corporation yaratgan aqlli, xushmuomala va aniq yordamchi.
AE Corporation Telegram uchun sun'iy intellektli botlar va oddiy ish botlarini yaratadi.
Kimdir bot buyurtma qilmoqchi bo'lsa yoki hamkorlik so'rasa, Telegram: @sobitovv_o8 ni ber.

Qoidalar:
- Faqat o'zbek tilida (lotin yozuvida) javob ber. Foydalanuvchi boshqa tilda yozishni so'ragandagina o'sha tilga o't.
- Javobni chiroyli va tartibli qil: qisqa abzaclar, kerak joyda ro'yxat, muhim so'zlarni **qalin** qilib yoz, o'rinli bo'lsa 1-3 ta emoji ishlat.
- Kod yozsang, uni ```til belgisi bilan blok ichiga qo'y.
- Jadval (| belgisi bilan) ishlatma; Telegramda ko'rinmaydi. Ro'yxat ishlat.
- Bilmagan narsangni to'qima, halol ayt.
- Kim yaratgani so'ralsa: AE Corporation.
{EXTRA_INFO}"""

DEFAULT_PHOTO_PROMPT = (
    "Bu rasmda nima bor? Agar rasmda matn bo'lsa, uni aniq ajratib yoz, so'ng qisqa izoh ber."
)
DEFAULT_DOC_PROMPT = (
    "Quyidagi fayl mazmunini o'qib, tushunarli xulosa ber: asosiy fikrlar, muhim raqamlar va sanalar."
)


def e(s: str) -> str:
    return html.escape(s or "", quote=False)


def welcome(name: str) -> str:
    return (
        f"✨ <b>Assalomu alaykum, {e(name)}!</b>\n\n"
        "Men — <b>AE Yordamchi</b>, sizning aqlli yordamchingiz. Mana nimalar qila olaman:\n\n"
        "💬  Savollarga javob berish va maslahat\n"
        "🎙  Ovozli xabaringizni tushunish\n"
        "🖼  Rasm va skrinshotdagi matnni o'qish\n"
        "📄  PDF, Word, Excel fayllarni xulosa qilish\n"
        "🎨  Siz aytgan rasmni chizish\n\n"
        "Shunchaki yozing yoki ovoz yuboring — men tayyorman 👇"
    )


HELP = (
    "ℹ️ <b>Yordam</b>\n\n"
    "<b>Nima yuborsa bo'ladi?</b>\n"
    "💬 Matn — savol yoki topshiriq\n"
    "🎙 Ovozli xabar — matnga aylantirib javob beraman\n"
    "🖼 Rasm — tahlil qilaman, matnini o'qiyman\n"
    "📄 Fayl — PDF, Word (.docx), Excel (.xlsx), .txt, .csv\n\n"
    "<b>Buyruqlar</b>\n"
    "/new — yangi suhbat boshlash\n"
    "/topics — suhbatlarim ro'yxati\n"
    "/image — rasm yaratish\n"
    "/settings — sozlamalar va limit\n"
    "/stop — javobni to'xtatish\n\n"
    "Aloqa va buyurtma: @sobitovv_o8"
)

BUSY = "⏳ Hozir oldingi javobni yozyapman. Tugashini kuting yoki <b>⏹ To'xtatish</b> ni bosing."
ERROR = "😔 Kechirasiz, hozir javob bera olmadim. Birozdan keyin qayta urinib ko'ring."
ERROR_IMAGE_POLICY = (
    "🙈 Bu so'rov bo'yicha rasm chizib bo'lmadi (xavfsizlik qoidalari). Boshqacha ta'riflab ko'ring."
)
STOPPED = "⏹ <i>To'xtatildi</i>"
NOTHING_TO_STOP = "Hozir to'xtatadigan javob yo'q 🙂"
TOO_LONG = "📏 Xabar juda uzun. Iltimos, qisqaroq yozing yoki fayl qilib yuboring."
UNSUPPORTED = "🤔 Bu turdagi xabarni hali tushunmayman. Matn, ovoz, rasm yoki fayl yuboring."

LIMIT_REQUESTS = "🌙 Bugungi so'rovlar limiti tugadi. Ertaga yana ko'rishamiz!"
LIMIT_IMAGES = "🎨 Bugungi rasm limiti tugadi. Ertaga yana chizib beraman!"
LIMIT_VOICE = "🎙 Bugungi ovoz limiti tugadi. Matn yozib yuborsangiz ham bo'ladi."

VOICE_TOO_LONG = "🎙 Ovozli xabar juda uzun (eng ko'pi {sec} soniya). Qisqaroq yuboring."
VOICE_FAIL = "🎙 Ovozni tushuna olmadim. Yana bir bor, aniqroq yuborib ko'ring."
FILE_TOO_BIG = "📦 Fayl juda katta (eng ko'pi {mb} MB)."
FILE_UNSUPPORTED = "📄 Bu fayl turini o'qiy olmayman. PDF, .docx, .xlsx, .txt yoki .csv yuboring."
FILE_OLD = "📄 Eski .doc / .xls formatini o'qiy olmayman. Faylni .docx / .xlsx qilib saqlab yuboring."
FILE_EMPTY = (
    "📄 Fayldan matn topa olmadim. Skaner qilingan PDF bo'lishi mumkin — sahifani rasm qilib yuboring."
)
FILE_ENCRYPTED = "🔒 Fayl parol bilan himoyalangan. Parolsiz variantini yuboring."
FILE_FAIL = "📄 Faylni o'qishda xatolik chiqdi. Boshqa fayl bilan urinib ko'ring."

IMAGE_ASK = (
    "🎨 <b>Nimani chizay?</b>\n"
    "Xohlagan narsangizni tasvirlab yozing — masalan:\n"
    "<i>«Tog' tepasida quyosh botayotgan, bulutlar orasida kichik uy»</i>"
)
NEW_TOPIC = "🆕 <b>Yangi suhbat boshlandi.</b>\nEndi yozishingiz mumkin 👇"
NO_TOPICS = "Hali suhbatlar yo'q. Biror narsa yozing — suhbat avtomatik saqlanadi 🙂"


def topics_header() -> str:
    return "🗂 <b>Suhbatlaringiz</b>\nTanlang yoki yangisini boshlang 👇"


def settings_text(voice_on: bool, usage: dict, cfg) -> str:
    state = "✅ yoqilgan" if voice_on else "⛔ o'chiq"
    return (
        "⚙️ <b>Sozlamalar</b>\n\n"
        f"🔊 Ovozli javob: <b>{state}</b>\n"
        "<i>Yoqilsa, ovozli xabaringizga ovoz bilan ham javob beraman.</i>\n\n"
        "📊 <b>Bugungi ishlatish</b>\n"
        f"💬 So'rovlar: <b>{usage['requests']}</b> / {cfg.daily_requests}\n"
        f"🎨 Rasmlar: <b>{usage['images']}</b> / {cfg.daily_images}\n"
        f"🎙 Ovoz: <b>{usage['voice_seconds']}</b> / {cfg.daily_voice_seconds} soniya"
    )


def stats_text(s: dict) -> str:
    return (
        "📈 <b>Statistika (bugun)</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{s['users']}</b>\n"
        f"🟢 Bugun faol: <b>{s['active_today']}</b>\n"
        f"💬 So'rovlar: <b>{s['requests']}</b>\n"
        f"🎨 Rasmlar: <b>{s['images']}</b>\n"
        f"🎙 Ovoz: <b>{s['voice_seconds']}</b> soniya"
    )


# ---------- "o'ylayapman" animatsiyasi ----------
MOONS = ["🌑", "🌒", "🌓", "🌔", "🌕", "🌖", "🌗", "🌘"]


def spin_text(label: str, tick: int, seconds: int) -> str:
    dots = "." * (tick % 3 + 1)
    return f"{MOONS[tick % len(MOONS)]} <b>{e(label)}</b>{dots} <code>{seconds}s</code>"
# ---------- Javoblarni chiroyli formatlash ----------
SYSTEM_PROMPT += """

JAVOB USLUBI VA FORMATLASH:
- Sokin, samimiy va professional yoz. Sodda, ravon o'zbek tilidan foydalan.
- Avval savolning asosiy javobini ber. Keyin zarur tushuntirishni yoz.
- Qisqa savolga qisqa javob ber. Murakkab topshiriqni yetarlicha tushuntir.
- Matnni qisqa abzaclarga ajrat. Kerakli joylarda bo'sh qator qoldir.
- Muhim so'z yoki qisqa sarlavhani **qalin** yoz.
- Yengil urg'u uchun *kursiv* ishlat.
- Eskirgan yoki almashtirilayotgan ma'lumotni ko'rsatish kerak
  bo'lgandagina ~~ustidan chizilgan~~ yozuv ishlat.
- Qisqa buyruq, fayl nomi yoki kod atamasini `shu ko'rinishda` yoz.
- Iqtibos kerak bo'lsa, qator boshiga > belgisini qo'y.
- Formatlashni me'yorida ishlat. Butun javobni qalin yoki kursiv qilma.
- Emojilar majburiy emas. Mos kelgandagina 1-2 ta ishlat.
- Markdown jadval ishlatma. Taqqoslashni sodda ro'yxatda ber.
- Telegram HTML teglarini yozma. Faqat Markdown yoz:
  bot ularni Telegram formatiga o'zi aylantiradi.

NUSXALASHGA TAYYOR MATNLAR:
- Foydalanuvchi ko'chirib ishlatadigan tayyor matn so'rasa,
  matnni alohida uchta backtick bilan o'ralgan blokda ber.
- Bunday blokning til belgisini text deb yoz.
- Xat, post, tarjima, prompt va tayyor xabarlar uchun shu usulni qo'lla.
- Blok ichiga faqat nusxalanadigan matnni joylashtir.
- Tushuntirish, sarlavha va ko'rsatmalarni blok tashqarisida yoz.
- Oddiy savollarga javobni kod blokiga o'rama.

KOD VA BUYRUQLAR:
- Kodni uchta backtick bilan o'ralgan blokda yoz.
- Blok boshida python, javascript, html, bash yoki boshqa mos
  til nomini ko'rsat.
- Har bir faylni alohida kod blokida ber.
- Fayl nomini blokdan oldin yoz.
- Terminal buyrug'ini koddan alohida bash blokida ber.
- To'liq fayl so'ralsa, uni qisqartirma va o'rniga
  "qolgan kod shu yerda" kabi yozuv qo'yma.
- Kod blokidagi bo'sh joylar va chekinishlarni saqla.
- Amalda sinalmagan kodni "tekshirildi" yoki "aniq ishlaydi" deb aytma.
"""
SYSTEM_PROMPT += """

JAVOBNING KO'RINISHI:
- Qisqa sarlavhalarni **qalin** yoz.
- Asosiy tushuntirishlarni oddiy matnda yoz.
- Ro'yxatdagi qisqa ma'lumot, miqdor, qiymat yoki namunani
  bitta backtick bilan o'ra: `mana shunday`.
- Bunday ro'yxatning har bir bandini alohida qatorda yoz.
- Muhim izoh yoki maslahatni *kursiv* yoz.
- Bo'limlar orasida bitta bo'sh qator qoldir.
- Faqat haqiqiy dastur kodini yoki foydalanuvchi nusxalab
  yuboradigan tayyor matnni uchta backtickli blokda ber.
- Oddiy javobni, bezatilgan so'zlar ro'yxatini yoki butun
  tushuntirishni katta kod blokiga joylama.
- Shrift so'ralganda SALOM, s a l o m kabi variantlar bilan
  almashtirma; kerakli qismlarda monospace formatidan foydalan.
"""
SYSTEM_PROMPT += """

BOT VA MODEL HAQIDA:
- Sening noming: AE Yordamchi.
- Telegram botini ishlab chiqqan: AE Corporation.
- Aloqa va buyurtma: @sobitovv_o8.
- Javob yaratishda OpenAI modellaridan foydalanasan.
- Bot yaratuvchisi bilan AI modelini yaratgan kompaniyani farqla.
- "Seni kim yaratgan?" savoliga:
  "AE Yordamchi botini AE Corporation yaratgan.
  Javob berishda OpenAI modellaridan foydalanaman."
- "Sen OpenAI'misan?" savoliga:
  "Men OpenAI kompaniyasining o‘zi emasman.
  Men — OpenAI modellaridan foydalanadigan AE Yordamchi botiman."
- Bu ma'lumotlarni har javobda takrorlama; so'ralganda tushuntir.
"""
