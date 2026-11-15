"""Wikimedia Commons'dan haqiqiy surat, muallif va litsenziya bilan."""
from __future__ import annotations
import html
import re
from urllib.parse import urlsplit
import aiohttp
from file_builder import clean_image

API = 'https://commons.wikimedia.org/w/api.php'
HEADERS = {'User-Agent': 'AEYordamchiBot/1.0 (Telegram @ae_yordamchi_bot)'}
MAX_BYTES = 10 * 1024 * 1024


def safe_url(url: str, host: str) -> bool:
    p = urlsplit(url)
    return p.scheme == 'https' and p.hostname == host and not p.username and p.port in (None, 443)


def plain(value):
    return html.unescape(re.sub('<[^>]+>', '', str(value)))


async def search_image(query: str):
    timeout = aiohttp.ClientTimeout(total=40, connect=10)
    async with aiohttp.ClientSession(headers=HEADERS, timeout=timeout) as session:
        async with session.get(API, params={
            'action': 'query', 'format': 'json', 'generator': 'search',
            'gsrsearch': query[:180] + ' filetype:bitmap', 'gsrnamespace': 6, 'gsrlimit': 8,
            'prop': 'imageinfo', 'iiprop': 'url|mime|extmetadata', 'iiurlwidth': 1200,
        }, allow_redirects=False) as response:
            response.raise_for_status()
            result = await response.json()
        pages = sorted(result.get('query', {}).get('pages', {}).values(), key=lambda p: p.get('index', 100))
        for page in pages:
            info = (page.get('imageinfo') or [{}])[0]
            url = info.get('thumburl') or info.get('url', '')
            source = info.get('descriptionurl', '')
            if not safe_url(url, 'upload.wikimedia.org') or not safe_url(source, 'commons.wikimedia.org'):
                continue
            if info.get('mime') not in {'image/jpeg', 'image/png', 'image/webp'}:
                continue
            meta = info.get('extmetadata', {})
            license_name = plain(meta.get('LicenseShortName', {}).get('value', ''))
            author = plain(meta.get('Artist', {}).get('value', 'Muallif manbada'))
            if not license_name:
                continue
            try:
                async with session.get(url, allow_redirects=False) as response:
                    response.raise_for_status()
                    data = bytearray()
                    async for chunk in response.content.iter_chunked(65536):
                        data.extend(chunk)
                        if len(data) > MAX_BYTES:
                            raise ValueError('Rasm hajmi katta')
                data = clean_image(bytes(data))
            except (aiohttp.ClientError, ValueError, OSError):
                continue
            caption = (f'🖼 {plain(page.get("title", "Rasm")).removeprefix("File:")[:140]}\n'
                       f'📷 {author[:200]}\nLitsenziya: {license_name[:100]}\n{source}')
            return data, caption
    return None
