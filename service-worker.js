// Courtside — offline app-shell cache.
// Everything the app needs (HTML/CSS/JS) is inlined in index.html, so caching
// that one file is enough for full offline use after the first load.
//
// IMPORTANT: the page itself is fetched NETWORK-FIRST. An earlier version used
// cache-first for everything, which meant an installed (home-screen) copy kept
// serving the old HTML forever and never picked up a new release. Static assets
// (icons, manifest) stay cache-first since they rarely change.
var CACHE_NAME = "courtside-v1";
var APP_SHELL = ["./", "./index.html", "./manifest.json", "./icon-192.png", "./icon-512.png"];

self.addEventListener("install", function (event) {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then(function (cache) {
      return cache.addAll(APP_SHELL).catch(function () {
        // Tolerate individual failures (e.g. an icon path mismatch) so install still succeeds.
      });
    })
  );
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys.filter(function (k) { return k !== CACHE_NAME; }).map(function (k) { return caches.delete(k); })
      );
    })
  );
  self.clients.claim();
});

function isPageRequest(req) {
  if (req.mode === "navigate") return true;
  var accept = req.headers.get("accept") || "";
  return accept.indexOf("text/html") !== -1;
}

self.addEventListener("fetch", function (event) {
  var req = event.request;
  if (req.method !== "GET") return;

  // Sayfa: önce ağ, sonra önbellek — güncellemeler böyle ulaşır.
  if (isPageRequest(req)) {
    event.respondWith(
      fetch(req)
        .then(function (res) {
          if (res && res.ok) {
            var clone = res.clone();
            caches.open(CACHE_NAME).then(function (cache) { cache.put("./index.html", clone); });
          }
          return res;
        })
        .catch(function () {
          return caches.match(req).then(function (hit) {
            return hit || caches.match("./index.html");
          });
        })
    );
    return;
  }

  // Diğer dosyalar: önce önbellek, yoksa ağdan alıp sakla.
  event.respondWith(
    caches.match(req).then(function (cached) {
      if (cached) return cached;
      return fetch(req)
        .then(function (res) {
          if (res && res.ok && req.url.indexOf(self.location.origin) === 0) {
            var resClone = res.clone();
            caches.open(CACHE_NAME).then(function (cache) { cache.put(req, resClone); });
          }
          return res;
        })
        .catch(function () {
          return caches.match("./index.html");
        });
    })
  );
});
