# AE Yordamchi — Telegram bot (qo'llanma)

Bu papka botning to'liq kodi. Tokenlar kodda YO'Q — ular Render'ning **Environment** bo'limida turadi.

## Fayllar nima qiladi

| Fayl | Vazifasi |
|---|---|
| `main.py` | Botni ishga tushiradi |
| `config.py` | Sozlamalar (hammasi muhit o'zgaruvchilaridan o'qiladi) |
| `texts.py` | **Barcha matnlar va botning "xarakteri"** (o'zgartirmoqchi bo'lsangiz — shu yerda) |
| `keyboards.py` | Tugmalar |
| `core.py` | Javob yozish: "O'ylayapman… 3s", jonli yozish, ⏹ To'xtatish, limitlar |
| `ai.py` | OpenAI bilan aloqa: suhbat, ovoz→matn, matn→ovoz, rasm yaratish |
| `db.py` | SQLite xotira: suhbatlar, xabarlar, kunlik limitlar |
| `docs.py` | PDF / Word / Excel dan matn ajratish |
| `formatting.py` | Javobni Telegram uchun chiroyli qilish (qalin, kod bloklari…) |
| `handlers/` | Buyruqlar va xabarlarni qabul qilish |
| `render.yaml` | Render uchun tayyor sozlama |

## 1-qadam. Kompyuterdagi botni to'xtating
Qora oynani (`python main.py`) yoping. Bitta token ikki joyda ishlamaydi — aks holda Render loglarida `Conflict: terminated by other getUpdates request` xatosi chiqadi.

