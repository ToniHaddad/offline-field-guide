/* Field guide app: search, results, section view, offline status. */
(function () {
  "use strict";
  var FS = window.FieldSearch;
  var $ = function (id) { return document.getElementById(id); };
  var main = $("main"), input = $("q"), box = $("search-box");
  var guide = null, index = null, byId = new Map();

  // ---------- helpers ----------
  function esc(s) { return FS.escapeHtml(String(s)); }
  function pageLabel(pages) {
    if (!pages.length) return "";
    var a = pages[0], b = pages[pages.length - 1];
    return a === b ? "p. " + a : "p. " + a + "\u2013" + b;
  }
  function pageSentence(pages) {
    var a = pages[0], b = pages[pages.length - 1];
    var of = " of the original";
    return a === b ? "Page " + a + of : "Pages " + a + "\u2013" + b + of;
  }
  function sectionText(s) {
    var out = [];
    s.blocks.forEach(function (b) {
      if (b.t === "p") out.push(b.text);
      else if (b.t === "ol" || b.t === "ul") b.items.forEach(function (i) { out.push(i.text); });
      else if (b.t === "table") b.rows.forEach(function (r) { out.push(r.join(" \u00b7 ")); });
    });
    return out.join(" ");
  }
  function snippet(text, terms) {
    var re = /[A-Za-z0-9\u00c0-\u024f]+/g, m, at = -1;
    while ((m = re.exec(text))) {
      if (terms.has(FS.stem(FS.normalize(m[0])))) { at = m.index; break; }
    }
    if (at < 0) return FS.escapeHtml(text.slice(0, 180)) + (text.length > 180 ? "\u2026" : "");
    var start = Math.max(0, at - 60);
    if (start > 0) { var sp = text.indexOf(" ", start); if (sp > 0 && sp < at) start = sp + 1; }
    var piece = text.slice(start, start + 220);
    return (start > 0 ? "\u2026" : "") + FS.highlight(piece, terms) + (start + 220 < text.length ? "\u2026" : "");
  }

  // ALL-CAPS headings read badly on a phone: "SECTION 4: HOME AND WORK" -> "Section 4: Home and Work".
  var SMALL = new Set("a an and as at but by for in of on or the to with".split(" "));
  function niceTitle(t) {
    if (!/[A-Z]{3}/.test(t) || t !== t.toUpperCase()) return t;
    return t.toLowerCase().replace(/[a-z][a-z'\u2019]*/g, function (w, i) {
      return i > 0 && SMALL.has(w) ? w : w.charAt(0).toUpperCase() + w.slice(1);
    }).replace(/\b(Cert|Cbrne|Ics|Ems|Eop|Hazmat)\b/g, function (w) { return w.toUpperCase(); });
  }
  function crumbHtml(s) {
    return s.crumbs.length ? '<div class="crumb">' + esc(s.crumbs.join(" \u203a ")) + "</div>" : "";
  }
  function prepare() {
    var roots = new Set(guide.sections.map(function (s) { return s.path[0] || ""; }));
    var sharedRoot = roots.size === 1;
    guide.sections.forEach(function (s, i) {
      s.n = i;
      s.display = niceTitle(s.title);
      s.crumbs = (sharedRoot ? s.path.slice(1) : s.path).map(niceTitle);
      s.group = s.crumbs[0] || s.display;
    });
  }

  // ---------- routing ----------
  function parseHash() {
    var p = new URLSearchParams(location.hash.slice(1));
    return { q: p.get("q") || "", s: p.get("s") || "" };
  }
  function go(q, s, replace) {
    var p = new URLSearchParams();
    if (q) p.set("q", q);
    if (s) p.set("s", s);
    var h = "#" + p.toString();
    if (h === location.hash) { render(); return; }
    if (replace) { history.replaceState(null, "", h); render(); }
    else location.hash = h;
  }
  window.addEventListener("hashchange", render);

  // ---------- views ----------
  function renderHome() {
    // Contents: one collapsible group per chapter (the first heading above
    // each section), in manual order.
    var groups = [];
    guide.sections.forEach(function (s) {
      var g = groups[groups.length - 1];
      if (!g || g.name !== s.group) { g = { name: s.group, items: [] }; groups.push(g); }
      g.items.push(s);
    });
    var html = '<div class="toc"><h2>Contents</h2>' + groups.map(function (g) {
      var first = g.items[0].pages[0], last = g.items[g.items.length - 1].pages.slice(-1)[0];
      var minLevel = Math.min.apply(null, g.items.map(function (s) { return s.level; }));
      return '<details><summary><span>' + esc(g.name) + '</span><span class="cnt">' + g.items.length +
        " \u00b7 " + pageLabel([first, last]) + "</span></summary><ol>" + g.items.map(function (s) {
          var sub = s.level > minLevel ? ' class="sub"' : "";
          return "<li" + sub + '><a href="#s=' + encodeURIComponent(s.id) + '"><span>' + esc(s.display) + "</span><span>" + pageLabel(s.pages) + "</span></a></li>";
        }).join("") + "</ol></details>";
    }).join("") + "</div>";
    var note = guide.note ? '<p class="note-banner">' + esc(guide.note) + "</p>" : "";
    var related = (guide.related || []).map(function (r) {
      return '<a class="related" href="' + esc(r.url) + '"><span>Switch guide</span><strong>' + esc(r.title) + "</strong></a>";
    }).join("");
    main.innerHTML = note + '<p class="meta">' + guide.sections.length + " sections from " + guide.pageCount +
      " pages. Type a few words, a typo is fine.</p>" + html + related;
  }

  function renderResults(q) {
    var t0 = performance.now();
    var res = index.search(q, 20);
    var ms = performance.now() - t0;
    var terms = new Set(res.terms);
    if (!res.results.length) {
      main.innerHTML = '<div class="empty"><strong>Nothing found for \u201c' + esc(q) + '\u201d</strong>Try a shorter word or another term the manual might use.</div>';
      return;
    }
    var items = res.results.map(function (r) {
      var s = guide.sections[r.doc];
      var crumb = crumbHtml(s);
      return '<li class="result"><a href="#q=' + encodeURIComponent(q) + "&s=" + encodeURIComponent(s.id) + '">' + crumb +
        '<div class="r-head"><span class="r-title">' + FS.highlight(s.display, terms) + '</span><span class="pg">' + pageLabel(s.pages) + "</span></div>" +
        '<p class="snippet">' + snippet(sectionText(s), terms) + "</p></a></li>";
    }).join("");
    main.innerHTML = '<p class="meta">' + res.results.length + (res.results.length === 20 ? "+" : "") + " results \u00b7 " +
      ms.toFixed(1) + ' ms</p><ol class="results">' + items + "</ol>";
  }

  function renderBlocks(s, terms) {
    var hl = function (t) { return FS.highlight(t, terms); };
    return s.blocks.map(function (b) {
      if (b.t === "p") return "<p>" + hl(b.text) + "</p>";
      if (b.t === "ul") return "<ul>" + b.items.map(function (i) { return "<li>" + hl(i.text) + "</li>"; }).join("") + "</ul>";
      if (b.t === "ol") return '<ol class="steps" style="--start:' + ((b.start || 1) - 1) + '">' +
        b.items.map(function (i) { return "<li>" + hl(i.text) + "</li>"; }).join("") + "</ol>";
      if (b.t === "table") {
        var head = b.rows[0], rest = b.rows.slice(1);
        return '<div class="table-wrap"><table><thead><tr>' + head.map(function (c) { return "<th>" + hl(c) + "</th>"; }).join("") +
          "</tr></thead><tbody>" + rest.map(function (r) {
            return "<tr>" + r.map(function (c) { return "<td>" + hl(c) + "</td>"; }).join("") + "</tr>";
          }).join("") + "</tbody></table></div>";
      }
      return "";
    }).join("");
  }

  function renderSection(id, q) {
    var s = byId.get(id);
    if (!s) { renderHome(); return; }
    var terms = new Set(q ? index.search(q, 1).terms : []);
    var crumb = crumbHtml(s);
    var pagesBtn = guide.pageImages
      ? '<button class="btn" id="show-page" type="button"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 8h6M9 12h6M9 16h3"/></svg>Show original page</button>'
      : '<span class="note">Page images not included in this build</span>';
    main.innerHTML =
      '<button class="back" id="back" type="button">\u2190 ' + (q ? "Back to results" : "Contents") + "</button>" +
      "<article>" + crumb + "<h1>" + FS.highlight(s.display, terms) + "</h1>" +
      '<div class="src"><span class="pg">' + pageSentence(s.pages) + "</span>" + pagesBtn + "</div>" +
      '<div class="pages" id="pages" hidden></div>' +
      '<div class="body">' + renderBlocks(s, terms) + "</div></article>";
    $("back").onclick = function () { go(q, "", false); };
    var btn = $("show-page");
    if (btn) btn.onclick = function () {
      var el = $("pages");
      if (el.hidden) {
        el.innerHTML = s.pages.slice(0, 6).map(function (n) {
          return '<figure><img src="pages/p' + n + '.jpg" alt="Page ' + n + ' of the original manual" loading="lazy"><figcaption>Page ' + n + "</figcaption></figure>";
        }).join("");
        el.hidden = false;
        btn.lastChild.textContent = "Hide original page";
      } else {
        el.hidden = true;
        btn.lastChild.textContent = "Show original page";
      }
    };
    var first = main.querySelector(".body mark");
    window.scrollTo(0, 0);
    // Bring the first highlighted word into view only if it is below the fold.
    if (first && first.getBoundingClientRect().bottom > window.innerHeight) first.scrollIntoView({ block: "center" });
  }

  function render() {
    if (!guide) return;
    var h = parseHash();
    if (input.value !== h.q && document.activeElement !== input) input.value = h.q;
    box.classList.toggle("has-query", !!input.value);
    if (h.s) renderSection(h.s, h.q);
    else if (h.q.trim()) renderResults(h.q);
    else renderHome();
  }

  // ---------- search box ----------
  var timer = 0;
  input.addEventListener("input", function () {
    box.classList.toggle("has-query", !!input.value);
    clearTimeout(timer);
    timer = setTimeout(function () { go(input.value, "", true); }, 60);
  });
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter") { input.blur(); }
  });
  $("clear").addEventListener("click", function () { input.value = ""; go("", "", true); input.focus(); });

  // ---------- offline status ----------
  var status = $("status"), statusText = $("status-text");
  function setStatus(state, text) { status.dataset.state = state; statusText.textContent = text; }
  function checkSaved() {
    if (!("caches" in window)) return Promise.resolve(false);
    return caches.keys().then(function (keys) {
      var prefix = "fieldguide-" + new URL("./", location.href).pathname + "-";
      var k = keys.filter(function (x) { return x.indexOf(prefix) === 0; });
      if (!k.length) return false;
      return caches.open(k[k.length - 1]).then(function (c) { return c.match("data/index.json"); }).then(Boolean);
    }).catch(function () { return false; });
  }
  // navigator.onLine only knows about the local link, so also try to reach
  // the server. HEAD requests skip the service worker cache.
  function reachable() {
    if (!navigator.onLine) return Promise.resolve(false);
    return fetch("index.html?fg-ping=" + Date.now(), { method: "HEAD", cache: "no-store" })
      .then(function (r) { return r.ok; }, function () { return false; });
  }
  function updateStatus() {
    return Promise.all([checkSaved(), reachable()]).then(function (r) {
      var saved = r[0], online = r[1];
      if (!online) setStatus(saved ? "offline" : "saving", saved ? "Offline \u00b7 saved copy" : "Offline");
      else setStatus(saved ? "saved" : "saving", saved ? "Saved for offline" : "Saving for offline");
      return saved;
    });
  }
  window.addEventListener("online", updateStatus);
  window.addEventListener("offline", updateStatus);
  setInterval(updateStatus, 4000);
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.addEventListener("controllerchange", updateStatus);
    navigator.serviceWorker.register("sw.js").then(function () {
      return navigator.serviceWorker.ready;
    }).then(updateStatus).catch(function () { setStatus("saving", "Offline cache unavailable"); });
  } else {
    setStatus("saving", "Offline cache unavailable");
  }

  // ---------- load ----------
  Promise.all([
    fetch("data/sections.json").then(function (r) { return r.json(); }),
    fetch("data/index.json").then(function (r) { return r.json(); })
  ]).then(function (all) {
    guide = all[0];
    index = new FS.Index(all[1]);
    guide.sections.forEach(function (s) { byId.set(s.id, s); });
    prepare();
    $("manual-title").textContent = guide.title;
    var src = guide.source;
    $("footer").innerHTML = "Built from " + (/^https?:/.test(src) ? '<a href="' + esc(src) + '">the original PDF</a>' : esc(src)) +
      ". Search runs on this device; nothing is sent anywhere.";
    document.body.dataset.ready = "1";
    render();
    updateStatus();
  }).catch(function () {
    main.innerHTML = '<div class="empty"><strong>Could not load the guide</strong>Open it once while connected so it can be saved for offline use.</div>';
  });
})();
