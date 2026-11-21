# offline-field-guide

Turns a long PDF manual into a static, installable web app (PWA) with
client-side search that keeps working with no connection. Main demo: a sample
Warehouse Keeper Handbook (written for this demo, not an official document);
second demo: the real 268-page FEMA CERT manual, built into `cert/`.

## Run and test

```
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"   # bin/ on Linux
python handbook/make_handbook.py            # regenerate manuals/warehouse-keeper-handbook.pdf
fieldguide build manuals/warehouse-keeper-handbook.pdf --out site --related "CERT manual=cert/"
fieldguide build manuals/cert-basic-training-participant-manual.pdf --out site/cert --related "Handbook=../"
fieldguide serve site                        # http://localhost:8101
pytest -q                                    # needs node on PATH for the JS search tests
node bench/run_bench.js site bench/handbook-questions.json
node bench/run_bench.js site/cert bench/cert-questions.json
<python with playwright> scripts/offline_check.py   # offline proof, both guides
```

## Layout

- `fieldguide/` extract.py (PDF to lines/tables, header/footer stripping), structure.py
  (sections, procedures and tables across page breaks), index.py (BM25), site.py, cli.py.
- `fieldguide/web/` shipped app: search.js, app.js, sw.js (per-guide cache), index.html.
- `handbook/` handbook.txt (text) and make_handbook.py (layout, appendices, PDF).
- `bench/` question sets; handbook labels come from answer phrases via resolve_pages.py.

## Quirks

- textutil.py and search.js must tokenize identically; a test compares them.
- After editing handbook.txt: regenerate the PDF, then run resolve_pages.py; tests check both.
- Build the root guide before the cert/ one: `build` deletes its output folder.
- Each guide must be opened once online before it works offline.
- Ranking: heading bonus, reference sections x0.6 (index.py), synonyms in search.js. Tune only on bench/handbook-questions.json and cert; handbook-unseen.json is the held-out set.
- Page numbers shown are PDF page numbers. Arabic text is not indexed.
