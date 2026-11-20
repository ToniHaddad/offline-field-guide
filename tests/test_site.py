"""End to end: a small PDF in, an installable offline site out."""

from __future__ import annotations

import json

import pytest

from fieldguide.cli import main
from fieldguide.site import build_site

from pdfmaker import PdfMaker


@pytest.fixture
def small_pdf(tmp_path):
    m = PdfMaker(header="", footer="")  # one page: no running header to detect
    for title in ("Radio Procedures", "Vehicle Checks", "First Aid Kit"):
        m.heading(title)
        m.body(3)
    return m.save(tmp_path / "manual.pdf")


def test_build_writes_a_complete_pwa(tmp_path, small_pdf):
    out = tmp_path / "site"
    stats = build_site(small_pdf, out, title="Test Manual")
    for name in ("index.html", "app.js", "search.js", "sw.js", "manifest.webmanifest",
                 "icon-192.png", "icon-512.png", "data/sections.json", "data/index.json"):
        assert (out / name).is_file(), name
    guide = json.loads((out / "data/sections.json").read_text(encoding="utf-8"))
    assert [s["title"] for s in guide["sections"]] == ["Radio Procedures", "Vehicle Checks", "First Aid Kit"]
    assert guide["pageImages"] is False
    sw = (out / "sw.js").read_text(encoding="utf-8")
    assert "__PRECACHE__" not in sw and "__VERSION__" not in sw
    precache = json.loads(sw.split("var PRECACHE = ", 1)[1].split(";", 1)[0])
    assert {"./", "index.html", "app.js", "search.js", "data/index.json", "data/sections.json",
            "manifest.webmanifest"} <= set(precache)
    manifest = json.loads((out / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert manifest["display"] == "standalone"
    assert {i["sizes"] for i in manifest["icons"]} >= {"192x192", "512x512"}
    assert "Test Manual" in (out / "index.html").read_text(encoding="utf-8")
    assert stats.sections == 3 and stats.images_bytes == 0


def test_page_images_are_optional(tmp_path, small_pdf):
    out = tmp_path / "site"
    stats = build_site(small_pdf, out, page_images=True)
    assert (out / "pages" / "p1.jpg").is_file()
    assert stats.images_bytes > 0
    sw = (out / "sw.js").read_text(encoding="utf-8")
    assert "pages/p1.jpg" in sw


def test_refuses_to_overwrite_a_foreign_folder(tmp_path, small_pdf):
    out = tmp_path / "precious"
    out.mkdir()
    (out / "notes.txt").write_text("keep me")
    with pytest.raises(SystemExit):
        build_site(small_pdf, out)
    assert (out / "notes.txt").read_text() == "keep me"


def test_cli_build(tmp_path, small_pdf, capsys):
    assert main(["build", str(small_pdf), "--out", str(tmp_path / "site")]) == 0
    out = capsys.readouterr().out
    assert "Sections:        3" in out