## 2-qadam. GitHub (private)
1. github.com → **New repository** → nomi `ae-bot` → **Private**.
2. Shu papkadagi fayllarni yuklang (`.env` fayl bo'lsa — yuklamang; `.gitignore` uni o'zi to'sadi).

## 3-qadam. Render
1. render.com → **New +** → **Background Worker** → GitHub repo'ni tanlang.
2. Region: **Frankfurt**. Instance type: **Starter**.
3. Build Command: `pip install -r requirements.txt`
4. Start Command: `python main.py`
5. **Environment** → quyidagilarni qo'shing:

| Nomi | Qiymati |
|---|---|
| `TELEGRAM_BOT_TOKEN` | BotFather bergan token |
| `OPENAI_API_KEY` | OpenAI kaliti |
| `ADMIN_ID` | Sizning Telegram ID raqamingiz (@userinfobot dan bilib oling) |
| `DB_PATH` | `/data/bot.db` |

6. **Disks** → Add Disk: nomi `ae-data`, Mount Path `/data`, hajmi `1 GB`.
   (Disk bo'lmasa, har deployda suhbat xotirasi o'chib ketadi.)
7. **Create** bosing. **Logs** da `Bot ishga tushdi: @...` yozuvi chiqsa — tayyor.

Narxlar va karta talablarini render.com/pricing da tekshiring.

## Sinab ko'rish ro'yxati
1. `/start` — chiroyli salomlashuv va pastki menyu chiqadi
2. Oddiy savol — "🌒 O'ylayapman… 2s" → javob jonli yoziladi, ostida ⏹ tugmasi
3. Ovozli xabar yuboring — "🎙 «…»" ko'rinadi va javob keladi
4. `⚙️ Sozlamalar` → 🔊 Ovozli javobni yoqing → yana ovoz yuboring → javob ovoz bilan ham keladi
5. Rasm yuboring (skrinshot ham) — matnini o'qib beradi
6. PDF / Word / Excel yuboring — xulosa qiladi
7. `🎨 Rasm yaratish` — tavsif yozing

## Modellar (muhim)
OpenAI modellarni tez-tez almashtiradi. Nomlar **Render → Environment** da o'zgartiriladi, kodga tegish shart emas.

| O'zgaruvchi | Hozirgi qiymat | Izoh |
|---|---|---|
| `OPENAI_MODEL` | `gpt-6-luna` | Eng arzon GPT-6 modeli, rasmni ham tushunadi |
| `OPENAI_REASONING` | `low` | Tezlik/narx uchun. Model qabul qilmasa, bot o'zi usiz urinadi |
| `STT_MODEL` | `gpt-transcribe` | Ovoz → matn |
| `STT_LANGUAGES` | bo'sh | Aniqlash yomon bo'lsa `uz` yoki `uz,ru` qo'ying |
| `IMAGE_MODEL` | `gpt-image-2` | Rasm yaratish (OpenAI hisobi tasdiqlanishi talab qilinishi mumkin) |
| `TTS_PROVIDER` | `edge` | Bepul, o'zbekcha ovoz (`uz-UZ-MadinaNeural`; erkak ovozi: `uz-UZ-SardorNeural`) |

Eslatma: OpenAI'ning o'z ovoz modellari (`gpt-4o-mini-tts`, `tts-1`) 2027-yil 6-yanvarda o'chiriladi, shuning uchun standart sifatida `edge` tanlangan. Modellar ro'yxati: developers.openai.com/api/docs/deprecations

## Xarajatni nazorat qilish (har foydalanuvchiga, kuniga)
`DAILY_REQUESTS` (100), `DAILY_IMAGES` (5), `DAILY_VOICE_SECONDS` (600), `MAX_VOICE_SECONDS` (120), `MAX_FILE_MB` (15).
`ADMIN_ID` egasiga limit qo'llanmaydi, `/stats` buyrug'i faqat unga ishlaydi. OpenAI hisobida mablag' tugasa, admin xabar oladi.
OpenAI panelida ham oylik **Spend limit** qo'yib qo'yishni tavsiya qilaman.

## Tez-tez uchraydigan muammolar
- **Bot javob bermayapti, logda `Conflict`** — bot boshqa joyda ham ishlayapti (kompyuterda yoki ikkinchi servis). Birini to'xtating.
- **`model_not_found` / 404** — `OPENAI_MODEL` nomi eskirgan. Yangisini Environment'da yozing.
- **`insufficient_quota`** — OpenAI hisobiga mablag' qo'shing.
- **Rasm yaratilmayapti** — `IMAGE_MODEL` uchun OpenAI hisobi tasdiqlanishi kerak bo'lishi mumkin, yoki nom eskirgan.
- **Ovoz kelmayapti, matn keladi** — logda `Ovozli javob yuborilmadi` yozuvini qidiring. `TTS_PROVIDER=openai` ga o'tib ko'ring.
- **Suhbat xotirasi yo'qolyapti** — Disk `/data` ga ulanmagan yoki `DB_PATH=/data/bot.db` yozilmagan.

## Botning "xarakterini" o'zgartirish
`texts.py` ichidagi `SYSTEM_PROMPT` va `EXTRA_INFO` ni tahrirlang (kompaniya xizmatlari, narxlar, manzil). GitHub'ga yuklasangiz, Render o'zi qayta deploy qiladi.

## Ushbu tuzatishlar
- Foydalanuvchining ovoz, rasm, fayl va matn so'rovlari bitta bandlik tizimiga ulandi.
- Rasm yaratishda ⏹ tugmasi qo'shildi. To'xtatish mahalliy kutishni bekor qiladi;
  OpenAI allaqachon boshlagan ish uchun haq olinmasligini kafolatlamaydi.
- Ovozning davomiyligi qolgan kunlik limit bilan tekshiriladi.
- Rasm parametridagi xato xavfsizlik taqiqi sifatida ko'rsatilmaydi.
- Pullik reja qo'shilmagan.

Tekshirish: `python -m unittest -v test_regressions`.
Avtomatik sinovlar tashqi xizmatlar o'rniga soxta obyektlardan foydalanadi.
Haqiqiy Telegram/OpenAI, ovoz chiqarish va rasm yaratish alohida sinalishi kerak.
Model nomlari va xizmat narxlari ushbu tuzatishda qayta tekshirilmagan.

Yangilash: ZIP ichidagi `ae_bot` papkasining fayllarini GitHub reposining
ildiziga yuklang va commit/push qiling. Renderda auto-deploy yoqilgan bo'lsa,
qayta deploy boshlanadi. Aks holda Manual Deploy ni bosing.
Environment kalitlarini almashtirish shart emas; ularni GitHubga yuklamang.
