// sw.js - keeps the app shell available offline and loading fast on slow networks.
// Only files under /app/ are cached. API calls (/scan, /compare, …) always go
// to the network: a stale verdict must never be served from a cache here.
const VERSION = "il-shell-20";   // bump with APP_VERSION in lib.js
const SHELL = ["./", "index.html", "app.css", "app.js", "lib.js", "camera.js",
               "manifest.webmanifest", "icon.svg", "icon-maskable.svg", "icon-192.png",
               "fonts/dm-sans-400.woff2", "fonts/dm-sans-600.woff2", "fonts/dm-sans-700.woff2",
               "fonts/bricolage-grotesque-600.woff2", "fonts/bricolage-grotesque-800.woff2"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(VERSION).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", e => {
  e.waitUntil(caches.keys()
    .then(keys => Promise.all(keys.filter(k => k !== VERSION).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});

// Network first, cache as fallback: a new deploy shows up on the next open.
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin || !url.pathname.startsWith("/app/")) return;
  e.respondWith(fetch(e.request).then(res => {
    if (res.ok) { const copy = res.clone(); caches.open(VERSION).then(c => c.put(e.request, copy)); }
    return res;
  }).catch(() => caches.match(e.request).then(hit => hit || caches.match("index.html"))));
});
