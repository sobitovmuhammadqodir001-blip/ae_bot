"""PDF uchun xavfsiz maket: hujjat yoki landshaft taqdimot. Kod/HTML bajarilmaydi."""
from __future__ import annotations

import io
import json
import random
import re
import threading
import unicodedata
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate, Paragraph,
                               Spacer, PageBreak, Table, TableStyle, Image,
                               KeepTogether, XPreformatted, Flowable)

_FONT_LOCK = threading.Lock()
NAVY = colors.HexColor('#102344')
MUTED = colors.HexColor('#53647d')
PALE = colors.HexColor('#f1f5fc')
THEMES = {'space': ('#19b8ed', '#ff8a38'), 'business': ('#197c8c', '#d29b38'),
          'education': ('#4564d9', '#ee8650'), 'nature': ('#22805e', '#d2a139')}


def get_font():
    with _FONT_LOCK:
        if 'AEDoc' not in pdfmetrics.getRegisteredFontNames():
            path = Path(__file__).with_name('AE_Font.ttf')
            if not path.exists():
                path = Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
            if not path.exists():
                raise ValueError('AE_Font.ttf faylini bot papkasiga yuklang.')
            pdfmetrics.registerFont(TTFont('AEDoc', str(path)))
            pdfmetrics.registerFontFamily('AEDoc', normal='AEDoc', bold='AEDoc',
                                           italic='AEDoc', boldItalic='AEDoc')
        return pdfmetrics.getFont('AEDoc')


def printable(value):
    font = get_font()
    text = str(value or '').replace('\x00', '')
    return ''.join(c for c in text if c in '\n\t' or (
        unicodedata.category(c) not in ('Cc', 'Cf') and ord(c) in font.face.charToGlyph))


def clean_copy(text):
    """Faqat assistentning aniq xizmat gaplarini olib tashlaydi; mazmunni qayta yozmaydi."""
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        refusal = re.match(r'^(?:bu chatda|afsuski|kechirasiz|hozir bu chatda)', line, re.I)
        if refusal and re.search(r'pdf.*(?:olmay|imkon.*yo.q)', line, re.I):
            continue
        if re.match(r'^(?:matnni|quyidagi matnni)\s+(?:word|google docs)', line, re.I) and re.search(r'pdf|saqla', line, re.I):
            continue
        if re.match(r'^(?:word yoki google docs orqali pdf|sifatida saqlash/yuklab olishni tanlang)', line, re.I):
            continue
        if re.match(r'^📎\s*AE_Yordamchi\.', line):
            continue
        lines.append(raw)
    return '\n'.join(lines).strip()


def infer_style(instruction, source=''):
    text = (instruction + '\n' + source).lower()
    layout = 'presentation' if re.search(r'vatman|landshaft|landscape|taqdimot|slayd|poster|plakat|albom', text) else 'document'
    theme = 'space' if re.search(r'kosmi|parvoz|raketa|quyosh tizim|astronom|sayyora', text) else 'education'
    if re.search(r'biznes|hisobot|savdo|moliya', text):
        theme = 'business'
    elif re.search(r'tabiat|ekolog|o.simlik', text):
        theme = 'nature'
    return layout, theme


def from_markdown(text, instruction=''):
    text = clean_copy(text)
    layout, theme = infer_style(instruction, text)
    lines = text.splitlines()
    title = 'Tayyor hujjat'
    for index, raw in enumerate(lines):
        value = printable(raw).strip().strip('#* ').strip()
        if value and not value.startswith('```'):
            title = value[:160]
            lines = lines[index + 1:]
            break
    sections = []
    section = {'title': 'Ma’lumot', 'paragraphs': [], 'bullets': [], 'tables': [], 'code': []}
    def flush():
        nonlocal section
        if any(section[k] for k in ('paragraphs','bullets','tables','code')):
            sections.append(section)
        section = {'title': 'Ma’lumot', 'paragraphs': [], 'bullets': [], 'tables': [], 'code': []}
    i = 0
    while i < len(lines):
        line = printable(lines[i]).strip()
        if not line:
            i += 1
            continue
        if line.startswith('```'):
            code = []; i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code.append(printable(lines[i])); i += 1
            section['code'].append('\n'.join(code))
        elif line.startswith('|') and line.count('|') >= 2:
            rows = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                cells = [c.strip() for c in printable(lines[i]).strip().strip('|').split('|')]
                if not all(re.fullmatch(r'[:\-\s]+', c) for c in cells):
                    rows.append(cells)
                i += 1
            if rows:
                section['tables'].append({'headers': rows[0], 'rows': rows[1:]})
            continue
        elif (line.startswith('#') or (line.upper() == line and len(line) > 6 and re.search(r'[A-Z]',line))
              or line.upper() in ('XULOSA','MAQSAD','KIRISH')
              or re.match(r'^\d+[.)]\s+[A-Z][A-Z\s‘’—–-]{5,}$', line)):
            flush(); section['title'] = line.lstrip('# ').strip('* ')[:160]
        elif re.match(r'^[-*•]\s+', line):
            section['bullets'].append(re.sub(r'^[-*•]\s+', '', line))
        else:
            section['paragraphs'].append(line)
        i += 1
    flush()
    # Birinchi satr ham hujjat mazmunining bir qismi sifatida sarlavhada saqlanadi.
    return {'ae_document': 1, 'title': title, 'subtitle': '', 'layout': layout, 'theme': theme,
            'cover': layout == 'presentation', 'sections': sections or []}


