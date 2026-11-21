"""Build the search index the browser loads.

The format is compact JSON that web/search.js reads directly:

    terms     sorted vocabulary (stemmed tokens)
    postings  per term, a flat list [doc, tf, doc, tf, ...]
    titles    per term, the docs whose own heading contains it
    dl        per document, its weighted length
    avgdl     mean of dl
    dw        per document, a ranking weight (1, or REFERENCE_WEIGHT)

Title words count TITLE_WEIGHT times and the parent headings once, a simple
form of field boosting. On top of that, search.js adds a bonus when a query
word is in the section's own heading (`titles`).

Reference sections (glossary, appendices, lists, catalogues, forms,
checklists, quick-reference cards, and sections that are mostly one big
table) get a lower weight, so that when a reference section and the section
that explains a procedure both match, the explanation comes first.
"""

from __future__ import annotations

import re
from collections import Counter

from .structure import Section
from .textutil import tokenize

TITLE_WEIGHT = 3
K1 = 1.2
B = 0.75
REFERENCE_WEIGHT = 0.6

REFERENCE_WORDS = re.compile(
    r"\b(glossary|appendix|appendices|annex|index|contents|quick reference|reference cards?|catalogue|catalog|"
    r"forms?|checklists?|lists?|definitions|abbreviations)\b",
    re.IGNORECASE,
)


def is_reference(section: Section) -> bool:
    """A glossary, appendix, list, form or table-only section."""
    if any(REFERENCE_WORDS.search(t) for t in [section.title, *section.path]):
        return True
    table_chars = sum(len(" ".join(r)) for b in section.blocks if b["t"] == "table" for r in b["rows"])
    rows = sum(len(b["rows"]) for b in section.blocks if b["t"] == "table")
    has_steps = any(b["t"] == "ol" for b in section.blocks)
    total = len(section.text()) or 1
    return rows >= 10 and table_chars / total >= 0.8 and not has_steps


def document_terms(section: Section) -> Counter[str]:
    tf: Counter[str] = Counter()
    for t in tokenize(section.title):
        tf[t] += TITLE_WEIGHT
    for t in tokenize(" ".join(section.path)):
        tf[t] += 1
    for t in tokenize(section.text()):
        tf[t] += 1
    return tf


def build_index(sections: list[Section]) -> dict:
    docs = [document_terms(s) for s in sections]
    vocab = sorted({t for d in docs for t in d})
    postings: dict[str, list[int]] = {t: [] for t in vocab}
    for i, d in enumerate(docs):
        for t, n in d.items():
            postings[t].extend((i, n))
    titles: dict[str, list[int]] = {t: [] for t in vocab}
    for i, s in enumerate(sections):
        for t in sorted(set(tokenize(s.title))):
            titles[t].append(i)
    dl = [sum(d.values()) for d in docs]
    return {
        "k1": K1,
        "b": B,
        "avgdl": round(sum(dl) / max(len(dl), 1), 3),
        "dl": dl,
        "dw": [REFERENCE_WEIGHT if is_reference(s) else 1 for s in sections],
        "terms": vocab,
        "postings": [postings[t] for t in vocab],
        "titles": [titles[t] for t in vocab],
    }
