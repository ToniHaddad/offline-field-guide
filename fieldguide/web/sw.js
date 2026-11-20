/* Service worker: cache the whole guide on first load, then serve it from
 * the cache so it keeps working with no connection. The build fills in the
 * version (a content hash) and the list of files. */
"use strict";

var VERSION = "__VERSION__";
var CACHE = "fieldguide-" + VERSION;
var PRECACHE = __PRECACHE__;

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
        if (k.indexOf("fieldguide-") === 0 && k !== CACHE) return caches.delete(k);
      }));
    }).then(function () { return self.clients.claim(); })
  );
});

self.addEventListener("fetch", function (event) {
  var req = event.request;
  if (req.method !== "GET") return;
  var url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  event.respondWith(
    caches.open(CACHE).then(function (cache) {
      var key = req.mode === "navigate" ? "./" : req;
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