def parse_plan(text):
    value = text.strip()
    if value.startswith('```'):
        value = re.sub(r'^```(?:json)?\s*|\s*```$', '', value, flags=re.I)
    try:
        data = json.loads(value)
    except (ValueError, TypeError):
        raise ValueError('Hujjat tuzilishi olinmadi. So‘rovni qayta yuboring.') from None
    if not isinstance(data, dict) or data.get('ae_document') != 1:
        raise ValueError('Hujjat tuzilishi noto‘g‘ri. Yana urinib ko‘ring.')
    return validate(data)


def validate(data):
    def string(value, limit=20000):
        if not isinstance(value, str):
            raise ValueError('Hujjatda noto‘g‘ri matn maydoni bor.')
        if len(value) > limit:
            raise ValueError('Hujjat bo‘lagi juda uzun. Qismlarga ajrating.')
        return clean_copy(value)
    result = {'ae_document': 1, 'title': string(data.get('title','Hujjat'),300),
              'subtitle': string(data.get('subtitle',''),600),
              'layout': data.get('layout') if data.get('layout') in ('document','presentation') else 'document',
              'theme': data.get('theme') if data.get('theme') in THEMES else 'education',
              'cover': data.get('cover') is True, 'cover_cards': [], 'sections': []}
    cards = data.get('cover_cards',[])
    if not isinstance(cards,list) or len(cards)>3:
        raise ValueError('Muqova kartochkalari noto‘g‘ri.')
    for card in cards:
        if not isinstance(card,dict):raise ValueError('Muqova kartochkasi noto‘g‘ri.')
        result['cover_cards'].append({'label':string(card.get('label',''),60),
                                      'value':string(card.get('value',''),150)})
    sections = data.get('sections', [])
    if not isinstance(sections, list) or len(sections) > 30:
        raise ValueError('Hujjat 30 tagacha bo‘limdan iborat bo‘lsin.')
    for item in sections:
        if not isinstance(item,dict):
            raise ValueError('Hujjat bo‘limi noto‘g‘ri.')
        section = {'title': string(item.get('title',''),300)}
        for key in ('paragraphs','bullets','code'):
            values = item.get(key,[])
            if not isinstance(values,list) or len(values)>200:
                raise ValueError('Hujjat bo‘limi juda katta.')
            section[key] = [string(v) for v in values]
        section['tables'] = []
        tables = item.get('tables',[])
        if not isinstance(tables,list) or len(tables)>8:
            raise ValueError('Hujjatdagi jadvallar noto‘g‘ri.')
        for table in tables:
            if not isinstance(table,dict): raise ValueError('Jadval noto‘g‘ri.')
            heads, rows = table.get('headers',[]), table.get('rows',[])
            if not isinstance(heads,list) or not 1<=len(heads)<=8 or not isinstance(rows,list) or len(rows)>300:
                raise ValueError('Jadval o‘lchami juda katta.')
            table = {'headers':[string(v,500) for v in heads], 'rows':[]}
            for row in rows:
                if not isinstance(row,list) or len(row)!=len(heads):
                    raise ValueError('Jadval ustunlari mos emas.')
                table['rows'].append([string(v,2000) for v in row])
            section['tables'].append(table)
        result['sections'].append(section)
    if sum(len(str(s)) for s in result['sections']) > 100000:
        raise ValueError('Hujjat juda katta.')
    return result


