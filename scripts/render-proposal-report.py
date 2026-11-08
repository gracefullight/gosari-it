#!/usr/bin/env python3
"""Render docs/proposal/*.md in the numbered report style of the earlier 기획서 PDFs.

Cover → boxed 목차 with dotted leaders → chapters (Ⅰ.~Ⅴ.) with ruled headings,
boxed section numbers, Myungjo body, Gothic tables, inline SVG diagrams and
"- n -" page numbers. Never overwrites an existing PDF.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from reportlab.graphics import renderPDF
from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    Image,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
NAVY = colors.HexColor("#2F3E50")
INK = colors.HexColor("#111111")
GRID = colors.HexColor("#9A9A9A")
HEAD_BG = colors.HexColor("#ECECEC")
RULE = colors.HexColor("#AAAAAA")
SERIF = "Myungjo"
SANS = "Gothic"
SANS_M = "GothicM"
SANS_B = "GothicB"
SANS_SB = "GothicSB"
# NanumGothic lacks U+2160.. roman numerals and ℃; substitute glyphs it has.
GLYPH_FIX = {"Ⅰ": "I", "Ⅱ": "II", "Ⅲ": "III", "Ⅳ": "IV", "Ⅴ": "V", "℃": "°C"}


def glyph_safe(text: str) -> str:
    for src, dst in GLYPH_FIX.items():
        text = text.replace(src, dst)
    return text


def register_fonts(font_dir: Path) -> None:
    """Myungjo body from macOS; sans from NanumGothic TrueType (Apple SD Gothic Neo is CFF, unusable here)."""
    sup = Path("/System/Library/Fonts/Supplemental")
    pdfmetrics.registerFont(TTFont(SERIF, str(sup / "AppleMyungjo.ttf")))
    weights = {SANS: "Regular", SANS_M: "Regular", SANS_SB: "Bold", SANS_B: "Bold"}
    missing = sorted({w for w in weights.values() if not (font_dir / f"NanumGothic-{w}.ttf").is_file()})
    if missing:
        raise SystemExit(
            f"Missing NanumGothic-{{{','.join(missing)}}}.ttf in {font_dir}; download them (OFL) from "
            "https://github.com/google/fonts/tree/main/ofl/nanumgothic or pass --font-dir"
        )
    for name, weight in weights.items():
        pdfmetrics.registerFont(TTFont(name, str(font_dir / f"NanumGothic-{weight}.ttf")))
    pdfmetrics.registerFontFamily(SERIF, normal=SERIF, bold=SANS_B, italic=SERIF, boldItalic=SANS_B)
    pdfmetrics.registerFontFamily(SANS, normal=SANS, bold=SANS_B, italic=SANS, boldItalic=SANS_B)


def inline(text: str) -> str:
    text = html.escape(glyph_safe(text), quote=False)
    text = re.sub(r"\[([^\]]+)\]\((https?://[^\s)]+)\)", r'<a href="\2" color="#1F3A5F"><u>\1</u></a>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`([^`]+)`", r'<font name="%s">\1</font>' % SANS, text)
    return text


def styles() -> dict[str, ParagraphStyle]:
    return {
        "body": ParagraphStyle("body", fontName=SERIF, fontSize=11, leading=19.5, spaceAfter=7, textColor=INK, wordWrap="CJK"),
        "bullet": ParagraphStyle("bullet", fontName=SERIF, fontSize=11, leading=19.5, spaceAfter=5, leftIndent=21, bulletIndent=3, bulletFontName=SERIF, bulletFontSize=11, textColor=INK, wordWrap="CJK"),
        "small": ParagraphStyle("small", fontName=SANS, fontSize=9.4, leading=14.5, spaceAfter=7, textColor=INK, wordWrap="CJK"),
        "subhead": ParagraphStyle("subhead", fontName=SANS_B, fontSize=11.6, leading=17, spaceBefore=4, spaceAfter=6, textColor=INK),
        "caption": ParagraphStyle("caption", fontName=SANS, fontSize=9.5, leading=13, alignment=TA_CENTER, spaceAfter=10, textColor=INK),
        "cell": ParagraphStyle("cell", fontName=SANS, fontSize=9.6, leading=14.6, textColor=INK, wordWrap="CJK"),
        "cell_first": ParagraphStyle("cell_first", fontName=SANS_B, fontSize=9.6, leading=14.6, textColor=INK, wordWrap="CJK"),
        "cell_head": ParagraphStyle("cell_head", fontName=SANS_B, fontSize=9.8, leading=14.6, alignment=TA_CENTER, textColor=INK, wordWrap="CJK"),
        "ref": ParagraphStyle("ref", fontName=SANS, fontSize=9.8, leading=15.5, spaceAfter=7, leftIndent=26, firstLineIndent=-26, textColor=INK, wordWrap="CJK"),
        "cover_top": ParagraphStyle("cover_top", fontName=SANS_M, fontSize=12.5, leading=20, alignment=TA_CENTER, textColor=INK),
        "cover_sub": ParagraphStyle("cover_sub", fontName=SANS_M, fontSize=17, leading=26, alignment=TA_CENTER, textColor=INK),
        "cover_date": ParagraphStyle("cover_date", fontName=SERIF, fontSize=20, leading=30, alignment=TA_CENTER, textColor=INK),
    }


# ---------- custom flowables ----------
class Rule(Flowable):
    def __init__(self, width: float, thickness: float, color=INK, space_before=0, space_after=0):
        super().__init__()
        self.width, self.thickness, self.color = width, thickness, color
        self.sb, self.sa = space_before, space_after
        self.height = thickness + space_before + space_after

    def wrap(self, *_):
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.setStrokeColor(self.color)
        c.setLineWidth(self.thickness)
        y = self.sa + self.thickness / 2
        c.line(0, y, self.width, y)


class ChapterHeading(Flowable):
    """Thick rule, 'Ⅰ. 구현목표', thin rule — mirrors the earlier PDF."""

    def __init__(self, text: str, width: float):
        super().__init__()
        self.text, self.width = text, width
        self.height = 46

    def wrap(self, *_):
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.setStrokeColor(INK)
        c.setLineWidth(1.6)
        c.line(0, self.height - 1, self.width, self.height - 1)
        c.setFillColor(INK)
        c.setFont(SANS_B, 18.5)
        c.drawString(3, self.height - 28, glyph_safe(self.text))
        c.setStrokeColor(RULE)
        c.setLineWidth(0.5)
        c.line(0, 2, self.width, 2)

    def getPlainText(self):
        return self.text


class SectionHeading(Flowable):
    """Boxed number + bold title, e.g. [1] 분석 주제."""

    def __init__(self, number: str, text: str, width: float):
        super().__init__()
        self.number, self.text, self.width = number, text, width
        self.height = 30

    def wrap(self, *_):
        return self.width, self.height

    def draw(self):
        c = self.canv
        box = 20
        y = 4
        c.setStrokeColor(INK)
        c.setLineWidth(0.9)
        c.rect(1, y, box, box, stroke=1, fill=0)
        c.setFillColor(INK)
        c.setFont(SANS_B, 12)
        c.drawCentredString(1 + box / 2, y + 5.5, self.number)
        c.setFont(SANS_B, 14.5)
        c.drawString(1 + box + 11, y + 4.5, self.text)

    def getPlainText(self):
        return self.text


class TocBox(Flowable):
    def __init__(self, width: float):
        super().__init__()
        self.width = width
        self.height = 70

    def wrap(self, *_):
        return self.width, self.height

    def draw(self):
        c = self.canv
        bw = self.width * 0.74
        x = (self.width - bw) / 2
        c.setStrokeColor(INK)
        c.setLineWidth(1)
        c.rect(x, 0, bw, self.height, stroke=1, fill=0)
        c.setFillColor(INK)
        c.setFont(SANS_B, 25)
        c.drawCentredString(self.width / 2, 25, "목    차")


class TocLine(Flowable):
    def __init__(self, text: str, page: str, width: float, level: int):
        super().__init__()
        self.text, self.page, self.width, self.level = glyph_safe(text), page, width, level
        self.font = SANS_B if level == 0 else SANS
        self.size = 13.5 if level == 0 else 11.2
        self.height = 25 if level == 0 else 21
        self.indent = 10 if level == 0 else 42

    def wrap(self, *_):
        return self.width, self.height

    def draw(self):
        c = self.canv
        base = 6
        c.setFillColor(INK)
        c.setFont(self.font, self.size)
        c.drawString(self.indent, base, self.text)
        tw = pdfmetrics.stringWidth(self.text, self.font, self.size)
        pw = pdfmetrics.stringWidth(self.page, self.font, self.size)
        right = self.width - 8
        c.drawRightString(right, base, self.page)
        c.setStrokeColor(colors.HexColor("#777777"))
        c.setLineWidth(0.6)
        c.setDash(0.8, 2.6)
        c.line(self.indent + tw + 7, base + 2.5, right - pw - 7, base + 2.5)
        c.setDash()


class CoverBand(Flowable):
    """Navy rule, icon + 고사리잇, navy rule."""

    def __init__(self, width: float, icon: Path):
        super().__init__()
        self.width, self.icon = width, icon
        self.height = 150

    def wrap(self, *_):
        return self.width, self.height

    def draw(self):
        c = self.canv
        c.setStrokeColor(NAVY)
        c.setLineWidth(4)
        c.line(0, self.height - 2, self.width, self.height - 2)
        c.line(0, 2, self.width, 2)
        title = "고사리잇"
        size = 40
        c.setFont(SANS_B, size)
        tw = pdfmetrics.stringWidth(title, SANS_B, size)
        ih, iw = 56, 56 * 58 / 64
        total = iw + 16 + tw
        x = (self.width - total) / 2
        y = (self.height - ih) / 2
        c.drawImage(str(self.icon), x, y, width=iw, height=ih, mask="auto")
        c.setFillColor(INK)
        c.drawString(x + iw + 16, y + 14, title)


# ---------- svg → reportlab drawing ----------
def svg_drawing(path: Path, target_width: float) -> Drawing:
    root = ET.parse(path).getroot()
    vw, vh = (float(v) for v in root.attrib["viewBox"].split()[2:])
    scale = target_width / vw
    d = Drawing(target_width, vh * scale)
    ns = "{http://www.w3.org/2000/svg}"

    def y(v: float) -> float:
        return (vh - v) * scale

    def color(v: str | None):
        if not v or v == "none":
            return None
        return colors.HexColor(v) if v.startswith("#") else getattr(colors, v, colors.black)

    drawable = [el for g in root.findall(f"{ns}g") for el in g.iter()]  # skips <defs>/<marker>
    for el in drawable:
        tag = el.tag.replace(ns, "")
        a = el.attrib
        if tag == "rect" and a.get("fill") == "white":
            continue
        if tag == "rect":
            fill, stroke = color(a.get("fill")), color(a.get("stroke"))
            r = Rect(float(a["x"]) * scale, y(float(a["y"]) + float(a["height"])), float(a["width"]) * scale, float(a["height"]) * scale)
            r.fillColor = fill
            r.strokeColor = stroke
            r.strokeWidth = 0.8
            d.add(r)
        elif tag == "text":
            size = float(a.get("font-size", "24")) * scale
            weight = a.get("font-weight", "400")
            font = SANS_SB if weight in ("600", "700", "bold") else SANS
            fill = color(a.get("fill")) or INK
            cx, cy = float(a.get("x", 0)), float(a.get("y", 0))
            spans = list(el.findall(f"{ns}tspan"))
            if not spans and (el.text or "").strip():
                s = String(cx * scale, y(cy), el.text.strip(), fontName=font, fontSize=size, fillColor=fill)
                d.add(s)
            for sp in spans:
                cx = float(sp.attrib.get("x", cx))
                cy += float(sp.attrib.get("dy", 0))
                txt = (sp.text or "").strip()
                if txt:
                    d.add(String(cx * scale, y(cy), txt, fontName=font, fontSize=size, fillColor=fill))
        elif tag == "path" and a.get("d", "").startswith("M"):
            pts = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", a["d"])]
            coords = list(zip(pts[0::2], pts[1::2]))
            stroke = color(a.get("stroke")) or INK
            width = float(a.get("stroke-width", "2")) * scale
            dash = a.get("stroke-dasharray")
            for (x1, y1), (x2, y2) in zip(coords, coords[1:]):
                ln = Line(x1 * scale, y(y1), x2 * scale, y(y2), strokeColor=stroke, strokeWidth=width)
                if dash:
                    ln.strokeDashArray = [float(v) * scale for v in dash.split()]
                d.add(ln)
            if a.get("marker-end") and len(coords) >= 2:
                (x1, y1), (x2, y2) = coords[-2], coords[-1]
                dx, dy = x2 - x1, y2 - y1
                length = (dx * dx + dy * dy) ** 0.5 or 1
                ux, uy = dx / length, dy / length
                size = 11 * scale
                tipx, tipy = x2 * scale, y(y2)
                bx, by = tipx - ux * size, tipy + uy * size
                px, py = -uy * size * 0.45, -ux * size * 0.45
                poly = Polygon([tipx, tipy, bx + px, by + py, bx - px, by - py], fillColor=stroke, strokeColor=stroke, strokeWidth=0.3)
                d.add(poly)
    return d


# ---------- markdown parsing ----------
def table_flowable(rows: list[list[str]], width: float, sty) -> Table:
    n = len(rows[0])
    head = rows[0]
    if n == 2:
        props = [0.2, 0.8]
    elif n == 3:
        props = [0.22, 0.47, 0.31]
        if head[1] in ("출처", "내부 Tool"):
            props = [0.26, 0.26, 0.48]
    elif n == 4:
        props = [0.13, 0.27, 0.32, 0.28]
        if head[1].startswith("정희"):
            props = [0.12, 0.293, 0.293, 0.294]
    else:
        props = [1 / n] * n
    data = []
    for r, row in enumerate(rows):
        cells = []
        for c, cell in enumerate(row):
            style = sty["cell_head"] if r == 0 else (sty["cell_first"] if c == 0 else sty["cell"])
            cells.append(Paragraph(inline(cell), style))
        data.append(cells)
    t = Table(data, colWidths=[width * p for p in props], repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEAD_BG),
        ("GRID", (0, 0), (-1, -1), 0.5, GRID),
        ("BOX", (0, 0), (-1, -1), 0.7, GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def build_story(source: str, base: Path, width: float, sty, toc: list[tuple[int, str, str]]) -> tuple[list, list[str]]:
    lines = source.splitlines()
    story: list = []
    cover: list[str] = []
    i = 0
    # cover block: everything before the first '## 목차'
    while i < len(lines) and not lines[i].startswith("## 목차"):
        if lines[i].strip():
            cover.append(lines[i].strip())
        i += 1
    # skip the markdown 목차 block (the PDF builds its own)
    while i < len(lines) and not lines[i].startswith("## Ⅰ"):
        i += 1
    section_no = 0
    pending_keep: list = []
    while i < len(lines):
        line = lines[i].rstrip()
        s = line.strip()
        if not s:
            i += 1
            continue
        if s.startswith("## "):
            title = s[3:]
            if title == "레퍼런스":
                story.append(PageBreak())
            elif title.startswith("Ⅱ") or title.startswith("Ⅳ"):
                story.append(Spacer(1, 14))
            else:
                story.append(PageBreak())
            h = ChapterHeading(title, width)
            h.toc = (0, title)
            story.append(h)
            story.append(Spacer(1, 4))
            section_no = 0
        elif s.startswith("### "):
            section_no += 1
            m = re.match(r"(\d+)\.\s*(.*)", s[4:])
            number, title = (m.group(1), m.group(2)) if m else (str(section_no), s[4:])
            h = SectionHeading(number, title, width)
            h.toc = (1, f"{number}. {title}")
            pending_keep = [h]
        elif s.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", c.replace(" ", "")) for c in cells):
                    rows.append(cells)
                i += 1
            t = table_flowable(rows, width, sty)
            if pending_keep:
                story.append(KeepTogether(pending_keep + [t]))
                pending_keep = []
            else:
                story.append(t)
            story.append(Spacer(1, 9))
            continue
        elif s.startswith("!["):
            m = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", s)
            caption, rel = m.group(1), m.group(2)
            img_path = base / rel
            if rel.endswith(".svg"):
                d = svg_drawing(img_path, width * 0.9)
                block = [Spacer(1, 4), d, Spacer(1, 4), Paragraph(caption, sty["caption"])]
                # center the drawing
                d.hAlign = "CENTER"
            else:
                block = [Image(str(img_path), width=width * 0.9), Paragraph(caption, sty["caption"])]
            story.append(KeepTogether(block))
        elif s.startswith("- "):
            p = Paragraph(inline(s[2:]), sty["bullet"], bulletText="○")
            if pending_keep:
                story.append(KeepTogether(pending_keep + [p]))
                pending_keep = []
            else:
                story.append(p)
        elif re.match(r"^\d+\. \*\*", s):
            m = re.match(r"^(\d+)\. \*\*([^*]+)\*\*:?\s*(.*)", s)
            num, title, rest = m.groups()
            text = f"{num}.&nbsp;&nbsp;<b>{html.escape(title)}</b><br/>{inline(rest)}"
            story.append(Paragraph(text, sty["ref"]))
        elif re.fullmatch(r"\*\*[^*]+\*\*", s):
            p = Paragraph(s.strip("*"), sty["subhead"])
            pending_keep = pending_keep + [p] if pending_keep else [p]
        else:
            para = [s]
            while i + 1 < len(lines) and lines[i + 1].strip() and not re.match(r"^(#|\||!\[|- |\d+\. \*\*|\*\*)", lines[i + 1].strip()):
                i += 1
                para.append(lines[i].strip())
            style = sty["small"] if s.startswith(("단위:", "GPT-6 Luna 기준", "지도 타일은 별도")) else sty["body"]
            p = Paragraph(inline(" ".join(para)), style)
            if pending_keep:
                story.append(KeepTogether(pending_keep + [p]))
                pending_keep = []
            else:
                story.append(p)
        i += 1
    if pending_keep:
        story.extend(pending_keep)
    return story, cover


class ReportDoc(BaseDocTemplate):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.toc_entries: list[tuple[int, str, int]] = []

    def afterFlowable(self, flowable):
        toc = getattr(flowable, "toc", None)
        if toc:
            level, text = toc
            self.toc_entries.append((level, text, self.page))
            if level == 0:
                key = f"ch-{len(self.toc_entries)}"
                self.canv.bookmarkPage(key)
                self.canv.addOutlineEntry(text, key, level=0, closed=False)


def cover_story(cover: list[str], width: float, sty, icon: Path) -> list:
    # cover lines: '# 고사리잇', subtitle, '신은광 · 2026. 11.'
    subtitle = cover[1] if len(cover) > 1 else ""
    author, date = "신은광", "2026. 11."
    if len(cover) > 2 and "·" in cover[2]:
        author, date = [v.strip() for v in cover[2].split("·", 1)]
    return [
        Spacer(1, 26 * mm),
        Paragraph("제주 AI·빅데이터 활용<br/>AI Agent 개발 챌린지", sty["cover_top"]),
        Spacer(1, 48 * mm),
        CoverBand(width, icon),
        Spacer(1, 9 * mm),
        Paragraph(subtitle, sty["cover_sub"]),
        Spacer(1, 38 * mm),
        Paragraph(" ".join(date), sty["cover_date"]),
        Spacer(1, 32 * mm),
        Paragraph(" ".join(author), sty["cover_date"]),
    ]


def toc_story(entries: list[tuple[int, str, int]], width: float) -> list:
    out: list = [Spacer(1, 14 * mm), TocBox(width), Spacer(1, 12 * mm)]
    for level, text, page in entries:
        if level == 0 and out and isinstance(out[-1], TocLine):
            out.append(Spacer(1, 7))
        out.append(TocLine(text, str(page), width, level))
    return out


def render(source_path: Path, output: Path, toc_entries: list[tuple[int, str, int]] | None) -> ReportDoc:
    source = source_path.read_text(encoding="utf-8")
    sty = styles()
    pw, ph = A4
    left = right = 20 * mm
    top, bottom = 19 * mm, 21 * mm
    width = pw - left - right
    icon = source_path.parent / "assets" / "고사리잇_제목아이콘_64.png"

    body, cover = build_story(source, source_path.parent, width, sty, [])
    story = cover_story(cover, width, sty, icon)
    story.append(PageBreak())
    story.extend(toc_story(toc_entries or [(0, "Ⅰ. 구현목표", 3)], width))
    story.extend(body)  # body starts with its own PageBreak

    def decorate(canvas, doc):
        if doc.page <= 2:
            return
        canvas.saveState()
        canvas.setFont(SERIF, 11)
        canvas.setFillColor(INK)
        canvas.drawCentredString(pw / 2, 11.5 * mm, f"- {doc.page} -")
        canvas.restoreState()

    doc = ReportDoc(str(output), pagesize=A4, leftMargin=left, rightMargin=right, topMargin=top, bottomMargin=bottom,
                    title="제주 고사리 채취 동행 AI 에이전트 개발 기획서", author="신은광")
    frame = Frame(left, bottom, width, ph - top - bottom, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0, id="body")
    doc.addPageTemplates(PageTemplate(id="report", frames=[frame], onPage=decorate))
    doc.build(story)
    return doc


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", type=Path, default=ROOT / "docs/proposal/제주고사리_AI_Agent_개발기획서_v0.21.md")
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--max-pages", type=int, default=15)
    ap.add_argument("--font-dir", type=Path, default=ROOT / ".local/fonts")
    args = ap.parse_args()
    if args.output.exists():
        raise SystemExit(f"Refusing to overwrite existing PDF: {args.output}")
    register_fonts(args.font_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    first = render(args.source, args.output, None)
    entries = first.toc_entries
    args.output.unlink()
    second = render(args.source, args.output, entries)
    if second.toc_entries != entries:
        args.output.unlink()
        third = render(args.source, args.output, second.toc_entries)
        if third.toc_entries != second.toc_entries:
            raise SystemExit("TOC page numbers did not converge")
    from pypdf import PdfReader

    reader = PdfReader(args.output)
    count = len(reader.pages)
    if count > args.max_pages:
        raise SystemExit(f"Rendered {count} pages, limit {args.max_pages}; keep draft for diagnosis")
    text = "\n".join(p.extract_text() or "" for p in reader.pages)
    for phrase in ("고사리잇", "구현목표", "Agent 개발 구성", "데이터 활용 계획", "개발·탑재 계획", "신은광", "레퍼런스"):
        if phrase not in text:
            raise SystemExit(f"Missing expected text: {phrase}")
    print(json.dumps({
        "output": str(args.output.resolve()), "pages": count,
        "toc": [[lvl, txt, pg] for lvl, txt, pg in entries],
        "source_sha256": hashlib.sha256(args.source.read_bytes()).hexdigest(),
        "pdf_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
