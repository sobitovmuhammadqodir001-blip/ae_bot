"""Matn bilan ishlash: Markdown -> Telegram HTML, uzun matnni bo'lish, ovoz uchun tozalash."""
from __future__ import annotations

import html
import re

_CODE_BLOCK = re.compile(r"```(?:([\w+#.\-]+)[ \t]*)?\n(.*?)```", re.S)
_CODE_ONELINE = re.compile(r"```([^\n]+?)```")
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_PLACEHOLDER = re.compile(r"\x00(\d+)\x00")
_TABLE_LINE = re.compile(r"^\s*\|.*\|\s*$")


def md_to_html(text: str) -> str:
    """Model yozgan Markdown'ni Telegram qabul qiladigan HTML'ga aylantiradi."""
    stash: list[str] = []

    def keep(fragment: str) -> str:
        stash.append(fragment)
        return f"\x00{len(stash) - 1}\x00"

    def code_block(m: re.Match) -> str:
        lang, code = m.group(1) or "", m.group(2).strip("\n")
        code = html.escape(code, quote=False)
        if lang:
            return keep(f'<pre><code class="language-{lang}">{code}</code></pre>')
        return keep(f"<pre>{code}</pre>")

    text = _CODE_BLOCK.sub(code_block, text)
    text = _CODE_ONELINE.sub(lambda m: keep(f"<code>{html.escape(m.group(1), quote=False)}</code>"), text)

    # Yopilmay qolgan ``` (javob uzilib qolgan bo'lsa)
    if "```" in text:
        head, _, tail = text.partition("```")
        if re.match(r"[\w+#.\-]*\n", tail):
            tail = tail.split("\n", 1)[1]
        text = head + keep(f"<pre>{html.escape(tail.rstrip(), quote=False)}</pre>")

    text = _INLINE_CODE.sub(lambda m: keep(f"<code>{html.escape(m.group(1), quote=False)}</code>"), text)

    text = html.escape(text, quote=False)

    # Jadvallar Telegramda yo'q -> monoshirift blokiga o'raymiz
    lines, out, i = text.split("\n"), [], 0
    while i < len(lines):
        if _TABLE_LINE.match(lines[i]):
            j = i
            while j < len(lines) and _TABLE_LINE.match(lines[j]):
                j += 1
            block = "\n".join(l.strip() for l in lines[i:j])
            out.append(keep(f"<pre>{block}</pre>"))
            i = j
        else:
            out.append(lines[i])
            i += 1
    text = "\n".join(out)

    text = re.sub(r"^[ \t]*([-*_])(?:[ \t]*\1){2,}[ \t]*$", "──────────", text, flags=re.M)
    text = re.sub(r"^#{1,6}[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$", r"<b>\1</b>", text, flags=re.M)
    text = re.sub(r"^([ \t]*)[-*+][ \t]+", r"\1• ", text, flags=re.M)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)
    text = re.sub(r"(?<![\*\w])\*(?![\s\*])(.+?)(?<![\s\*])\*(?![\*\w])", r"<i>\1</i>", text)
    text = re.sub(r"(?<![_\w])_(?![\s_])(.+?)(?<![\s_])_(?![_\w])", r"<i>\1</i>", text)
    text = re.sub(r"\[([^\]\n]+)\]\((https?://[^\s)\"]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"^&gt;[ \t]?(.*)$", r"<blockquote>\1</blockquote>", text, flags=re.M)
    text = text.replace("</blockquote>\n<blockquote>", "\n")

    for _ in range(5):  # ichma-ich saqlangan bo'laklarni ham qaytaramiz
        if "\x00" not in text:
            break
        text = _PLACEHOLDER.sub(lambda m: stash[int(m.group(1))], text)
    return text


def split_markdown(text: str, limit: int = 3500) -> list[str]:
    """Uzun matnni Telegram chegarasiga (4096) sig'adigan bo'laklarga bo'ladi.
    Kod bloki o'rtasida kesilsa, bloklarni to'g'ri yopib/ochib ketadi."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    in_code = False
    lang = ""

    def flush(final: bool = False) -> None:
        nonlocal cur, cur_len
        only_fence = len(cur) == 1 and cur[0].startswith("```")
        body = "\n".join(cur).rstrip()
        if in_code and not final:
            body += "\n```"
        if body.strip() and not only_fence:
            chunks.append(body)
        cur, cur_len = [], 0
        if in_code and not final:
            cur = ["```" + lang]
            cur_len = len(cur[0]) + 1

    step = limit - 50
    for line in text.split("\n"):
        pieces = [line[i:i + step] for i in range(0, len(line), step)] or [""]
        for piece in pieces:
            if cur and cur_len + len(piece) + 1 > limit:
                flush()
            cur.append(piece)
            cur_len += len(piece) + 1
            stripped = piece.strip()
            if stripped.startswith("```"):
                if in_code:
                    in_code = False
                else:
                    in_code = True
                    lang = stripped[3:].strip()
    flush(final=True)
    return chunks


_EMOJI = re.compile("[\U00010000-\U0010ffff\u2600-\u27bf\u2B00-\u2BFF\ufe0f]")


def plain_text(md: str, max_chars: int = 1200) -> str:
    """Ovozga aylantirish uchun: kod, belgilar va emojilarni olib tashlaydi."""
    t = re.sub(r"```.*?```", " ", md, flags=re.S)
    t = re.sub(r"`([^`]*)`", r"\1", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    t = re.sub(r"^[ \t]*[-+•*][ \t]+", "", t, flags=re.M)
    t = re.sub(r"[*_#>~|]+", "", t)
    t = _EMOJI.sub("", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"[ \t]*\n[ \t]*", "\n", t)
    t = re.sub(r"\n{2,}", "\n", t).strip()
    if len(t) > max_chars:
        cut = t[:max_chars]
        pos = max(cut.rfind("."), cut.rfind("!"), cut.rfind("?"), cut.rfind("\n"))
        t = cut[: pos + 1] if pos > max_chars // 2 else cut
    return t
