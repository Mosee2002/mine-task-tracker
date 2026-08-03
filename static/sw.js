// MWDTS wrapper site — Service Worker
//
// Deliberately minimal, same reasoning as the in-app service worker:
// this only caches the wrapper page's own static shell (icon,
// manifest) for fast repeat loads and PWA installability. It never
// caches the actual app content — which lives in a cross-origin
// iframe this service worker cannot reach anyway, by the browser's
// own same-origin policy, even if it tried.

const SHELL_CACHE = "mwdts-wrapper-shell-v1";
const SHELL_ASSETS = [
  "./index.html",
  "./manifest.json",
  "./icon-192.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(
        names.filter((n) => n !== SHELL_CACHE).map((n) => caches.delete(n))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  const isShellAsset = SHELL_ASSETS.some((a) => url.pathname.endsWith(a.replace("./", "")));
  if (!isShellAsset) return; // let the browser handle everything else normally,
                              // including the cross-origin iframe request

  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});
