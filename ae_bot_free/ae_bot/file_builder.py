"""Matn, kod va rasmdan tayyor fayl yaratish."""
from __future__ import annotations

import io
import re
import textwrap
import warnings
from html import escape
from pathlib import Path

TEXT_FORMATS = {
    "txt", "tex", "html", "css", "js", "ts", "py",
    "json", "csv", "md", "xml", "yaml", "sql", "svg",
}
FORMATS = TEXT_FORMATS | {"pdf", "docx", "pptx"}
MAX_TEXT = 60000


def clean_image(data: bytes) -> bytes:
    from PIL import Image, ImageOps

    with warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)

        with Image.open(io.BytesIO(data)) as source:
            if source.width * source.height > 25_000_000:
                raise ValueError(
                    "Rasm juda katta. Kichikroq rasm yuboring."
                )

            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((2400, 2400))

            result = io.BytesIO()
            image.save(result, "JPEG", quality=90)
            return result.getvalue()


def strip_fence(text: str) -> str:
    match = re.fullmatch(
        r"\s*```[^\n]*\n(.*?)\n```\s*",
        text,
        re.S,
    )
    return match.group(1) if match else text


def blocks(text: str):
    """Uzun matnlarni slaydlarga ajratish."""
    for block in re.split(r"\n\s*---\s*\n", text):
        lines = block.strip().splitlines()
        if not lines:
            continue

        title = lines[0].lstrip("# ").strip()[:100]
        body = "\n".join(lines[1:]).strip()

        wrapped = []
        for line in body.splitlines():
            wrapped.extend(
                textwrap.wrap(
                    line,
                    72,
                    replace_whitespace=False,
                ) or [""]
            )

        for index in range(0, max(1, len(wrapped)), 14):
            suffix = " (davomi)" if index else ""
            yield (
                title + suffix,
                "\n".join(wrapped[index:index + 14]),
            )


def build_file(
    fmt: str,
    text: str,
    images: list[bytes] | None = None,
) -> tuple[bytes, str]:
    fmt = fmt.lower().lstrip(".")

    if fmt not in FORMATS:
        raise ValueError("Bu format hozircha qo‘llanmaydi.")

    if len(text) > MAX_TEXT:
        raise ValueError(
            "Matn juda uzun. Uni qismlarga ajrating."
        )

    pictures = [
        clean_image(image)
        for image in (images or [])[:8]
    ]
    result = io.BytesIO()

    if fmt in TEXT_FORMATS:
        if pictures:
            raise ValueError(
                "Rasmni joylash uchun PDF, DOCX yoki PPTX tanlang."
            )

        return (
            strip_fence(text).encode("utf-8"),
            "AE_Yordamchi." + fmt,
        )

    if fmt == "pdf":
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import (
            SimpleDocTemplate,
            Paragraph,
            Spacer,
            Image,
        )

        font = Path(__file__).with_name("AE_Font.ttf")

        if not font.exists():
            font = Path(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
            )

        if not font.exists():
            raise ValueError(
                "AE_Font.ttf shrift faylini bot papkasiga yuklang."
            )

        if "AEUnicode" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(
                TTFont("AEUnicode", str(font))
            )

        style = ParagraphStyle(
            "AE",
            fontName="AEUnicode",
            fontSize=10.5,
            leading=16,
            spaceAfter=8,
            wordWrap="CJK",
        )

        heading = ParagraphStyle(
            "AEHeading",
            parent=style,
            fontSize=17,
            leading=23,
            spaceBefore=12,
            spaceAfter=12,
        )

        story = []

        for line in text.splitlines():
            if line.startswith("# "):
                story.append(
                    Paragraph(escape(line[2:]), heading)
                )
            else:
                value = escape(line) if line.strip() else " "
                story.append(Paragraph(value, style))

        for picture in pictures:
            image = Image(io.BytesIO(picture))
            factor = min(
                480 / image.imageWidth,
                650 / image.imageHeight,
                1,
            )
            image.drawWidth = image.imageWidth * factor
            image.drawHeight = image.imageHeight * factor
            story.extend([Spacer(1, 12), image])

        document = SimpleDocTemplate(
            result,
            title="AE Yordamchi",
            leftMargin=45,
            rightMargin=45,
            topMargin=42,
            bottomMargin=42,
        )
        document.build(story or [Paragraph(" ", style)])

    elif fmt == "docx":
        from docx import Document
        from docx.shared import Inches, Pt
        from PIL import Image

        document = Document()
        document.styles["Normal"].font.name = "Calibri"
        document.styles["Normal"].font.size = Pt(11)

        for line in text.splitlines():
            if line.startswith("# "):
                document.add_heading(line[2:], 1)
            else:
                document.add_paragraph(line)

        for picture in pictures:
            with Image.open(io.BytesIO(picture)) as image:
                width, height = image.size

            factor = min(6 / width, 8 / height)

            document.add_picture(
                io.BytesIO(picture),
                width=Inches(width * factor),
                height=Inches(height * factor),
            )

        document.save(result)

    elif fmt == "pptx":
        from pptx import Presentation
        from pptx.util import Inches, Pt
        from pptx.dml.color import RGBColor
        from PIL import Image

        presentation = Presentation()
        presentation.slide_width = Inches(13.333)
        presentation.slide_height = Inches(7.5)

        for title, body in blocks(text):
            slide = presentation.slides.add_slide(
                presentation.slide_layouts[6]
            )
            slide.background.fill.solid()
            slide.background.fill.fore_color.rgb = RGBColor(
                19, 28, 42
            )

            areas = [
                (title, 0.45, 1.1, 30, (69, 204, 185)),
                (body, 1.65, 5.3, 22, (245, 247, 250)),
            ]

            for value, top, height, size, color in areas:
                box = slide.shapes.add_textbox(
                    Inches(0.65),
                    Inches(top),
                    Inches(12),
                    Inches(height),
                )
                frame = box.text_frame
                frame.word_wrap = True

                for index, line in enumerate(value.splitlines()):
                    paragraph = (
                        frame.paragraphs[0]
                        if index == 0
                        else frame.add_paragraph()
                    )
                    paragraph.text = line
                    paragraph.font.size = Pt(size)
                    paragraph.font.name = "Calibri"
                    paragraph.font.color.rgb = RGBColor(*color)

        for picture in pictures:
            slide = presentation.slides.add_slide(
                presentation.slide_layouts[6]
            )

            with Image.open(io.BytesIO(picture)) as image:
                width, height = image.size

            factor = min(12 / width, 6.5 / height)
            picture_width = width * factor
            picture_height = height * factor

            slide.shapes.add_picture(
                io.BytesIO(picture),
                Inches((13.333 - picture_width) / 2),
                Inches((7.5 - picture_height) / 2),
                Inches(picture_width),
                Inches(picture_height),
            )

        if not presentation.slides:
            presentation.slides.add_slide(
                presentation.slide_layouts[6]
            )

        presentation.save(result)

    return result.getvalue(), "AE_Yordamchi." + fmt
