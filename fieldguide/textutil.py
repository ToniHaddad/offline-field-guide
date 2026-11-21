"""Tokenizer shared with the browser.

This must produce exactly the same tokens as `tokenize` in web/search.js,
because Python builds the index and JavaScript queries it.
tests/test_tokenizer_parity.py runs both and compares.
"""

from __future__ import annotations

import re
import unicodedata

STOPWORDS = frozenset(
    (
        "a an and are as at be been but by can do does for from has have how i if in into is it its "
        "may must no not of on or should so than that the their them then there these they this to "
        "was we were what when where which while who will with you your"
    ).split()
)

_WORD = re.compile(r"[a-z0-9]+")
_DIGIT = re.compile(r"[0-9]")
_ACRONYM = re.compile(r"\b(?:[a-z]\.){2,}")  # "p.a.s.s." -> "pass"


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not ("\u0300" <= ch <= "\u036f"))
    return s.lower()


def stem(t: str) -> str:
    if len(t) > 4 and t.endswith("ies"):
        t = t[:-3] + "y"
    elif t.endswith("sses"):
        t = t[:-2]
    elif len(t) > 4 and t.endswith(("xes", "ches", "shes", "zes")):  # boxes -> box
        t = t[:-2]
    elif len(t) > 3 and t.endswith("s") and not t.endswith(("ss", "us", "is")):
        t = t[:-1]
    if len(t) >= 7 and t.endswith("ing"):
        t = t[:-3]
    elif len(t) >= 6 and t.endswith("ed"):
        t = t[:-2]
    # "damage", "damaged", "damages" and "receive", "received" share a stem.
    if len(t) > 4 and t.endswith("e"):
        t = t[:-1]
    return t


def tokenize(s: str) -> list[str]:
    out = []
    text = _ACRONYM.sub(lambda m: m.group(0).replace(".", ""), normalize(s))
    for w in _WORD.findall(text):
        if w in STOPWORDS:
            continue
        if len(w) < 2 and not _DIGIT.search(w):
            continue
        out.append(stem(w))
    return out
