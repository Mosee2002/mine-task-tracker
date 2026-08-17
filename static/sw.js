// Mine & Workshop Digital Tracker — Service Worker
//
// DELIBERATELY MINIMAL. This app is safety-critical and backed by a
// live Supabase database (permit status, incident state, stock
// levels, task assignments). A service worker that caches and serves
// DATA while offline would show a worker a stale "permit still
// active" status after it's actually been signed back, or a task as
// "unassigned" after someone already took it — that's not a
// convenience, it's a hazard. So this file does exactly one thing:
// receive and display push notifications. It does NOT intercept or
// cache page content, API calls, the manifest, or icons — those are
// already embedded as data: URIs directly in the app's own HTML
// specifically so installability needs no separate static files, so
// there is nothing here for a shell cache to usefully hold. (An
// earlier draft tried caching ./manifest.json / ./icon-*.png as
// "shell assets" — those paths don't actually exist as real files in
// this app, and cache.addAll() rejects entirely if even one URL
// 404s, which would have silently broken installation of this whole
// worker, push included. Removed rather than fixed with fallback
// URLs, since there was nothing real for it to accomplish anyway.)
//
// Real offline support for this app would need a fundamentally
// different architecture (local-first data sync with conflict
// resolution) — out of scope here, and not something to fake with a
// naive cache-everything service worker.

self.addEventListener("install", (event) => {
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
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
