"""Build the search index the browser loads.

The format is compact JSON that web/search.js reads directly:

    terms     sorted vocabulary (stemmed tokens)
    postings  per term, a flat list [doc, tf, doc, tf, ...]
    dl        per document, its weighted length
    avgdl     mean of dl

Title words count TITLE_WEIGHT times and the parent headings once, a simple
form of field boosting, so "tourniquet" ranks the section named after it
above a section that only mentions it.
"""

from __future__ import annotations

from collections import Counter

from .structure import Section
from .textutil import tokenize

TITLE_WEIGHT = 3
K1 = 1.2
B = 0.75


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
    dl = [sum(d.values()) for d in docs]
    return {
        "k1": K1,
        "b": B,
        "avgdl": round(sum(dl) / max(len(dl), 1), 3),
        "dl": dl,
        "terms": vocab,
        "postings": [postings[t] for t in vocab],
    }
