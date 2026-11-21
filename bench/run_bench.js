#!/usr/bin/env node
/*
 * Retrieval benchmark. Runs the search.js shipped in the built site (the
 * exact code the phone runs) against a question set (bench/*-questions.json) and prints top-1
 * and top-3 accuracy, download and index sizes, and search time.
 *
 * A result counts as correct when the section it opens includes one of the
 * pages that hold the answer, and the section is at most MAX_SPAN pages long
 * (so a 40-page catch-all section cannot score by covering everything).
 *
 * Usage: node bench/run_bench.js [site-dir] [questions.json]  (default: the handbook questions)
 */
"use strict";
const fs = require("fs");
const path = require("path");
const zlib = require("zlib");

const MAX_SPAN = 6;
const RUNS = 30;

const site = path.resolve(process.argv[2] || "site");
const qfile = path.resolve(process.argv[3] || path.join(__dirname, "handbook-questions.json"));
const FS = require(path.join(site, "search.js"));
const read = (f) => fs.readFileSync(path.join(site, f));
const index = new FS.Index(JSON.parse(read("data/index.json")));
const guide = JSON.parse(read("data/sections.json"));
const questions = JSON.parse(fs.readFileSync(qfile, "utf8")).questions;

function walk(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) => {
    const p = path.join(dir, e.name);
    // A sub-folder holding another guide (e.g. cert/) is a separate download.
    if (e.isDirectory()) return fs.existsSync(path.join(p, ".fieldguide-site")) ? [] : walk(p);
    return e.name.startsWith(".") ? [] : [p];
  });
}
const files = walk(site);
const bytes = (list) => list.reduce((n, f) => n + fs.statSync(f).size, 0);
const gz = (list) => list.reduce((n, f) => n + zlib.gzipSync(fs.readFileSync(f)).length, 0);
const images = files.filter((f) => f.includes(path.sep + "pages" + path.sep));
const core = files.filter((f) => !images.includes(f));

function correct(section, pages) {
  const span = section.pages[section.pages.length - 1] - section.pages[0] + 1;
  return span <= MAX_SPAN && section.pages.some((p) => pages.includes(p));
}

let top1 = 0, top3 = 0;
const times = [];
const rows = [];
for (const q of questions) {
  const res = index.search(q.query, 3).results.map((r) => guide.sections[r.doc]);
  for (let i = 0; i < RUNS; i++) {
    const t0 = process.hrtime.bigint();
    index.search(q.query, 10);
    times.push(Number(process.hrtime.bigint() - t0) / 1e6);
  }
  const rank = res.findIndex((s) => correct(s, q.pages)) + 1;
  if (rank === 1) top1++;
  if (rank >= 1) top3++;
  const got = res[0] ? `${res[0].title} (p. ${res[0].pages[0]})` : "(nothing)";
  rows.push(`${rank === 1 ? "ok  " : rank ? "top3" : "MISS"}  ${q.query.padEnd(26)} want p.${q.pages.join(",").padEnd(8)} got: ${got}`);
}
times.sort((a, b) => a - b);
const median = times[Math.floor(times.length / 2)];
const p95 = times[Math.floor(times.length * 0.95)];
const kb = (n) => (n / 1024).toFixed(0) + " KB";
const mb = (n) => (n / 1024 / 1024).toFixed(2) + " MB";
const size = (n) => (n >= 1024 * 1024 ? mb(n) : kb(n));

console.log(rows.join("\n"));
console.log("");
console.log(`Questions:            ${questions.length}`);
console.log(`Top-1 accuracy:       ${top1}/${questions.length} (${((100 * top1) / questions.length).toFixed(0)}%)`);
console.log(`Top-3 accuracy:       ${top3}/${questions.length} (${((100 * top3) / questions.length).toFixed(0)}%)`);
console.log(`Sections:             ${guide.sections.length} from ${guide.pageCount} pages`);
console.log(`Index size:           ${size(fs.statSync(path.join(site, "data/index.json")).size)} (${size(gz([path.join(site, "data/index.json")]))} gzipped)`);
console.log(`Download, no images:  ${size(bytes(core))} in ${core.length} files (${size(gz(core))} gzipped)`);
if (images.length) console.log(`Download, with images: ${size(bytes(files))} in ${files.length} files (page images ${size(bytes(images))})`);
console.log(`Search time:          median ${median.toFixed(2)} ms, p95 ${p95.toFixed(2)} ms (${times.length} runs, Node ${process.version})`);
