"""Build the sample Warehouse Keeper Handbook PDF.

The text lives in handbook/handbook.txt (a small markup: "# chapter",
"## section", "1. step", "TABLE: caption" followed by "| a | b |" rows,
"NOTE: text"). The appendices (item catalogue, warehouse list, paper forms)
are generated here from invented data.

The layout is done by hand with PyMuPDF so that the PDF has what real
manuals have and what the extractor must cope with: a cover, a contents
page, running headers and footers with "Page N of M", numbered procedures
that run over page breaks, tables that start at the top of a page or
continue onto the next one with the header row repeated, and a PDF outline.

Usage: python handbook/make_handbook.py [out.pdf]
Everything in this handbook is invented for the offline-field-guide demo.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import re

import pymupdf

STEP = re.compile(r"^(\d{1,2})\. (.+)$")

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "handbook.txt"
DEFAULT_OUT = HERE.parent / "manuals" / "warehouse-keeper-handbook.pdf"

W, H = 595, 842  # A4
LEFT, RIGHT = 64, 64
TOP, BOTTOM = 84, 772
WIDTH = W - LEFT - RIGHT
BODY = 12
LEAD = 1.5
INK = (0.12, 0.14, 0.14)
ACCENT = (0.12, 0.23, 0.23)
GREY = (0.35, 0.38, 0.37)

HEADER_LEFT = "Warehouse Keeper Handbook (sample)"
HEADER_RIGHT = "Stock procedures - Lebanon warehouses"
FOOTER_LEFT = "Sample document written for a software demo - Version 1.0, November 2026"


def text_width(s: str, font: str, size: float) -> float:
    return pymupdf.get_text_length(s, fontname=font, fontsize=size)


def wrap(s: str, font: str, size: float, width: float) -> list[str]:
    words, lines, cur = s.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if text_width(trial, font, size) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


class Layout:
    def __init__(self) -> None:
        self.doc = pymupdf.open()
        self.page: pymupdf.Page | None = None
        self.y = TOP
        self.toc: list[list] = []
        self.chapter = 0
        self.section = ""
        # Where a numbered procedure runs over a page break: (section, item, from_page, to_page)
        self.breaks: list[tuple[str, int, int, int]] = []
        self.tables_at_top: list[tuple[str, int]] = []
        self.tables_split: list[tuple[str, int, int]] = []
        self._last_step_page: int | None = None

    # -- pages ------------------------------------------------------------
    @property
    def pno(self) -> int:
        return self.doc.page_count

    def new_page(self) -> None:
        self.page = self.doc.new_page(width=W, height=H)
        self.y = TOP

    def ensure(self, h: float) -> None:
        if self.page is None or self.y + h > BOTTOM:
            self.new_page()

    def put(self, x: float, s: str, font: str = "helv", size: float = BODY, color=INK) -> None:
        self.page.insert_text((x, self.y + size), s, fontname=font, fontsize=size, color=color)

    # -- blocks -----------------------------------------------------------
    def chapter_title(self, title: str, numbered: bool = True) -> None:
        self.new_page()
        if numbered:
            self.chapter += 1
            title = f"Chapter {self.chapter}: {title}"
        self.toc.append([1, title, self.pno])
        self.page.draw_rect(pymupdf.Rect(LEFT, self.y, LEFT + 40, self.y + 4), color=None, fill=(0.78, 0.31, 0.11))
        self.y += 14
        for line in wrap(title, "hebo", 20, WIDTH):
            self.put(LEFT, line, "hebo", 20, ACCENT)
            self.y += 26
        self.y += 10

    def section_title(self, title: str) -> None:
        self.ensure(14 * 1.4 + 3 * BODY * LEAD)
        self.y += 8
        self.section = title
        self.toc.append([2, title, self.pno])
        self.put(LEFT, title, "hebo", 14, ACCENT)
        self.y += 14 * 1.4 + 4

    def paragraph(self, s: str, font: str = "helv", size: float = BODY, indent: float = 0) -> None:
        for line in wrap(s, font, size, WIDTH - indent):
            self.ensure(size * LEAD)
            self.put(LEFT + indent, line, font, size)
            self.y += size * LEAD
        self.y += 6

    def note(self, s: str) -> None:
        lines = wrap(s, "heit", BODY, WIDTH - 16)
        for line in lines:
            self.ensure(BODY * LEAD)
            self.page.draw_rect(pymupdf.Rect(LEFT, self.y, LEFT + 3, self.y + BODY * LEAD), color=None,
                                fill=(0.78, 0.31, 0.11))
            self.put(LEFT + 14, line, "heit", BODY, GREY)
            self.y += BODY * LEAD
        self.y += 8

    def step(self, n: int, s: str) -> None:
        lines = wrap(s, "helv", BODY, WIDTH - 22)
        start = self.pno
        for i, line in enumerate(lines):
            self.ensure(BODY * LEAD)
            if i == 0:
                prev_page = self.pno
                self.put(LEFT, f"{n}.", "helv", BODY)
                if n > 1 and self._last_step_page not in (None, self.pno):
                    self.breaks.append((self.section, n, self._last_step_page, self.pno))
                start = self.pno
            self.put(LEFT + 22, line, "helv", BODY)
            self.y += BODY * LEAD
        if self.pno != start:
            self.breaks.append((self.section, n, start, self.pno))
        self._last_step_page = self.pno
        self.y += 3

    def end_list(self) -> None:
        self.y += 5

    def table(self, caption: str, rows: list[list[str]], widths: list[float] | None = None) -> None:
        ncol = len(rows[0])
        widths = widths or [1 / ncol] * ncol
        cols = [w * WIDTH for w in widths]
        size, pad = 10, 5

        def cell_lines(row, bold):
            return [wrap(c, "hebo" if bold else "helv", size, cols[i] - 2 * pad) for i, c in enumerate(row)]

        def row_height(lines):
            return max(len(l) for l in lines) * size * 1.3 + 2 * pad

        header = cell_lines(rows[0], True)
        first_body = cell_lines(rows[1], False) if len(rows) > 1 else header
        # Caption, header row and the first body row stay together.
        self.ensure(18 + row_height(header) + row_height(first_body))
        if self.y == TOP:
            self.tables_at_top.append((caption, self.pno))
        self.put(LEFT, caption, "hebo", 10.5, ACCENT)
        self.y += 18
        start_page = self.pno

        def draw_row(lines, bold):
            h = row_height(lines)
            x = LEFT
            for i, cl in enumerate(lines):
                rect = pymupdf.Rect(x, self.y, x + cols[i], self.y + h)
                if bold:
                    self.page.draw_rect(rect, color=(0.4, 0.42, 0.41), fill=(0.92, 0.91, 0.87), width=0.6)
                else:
                    self.page.draw_rect(rect, color=(0.4, 0.42, 0.41), width=0.6)
                ty = self.y + pad
                for t in cl:
                    self.page.insert_text((x + pad, ty + size), t, fontname="hebo" if bold else "helv",
                                          fontsize=size, color=INK)
                    ty += size * 1.3
                x += cols[i]
            self.y += h

        draw_row(header, True)
        for row in rows[1:]:
            lines = cell_lines(row, False)
            if self.y + row_height(lines) > BOTTOM:
                self.new_page()
                draw_row(header, True)  # repeat the header row on the next page
            draw_row(lines, False)
        if self.pno != start_page:
            self.tables_split.append((caption, start_page, self.pno))
        self.y += 14


# -- invented data for the appendices -------------------------------------

FOOD = [("RIC", "Rice", ["1 kg bag", "5 kg bag", "25 kg sack"], [10, 4, 1]),
        ("LEN", "Red lentils", ["1 kg bag", "5 kg bag"], [12, 4]),
        ("CHE", "Canned cheese", ["200 g can", "500 g can"], [48, 24]),
        ("CHK", "Canned chickpeas", ["400 g can"], [24]),
        ("OIL", "Sunflower oil", ["1 L bottle", "4 L bottle"], [12, 4]),
        ("SUG", "Sugar", ["1 kg bag", "5 kg bag"], [10, 4]),
        ("BUL", "Bulgur", ["1 kg bag", "5 kg bag"], [12, 4]),
        ("PAS", "Pasta", ["500 g pack"], [20]),
        ("TOM", "Tomato paste", ["400 g can"], [24]),
        ("TUN", "Canned tuna", ["160 g can"], [48]),
        ("BEA", "Canned fava beans", ["400 g can"], [24]),
        ("TEA", "Black tea", ["250 g pack"], [24]),
        ("SAL", "Salt", ["1 kg bag"], [20]),
        ("MLK", "Milk powder", ["400 g tin", "900 g tin"], [12, 6]),
        ("HAL", "Halawa", ["500 g tub"], [12]),
        ("DAT", "Dates", ["1 kg pack"], [10]),
        ("FLO", "Wheat flour", ["25 kg sack"], [1]),
        ("BIS", "Biscuits", ["200 g pack"], [36]),
        ("FPK", "Food parcel (family, one month)", ["parcel"], [1]),
        ("BBF", "Baby cereal", ["250 g box"], [12])]
HYGIENE = [("SOA", "Soap bar", ["125 g"], [72]), ("SHA", "Shampoo", ["400 ml"], [24]),
           ("PAD", "Sanitary pads", ["pack of 10"], [48]), ("DIA", "Baby diapers", ["size 3 pack", "size 4 pack", "size 5 pack"], [6, 6, 6]),
           ("ADI", "Adult diapers", ["medium pack", "large pack"], [8, 8]), ("TPA", "Toothpaste", ["100 ml"], [72]),
           ("TBR", "Toothbrush", ["single"], [144]), ("DET", "Laundry detergent", ["3 kg bag"], [6]),
           ("BLE", "Bleach", ["1 L bottle"], [12]), ("HKT", "Family hygiene kit", ["kit"], [1]),
           ("WIP", "Wet wipes", ["pack of 72"], [24]), ("SAN", "Hand sanitizer", ["500 ml"], [20])]
MEDICAL = [("FAK", "First aid kit", ["small", "large"], [10, 4]), ("GAU", "Gauze pads", ["box of 100"], [20]),
           ("GLO", "Examination gloves", ["box of 100, M", "box of 100, L"], [10, 10]),
           ("ORS", "Oral rehydration salts", ["sachet"], [100]), ("MSK", "Surgical masks", ["box of 50"], [40]),
           ("BAN", "Elastic bandage", ["10 cm roll"], [50]), ("THR", "Digital thermometer", ["single"], [50]),
           ("SPL", "Splint", ["arm", "leg"], [10, 10]), ("ALC", "Alcohol swabs", ["box of 100"], [50])]
SHELTER = [("TAR", "Tarpaulin", ["4 x 6 m", "4 x 8 m"], [5, 5]), ("MAT", "Foam mattress", ["single"], [1]),
           ("SOK", "Sealing-off kit", ["kit"], [1]), ("ROP", "Rope", ["30 m coil"], [10]),
           ("TIM", "Timber batten", ["2.4 m"], [20]), ("NAI", "Nails", ["1 kg box"], [12]),
           ("PLS", "Plastic sheeting", ["roll 4 x 50 m"], [1]), ("TEN", "Family tent", ["kit"], [1])]
NFI = [("BLK", "Blanket", ["standard", "thermal"], [10, 10]), ("JER", "Jerrycan", ["10 L", "20 L"], [20, 10]),
       ("KIT", "Kitchen set", ["family"], [4]), ("LMP", "Solar lamp", ["single"], [20]),
       ("STV", "Gas stove", ["single burner"], [6]), ("BUC", "Bucket with lid", ["14 L"], [20]),
       ("HEA", "Heater", ["kerosene"], [2]), ("CLO", "Winter clothing kit", ["child", "adult"], [6, 6]),
       ("PWB", "Power bank", ["10000 mAh"], [20]), ("FAN", "Rechargeable fan", ["single"], [6])]

TOWNS = ["Zahle", "Jbeil", "Saida", "Tripoli", "Halba", "Baalbek", "Tyre", "Nabatieh", "Jounieh", "Batroun",
         "Chtaura", "Aley", "Marjayoun", "Hermel", "Bcharre", "Zgharta", "Jezzine", "Rashaya", "Hasbaya", "Damour"]


def item_rows() -> list[list[str]]:
    rows = []
    for fam, code, items in (("Food", "FOO", FOOD), ("Hygiene", "HYG", HYGIENE), ("Medical", "MED", MEDICAL),
                             ("Shelter", "SHE", SHELTER), ("NFI", "NFI", NFI)):
        for short, name, variants, ppb in items:
            for k, (v, p) in enumerate(zip(variants, ppb), start=1):
                rows.append([f"{code}-{short}-{k:03d}", f"{name}, {v}", fam, str(p)])
    return rows


def warehouse_rows() -> list[list[str]]:
    kinds = ["Main warehouse", "Centre store", "Field store", "Medical store"]
    rows = []
    for i in range(1, 41):
        town = TOWNS[(i * 7) % len(TOWNS)]
        status = "Unlocked" if i <= 26 else "Not yet unlocked"
        projects = ["FA-2026, EA-2026", "FA-2026, INKIND", "EA-2026, WASH-2026", "FA-2026, EA-2026, INKIND"][i % 4]
        rows.append([f"WH-{i:02d}", town, kinds[i % 4], projects, status])
    return rows


FORMS = {
    "Paper goods received note": ["Paper number (WH-xx-P-nnn)", "Date and time", "Warehouse", "Project",
                                  "Purchase order or donor name", "Estimated value (donations, optional)",
                                  "Driver name and vehicle", "Item code / quantity in pieces / expiry (line 1)",
                                  "Item code / quantity in pieces / expiry (line 2)",
                                  "Item code / quantity in pieces / expiry (line 3)", "Shortage, excess or damage",
                                  "Keeper signature", "Driver signature", "System RCV number (when entered)"],
    "Paper waybill": ["Paper number (WH-xx-P-nnn)", "Date and time", "Warehouse", "Project",
                      "Destination: centre, department or partner", "Item code / quantity in pieces / expiry (line 1)",
                      "Item code / quantity in pieces / expiry (line 2)",
                      "Item code / quantity in pieces / expiry (line 3)", "Number of boxes loaded",
                      "Keeper signature", "Driver signature", "Receiver signature and date",
                      "System DSP number (when entered)"],
    "Paper damage report": ["Paper number (WH-xx-P-nnn)", "Date found", "Warehouse", "Project",
                            "Item code / quantity in pieces / expiry", "Incident description (what, when, where)",
                            "Photos taken (number)", "Quarantine location", "Keeper signature",
                            "System DMG number (when entered)", "Operations manager decision and date"],
    "Connection log": ["Date and time connection dropped", "Date and time connection returned",
                       "Paper documents written during the outage", "Documents entered in the system",
                       "Documents refused by the system and why", "Operations manager informed (date)"],
}


def parse(source: str) -> list[tuple]:
    blocks: list[tuple] = []
    lines = source.splitlines()
    i = 0
    while i < len(lines):
        ln = lines[i].rstrip()
        i += 1
        if not ln.strip():
            continue
        if ln.startswith("# "):
            blocks.append(("chapter", ln[2:].strip()))
        elif ln.startswith("## "):
            blocks.append(("section", ln[3:].strip()))
        elif ln.startswith("TABLE: "):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            blocks.append(("table", ln[7:].strip(), rows))
        elif ln.strip() == "PAGEBREAK":
            blocks.append(("pagebreak",))
        elif ln.startswith("NOTE: "):
            blocks.append(("note", ln[6:].strip()))
        elif STEP.match(ln):
            m = STEP.match(ln)
            blocks.append(("step", int(m.group(1)), m.group(2).strip()))
        else:
            blocks.append(("p", ln.strip()))
    return blocks


def cover(lay: Layout) -> None:
    lay.new_page()
    p = lay.page
    p.draw_rect(pymupdf.Rect(0, 0, W, 300), color=None, fill=ACCENT)
    p.insert_text((LEFT, 150), "the Organization", fontname="helv", fontsize=13, color=(0.75, 0.84, 0.81))
    p.insert_text((LEFT, 200), "Warehouse Keeper", fontname="hebo", fontsize=34, color=(1, 1, 1))
    p.insert_text((LEFT, 242), "Handbook", fontname="hebo", fontsize=34, color=(1, 1, 1))
    p.insert_text((LEFT, 350), "Receiving, storing, dispatching and counting relief stock", fontname="helv",
                  fontsize=14, color=INK)
    p.insert_text((LEFT, 372), "in the Organization's warehouses across Lebanon", fontname="helv", fontsize=14,
                  color=INK)
    box = pymupdf.Rect(LEFT, 430, W - RIGHT, 560)
    p.draw_rect(box, color=(0.78, 0.31, 0.11), fill=(0.99, 0.95, 0.92), width=1.5)
    p.insert_text((LEFT + 16, 458), "SAMPLE DOCUMENT", fontname="hebo", fontsize=13, color=(0.6, 0.22, 0.06))
    y = 482
    for line in wrap("This handbook was written for the offline-field-guide software demo. It is not an official "
                     "document of any organization. The Organization, all codes, names, places of storage and "
                     "figures in it are invented for the demo.", "helv", 11, box.width - 32):
        p.insert_text((LEFT + 16, y), line, fontname="helv", fontsize=11, color=INK)
        y += 16
    p.insert_text((LEFT, 740), "Version 1.0 - November 2026", fontname="helv", fontsize=11, color=GREY)
    lay.toc.append([1, "Warehouse Keeper Handbook", 1])


def contents(lay: Layout, pno: int) -> None:
    page = lay.doc[pno - 1]
    y = TOP
    page.insert_text((LEFT, y + 20), "Contents", fontname="hebo", fontsize=20, color=ACCENT)
    y += 50
    for lvl, title, pg in lay.toc:
        if lvl != 1 or pg <= 2:
            continue
        label = f"{title} "
        num = f" {pg}"
        dots = "." * int((WIDTH - text_width(label, "helv", 10.5) - text_width(num, "helv", 10.5)) /
                         text_width(".", "helv", 10.5))
        page.insert_text((LEFT, y), label + dots + num, fontname="helv", fontsize=10.5, color=INK)
        y += 17


def headers_footers(lay: Layout) -> None:
    total = lay.doc.page_count
    for i, page in enumerate(lay.doc, start=1):
        if i == 1:
            continue
        page.insert_text((LEFT, 46), HEADER_LEFT, fontname="helv", fontsize=8.5, color=GREY)
        page.insert_text((W - RIGHT - text_width(HEADER_RIGHT, "helv", 8.5), 46), HEADER_RIGHT, fontname="helv",
                         fontsize=8.5, color=GREY)
        page.draw_line((LEFT, 52), (W - RIGHT, 52), color=(0.8, 0.8, 0.78), width=0.5)
        page.draw_line((LEFT, 794), (W - RIGHT, 794), color=(0.8, 0.8, 0.78), width=0.5)
        page.insert_text((LEFT, 808), FOOTER_LEFT, fontname="helv", fontsize=8, color=GREY)
        num = f"Page {i} of {total}"
        page.insert_text((W - RIGHT - text_width(num, "helv", 8), 808), num, fontname="helv", fontsize=8,
                         color=GREY)


def build(out: Path = DEFAULT_OUT) -> dict:
    lay = Layout()
    cover(lay)
    lay.new_page()  # contents, filled in at the end
    for b in parse(SOURCE.read_text(encoding="utf-8")):
        kind = b[0]
        if kind != "step":
            lay._last_step_page = None
        if kind == "chapter":
            lay.chapter_title(b[1], numbered=b[1] not in ("Glossary",))
        elif kind == "section":
            lay.section_title(b[1])
        elif kind == "p":
            lay.paragraph(b[1])
        elif kind == "note":
            lay.note(b[1])
        elif kind == "pagebreak":
            lay.new_page()
        elif kind == "step":
            lay.step(b[1], b[2])
        elif kind == "table":
            widths = None
            if len(b[2][0]) == 2:
                widths = [0.38, 0.62]
            lay.table(b[1], b[2], widths)

    lay.chapter_title("Appendix A: Item Catalogue", numbered=False)
    lay.paragraph("Pieces per box for the items most often handled. The piece is the unit you hand over; "
                  "use the pieces-per-box figure to convert a count of boxes into pieces.")
    lay.section_title("Items by Family")
    lay.table("Table A.1: Item codes and pieces per box", [["Item code", "Description", "Family", "Pieces per box"]]
              + item_rows(), [0.22, 0.48, 0.15, 0.15])

    lay.chapter_title("Appendix B: Warehouse List", numbered=False)
    lay.paragraph("Warehouses of the Organization and the projects that hold stock in each. Warehouses join the "
                  "system one at a time; a warehouse that is not yet unlocked cannot record movements.")
    lay.section_title("Warehouses and Projects")
    lay.table("Table B.1: Warehouses", [["Code", "Town", "Type", "Projects", "Status"]] + warehouse_rows(),
              [0.12, 0.17, 0.2, 0.3, 0.21])

    lay.chapter_title("Appendix C: Paper Forms", numbered=False)
    lay.paragraph("Use these forms when the connection drops. Copy the layout on paper if you have no printer. "
                  "Enter every form in the system when the connection is back, oldest first.")
    for k, (name, fields) in enumerate(FORMS.items()):
        if k:
            lay.new_page()  # one form per page, ready to print
        lay.section_title(name)
        lay.table(f"Form: {name}", [["Field", "Write here"]] + [[f, ""] for f in fields], [0.5, 0.5])

    contents(lay, 2)
    headers_footers(lay)
    lay.doc.set_toc(lay.toc)
    lay.doc.set_metadata({"title": "Warehouse Keeper Handbook (sample)", "author": "offline-field-guide demo",
                          "subject": "Sample handbook written for a software demo; not an official document",
                          "creationDate": "D:20261121000000Z", "modDate": "D:20261121000000Z"})
    out.parent.mkdir(parents=True, exist_ok=True)
    pages = lay.doc.page_count
    lay.doc.save(str(out), garbage=3, deflate=True, no_new_id=True)
    lay.doc.close()
    return {"pages": pages, "breaks": lay.breaks, "tables_at_top": lay.tables_at_top,
            "tables_split": lay.tables_split}


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    info = build(target)
    print(f"Wrote {target.name}: {info['pages']} pages")
    print(f"Procedures running over a page break: {len(info['breaks'])}")
    for sec, n, a, b in info["breaks"]:
        print(f"  '{sec}' step {n}: page {a} -> {b}")
    print(f"Tables starting at the top of a page: {len(info['tables_at_top'])}")
    print(f"Tables continued on the next page: {len(info['tables_split'])}")
    print(json.dumps({"pages": info["pages"]}))
