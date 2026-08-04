// Mine & Workshop Digital Tracker — Service Worker
//
// DELIBERATELY MINIMAL. This app is safety-critical and backed by a
// live Supabase database (permit status, incident state, stock
// levels, task assignments). A service worker that caches and serves
// DATA while offline would show a worker a stale "permit still
// active" status after it's actually been signed back, or a task as
// "unassigned" after someone already took it — that's not a
// convenience, it's a hazard. So this only caches the static app
// shell (icons, manifest) for fast repeat loads and PWA
// installability. It does NOT intercept or cache any page content or
// API calls, and does NOT claim to make the app usable offline.
//
// Real offline support for this app would need a fundamentally
// different architecture (local-first data sync with conflict
// resolution) — out of scope here, and not something to fake with a
// naive cache-everything service worker.

const SHELL_CACHE = "mine-tracker-shell-v1";
const SHELL_ASSETS = [
  "./manifest.json",
  "./icon-192.png",
  "./icon-512.png",
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

// Only serve from cache for the exact shell assets above, and only
// as a fallback if the network fails — never for anything else.
// Everything else (the app itself, all data) always goes to network.
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  const isShellAsset = SHELL_ASSETS.some((a) => url.pathname.endsWith(a.replace("./", "")));
  if (!isShellAsset) return; // let the browser handle it normally

  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});

// Push notifications — this is the piece that actually displays a
// system-level notification when a message arrives from the server.
// Deliberately simple: the payload is just {title, body}, no attempt
// to cache or act on the data itself, consistent with this service
// worker's overall minimal, no-offline-data philosophy stated above.
self.addEventListener("push", (event) => {
  let payload = { title: "MWDTS", body: "You have a new notification." };
  try {
    if (event.data) payload = event.data.json();
  } catch (e) {
    // Malformed or missing payload — fall back to the generic
    // message above rather than let the whole push event fail
    // silently with no notification shown at all.
  }
  event.waitUntil(
    self.registration.showNotification(payload.title || "MWDTS", {
      body: payload.body || "",
      icon: "./icon-192.png",
      badge: "./icon-192.png",
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: "window" }).then((clientList) => {
      for (const client of clientList) {
        if ("focus" in client) return client.focus();
      }
      if (self.clients.openWindow) return self.clients.openWindow("./");
    })
  );
});
