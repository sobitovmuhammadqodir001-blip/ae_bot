"""ElevenLabs TTS. Maxfiy kalit faqat Render Environment'dan olinadi."""
import os
import re
import aiohttp


class ElevenTTSError(RuntimeError):
    pass


def settings():
    key = os.getenv('ELEVENLABS_API_KEY', '').strip()
    voice = os.getenv('ELEVENLABS_VOICE_ID', '').strip()
    model = os.getenv('ELEVENLABS_MODEL', 'eleven_v3').strip()
    language = os.getenv('ELEVENLABS_LANGUAGE', 'uz').strip()
    if not key:
        raise ElevenTTSError('Render’da ELEVENLABS_API_KEY sozlamasi kiritilmagan.')
    if not voice or not re.fullmatch(r'[A-Za-z0-9_-]+', voice):
        raise ElevenTTSError('Render’da tanlangan ovozning ELEVENLABS_VOICE_ID qiymatini kiriting.')
    return key, voice, model, language


def cache_key():
    _, voice, model, language = settings()
    return 'elevenlabs:' + ':'.join((voice, model, language, 'mp3_44100_128'))


async def generate(text):
    key, voice, model, language = settings()
    body = {'text': text, 'model_id': model}
    if language:
        body['language_code'] = language
    headers = {'xi-api-key': key, 'Accept': 'audio/mpeg'}
    timeout = aiohttp.ClientTimeout(total=80, connect=15)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                'https://api.elevenlabs.io/v1/text-to-speech/' + voice,
                params={'output_format': 'mp3_44100_128'},
                headers=headers, json=body, allow_redirects=False,
            ) as response:
                if response.status != 200:
                    errors = {
                        400: 'ElevenLabs ovoz yoki model sozlamasini qabul qilmadi.',
                        401: 'ElevenLabs API kaliti noto‘g‘ri yoki muddati tugagan.',
                        402: 'ElevenLabs hisobidagi kredit yoki tarifni tekshiring.',
                        403: 'ElevenLabs kalitida shu ovoz/modeldan foydalanish ruxsati yo‘q.',
                        404: 'ElevenLabs ovoz ID yoki modeli topilmadi.',
                        422: 'ElevenLabs til yoki so‘rov parametrlarini qabul qilmadi.',
                        429: 'ElevenLabs limiti tugagan yoki so‘rovlar ko‘p. Hisobni tekshiring.',
                    }
                    try:
                        payload = await response.json(content_type=None)
                    except Exception:
                        payload = {}
                    detail = payload.get('detail', {}) if isinstance(payload, dict) else {}
                    if isinstance(detail, dict):
                        code = str(detail.get('status', 'unknown'))
                        reason = str(detail.get('message', ''))
                    else:
                        code, reason = 'unknown', str(detail)
                    # Kalit hamda ehtimoliy maxfiy qiymatlar chiqarilmaydi.
                    reason = reason.replace(key, '[maxfiy]')
                    reason = re.sub(r'sk_[A-Za-z0-9_-]+', '[maxfiy]', reason)
                    reason = re.sub(r'[\\x00-\\x1f]', ' ', reason)[:350]
                    code = re.sub(r'[^A-Za-z0-9_-]', '', code)[:60]
                    base = errors.get(response.status, 'ElevenLabs so‘rovni rad etdi.')
                    raise ElevenTTSError(
                        f'{base}\\nHTTP {response.status} | {code}\\n{reason}'
                    )
                mime = response.headers.get('Content-Type', '').lower()
                if not mime.startswith(('audio/', 'application/octet-stream')):
                    raise ElevenTTSError('ElevenLabs audio o‘rniga boshqa javob qaytardi.')
                audio = await response.read()
                if not audio:
                    raise ElevenTTSError('ElevenLabs bo‘sh audio qaytardi.')
                return audio, 'AE_Yordamchi.mp3'
    except (aiohttp.ClientError, TimeoutError) as exc:
        raise ElevenTTSError('ElevenLabs bilan ulanish uzildi. Keyinroq urinib ko‘ring.') from None
