// Service worker: caches the app shell so the menu opens instantly / offline.
// index.html is fetched network-first so a newly published menu shows up as soon as there is signal.
const CACHE = "ttr-v10";
const SHELL = ["./", "./index.html", "./manifest.webmanifest",
  "./icons/icon-192.png", "./icons/icon-512.png", "./icons/icon-512-maskable.png", "./icons/apple-touch-icon.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;                       // ratings POST always goes to the network
  if (url.origin !== location.origin) {                         // fonts: cache once, serve from cache after
    if (url.hostname.endsWith("gstatic.com") || url.hostname.endsWith("googleapis.com")) {
      e.respondWith(caches.open(CACHE).then(async (c) => (await c.match(e.request)) || fetch(e.request).then((r) => { c.put(e.request, r.clone()); return r; })));
    }
    return;                                                     // Apps Script API etc: network only
  }
  if (e.request.mode === "navigate" || url.pathname.endsWith("index.html")) {
    e.respondWith(fetch(e.request).then((r) => { caches.open(CACHE).then((c) => c.put("./index.html", r.clone())); return r; })
      .catch(() => caches.match("./index.html")));
    return;
  }
  e.respondWith(caches.match(e.request).then((r) => r || fetch(e.request)));
});
