"""Xotirada fayl yaratish. Foydalanuvchi kodi hech qachon ishga tushirilmaydi."""
from __future__ import annotations
import io
import re
import textwrap
from html import escape
from pathlib import Path

TEXT_FORMATS = {'txt', 'tex', 'html', 'css', 'js', 'ts', 'py', 'json', 'csv', 'md', 'xml', 'yaml', 'sql', 'svg'}
FORMATS = TEXT_FORMATS | {'pdf', 'docx', 'pptx'}
MAX_TEXT = 60000


def clean_image(data: bytes) -> bytes:
    from PIL import Image, ImageOps
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter('error', Image.DecompressionBombWarning)
        with Image.open(io.BytesIO(data)) as src:
            if src.width * src.height > 25_000_000:
                raise ValueError('Rasm juda katta. Kichikroq rasm yuboring.')
            img = ImageOps.exif_transpose(src).convert('RGB')
            img.thumbnail((2400, 2400))
            out = io.BytesIO()
            img.save(out, 'JPEG', quality=90)
            return out.getvalue()


def strip_fence(text: str) -> str:
    match = re.fullmatch(r'\s*```[^\n]*\n(.*?)\n```\s*', text, re.S)
    return match.group(1) if match else text


def blocks(text: str):
    """Slaydlar: model --- bilan bo'ladi; uzun bo'laklar davom slaydiga o'tadi."""
    for block in re.split(r'\n\s*---\s*\n', text):
        lines = block.strip().splitlines()
        if not lines:
            continue
        title = lines[0].lstrip('# ').strip()[:100]
        body = '\n'.join(lines[1:]).strip()
        wrapped = []
        for line in body.splitlines():
            wrapped.extend(textwrap.wrap(line, 72, replace_whitespace=False) or [''])
        for n in range(0, max(1, len(wrapped)), 14):
            yield title + (' (davomi)' if n else ''), '\n'.join(wrapped[n:n + 14])


def build_file(fmt: str, text: str, images: list[bytes] | None = None) -> tuple[bytes, str]:
    fmt = fmt.lower().lstrip('.')
    if fmt not in FORMATS:
        raise ValueError('Bu format hozircha qo‘llanmaydi.')
    if len(text) > MAX_TEXT:
        raise ValueError('Matn juda uzun. Uni qismlarga ajrating.')
    pics = [clean_image(p) for p in (images or [])[:8]]
    out = io.BytesIO()
    if fmt in TEXT_FORMATS:
        if pics:
            raise ValueError('Rasmni joylash uchun PDF, DOCX yoki PPTX tanlang.')
        return strip_fence(text).encode('utf-8'), 'AE_Yordamchi.' + fmt
    if fmt == 'pdf':
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
        font = Path(__file__).with_name('AE_Font.ttf')
        if not font.exists():
            font = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
        if not font.exists():
            raise ValueError('AE_Font.ttf shrift faylini bot papkasiga yuklang.')
        if 'AEUnicode' not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont('AEUnicode', str(font)))
        style = ParagraphStyle('AE', fontName='AEUnicode', fontSize=10.5, leading=16,
                               spaceAfter=8, wordWrap='CJK')
        heading = ParagraphStyle('AEHeading', parent=style, fontSize=17, leading=23,
                                 spaceBefore=12, spaceAfter=12)
        story = []
        for line in text.splitlines():
            if line.startswith('# '):
                story.append(Paragraph(escape(line[2:]), heading))
            else:
                story.append(Paragraph(escape(line) if line.strip() else ' ', style))
        for pic in pics:
            image = Image(io.BytesIO(pic))
            factor = min(480 / image.imageWidth, 650 / image.imageHeight, 1)
            image.drawWidth = image.imageWidth * factor
            image.drawHeight = image.imageHeight * factor
            story.extend([Spacer(1, 12), image])
        SimpleDocTemplate(out, title='AE Yordamchi', leftMargin=45, rightMargin=45,
                          topMargin=42, bottomMargin=42).build(story or [Paragraph(' ', style)])
    elif fmt == 'docx':
        from docx import Document
        from docx.shared import Inches, Pt
        doc = Document()
        doc.styles['Normal'].font.name = 'Calibri'
        doc.styles['Normal'].font.size = Pt(11)
        for line in text.splitlines():
            if line.startswith('# '):
                doc.add_heading(line[2:], 1)
            else:
                doc.add_paragraph(line)
        for pic in pics:
            from PIL import Image
            with Image.open(io.BytesIO(pic)) as im:
                w, h = im.size
            factor = min(6 / w, 8 / h)
            doc.add_picture(io.BytesIO(pic), width=Inches(w * factor), height=Inches(h * factor))
        doc.save(out)
    elif fmt == 'pptx':
        from pptx import Presentation
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor
        from PIL import Image
        deck = Presentation()
        deck.slide_width, deck.slide_height = Inches(13.333), Inches(7.5)
        for title, body in blocks(text):
            slide = deck.slides.add_slide(deck.slide_layouts[6])
            slide.background.fill.solid()
            slide.background.fill.fore_color.rgb = RGBColor(19, 28, 42)
            for value, y, h, size, color in [(title, .45, 1.1, 30, (69, 204, 185)),
                                            (body, 1.65, 5.3, 22, (245, 247, 250))]:
                box = slide.shapes.add_textbox(Inches(.65), Inches(y), Inches(12), Inches(h))
                tf = box.text_frame
                tf.word_wrap = True
                for i, line in enumerate(value.splitlines()):
                    p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
                    p.text = line
                    p.font.size, p.font.name = Pt(size), 'Calibri'
                    p.font.color.rgb = RGBColor(*color)
        for pic in pics:
            slide = deck.slides.add_slide(deck.slide_layouts[6])
            with Image.open(io.BytesIO(pic)) as im:
                w, h = im.size
            factor = min(12 / w, 6.5 / h)
            pw, ph = w * factor, h * factor
            slide.shapes.add_picture(io.BytesIO(pic), Inches((13.333-pw)/2),
                                     Inches((7.5-ph)/2), Inches(pw), Inches(ph))
        if not deck.slides:
            deck.slides.add_slide(deck.slide_layouts[6])
        deck.save(out)
    return out.getvalue(), 'AE_Yordamchi.' + fmt
