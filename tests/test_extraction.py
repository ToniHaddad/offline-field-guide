"""Extraction: headers/footers, procedures across page breaks, tables, headings."""

from __future__ import annotations

from fieldguide.extract import read_pdf
from fieldguide.structure import build_sections

from pdfmaker import PdfMaker

BULLET_CHAR = chr(0x2022)


def sections_of(path):
    pages, toc = read_pdf(str(path))
    return build_sections(pages, toc)


def by_title(sections, title):
    return next(s for s in sections if s.title == title)


def all_text(sections):
    return "\n".join(s.title + "\n" + s.text() for s in sections)


def test_procedure_across_page_break_stays_one_section(tmp_path):
    m = PdfMaker()
    m.heading("Control Severe Bleeding")
    # Fill the page so step 4 starts at the very bottom and wraps onto page 2.
    while m.y < 640:
        m.body(1)
    m.text("Follow these steps in order:")
    m.text("1. Put on gloves and expose the wound.")
    m.text("2. Apply firm, direct pressure with a clean dressing.")
    m.text("3. Keep the pressure on for at least five minutes.")
    assert m.y > 715
    m.text("4. If bleeding does not stop, apply a tourniquet two to three")
    m.new_page()
    m.text("inches above the wound, never over a joint.", x=86)
    m.text("5. Write the time on the tourniquet.")
    m.text("6. Do not remove it; hand over to medical staff.")
    m.heading("Shut Off Utilities")
    m.body(2)
    path = m.save(tmp_path / "bleeding.pdf")

    secs = sections_of(path)
    bleeding = by_title(secs, "Control Severe Bleeding")
    procs = [b for b in bleeding.blocks if b["t"] == "ol"]
    assert len(procs) == 1, procs
    items = procs[0]["items"]
    assert [i["n"] for i in items] == [1, 2, 3, 4, 5, 6]
    assert items[3]["text"] == (
        "If bleeding does not stop, apply a tourniquet two to three inches above the wound, never over a joint."
    )
    assert sorted(bleeding.pages) == [1, 2]
    text = all_text(secs)
    assert "Northbridge Relief Field Manual" not in text
    assert "Page 1" not in text and "Page 2" not in text
    assert by_title(secs, "Shut Off Utilities").pages == {2}


def test_paragraph_continues_across_page_break(tmp_path):
    m = PdfMaker()
    m.heading("Radio Check")
    while m.y < 700:
        m.body(1)
    m.y = 722
    m.text("Call the base station every hour on the hour and if there is")
    m.new_page()
    m.text("no answer after three calls, move to higher ground.")
    m.body(2)
    path = m.save(tmp_path / "radio.pdf")
    sec = by_title(sections_of(path), "Radio Check")
    joined = [b["text"] for b in sec.blocks if b["t"] == "p" and "base station" in b["text"]]
    assert len(joined) == 1
    assert (
        "Call the base station every hour on the hour and if there is no answer after three calls, move to higher ground."
        in joined[0]
    )


def test_headers_footers_and_page_numbers_are_stripped(tmp_path):
    m = PdfMaker(header="Shelter Handbook, Edition 3", footer="Version 2 | Page {n}")
    for i in range(4):
        m.heading(f"Topic {chr(65 + i)}")
        m.body(3)
        # The header text inside the body must survive: it is not in the margin.
        if i == 1:
            m.text("See the Shelter Handbook, Edition 3 for site layouts.")
        m.new_page()
    m.text("12", size=9)  # stray number near the top of a page body is kept
    m.body(1)
    path = m.save(tmp_path / "shelter.pdf")
    pages, _ = read_pdf(str(path))
    lines = [ln.text for p in pages for ln in p.lines]
    assert not any(t.startswith("Version 2") for t in lines)
    assert lines.count("Shelter Handbook, Edition 3") == 0
    assert "See the Shelter Handbook, Edition 3 for site layouts." in lines
    assert "12" in lines


def test_numbered_footer_with_page_counts_is_stripped(tmp_path):
    m = PdfMaker(header="", footer="{n}")
    for _ in range(3):
        m.heading("Water")
        m.body(2)
        m.new_page()
    path = m.save(tmp_path / "nums.pdf")
    pages, _ = read_pdf(str(path))
    assert all(not ln.text.isdigit() for p in pages for ln in p.lines)