PLAN_PROMPT = '''You prepare a finished, visually structured PDF, not a chat reply or code.
Return ONLY valid JSON with this schema:
{"ae_document":1,"title":"short title","subtitle":"short subtitle","layout":"document",
"theme":"education","cover":false,"cover_cards":[{"label":"short label","value":"short metadata"}],"sections":[{"title":"section title","paragraphs":["paragraph"],
"bullets":["short item"],"tables":[{"headers":["column"],"rows":[["cell"]]}],"code":["literal code with indentation"]}]}
Allowed layout: document (portrait A4), presentation (landscape A4).
For vatman, poster, presentation, slayd, landshaft choose presentation and cover=true.
Cover may have up to 3 compact metadata cards. Group related short code scripts in one section's code array.
Themes: space, education, business, nature. Choose subject-appropriate theme.
Respond in user's language. Preserve all supplied facts and meaningful content, including algorithms.
Never say you cannot create/attach a PDF. Never tell the user to copy text into Word or save as PDF.
No Markdown fences, emoji, assistant greetings, internal notes or invented sources/statistics.
Put comparisons/variables into real tables; use bullets for rules/steps. Code goes into code arrays, not prose.
For presentation keep each section concise with a short heading; overflow can continue onto another page.
When source material is supplied, don't drop details to make it fit: use extra sections/pages.
Maximum 20 sections and 18000 characters. Images are embedded separately; don't invent image contents.
Do not use placeholders for facts unless user explicitly wants a blank template.
'''


def rich(value):
    text = escape(printable(value))
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'`([^`]+)`', r'<font color="#197c8c">\1</font>', text)
    return text.replace('\n','<br/>')


class Cover(Flowable):
    def __init__(self, plan, width, height, accent, secondary):
        super().__init__(); self.width=width; self.height=height
        self.plan=plan; self.accent=accent; self.secondary=secondary
    def draw(self):
        c=self.canv; w=self.width; h=self.height
        c.setFillColor(NAVY); c.roundRect(0,0,w,h,18,fill=1,stroke=0)
        rng=random.Random(42)
        if self.plan['theme']=='space':
            for _ in range(85):
                c.setFillColor(colors.Color(.6+rng.random()*.4,.7+rng.random()*.3,1))
                c.circle(rng.uniform(12,w-12),rng.uniform(12,h-12),rng.uniform(.4,1.5),fill=1,stroke=0)
        c.setFillColor(self.secondary); c.roundRect(22,h-52,152,25,12,fill=1,stroke=0)
        c.setFillColor(colors.white); c.setFont('AEDoc',10)
        c.drawString(34,h-44,'TAQDIMOT' if self.plan['layout']=='presentation' else 'HUJJAT')
        title_style=ParagraphStyle('cover',fontName='AEDoc',fontSize=32,leading=40,textColor=colors.white)
        p=Paragraph(rich(self.plan['title']),title_style)
        _,ph=p.wrap(w*.62,h-100)
        if ph>h-110:
            title_style.fontSize=23; title_style.leading=30
            p=Paragraph(rich(self.plan['title']),title_style); _,ph=p.wrap(w*.64,h-100)
        p.drawOn(c,24,h-80-ph)
        sub=Paragraph(rich(self.plan['subtitle']),ParagraphStyle('sub',fontName='AEDoc',fontSize=12,leading=18,textColor=colors.HexColor('#c1d3ef')))
        _,sh=sub.wrap(w*.64,h)
        sub.drawOn(c,24,max(24,h-98-ph-sh))
        if self.plan['theme']=='space':
            c.saveState(); c.translate(w*.82,h*.43); c.rotate(-27)
            c.setFillColor(self.secondary)
            path=c.beginPath(); path.moveTo(-13,-36);path.lineTo(0,-90);path.lineTo(13,-36);path.close()
            c.drawPath(path,fill=1,stroke=0)
            c.setFillColor(colors.HexColor('#f34c64'))
            for flip in (-1,1):
                path=c.beginPath();path.moveTo(flip*16,-30);path.lineTo(flip*40,-52);path.lineTo(flip*20,7);path.close();c.drawPath(path,fill=1,stroke=0)
            c.setFillColor(colors.white)
            path=c.beginPath();path.moveTo(-22,-38);path.lineTo(22,-38);path.curveTo(29,15,18,57,0,80);path.curveTo(-18,57,-29,15,-22,-38);path.close()
            c.drawPath(path,fill=1,stroke=0)
            c.setFillColor(self.accent);c.circle(0,20,13,fill=1,stroke=0)
            c.setFillColor(NAVY);c.circle(0,20,8,fill=1,stroke=0)
            c.restoreState()
        else:
            c.setFillColor(self.accent);c.circle(w*.82,h*.52,38,fill=1,stroke=0)
            c.setFillColor(self.secondary);c.circle(w*.9,h*.3,20,fill=1,stroke=0)
        cards=self.plan.get('cover_cards',[])
        if cards:
            gap=10;cw=(w-44-gap*(len(cards)-1))/len(cards)
            for i,card in enumerate(cards):
                x=22+i*(cw+gap)
                c.setFillColor(colors.white);c.roundRect(x,18,cw,86,9,fill=1,stroke=0)
                c.setFillColor(self.accent);c.roundRect(x,18,4,86,2,fill=1,stroke=0)
                label=Paragraph(rich(card['label']),ParagraphStyle('label',fontName='AEDoc',fontSize=8,leading=10,textColor=MUTED))
                label.wrap(cw-24,20);label.drawOn(c,x+12,83)
                val=Paragraph(rich(card['value']),ParagraphStyle('value',fontName='AEDoc',fontSize=11,leading=15,textColor=NAVY))
                _,vh=val.wrap(cw-24,62);val.drawOn(c,x+12,max(23,75-vh))


