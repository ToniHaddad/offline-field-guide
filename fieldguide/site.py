"""Write the static, installable web app."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import pymupdf

from .extract import read_pdf, render_page_images
from .index import build_index
from .structure import build_sections

WEB_FILES = ["index.html", "app.js", "search.js", "sw.js"]
MARKER = ".fieldguide-site"


@dataclass
class BuildStats:
    pages: int
    sections: int
    terms: int
    index_bytes: int
    sections_bytes: int
    images_bytes: int
    total_bytes: int
    files: int


def _dump(obj, path: Path) -> int:
    data = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    path.write_bytes(data)
    return len(data)


def _pdf_title(pdf: Path) -> str:
    with pymupdf.open(pdf) as doc:
        title = (doc.metadata or {}).get("title") or ""
    return title.strip() or pdf.stem.replace("_", " ").replace("-", " ").title()


def _render_icons(out: Path, svg: str) -> None:
    with pymupdf.open(stream=svg.encode("utf-8"), filetype="svg") as doc:
        page = doc[0]
        for size in (192, 512):
            zoom = size / page.rect.width
            page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False).save(str(out / f"icon-{size}.png"))


def build_site(pdf: Path, out: Path, page_images: bool = False, title: str | None = None,
               source_url: str | None = None) -> BuildStats:
    pdf = Path(pdf)
    out = Path(out)
    if out.exists():
        if any(out.iterdir()) and not (out / MARKER).exists():
            raise SystemExit(f"{out} exists and was not made by fieldguide; refusing to overwrite it")
        shutil.rmtree(out)
    (out / "data").mkdir(parents=True)
    (out / MARKER).write_text("built by fieldguide\n")

    pages, toc = read_pdf(str(pdf))
    sections = build_sections(pages, toc)
    index = build_index(sections)
    title = title or _pdf_title(pdf)

    images: list[str] = []
    if page_images:
        (out / "pages").mkdir()
        images = [f"pages/{n}" for n in render_page_images(str(pdf), out / "pages")]

    meta = {
        "title": title,
        "source": source_url or pdf.name,
        "pageCount": len(pages),
        "pageImages": bool(images),
        "sections": [s.to_json() for s in sections],
    }
    sections_bytes = _dump(meta, out / "data" / "sections.json")
    index_bytes = _dump(index, out / "data" / "index.json")

    web = resources.files("fieldguide") / "web"
    for name in WEB_FILES:
        (out / name).write_bytes((web / name).read_bytes())
    icon_svg = (web / "icon.svg").read_text(encoding="utf-8")
    (out / "icon.svg").write_text(icon_svg, encoding="utf-8")
    _render_icons(out, icon_svg)
    short = re.sub(r"\s+", " ", title)
    manifest = {
        "name": f"{short} - Field Guide",
        "short_name": "Field Guide",
        "start_url": "./",
        "scope": "./",
        "display": "standalone",
        "background_color": "#f4f1ea",
        "theme_color": "#1f3b3a",
        "icons": [
            {"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"},
            {"src": "icon.svg", "sizes": "any", "type": "image/svg+xml"},
        ],
    }
    _dump(manifest, out / "manifest.webmanifest")
    html = (out / "index.html").read_text(encoding="utf-8").replace("__TITLE__", _escape(short))
    (out / "index.html").write_text(html, encoding="utf-8")

    # The service worker precaches every file. Its version is a hash of the
    # content, so a rebuilt guide replaces the old cache.
    files = sorted(
        p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file() and p.name not in ("sw.js", MARKER)
    )
    digest = hashlib.sha256()
    for f in files:
        digest.update(f.encode())
        digest.update((out / f).read_bytes())
    precache = ["./"] + files
    sw = (out / "sw.js").read_text(encoding="utf-8")
    sw = sw.replace("__VERSION__", digest.hexdigest()[:12]).replace("__PRECACHE__", json.dumps(precache))
    (out / "sw.js").write_text(sw, encoding="utf-8")

    all_files = [p for p in out.rglob("*") if p.is_file() and p.name != MARKER]
    total = sum(p.stat().st_size for p in all_files)
    img_bytes = sum((out / f).stat().st_size for f in images)
    return BuildStats(len(pages), len(sections), len(index["terms"]), index_bytes, sections_bytes,
                      img_bytes, total, len(all_files))


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
