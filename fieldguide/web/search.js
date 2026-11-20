/*
 * Field guide search: a small BM25 ranker with prefix and typo tolerance.
 * Plain JavaScript, no dependencies. Runs in the browser and under Node
 * (the benchmark loads this same file).
 *
 * The tokenizer must stay identical to fieldguide/textutil.py, which builds
 * the index at build time. tests/test_tokenizer_parity.py checks both.
 */
(function (root) {
  "use strict";

  var STOPWORDS = new Set((
    "a an and are as at be been but by can do does for from has have how i if in into is it its " +
    "may must no not of on or should so than that the their them then there these they this to " +
    "was we were what when where which while who will with you your"
  ).split(" "));

  function normalize(s) {
    return String(s).normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  }

  function stem(t) {
    if (t.length > 4 && t.endsWith("ies")) t = t.slice(0, -3) + "y";
    else if (t.endsWith("sses")) t = t.slice(0, -2);
    else if (t.length > 3 && t.endsWith("s") && !/(ss|us|is)$/.test(t)) t = t.slice(0, -1);
    if (t.length >= 7 && t.endsWith("ing")) t = t.slice(0, -3);
    else if (t.length >= 6 && t.endsWith("ed")) t = t.slice(0, -2);
    return t;
  }

  function tokenize(s) {
    // Dotted acronyms become one word: "P.A.S.S." -> "pass".
    var text = normalize(s).replace(/\b(?:[a-z]\.){2,}/g, function (m) { return m.replace(/\./g, ""); });
    var words = text.match(/[a-z0-9]+/g) || [];
    var out = [];
    for (var i = 0; i < words.length; i++) {
      var w = words[i];
      if (STOPWORDS.has(w)) continue;
      if (w.length < 2 && !/[0-9]/.test(w)) continue;
      out.push(stem(w));
    }
    return out;
  }

  // Damerau-Levenshtein (optimal string alignment) with an early exit.
  function editDistance(a, b, max) {
    var la = a.length, lb = b.length;
    if (Math.abs(la - lb) > max) return max + 1;
    var prev2 = null, prev = new Array(lb + 1), cur;
    for (var j = 0; j <= lb; j++) prev[j] = j;
    for (var i = 1; i <= la; i++) {
      cur = new Array(lb + 1);
      cur[0] = i;
      var rowMin = cur[0];
      for (j = 1; j <= lb; j++) {
        var cost = a.charCodeAt(i - 1) === b.charCodeAt(j - 1) ? 0 : 1;
        var v = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost);
        if (prev2 && i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) {
          v = Math.min(v, prev2[j - 2] + 1);
        }
        cur[j] = v;
        if (v < rowMin) rowMin = v;
      }
      if (rowMin > max) return max + 1;
      prev2 = prev;
      prev = cur;
    }
    return prev[lb];
  }

  function Index(data) {
    this.terms = data.terms;             // sorted vocabulary
    this.postings = data.postings;       // per term: flat [doc, tf, doc, tf, ...]
    this.dl = data.dl;                   // weighted document lengths
    this.N = this.dl.length;
    this.avgdl = data.avgdl;
    this.k1 = data.k1 || 1.2;
    this.b = data.b || 0.75;
    this.termId = new Map();
    for (var i = 0; i < this.terms.length; i++) this.termId.set(this.terms[i], i);
  }

  Index.prototype.idf = function (t) {
    var df = this.postings[t].length / 2;
    return Math.log(1 + (this.N - df + 0.5) / (df + 0.5));
  };

  // First vocabulary position whose term is >= s (binary search).
  Index.prototype.lowerBound = function (s) {
    var lo = 0, hi = this.terms.length;
    while (lo < hi) {
      var mid = (lo + hi) >> 1;
      if (this.terms[mid] < s) lo = mid + 1; else hi = mid;
    }
    return lo;
  };

  // Map one query token to vocabulary terms with a weight each:
  // exact 1.0, prefix 0.8, one typo 0.7, two typos 0.45.
  Index.prototype.expand = function (q) {
    var out = new Map();
    var exact = this.termId.get(q);
    if (exact !== undefined) out.set(exact, 1.0);
    if (q.length >= 3) {
      for (var i = this.lowerBound(q); i < this.terms.length && this.terms[i].startsWith(q); i++) {
        if (!out.has(i)) out.set(i, 0.8);
      }
    }
    if (out.size === 0 && q.length >= 4 && !/^[0-9]+$/.test(q)) {
      var max = q.length >= 8 ? 2 : 1;
      for (var k = 0; k < this.terms.length; k++) {
        var t = this.terms[k];
        var d = editDistance(q, t, max);
        // A typo in a partly typed word: compare against the term's prefix too.
        if (d > max && t.length > q.length) d = editDistance(q, t.slice(0, q.length), max);
        if (d <= max) out.set(k, d === 1 ? 0.7 : 0.45);
      }
    }
    return out;
  };

  Index.prototype.search = function (query, limit) {
    limit = limit || 10;
    var qtokens = Array.from(new Set(tokenize(query)));
    var N = this.N, k1 = this.k1, b = this.b, avgdl = this.avgdl;
    var total = new Float64Array(N);
    var hits = new Uint8Array(N);
    var matched = new Set();
    var self = this;
    qtokens.forEach(function (q) {
      var best = new Float64Array(N);   // best expansion per document for this token
      self.expand(q).forEach(function (w, t) {
        matched.add(self.terms[t]);
        var idf = self.idf(t), p = self.postings[t];
        for (var i = 0; i < p.length; i += 2) {
          var doc = p[i], tf = p[i + 1];
          var s = w * idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * self.dl[doc] / avgdl));
          if (s > best[doc]) best[doc] = s;
        }
      });
      for (var d = 0; d < N; d++) if (best[d] > 0) { total[d] += best[d]; hits[d]++; }
    });
    var results = [];
    var n = qtokens.length;
    for (var d = 0; d < N; d++) {
      if (total[d] > 0) {
        // Favour sections that match every word of the query.
        results.push({ doc: d, score: total[d] * (0.5 + 0.5 * hits[d] / n) });
      }
    }
    results.sort(function (x, y) { return y.score - x.score; });
    return { results: results.slice(0, limit), terms: Array.from(matched) };
  };

  // Wrap words whose stem is in `terms` with <mark>. Returns HTML.
  function escapeHtml(s) {
    return s.replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function highlight(text, termSet) {
    var parts = String(text).split(/([A-Za-z0-9\u00c0-\u024f]+)/);
    var html = "";
    for (var i = 0; i < parts.length; i++) {
      var p = parts[i];
      if (i % 2 === 1 && termSet.has(stem(normalize(p)))) html += "<mark>" + escapeHtml(p) + "</mark>";
      else html += escapeHtml(p);
    }
    return html;
  }

  var api = {
    tokenize: tokenize, stem: stem, normalize: normalize, editDistance: editDistance,
    Index: Index, highlight: highlight, escapeHtml: escapeHtml
  };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.FieldSearch = api;
})(typeof self !== "undefined" ? self : this);
