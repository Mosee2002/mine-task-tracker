const CACHE_NAME = 'mine-tracker-v3';
const urlsToCache = [
  '/',
  '/static/manifest.json'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
  );
});

self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        if (response) {
          return response;
        }
        return fetch(event.request).catch(() => {
          // Offline fallback – return a simple offline page
          return new Response('You are offline. Please connect to the internet.', {
            status: 503,
            statusText: 'Service Unavailable'
          });
        });
      })
  );
});