def render_pdf(plan, images=None):
    plan=validate(plan); get_font()
    accent, secondary=[colors.HexColor(v) for v in THEMES[plan['theme']]]
    wide=plan['layout']=='presentation'
    page=landscape(A4) if wide else A4
    width,height=page; margin=36 if wide else 44
    usable=width-2*margin
    body=ParagraphStyle('body',fontName='AEDoc',fontSize=12 if wide else 10.5,
                        leading=19 if wide else 16,spaceAfter=10,textColor=NAVY,
                        splitLongWords=True)
    heading=ParagraphStyle('heading',parent=body,fontSize=23 if wide else 19,
                           leading=31 if wide else 26,spaceBefore=8,spaceAfter=16,keepWithNext=True)
    small=ParagraphStyle('small',parent=body,fontSize=11 if wide else 9.5,leading=16 if wide else 14)
    tablehead=ParagraphStyle('th',parent=small,textColor=colors.white)
    code_size=10.5 if wide else 9
    code_style=ParagraphStyle('code',parent=small,fontName='AEDoc',fontSize=code_size,
                              leading=15 if wide else 13,spaceAfter=0)
    out=io.BytesIO()
    doc=BaseDocTemplate(out,pagesize=page,leftMargin=margin,rightMargin=margin,
                        topMargin=68,bottomMargin=48,title=printable(plan['title']),author='AE Yordamchi')
    def decorate(c,d):
        c.saveState();c.setFillColor(PALE);c.rect(0,0,width,height,fill=1,stroke=0)
        c.setFillColor(NAVY);c.rect(0,height-45,width,45,fill=1,stroke=0)
        c.setFillColor(accent);c.rect(0,height-48,width,3,fill=1,stroke=0)
        text=printable(plan['title']); maxw=usable-90
        while pdfmetrics.stringWidth(text,'AEDoc',9)>maxw and text:
            text=text[:-1]
        c.setFillColor(colors.white);c.setFont('AEDoc',9);c.drawString(margin,height-27,text)
        c.setFillColor(MUTED);c.setFont('AEDoc',8)
        c.drawString(margin,24,'AE Yordamchi  •  AE Corporation')
        c.drawRightString(width-margin,24,str(d.page))
        c.restoreState()
    frame=Frame(margin,48,usable,height-116,leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)
    doc.addPageTemplates(PageTemplate(id='main',frames=frame,onPage=decorate))
    story=[]
    sections=plan['sections']
    if plan['cover']:
        story += [Cover(plan,usable,height-122,accent,secondary),PageBreak()]
    elif sections or not images:
        story.append(Paragraph(rich(plan['title']),heading))
        if plan['subtitle']:
            story.append(Paragraph(rich(plan['subtitle']),body))
    for index,section in enumerate(sections):
        if wide and index>0:
            story.append(PageBreak())
        title=section['title']
        if title:
            label=(f'{index+1:02d}  /  ' if wide else '')+title
            story.append(Paragraph(rich(label),heading))
        for paragraph in section['paragraphs']:
            story.append(Paragraph(rich(paragraph),body))
        for bullet in section['bullets']:
            style=ParagraphStyle('bullet',parent=body,leftIndent=14,firstLineIndent=-12)
            story.append(Paragraph('•  '+rich(bullet),style))
        for table in section['tables']:
            n=len(table['headers']); widths=[usable/n]*n
            rows=[[Paragraph(rich(v),tablehead) for v in table['headers']]]
            rows += [[Paragraph(rich(v),small) for v in row] for row in table['rows']]
            grid=Table(rows,colWidths=widths,repeatRows=1,hAlign='LEFT',splitInRow=1)
            grid.setStyle(TableStyle([
                ('BACKGROUND',(0,0),(-1,0),NAVY),('VALIGN',(0,0),(-1,-1),'TOP'),
                ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#e5edf9')]),
                ('LEFTPADDING',(0,0),(-1,-1),10),('RIGHTPADDING',(0,0),(-1,-1),10),
                ('TOPPADDING',(0,0),(-1,-1),11),('BOTTOMPADDING',(0,0),(-1,-1),11),
                ('LINEBELOW',(0,0),(-1,0),2,accent),
            ]))
            story.extend([grid,Spacer(1,14)])
        codes=section['code']
        grid_mode=wide and 1<len(codes)<=4
        colwidth=(usable-12)/2 if grid_mode else usable
        font_size=9 if grid_mode else code_size
        leading=13 if grid_mode else code_style.leading
        boxes=[];heights=[]
        for code in codes:
            lines=[]
            for line in printable(code).expandtabs(4).splitlines():
                indent=len(line)-len(line.lstrip())
                while pdfmetrics.stringWidth(line,'AEDoc',font_size)>colwidth-32:
                    cut=len(line)
                    while cut>1 and pdfmetrics.stringWidth(line[:cut],'AEDoc',font_size)>colwidth-32:
                        cut-=1
                    lines.append(line[:cut]);line=' '*min(indent,12)+line[cut:]
                lines.append(line)
            style=ParagraphStyle('codeblock',parent=code_style,fontSize=font_size,leading=leading)
            box=Table([[XPreformatted(escape('\n'.join(lines)),style)]],
                       colWidths=[colwidth],splitInRow=1,hAlign='LEFT')
            box.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),colors.white),
                ('LINEBEFORE',(0,0),(0,-1),3,accent),
                ('LEFTPADDING',(0,0),(-1,-1),14),('RIGHTPADDING',(0,0),(-1,-1),14),
                ('TOPPADDING',(0,0),(-1,-1),12),('BOTTOMPADDING',(0,0),(-1,-1),12)]))
            boxes.append(box);heights.append(len(lines)*leading+24)
        if grid_mode and sum(max(heights[i:i+2])+12 for i in range(0,len(heights),2)) < height-200:
            rows=[]
            for i in range(0,len(boxes),2):
                rows.append([boxes[i],Spacer(12,1),boxes[i+1] if i+1<len(boxes) else ''])
            grid=Table(rows,colWidths=[colwidth,12,colwidth],hAlign='LEFT')
            grid.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),
                ('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),
                ('TOPPADDING',(0,0),(-1,-1),0),('BOTTOMPADDING',(0,0),(-1,-1),12)]))
            story.append(grid)
        else:
            for box in boxes:
                story.extend([box,Spacer(1,12)])
        story.append(Spacer(1,6))
    for raw in images or []:
        from file_builder import clean_image
        data=clean_image(raw);picture=Image(io.BytesIO(data))
        factor=min(usable/picture.imageWidth,(height-135)/picture.imageHeight)
        picture.drawWidth=picture.imageWidth*factor;picture.drawHeight=picture.imageHeight*factor
        if wide or not sections:
            if story and not isinstance(story[-1],PageBreak): story.append(PageBreak())
        story.append(picture)
    if story and isinstance(story[-1],PageBreak):story.pop()
    doc.build(story or [Paragraph(' ',body)])
    return out.getvalue()
