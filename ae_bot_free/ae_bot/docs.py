"""Fayllardan matn ajratish: PDF, Word (.docx), Excel (.xlsx) va oddiy matn fayllari."""
from __future__ import annotations

import io


class FileProblem(Exception):
    """code: unsupported | old | empty | encrypted | failed"""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


TEXT_EXT = {
    ".txt", ".md", ".csv", ".tsv", ".json", ".log", ".xml", ".yaml", ".yml",
    ".ini", ".sql", ".html", ".py", ".js", ".ts", ".css",
}


def _pdf(data: bytes, limit: int) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted:
        try:
            if reader.decrypt("") == 0:
                raise FileProblem("encrypted")
        except Exception:
            raise FileProblem("encrypted")
    parts, total = [], 0
    for page in reader.pages[:300]:
        txt = page.extract_text() or ""
        parts.append(txt)
        total += len(txt)
        if total > limit * 1.3:
            break
    return "\n\n".join(parts)


def _docx(data: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(data))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells]
            if any(cells):
                parts.append(" | ".join(cells))
    return "\n".join(parts)


def _xlsx(data: bytes, limit: int) -> str:
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    parts, total = [], 0
    for ws in wb.worksheets:
        parts.append(f"## Varaq: {ws.title}")
        for n, row in enumerate(ws.iter_rows(values_only=True)):
            if n >= 3000:
                break
            cells = ["" if v is None else str(v) for v in row]
            if any(c.strip() for c in cells):
                line = " | ".join(cells).rstrip(" |")
                parts.append(line)
                total += len(line)
            if total > limit * 1.3:
                break
        if total > limit * 1.3:
            break
    return "\n".join(parts)


def extract_text(data: bytes, ext: str, limit: int) -> str:
    ext = (ext or "").lower()
    try:
        if ext == ".pdf":
            text = _pdf(data, limit)
        elif ext == ".docx":
            text = _docx(data)
        elif ext in (".xlsx", ".xlsm"):
            text = _xlsx(data, limit)
        elif ext in TEXT_EXT:
            text = data.decode("utf-8", errors="replace")
        elif ext in (".doc", ".xls", ".ppt"):
            raise FileProblem("old")
        else:
            raise FileProblem("unsupported")
    except FileProblem:
        raise
    except Exception as exc:  # buzilgan fayl va h.k.
        raise FileProblem("failed") from exc

    text = text.strip()
    if not text:
        raise FileProblem("empty")
    if len(text) > limit:
        text = text[:limit] + "\n\n[... fayl uzun bo'lgani uchun qolgan qismi kesib tashlandi]"
    return text