def test_table_with_exceptions_stays_in_its_section(tmp_path):
    m = PdfMaker()
    m.heading("Purify Drinking Water")
    m.body(3)
    m.text("1. Boil clear water for one full minute.")
    m.text("2. Let it cool in a covered container.")
    while m.y < 690:
        m.body(1)
    m.new_page()
    # Top of page 2: a caption and a table whose bold header row is larger
    # than body text. Neither may start a new section.
    m.text("Table 3: Exceptions", bold=True)
    m.table(
        [
            ["Situation", "Exception"],
            ["Above 2,000 m altitude", "Boil for three minutes"],
            ["Cloudy water", "Filter through cloth first"],
            ["Chemical contamination", "Do not drink; boiling does not help"],
        ],
        [200, 260],
    )
    m.heading("Set Up a Shelter")
    m.body(2)
    path = m.save(tmp_path / "water.pdf")

    secs = sections_of(path)
    titles = [s.title for s in secs]
    assert titles == ["Purify Drinking Water", "Set Up a Shelter"], titles
    water = by_title(secs, "Purify Drinking Water")
    tables = [b for b in water.blocks if b["t"] == "table"]
    assert len(tables) == 1
    assert tables[0]["rows"][0] == ["Situation", "Exception"]
    assert ["Above 2,000 m altitude", "Boil for three minutes"] in tables[0]["rows"]
    assert sorted(water.pages) == [1, 2]
    assert "Table 3: Exceptions" in water.text()
    # Table cells are not duplicated as loose paragraphs.
    assert sum("Cloudy water" in b.get("text", "") for b in water.blocks) == 0


def test_table_continued_on_next_page_is_one_table(tmp_path):
    m = PdfMaker()
    m.heading("Supply Checklist")
    m.body(2)
    while m.y < 640:
        m.body(1)
    m.table([["Item", "Quantity"], ["Water (litres)", "4 per person per day"], ["Torch", "1 per team"]], [200, 200])
    m.new_page()
    m.table([["Item", "Quantity"], ["Radio", "1 per team"], ["Gloves", "2 pairs per person"]], [200, 200])
    m.heading("Next Steps")
    m.body(2)
    path = m.save(tmp_path / "supplies.pdf")
    sec = by_title(sections_of(path), "Supply Checklist")
    tables = [b for b in sec.blocks if b["t"] == "table"]
    assert len(tables) == 1
    assert [r[0] for r in tables[0]["rows"]] == ["Item", "Water (litres)", "Torch", "Radio", "Gloves"]
    assert tables[0]["pages"] == [1, 2]


def test_heading_levels_and_paths(tmp_path):
    m = PdfMaker()
    m.heading("Unit 2: Fire Safety", size=20)
    m.body(2)
    m.heading("Extinguisher Types", size=15)
    m.body(3)
    m.text("Checking the Gauge", bold=True)
    m.space(6)
    m.body(2)
    m.heading("Unit 3: Medical Operations", size=20)
    m.body(2)
    path = m.save(tmp_path / "levels.pdf")
    secs = sections_of(path)
    gauge = by_title(secs, "Checking the Gauge")
    assert gauge.path == ["Unit 2: Fire Safety", "Extinguisher Types"]
    assert by_title(secs, "Unit 3: Medical Operations").path == []


def test_bold_run_in_line_is_not_a_heading(tmp_path):
    m = PdfMaker(header="")
    m.heading("Gas Leaks")
    m.text("Never use a lighter or switch on lights", bold=True)
    m.text("when you smell gas; leave the building first.")
    m.body(2)
    path = m.save(tmp_path / "runin.pdf")
    assert [s.title for s in sections_of(path)] == ["Gas Leaks"]


def test_outline_marks_headings_the_fonts_would_miss(tmp_path):
    m = PdfMaker()
    m.body(2)
    m.text("Evacuation Routes")  # plain body font, but listed in the outline
    m.body(3)
    path = m.save(tmp_path / "outline.pdf", toc=[[1, "Evacuation Routes", 1]])
    secs = sections_of(path)
    assert "Evacuation Routes" in [s.title for s in secs]


def test_continued_heading_does_not_split_section(tmp_path):
    m = PdfMaker()
    m.heading("Triage")
    m.body(3)
    m.new_page()
    m.heading("Triage (continued)")
    m.body(2)
    path = m.save(tmp_path / "continued.pdf")
    secs = sections_of(path)
    assert [s.title for s in secs] == ["Triage"]
    assert secs[0].pages == {1, 2}


def test_wrapped_heading_is_merged(tmp_path):
    m = PdfMaker(header="", footer="")
    m.heading("How to Lift a Heavy Object Using", size=16)
    m.y -= 9
    m.text("Leverage and Cribbing", size=16, bold=True)
    m.body(3)
    path = m.save(tmp_path / "wrap.pdf")
    assert [s.title for s in sections_of(path)] == ["How to Lift a Heavy Object Using Leverage and Cribbing"]


def test_bullet_glyph_drawn_apart_from_its_text(tmp_path):
    # Word exports often draw the bullet as its own, smaller span: its top sits below the text top.
    m = PdfMaker()
    m.heading("Size-up Questions")
    m.text("Responders ask:")
    for item in ("What is going on;", "How bad the situation is;", "What resources will be needed."):
        m.page.insert_text((90, m.y), BULLET_CHAR, fontsize=9, fontname="helv")
        m.text(item, x=108)
    m.body(1)
    path = m.save(tmp_path / "bullets.pdf")
    sec = by_title(sections_of(path), "Size-up Questions")
    lists = [b for b in sec.blocks if b["t"] == "ul"]
    assert [i["text"] for i in lists[0]["items"]] == [
        "What is going on;", "How bad the situation is;", "What resources will be needed."]
    assert BULLET_CHAR not in sec.text()
