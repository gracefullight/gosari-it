#!/usr/bin/env python3
"""Render the checked-in Korean proposal with existing ReportLab; never overwrite PDFs."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path
import re

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Flowable, Frame, PageBreak, PageTemplate,
    Paragraph, Spacer, Table, TableStyle,
)
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
GREEN = colors.HexColor('#155638')
INK = colors.HexColor('#23332A')
MUTED = colors.HexColor('#617168')
LINE = colors.HexColor('#DCE7DF')
PALE = colors.HexColor('#F2F7F3')
FONT_NAME = 'GosariKorean'


def inline(text: str) -> str:
    text = html.escape(text)
    text = re.sub(r'\[([^\]]+)\]\((https?://[^\s)]+)\)', r'<a href="\2" color="#155638"><u>\1</u></a>', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<font color="#155638">\1</font>', text)
    text = re.sub(r'`([^`]+)`', r'<font color="#435C4C">\1</font>', text)
    return text


def styles() -> dict[str, ParagraphStyle]:
    base = dict(fontName=FONT_NAME, textColor=INK, wordWrap='CJK', splitLongWords=True)
    return {
        'title': ParagraphStyle('title', fontSize=37, leading=48, spaceAfter=18, **base),
        'cover_sub': ParagraphStyle('cover_sub', fontSize=20, leading=30, spaceAfter=22, **base),
        'cover_body': ParagraphStyle('cover_body', fontSize=12.5, leading=21, spaceAfter=18, **base),
        'h1': ParagraphStyle('h1', fontSize=21, leading=30, spaceAfter=15, **base),
        'h2': ParagraphStyle('h2', fontSize=13, leading=20, spaceBefore=12, spaceAfter=7, **base),
        'body': ParagraphStyle('body', fontSize=10.4, leading=16.3, spaceAfter=9, **base),
        'bullet': ParagraphStyle('bullet', fontSize=10.4, leading=16.3, spaceAfter=8, leftIndent=11, firstLineIndent=-9, **base),
        'cell': ParagraphStyle('cell', fontSize=9.1, leading=14.1, **base),
        'cell_head': ParagraphStyle('cell_head', fontSize=9.1, leading=14.1, textColor=GREEN, fontName=FONT_NAME, wordWrap='CJK'),
        'small': ParagraphStyle('small', fontSize=8.5, leading=13, textColor=MUTED, fontName=FONT_NAME, wordWrap='CJK'),
    }


class CoverMark(Flowable):
    def __init__(self, width: float):
        super().__init__()
        self.width, self.height = width, 80

    def draw(self):
        c = self.canv
        c.setStrokeColor(GREEN)
        c.setLineWidth(3)
        c.line(3, 0, 3, 49)
        p = c.beginPath()
        p.moveTo(3, 49)
        p.curveTo(3, 78, 50, 79, 48, 51)
        p.curveTo(47, 29, 17, 30, 18, 48)
        p.curveTo(19, 59, 36, 61, 35, 49)
        c.drawPath(p)
        c.setStrokeColor(LINE)
        c.setLineWidth(1)
        c.line(74, 4, self.width, 4)


def table(rows: list[list[str]], width: float, sty: dict[str, ParagraphStyle]) -> Table:
    count = len(rows[0])
    proportions = {
        2: [0.27, 0.73],
        3: [0.22, 0.39, 0.39],
        4: [0.17, 0.28, 0.30, 0.25],
    }.get(count, [1 / count] * count)
    if rows[0] == ['ID', '자료·공식 주소']:
        proportions = [0.09, 0.91]
    elif rows[0] == ['장', '내용', '쪽']:
        proportions = [0.12, 0.76, 0.12]
    wrapped = [[Paragraph(inline(cell), sty['cell_head' if r == 0 else 'cell']) for cell in row] for r, row in enumerate(rows)]
    obj = Table(wrapped, colWidths=[width * p for p in proportions], repeatRows=1, hAlign='LEFT')
    obj.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PALE),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, 0), (-1, 0), 0.8, GREEN),
        ('LINEBELOW', (0, 1), (-1, -1), 0.45, LINE),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
    ]))
    return obj


def parse_page(page: str, number: int, width: float, sty: dict[str, ParagraphStyle]) -> list:
    lines = page.strip().splitlines()
    story: list = []
    if number == 1:
        story.extend([Spacer(1, 28 * mm), CoverMark(width), Spacer(1, 18 * mm)])
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith('|'):
            rows = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                cells = [cell.strip() for cell in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-+:?', cell.replace(' ', '')) for cell in cells):
                    rows.append(cells)
                i += 1
            story.extend([table(rows, width, sty), Spacer(1, 10)])
            continue
        if line.startswith('# '):
            key = 'title' if number == 1 else 'h1'
            story.append(Paragraph(inline(line[2:]), sty[key]))
        elif line.startswith('## '):
            key = 'cover_sub' if number == 1 else 'h2'
            story.append(Paragraph(inline(line[3:]), sty[key]))
        elif line.startswith('- ') or re.match(r'^\d+\. ', line):
            story.append(Paragraph(inline(line), sty['bullet']))
        else:
            paragraph = [line]
            while i + 1 < len(lines) and lines[i + 1].strip() and not lines[i + 1].lstrip().startswith(('#', '|', '- ')) and not re.match(r'^\d+\. ', lines[i + 1].strip()):
                i += 1
                paragraph.append(lines[i].strip())
            story.append(Paragraph(inline(' '.join(paragraph)), sty['cover_body' if number == 1 else 'body']))
        i += 1
    return story


class ProposalDocTemplate(BaseDocTemplate):
    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name in ('title', 'h1'):
            key = f'proposal-page-{self.page}'
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(flowable.getPlainText(), key, level=0, closed=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'docs/submission-proposal.md')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--font', type=Path, default=Path('/System/Library/Fonts/Supplemental/Arial Unicode.ttf'))
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(f'Refusing to overwrite existing PDF: {args.output}')
    pdfmetrics.registerFont(TTFont(FONT_NAME, str(args.font)))
    source = args.source.read_text(encoding='utf-8')
    pages = source.split('<!-- pagebreak -->')
    if len(pages) > 15:
        raise SystemExit('Proposal source exceeds 15 pages')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    width, height = A4
    left, right, top, bottom = 19 * mm, 19 * mm, 20 * mm, 18 * mm
    usable_width = width - left - right
    sty = styles()
    story = []
    for number, page in enumerate(pages, start=1):
        if number > 1:
            story.append(PageBreak())
        story.extend(parse_page(page, number, usable_width, sty))

    def decorate(canvas, doc):
        canvas.saveState()
        canvas.setTitle('고사리잇 - 제주 고사리 생활 에이전트 개발 기획서')
        canvas.setAuthor('신은광')
        if doc.page > 1:
            canvas.setFillColor(MUTED)
            canvas.setFont(FONT_NAME, 8)
            canvas.drawString(left, height - 12 * mm, '고사리잇 | 제주 고사리 생활 에이전트')
            canvas.setStrokeColor(LINE)
            canvas.line(left, height - 15 * mm, width - right, height - 15 * mm)
        canvas.setStrokeColor(LINE)
        canvas.line(left, 14 * mm, width - right, 14 * mm)
        canvas.setFont(FONT_NAME, 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(left, 9.5 * mm, '2026-11-08 · 개발 기획서')
        canvas.drawRightString(width - right, 9.5 * mm, f'{doc.page:02d} / {len(pages):02d}')
        canvas.restoreState()

    doc = ProposalDocTemplate(str(args.output), pagesize=A4, leftMargin=left, rightMargin=right,
                          topMargin=top, bottomMargin=bottom, title='고사리잇 개발 기획서', author='신은광')
    frame = Frame(left, bottom, usable_width, height - top - bottom, leftPadding=0, rightPadding=0,
                  topPadding=0, bottomPadding=0, id='content')
    doc.addPageTemplates(PageTemplate(id='proposal', frames=[frame], onPage=decorate))
    doc.build(story)
    reader = PdfReader(args.output)
    count = len(reader.pages)
    if count != len(pages) or count > 15:
        raise SystemExit(f'Layout overflow: expected {len(pages)}, rendered {count}; keep draft for diagnosis')
    text = '\n'.join(page.extract_text() or '' for page in reader.pages)
    for phrase in ('고사리잇', '구현 목표', 'Agent 개발 구성', '데이터 활용 계획', '개발·탑재 계획', '신은광'):
        if phrase not in text:
            raise SystemExit(f'Missing expected Korean text: {phrase}')
    if '\ufffd' in text:
        raise SystemExit('Replacement character found in PDF text')
    for page in reader.pages:
        if abs(float(page.mediabox.width) - width) > 0.1 or abs(float(page.mediabox.height) - height) > 0.1:
            raise SystemExit('Non-A4 page found')
    print(json.dumps({'output': str(args.output.resolve()), 'pages': count, 'a4': True,
                      'source_sha256': hashlib.sha256(source.encode()).hexdigest(),
                      'pdf_sha256': hashlib.sha256(args.output.read_bytes()).hexdigest(),
                      'korean_text_checks': 'passed', 'visual_review': 'pending'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
