"""Build small, controlled test PDFs with PyMuPDF.

Every page gets a running header and a "Page N" footer, like a real manual,
so the tests exercise header/footer stripping at the same time.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf

LOREM = (
    "Field teams use this guide when the network is down and no supervisor is reachable.",
    "Read the whole procedure before you start and keep the kit within reach at all times.",
    "Record what you did, the time you did it, and who was present for the handover.",
)


class PdfMaker:
    def __init__(self, header: str = "Warehouse Keeper Handbook (sample)", footer: str = "Page {n}",
                 bottom: float = 730):
        self.doc = pymupdf.open()
        self.header = header
        self.footer = footer
        self.bottom = bottom
        self.page: pymupdf.Page | None = None
        self.y = 0.0
        self.new_page()

    def new_page(self) -> None:
        self.page = self.doc.new_page(width=612, height=792)
        n = self.doc.page_count
        if self.header:
            self.page.insert_text((72, 42), self.header, fontsize=9, fontname="helv")
        if self.footer:
            self.page.insert_text((280, 770), self.footer.format(n=n), fontsize=9, fontname="helv")
        self.y = 96

    def text(self, s: str, size: float = 11, bold: bool = False, x: float = 72, gap: float = 1.45) -> None:
        if self.y > self.bottom:
            self.new_page()
        self.page.insert_text((x, self.y), s, fontsize=size, fontname="hebo" if bold else "helv")
        self.y += size * gap

    def heading(self, s: str, size: float = 16) -> None:
        self.y += 8
        self.text(s, size=size, bold=True)
        self.y += 4

    def body(self, n: int = 3) -> None:
        for i in range(n):
            self.text(LOREM[i % len(LOREM)])
        self.y += 6

    def space(self, h: float) -> None:
        self.y += h

    def table(self, rows: list[list[str]], widths: list[float], bold_header: bool = True, size: float = 10) -> None:
        h = 20
        if self.y + h * len(rows) > self.bottom + 20:
            self.new_page()
        top = self.y
        for r, row in enumerate(rows):
            x = 72.0
            for c, cell in enumerate(row):
                rect = pymupdf.Rect(x, top + r * h, x + widths[c], top + (r + 1) * h)
                self.page.draw_rect(rect, color=(0, 0, 0), width=0.8)
                font = "hebo" if (bold_header and r == 0) else "helv"
                fs = size + 2 if (bold_header and r == 0) else size
                self.page.insert_text((x + 4, rect.y1 - 6), cell, fontsize=fs, fontname=font)
                x += widths[c]
        self.y = top + h * len(rows) + 16

    def save(self, path: Path, toc: list[list] | None = None) -> Path:
        if toc:
            self.doc.set_toc(toc)
        self.doc.save(str(path))
        self.doc.close()
        return path
