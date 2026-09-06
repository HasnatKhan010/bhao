/* Bhao service worker — offline shell + resilient API reads.
   Strategy:
   - navigations: network first, cached page fallback, then /offline.html
   - static assets (/_next/static, /icons): cache first (immutable builds)
   - API GETs: network first with a 1-hour cache fallback — the last known
     truth is better than a blank screen when offline. */
const VERSION = "bhao-v1";
const PAGE_CACHE = `${VERSION}-pages`;
const ASSET_CACHE = `${VERSION}-assets`;
const API_CACHE = `${VERSION}-api`;
const OFFLINE_URL = "/offline.html";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(PAGE_CACHE).then((c) => c.addAll([OFFLINE_URL, "/en", "/ur"])).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => !k.startsWith(VERSION)).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(PAGE_CACHE).then((c) => c.put(req, copy));
          return res;
        })
        .catch(async () => (await caches.match(req)) || (await caches.match(OFFLINE_URL)))
    );
    return;
  }

  if (url.origin === self.location.origin && /\/_next\/static\/|\/icons\//.test(url.pathname)) {
    event.respondWith(
      caches.match(req).then((hit) =>
        hit || fetch(req).then((res) => {
          const copy = res.clone();
          caches.open(ASSET_CACHE).then((c) => c.put(req, copy));
          return res;
        })
      )
    );
    return;
  }

  if (url.origin === self.location.origin && url.pathname.startsWith("/api/")) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(API_CACHE).then((c) => c.put(req, copy));
          return res;
        })
        .catch(async () => (await caches.match(req)) || new Response(
          JSON.stringify({ error: { code: "OFFLINE", message: "You are offline — showing is unavailable." } }),
          { status: 503, headers: { "Content-Type": "application/json" } }
        ))
    );
  }
});
