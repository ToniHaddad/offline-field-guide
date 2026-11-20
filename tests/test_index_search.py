"""Index building, and the shipped JavaScript search run under Node."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from fieldguide.index import TITLE_WEIGHT, build_index
from fieldguide.structure import Section
from fieldguide.textutil import tokenize

SEARCH_JS = Path(__file__).resolve().parents[1] / "fieldguide" / "web" / "search.js"
node = shutil.which("node")
needs_node = pytest.mark.skipif(node is None, reason="node is not installed")


def make_sections():
    def sec(i, title, text, path=()):
        s = Section(f"s{i}", title, 2, list(path), {i + 1})
        s.blocks = [{"t": "p", "text": text}]
        return s

    return [
        sec(0, "Applying a Tourniquet", "Place the tourniquet two inches above the wound and tighten it.", ["Bleeding"]),
        sec(1, "Shutting Off Gas", "Turn the valve a quarter turn with a wrench so it runs across the pipe."),
        sec(2, "Triage Categories", "Immediate, delayed, minor and dead. Check airway, bleeding and shock."),
        sec(3, "Fire Extinguishers", "Remember PASS: pull, aim, squeeze, sweep. Check the gauge first."),
        sec(4, "Cribbing", "Lift and crib a heavy object with a lever and wooden blocks."),
    ]


def test_index_structure():
    secs = make_sections()
    idx = build_index(secs)
    assert idx["terms"] == sorted(idx["terms"])
    assert len(idx["postings"]) == len(idx["terms"])
    assert len(idx["dl"]) == len(secs)
    t = idx["terms"].index("tourniquet")
    # "tourniquet" is in the title (weight 3) and once in the body.
    assert idx["postings"][t] == [0, TITLE_WEIGHT + 1]
    # The parent heading is indexed too.
    assert 0 in idx["postings"][idx["terms"].index("bleed")][0::2]
    assert idx["avgdl"] == pytest.approx(sum(idx["dl"]) / len(secs), abs=1e-3)


def test_tokenizer_basics():
    assert tokenize("Shutting off the GAS valves") == ["shutt", "off", "gas", "valve"]
    assert tokenize("Injuries, bleeding!") == ["injury", "bleed"]


def run_node(script: str, *args: str) -> str:
    out = subprocess.run([node, "-e", script, str(SEARCH_JS), *args], capture_output=True, text=True, check=True)
    return out.stdout


@needs_node
def test_tokenizer_parity_with_javascript():
    samples = [
        "Shutting off the GAS valves",
        "Injuries, bleeding! Café crème; 3-step check (10 min)",
        "Classes", "processes", "glasses", "status", "basis", "studies", "tied", "controlled",
        "X-ray of the 2nd floor at 5:30 p.m.",
        "  Tourniquets and\tcribbing  ",
    ]
    script = (
        "const fs=require(process.argv[1]);"
        "const s=JSON.parse(process.argv[2]);"
        "console.log(JSON.stringify(s.map(x=>fs.tokenize(x))));"
    )
    js = json.loads(run_node(script, json.dumps(samples)))
    assert js == [tokenize(s) for s in samples]


SEARCH_SCRIPT = (
    "const fs=require(process.argv[1]);"
    "const idx=new fs.Index(JSON.parse(require('fs').readFileSync(process.argv[2],'utf8')));"
    "const out={};for(const q of JSON.parse(process.argv[3])){out[q]=idx.search(q,3).results.map(r=>r.doc);}"
    "console.log(JSON.stringify(out));"
)


@needs_node
@pytest.mark.parametrize(
    "query, expected",
    [
        ("tourniquet", 0),
        ("tourn", 0),          # prefix while typing
        ("turniquet", 0),      # one typo
        ("tourniqet", 0),      # one missing letter
        ("shut off gas", 1),
        ("gass valve", 1),     # typo in a short word with another exact word
        ("triage", 2),
        ("extinguisher gauge", 3),
        ("extingusher", 3),    # typo
        ("crib heavy", 4),
    ],
)
def test_javascript_search_ranks_expected_section(tmp_path, query, expected):
    idx_path = tmp_path / "index.json"
    idx_path.write_text(json.dumps(build_index(make_sections())))
    res = json.loads(run_node(SEARCH_SCRIPT, str(idx_path), json.dumps([query])))
    assert res[query][0] == expected, res


@needs_node
def test_javascript_search_returns_nothing_for_unknown_words(tmp_path):
    idx_path = tmp_path / "index.json"
    idx_path.write_text(json.dumps(build_index(make_sections())))
    res = json.loads(run_node(SEARCH_SCRIPT, str(idx_path), json.dumps(["zzzz qqqq"])))
    assert res["zzzz qqqq"] == []
