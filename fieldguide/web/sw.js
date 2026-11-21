/* Service worker: cache the whole guide on first load, then serve it from
 * the cache so it keeps working with no connection. The build fills in the
 * version (a content hash) and the list of files. */
"use strict";

var VERSION = "__VERSION__";
var PRECACHE = __PRECACHE__;
var SCOPE_PATH = new URL("./", self.location).pathname;
// One cache per guide (scope), so two guides on one site never delete each other's files.
var PREFIX = "fieldguide-" + SCOPE_PATH + "-";
var CACHE = PREFIX + VERSION;
var OWN = new Set(PRECACHE.map(function (u) { return new URL(u, self.location).pathname; }));

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(CACHE).then(function (cache) {
      // cache: "reload" skips the HTTP cache so a rebuild is picked up whole.
      return cache.addAll(PRECACHE.map(function (u) { return new Request(u, { cache: "reload" }); }));
    }).then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(keys.map(function (k) {
        if (k.indexOf(PREFIX) === 0 && k !== CACHE) return caches.delete(k);
      }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener("fetch", function (event) {
  var req = event.request;
  if (req.method !== "GET") return;
  var url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  var path = url.pathname;
  if (path === SCOPE_PATH + "index.html") path = SCOPE_PATH;
  // Only answer for this guide's own files. Another guide built into a
  // sub-folder (for example cert/) has its own service worker and cache.
  if (!OWN.has(path)) return;
  event.respondWith(
    caches.open(CACHE).then(function (cache) {
      var key = path === SCOPE_PATH ? "./" : req;
      return cache.match(key, { ignoreSearch: true }).then(function (hit) {
        return hit || fetch(req);
      });
    })
  );
});

self.addEventListener("message", function (event) {
  if (event.data === "status") {
    caches.open(CACHE).then(function (cache) { return cache.keys(); }).then(function (keys) {
      event.source.postMessage({ type: "status", cached: keys.length, total: PRECACHE.length, version: VERSION });
    });
  }
});
