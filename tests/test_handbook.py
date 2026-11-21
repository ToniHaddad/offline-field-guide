"""The sample Warehouse Keeper Handbook: the generator and how the extractor reads it."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pymupdf
import pytest

from fieldguide.extract import read_pdf
from fieldguide.structure import build_sections

ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


make_handbook = _load("make_handbook", ROOT / "handbook" / "make_handbook.py")
resolve_pages = _load("resolve_pages", ROOT / "bench" / "resolve_pages.py")


@pytest.fixture(scope="module")
def handbook(tmp_path_factory):
    out = tmp_path_factory.mktemp("hb") / "handbook.pdf"
    info = make_handbook.build(out)
    pages, toc = read_pdf(str(out))
    return out, info, build_sections(pages, toc)


def section(sections, title):
    return next(s for s in sections if s.title == title)


def test_handbook_is_long_and_marked_as_a_sample(handbook):
    out, info, _ = handbook
    assert info["pages"] >= 40
    with pymupdf.open(out) as doc:
        cover = " ".join(doc[0].get_text().split())
    assert "SAMPLE DOCUMENT" in cover
    assert "not an official document of any organization" in cover


def test_committed_pdf_matches_the_generator(handbook):
    out, _, _ = handbook
    with pymupdf.open(out) as fresh, pymupdf.open(ROOT / "manuals" / "warehouse-keeper-handbook.pdf") as kept:
        assert [p.get_text() for p in fresh] == [p.get_text() for p in kept]


def test_procedures_that_cross_a_page_break_stay_one_list(handbook):
    _, info, sections = handbook
    assert info["breaks"], "the layout should put at least one procedure over a page break"
    for title, n, from_page, to_page in info["breaks"]:
        sec = section(sections, title)
        assert {from_page, to_page} <= sec.pages
        lists = [b for b in sec.blocks if b["t"] == "ol" and any(i["n"] == n for i in b["items"])]
        assert len(lists) == 1
        numbers = [i["n"] for i in lists[0]["items"]]
        assert numbers == list(range(1, numbers[-1] + 1)), numbers


def test_exceptions_table_at_top_of_page_stays_in_its_section(handbook):
    _, info, sections = handbook
    assert any(c == "Table 4.1: Exceptions at receipt" for c, _ in info["tables_at_top"])
    sec = section(sections, "Problems at Receipt")
    tables = [b for b in sec.blocks if b["t"] == "table"]
    assert len(tables) == 1
    assert tables[0]["rows"][0] == ["Problem", "What to do"]
    assert any(r[0] == "No purchase order in the system" for r in tables[0]["rows"])
    assert "Exceptions at receipt" not in [s.title for s in sections]


def test_table_split_over_pages_is_one_table_with_one_header(handbook):
    _, info, sections = handbook
    split = dict((c, (a, b)) for c, a, b in info["tables_split"])
    assert "Table A.1: Item codes and pieces per box" in split
    sec = section(sections, "Items by Family")
    tables = [b for b in sec.blocks if b["t"] == "table"]
    assert len(tables) == 1
    rows = tables[0]["rows"]
    assert len(rows) == len(make_handbook.item_rows()) + 1
    assert sum(r[0] == "Item code" for r in rows) == 1
    assert ["FOO-CHE-002", "Canned cheese, 500 g can", "Food", "24"] in rows


def test_running_headers_and_footers_are_gone(handbook):
    _, _, sections = handbook
    text = "\n".join(s.title + "\n" + s.text() for s in sections)
    assert make_handbook.HEADER_RIGHT not in text
    assert "Sample document written for a software demo" not in text
    assert " of 42" not in text


def test_question_pages_match_the_committed_set():
    src = json.loads((ROOT / "bench" / "handbook-questions.src.json").read_text(encoding="utf-8"))
    kept = json.loads((ROOT / "bench" / "handbook-questions.json").read_text(encoding="utf-8"))
    assert resolve_pages.resolve(src)["questions"] == kept["questions"]
    assert len(kept["questions"]) >= 15
