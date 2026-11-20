"""Turn the line/table stream into sections.

A section starts at every heading. Everything between two headings
(paragraphs, numbered procedures, bullet lists, tables) belongs to the
section, whatever page it is on. Two rules make page breaks harmless:

* headers, footers and page numbers are already gone (extract.py), so the
  last line of page N is followed directly by the first line of page N+1;
* a list item or paragraph that does not end a sentence continues onto the
  next page, and a numbered item that follows item k with number k+1
  extends the same procedure.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

from .extract import Line, PageInfo, Table, body_size, stream

NUMBERED = re.compile(r"^(?:step\s+)?(\d{1,2})\s*[.):]\s+(\S.*)$", re.IGNORECASE)
BULLET = re.compile(r"^[•▪●○■►➢–—·*-]\s*(\S.*)$")
CAPTION = re.compile(r"^(table|figure|exhibit)\s+[\w.-]+\s*[:.\-–]?", re.IGNORECASE)
CONTINUED = re.compile(r"\s*[\(\[]?\s*(continued|cont'?d\.?)\s*[\)\]]?\s*$", re.IGNORECASE)
SENTENCE_END = re.compile(r"[.!?:;]['\")\]]?$")


@dataclass
class Section:
    id: str
    title: str
    level: int
    path: list[str]
    pages: set[int] = field(default_factory=set)
    blocks: list[dict] = field(default_factory=list)

    def text(self) -> str:
        parts = []
        for b in self.blocks:
            if b["t"] == "p":
                parts.append(b["text"])
            elif b["t"] in ("ol", "ul"):
                parts.extend(i["text"] for i in b["items"])
            elif b["t"] == "table":
                parts.extend(" ".join(r) for r in b["rows"])
        return "\n".join(parts)

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "level": self.level,
            "path": self.path,
            "pages": sorted(self.pages),
            "blocks": self.blocks,
        }


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:48] or "section"


class HeadingRules:
    """Decide which lines are headings, and at what level."""

    def __init__(self, pages: list[PageInfo], toc: list[list]):
        self.body = body_size(pages)
        self.toc: dict[int, list[tuple[int, str]]] = {}
        for lvl, title, page in toc:
            if title.strip():
                self.toc.setdefault(page, []).append((lvl, _norm(title)))
        self.toc_depth = max((lvl for lvl, _, _ in toc), default=0)
        big = Counter()
        for p in pages:
            for ln in p.lines:
                if self._looks_like_heading_text(ln.text) and ln.size >= self.body + 1.5:
                    big[ln.size] += 1
        self.sizes = sorted(big, reverse=True)

    @staticmethod
    def _looks_like_heading_text(text: str) -> bool:
        if not (2 <= len(text) <= 120) or not re.search(r"[A-Za-z]", text):
            return False
        if NUMBERED.match(text) or BULLET.match(text) or CAPTION.match(text):
            return False
        return not re.search(r"[.,;]$", text)

    def level(self, ln: Line) -> int | None:
        for lvl, title in self.toc.get(ln.page, []):
            t = _norm(ln.text)
            if t and (t == title or (len(t) >= 8 and title.startswith(t))):
                return lvl
        if not self._looks_like_heading_text(ln.text):
            return None
        if ln.size >= self.body + 1.5:
            return self.toc_depth + self.sizes.index(ln.size) + 1
        if ln.bold and ln.size >= self.body - 0.5 and len(ln.text) <= 90:
            return self.toc_depth + len(self.sizes) + 1
        return None


class _Builder:
    def __init__(self) -> None:
        self.sections: list[Section] = []
        self.stack: list[tuple[int, str]] = []
        self.cur: Section | None = None
        self.prev_line: Line | None = None
        self.list_x0 = 0.0  # x of the current list item's marker
        self.used_ids: Counter[str] = Counter()
        self._table_was_last = False  # the last body item added was a table

    # -- sections -------------------------------------------------------
    def start_section(self, title: str, level: int, page: int) -> None:
        if self.cur and _norm(CONTINUED.sub("", title)) == _norm(self.cur.title) and CONTINUED.search(title):
            return  # "Title (continued)" on the next page: same section
        while self.stack and self.stack[-1][0] >= level:
            self.stack.pop()
        path = [t for _, t in self.stack]
        self.stack.append((level, title))
        base = _slug(title)
        self.used_ids[base] += 1
        sid = base if self.used_ids[base] == 1 else f"{base}-{self.used_ids[base]}"
        self.cur = Section(sid, title, level, path, {page})
        self.sections.append(self.cur)
        self.prev_line = None
        self._table_was_last = False

    def ensure_section(self, page: int) -> Section:
        if self.cur is None:
            self.start_section("Front matter", 1, page)
            self.stack.clear()
        assert self.cur is not None
        return self.cur

    # -- body -----------------------------------------------------------
    def add_table(self, tb: Table) -> None:
        sec = self.ensure_section(tb.page)
        sec.pages.add(tb.page)
        last = sec.blocks[-1] if sec.blocks else None
        if (
            last
            and last["t"] == "table"
            and self._table_was_last
            and tb.page == last["pages"][-1] + 1
            and len(tb.rows[0]) == len(last["rows"][0])
        ):
            # A table that runs onto the next page: one table, header row once.
            rows = tb.rows[1:] if tb.rows[0] == last["rows"][0] else tb.rows
            last["rows"].extend(rows)
            last["pages"].append(tb.page)
        else:
            sec.blocks.append({"t": "table", "rows": [list(r) for r in tb.rows], "pages": [tb.page]})
        self._table_was_last = True

    def add_line(self, ln: Line) -> None:
        sec = self.ensure_section(ln.page)
        sec.pages.add(ln.page)
        prev = self.prev_line
        last = sec.blocks[-1] if sec.blocks else None
        page_break = prev is not None and ln.page != prev.page
        table_between = self._table_was_last
        self._table_was_last = False

        m = NUMBERED.match(ln.text)
        if m:
            n = int(m.group(1))
            if last and last["t"] == "ol" and n == last["items"][-1]["n"] + 1:
                last["items"].append({"n": n, "text": m.group(2)})
            else:
                sec.blocks.append({"t": "ol", "start": n, "items": [{"n": n, "text": m.group(2)}]})
            self.list_x0 = ln.x0
            self.prev_line = ln
            return
        b = BULLET.match(ln.text)
        if b:
            if last and last["t"] == "ul" and not table_between:
                last["items"].append({"text": b.group(1)})
            else:
                sec.blocks.append({"t": "ul", "items": [{"text": b.group(1)}]})
            self.list_x0 = ln.x0
            self.prev_line = ln
            return

        if last and not table_between and prev is not None and self._continues(last, prev, ln, page_break):
            target = last["items"][-1] if last["t"] in ("ol", "ul") else last
            target["text"] = _join(target["text"], ln.text)
        else:
            sec.blocks.append({"t": "p", "text": ln.text})
        self.prev_line = ln

    def _continues(self, last: dict, prev: Line, ln: Line, page_break: bool) -> bool:
        if last["t"] == "table":
            return False
        text = last["items"][-1]["text"] if last["t"] in ("ol", "ul") else last["text"]
        if page_break:
            # The text before the break did not finish its sentence: carry on.
            return not SENTENCE_END.search(text)
        gap = ln.y0 - prev.y1
        close = -2 <= gap < 0.9 * max(ln.height, 6)
        if last["t"] in ("ol", "ul"):
            return close and ln.x0 > self.list_x0 + 3
        return close and abs(ln.size - prev.size) < 1


def _join(a: str, b: str) -> str:
    if a.endswith("-") and not a.endswith(" -") and b[:1].islower():
        return a[:-1] + b
    return f"{a} {b}"


def build_sections(pages: list[PageInfo], toc: list[list]) -> list[Section]:
    rules = HeadingRules(pages, toc)
    builder = _Builder()
    pending: Line | None = None  # heading lines are merged when a heading wraps

    def flush() -> None:
        nonlocal pending
        if pending is not None:
            builder.start_section(pending.text, pending_level, pending.page)
            pending = None

    pending_level = 0
    for it in stream(pages):
        if isinstance(it, Table):
            flush()
            builder.add_table(it)
            continue
        lvl = rules.level(it)
        if lvl is not None:
            if (
                pending is not None
                and it.page == pending.page
                and it.size == pending.size
                and it.bold == pending.bold
                and -4 <= it.y0 - pending.y1 < 0.8 * it.height
            ):
                pending.text = f"{pending.text} {it.text}"
                pending.y1 = it.y1
                continue
            flush()
            pending = Line(it.page, it.text, it.size, it.bold, it.x0, it.y0, it.x1, it.y1)
            pending_level = lvl
            continue
        flush()
        builder.add_line(it)
    flush()
    return [s for s in builder.sections if s.blocks]
