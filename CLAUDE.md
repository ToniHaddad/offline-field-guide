# offline-field-guide

Turns a long PDF manual into a static, installable web app (PWA) with
client-side search that keeps working with no connection.

## Run and test

```
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"   # bin/ on Linux
fieldguide build manuals/cert-basic-training-participant-manual.pdf --out site [--page-images]
fieldguide serve site            # http://localhost:8101
pytest -q                        # needs node on PATH for the JS search tests
node bench/run_bench.js site     # retrieval benchmark
<python with playwright> scripts/offline_check.py   # offline proof
```

## Layout

- `fieldguide/extract.py` PDF to lines + tables, strips headers/footers/page numbers.
- `fieldguide/structure.py` lines to sections: headings (fonts + PDF outline),
  procedures and paragraphs joined across page breaks, tables kept in their section.
- `fieldguide/index.py` BM25 index built at build time; `textutil.py` tokenizer.
- `fieldguide/web/` the shipped app: `search.js` (BM25, prefix, typo), `app.js`,
  `sw.js` (precache list and version filled in by the build), `index.html`.
- `bench/` questions with answer pages, and the Node runner.
- `tests/pdfmaker.py` builds small test PDFs with PyMuPDF.

## Quirks

- `textutil.py` and `search.js` must tokenize identically; a test compares them.
- `build` deletes the output folder only if it holds a `.fieldguide-site` marker.
- Port 8101 is the default for `serve`.
- Page numbers shown are PDF page numbers, not the manual's printed "1-5" labels.
