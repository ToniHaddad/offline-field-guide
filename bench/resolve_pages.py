"""Find the PDF page(s) that hold each answer phrase and write the question set.

Usage: python bench/resolve_pages.py bench/handbook-questions.src.json bench/handbook-questions.json
Fails if a phrase is not found, so the labels cannot drift from the PDF.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]


def flat(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\u2019", "'")).strip().lower()


def resolve(src: dict) -> dict:
    doc = pymupdf.open(ROOT / src["manual"])
    texts = [flat(p.get_text()) for p in doc]
    out = []
    for q in src["questions"]:
        pages = set()
        for phrase in q["answer"]:
            hits = [i + 1 for i, t in enumerate(texts) if flat(phrase) in t]
            if not hits:
                # A phrase may run over a page break: look in each page pair.
                hits = [i + 1 for i in range(len(texts) - 1) if flat(phrase) in texts[i] + " " + texts[i + 1]]
                hits = [h for i in hits for h in (i, i + 1)]
            if not hits:
                raise SystemExit(f"answer phrase not found for {q['query']!r}: {phrase!r}")
            pages.update(hits)
        out.append({"query": q["query"], "pages": sorted(pages), "answer": q["answer"][0]})
    return {"manual": src["manual"], "note": src["note"], "questions": out}


def main() -> int:
    src = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    result = resolve(src)
    Path(sys.argv[2]).write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(result['questions'])} questions written to {sys.argv[2]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
