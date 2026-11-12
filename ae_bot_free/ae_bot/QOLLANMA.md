# AE Yordamchi — Render Free

Bu versiya Web Service + Telegram webhook + tashqi PostgreSQL bilan ishlaydi.
Mini App va pullik foydalanuvchi rejasi qo'shilmagan. OpenAI API ishlatish xarajati alohida.

## 1. Tashqi baza
Neon (https://neon.com) da Free loyihani yarating. Imkon bo'lsa Frankfurt hududini tanlang.
Connect bo'limidan PostgreSQL ulanish satrini oling (sslmode=require bilan).
Uni faqat Render Environment dagi DATABASE_URL ga yozing. Bu parol hisoblanadi.
Renderning vaqtinchalik bepul Postgres bazasi o'rniga tashqi bazadan foydalaning.
Jadvallar birinchi ishga tushishda avtomatik yaratiladi. SQLite dagi oldingi suhbatlar
avtomatik ko'chirilmaydi. Free xizmatlarning joriy kvotalarini provayderdan tekshiring.

## 2. GitHub
ZIP ichidagi ae_bot papkasining fayllarini repo ildiziga yuklang.
.env faylni va tokenlarni yuklamang. Eski kompyuter botini yoki Workerni to'xtating.

## 3. Render
New -> Web Service -> repo. Name: ae-yordamchi; Language: Python 3;
Branch: main; Region: Frankfurt; Instance: Free.
Root Directory: main.py repo ildizida bo'lsa bo'sh; ae_bot ichida bo'lsa ae_bot.
Build Command: pip install -r requirements.txt
Start Command: python main.py
Persistent Disk kerak emas.

Environment:
- TELEGRAM_BOT_TOKEN: BotFather tokeni
- OPENAI_API_KEY: OpenAI kaliti
- ADMIN_ID: raqamli Telegram ID
- PYTHON_VERSION: 3.12.8
- BOT_MODE: webhook
- DATABASE_URL: Neon ulanish satri
- WEBHOOK_SECRET: kamida 32 ta tasodifiy A-Z/a-z/0-9/_/- belgisi

WEBHOOK_SECRET ni masalan lokal Python bilan yarating:
python -c "import secrets; print(secrets.token_urlsafe(32))"
Render Blueprint render.yaml orqali yaratilsa secret avtomatik yaratiladi.
RENDER_EXTERNAL_URL ni Render o'zi beradi. U yo'q bo'lsa WEBHOOK_BASE_URL ga
servisning https://...onrender.com manzilini yozing (oxirida / bo'lmasin).
DB_PATH webhook rejimida ishlatilmaydi; DATABASE_URL majburiy.
Deploy -> logda 'Bot ishga tushdi: @... | webhook' ni kuting.

## 4. Sinov
/start, oddiy savol va to'xtatish, ovoz, sozlamadan ovozli javob, rasm tahlili,
PDF/Word/Excel, rasm yaratish va uni to'xtatishni tekshiring.
So'ng deploy qilib, /topics orqali suhbat saqlanganini tekshiring.
Avtomatik sinov: python -m unittest -v test_regressions

## Cheklovlar
Render Free 15 daqiqa kiruvchi trafik bo'lmasa uxlaydi. Keyingi xabarda uyg'onish
va Telegram qayta yetkazishi sabab kechikish bo'lishi mumkin. Doimiy tez javob kafolatlanmaydi.
Bazadagi suhbatlar tashqi PostgreSQLda qoladi, ammo ayni paytda bajarilayotgan ish,
IMAGE_PENDING va bandlik holati restartda yo'qoladi. Webhook tez tasdiqlanadi;
restart vaqtida davom etayotgan so'rov avtomatik qayta bajarilmaydi, qayta yuboring.
Rasmni to'xtatish OpenAI tomonda allaqachon bajarilgan ish haqini bekor qilmaydi.
Haqiqiy Telegram/OpenAI/Neon integratsiyasi ushbu muhitda sinalmagan.
Model nomlari va tariflar bu kod o'zgarishida tasdiqlanmagan; model_not_found bo'lsa
Render Environmentdagi tegishli modelni rasmiy OpenAI hujjatlari bilan tekshiring.

## Yangilash
GitHubga commit/push -> auto-deploy yoqilgan bo'lsa Render qayta deploy qiladi.
Aks holda Manual Deploy. Kalitlarni chatga yubormang.

## Manbalar
https://render.com/docs/free
https://render.com/docs/web-services
https://neon.com/docs/connect/connect-from-any-app
