"""Read a PDF into a flat, ordered stream of lines and tables.

Steps per page:
1. find tables (PyMuPDF `find_tables`) and keep their cells as rows;
2. read text lines with font size and weight, skipping lines inside a table;
3. drop running headers, footers and page numbers.

The output is one list of `Line` and `Table` items in reading order, so a
page break is only a change in the `page` field. `structure.py` turns the
stream into sections.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

import pymupdf

# A line in the top or bottom band of the page may be a running header/footer.
MARGIN_BAND = 0.09

PAGE_NUMBER = re.compile(
    r"^(?:page\s*)?(?:[ivxlc]+|\d+(?:\s*[-–.]\s*\d+)?)(?:\s*(?:of|/)\s*\d+)?$",
    re.IGNORECASE,
)


@dataclass
class Line:
    page: int  # 1-based page number in the PDF
    text: str
    size: float  # dominant font size, rounded to 0.5 pt
    bold: bool
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def height(self) -> float:
        return self.y1 - self.y0


@dataclass
class Table:
    page: int
    y0: float
    y1: float
    rows: list[list[str]]
    x0: float = 0.0
    x1: float = 0.0
    pages: list[int] = field(default_factory=list)

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        return (self.x0, self.y0, self.x1, self.y1)

    def __post_init__(self) -> None:
        if not self.pages:
            self.pages = [self.page]


Item = Line | Table


@dataclass
class PageInfo:
    number: int
    width: float
    height: float
    lines: list[Line]
    tables: list[Table]


def _clean(text: str) -> str:
    text = text.replace("­", "").replace("ﬁ", "fi").replace("ﬂ", "fl")
    return re.sub(r"\s+", " ", text).strip()


def _is_bold(span: dict) -> bool:
    return bool(span["flags"] & 16) or bool(re.search(r"bold|black|heavy|semibold", span["font"], re.I))


def _inside(line_bbox: tuple, rect: tuple, pad: float = 2.0) -> bool:
    cx = (line_bbox[0] + line_bbox[2]) / 2
    cy = (line_bbox[1] + line_bbox[3]) / 2
    return rect[0] - pad <= cx <= rect[2] + pad and rect[1] - pad <= cy <= rect[3] + pad


def _read_tables(page: pymupdf.Page, number: int) -> list[Table]:
    tables = []
    try:
        found = page.find_tables()
    except Exception:  # pragma: no cover - PyMuPDF raises on some odd pages
        return tables
    for t in found.tables:
        rows = []
        for row in t.rows:
            # Text by clip keeps the spaces that Table.extract() drops on some fonts.
            cells = [_clean(page.get_text("text", clip=c)) if c else "" for c in row.cells]
            if any(cells):
                rows.append(cells)
        # A one-column or one-row "table" is usually a text box or a rule line.
        if len(rows) < 2 or max(len(r) for r in rows) < 2:
            continue
        x0, y0, x1, y1 = t.bbox
        tables.append(Table(page=number, y0=y0, y1=y1, rows=rows, x0=x0, x1=x1))
    return tables


def _read_lines(page: pymupdf.Page, number: int, tables: list[Table]) -> list[Line]:
    lines: list[Line] = []
    data = page.get_text("dict", sort=True, flags=pymupdf.TEXT_PRESERVE_WHITESPACE)
    for block in data["blocks"]:
        if block.get("type") != 0:
            continue
        for ln in block["lines"]:
            spans = [s for s in ln["spans"] if s["text"].strip()]
            if not spans:
                continue
            text = _clean("".join(s["text"] for s in ln["spans"]))
            if not text:
                continue
            bbox = ln["bbox"]
            if any(_inside(bbox, t.bbox) for t in tables):
                continue
            weight = Counter()
            bold_chars = 0
            total = 0
            for s in spans:
                n = len(s["text"].strip())
                weight[round(s["size"] * 2) / 2] += n
                total += n
                if _is_bold(s):
                    bold_chars += n
            size = weight.most_common(1)[0][0]
            lines.append(
                Line(number, text, size, bold_chars >= 0.8 * total, bbox[0], bbox[1], bbox[2], bbox[3])
            )
    return _merge_same_row(lines)


def _merge_same_row(lines: list[Line]) -> list[Line]:
    """Join fragments that sit on the same baseline (e.g. a bullet glyph and its text)."""
    merged: list[Line] = []
    for ln in sorted(lines, key=lambda l: (round(l.y0), l.x0)):
        prev = merged[-1] if merged else None
        if (
            prev
            and abs(prev.y0 - ln.y0) < 2.5
            and abs(prev.y1 - ln.y1) < 2.5
            and ln.x0 >= prev.x1 - 1
            and ln.x0 - prev.x1 < 40
        ):
            prev.text = f"{prev.text} {ln.text}"
            prev.x1 = ln.x1
            prev.bold = prev.bold and ln.bold
            prev.size = max(prev.size, ln.size)
        else:
            merged.append(ln)
    return merged


def _margin_key(text: str) -> str:
    return re.sub(r"\d+", "#", text.lower()).strip()


def strip_headers_footers(pages: list[PageInfo]) -> None:
    """Remove running headers, footers and page numbers in place.

    A line in the top or bottom band is dropped when it looks like a page
    number, or when the same text (digits ignored) sits in the same band on
    at least three pages (or on every page of a shorter document).
    """
    seen: Counter[tuple[str, str]] = Counter()
    for p in pages:
        keys = set()
        for ln in p.lines:
            band = _band(ln, p)
            if band:
                keys.add((band, _margin_key(ln.text)))
        seen.update(keys)
    need = min(3, len(pages))
    for p in pages:
        kept = []
        for ln in p.lines:
            band = _band(ln, p)
            if band and (PAGE_NUMBER.match(ln.text) or (need >= 2 and seen[(band, _margin_key(ln.text))] >= need)):
                continue
            kept.append(ln)
        p.lines = kept


def _band(ln: Line, p: PageInfo) -> str | None:
    if ln.y1 <= p.height * MARGIN_BAND:
        return "top"
    if ln.y0 >= p.height * (1 - MARGIN_BAND):
        return "bottom"
    return None


def read_pdf(path: str) -> tuple[list[PageInfo], list[list]]:
    """Return the pages (headers and footers removed) and the PDF outline."""
    doc = pymupdf.open(path)
    pages = []
    for i, page in enumerate(doc, start=1):
        tables = _read_tables(page, i)
        lines = _read_lines(page, i, tables)
        pages.append(PageInfo(i, page.rect.width, page.rect.height, lines, tables))
    toc = doc.get_toc(simple=True)
    doc.close()
    strip_headers_footers(pages)
    return pages, toc


def stream(pages: list[PageInfo]) -> list[Item]:
    """Lines and tables of every page in reading order."""
    items: list[Item] = []
    for p in pages:
        page_items: list[Item] = [*p.lines, *p.tables]
        page_items.sort(key=lambda it: (it.y0, it.x0))
        items.extend(page_items)
    return items


def body_size(pages: list[PageInfo]) -> float:
    """Most common font size by character count: the body text size."""
    c: Counter[float] = Counter()
    for p in pages:
        for ln in p.lines:
            c[ln.size] += len(ln.text)
    return c.most_common(1)[0][0] if c else 10.0


def render_page_images(path: str, out_dir, width: int = 480, quality: int = 45) -> list[str]:
    """Render every page as a small greyscale JPEG. Returns file names."""
    doc = pymupdf.open(path)
    names = []
    for i, page in enumerate(doc, start=1):
        zoom = width / page.rect.width
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csGRAY)
        name = f"p{i}.jpg"
        pix.save(str(out_dir / name), jpg_quality=quality)
        names.append(name)
    doc.close()
    return names


__all__ = ["Line", "Table", "PageInfo", "read_pdf", "stream", "body_size", "render_page_images"]
