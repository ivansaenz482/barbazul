/* Service Worker del Sistema Barbazul (PWA).
   Permite instalar el sistema como app y mantenerlo disponible.
   Estrategia: red primero, y si no hay conexion, usa lo cacheado. */
const CACHE = "barbazul-v1";
const PRE = ["/", "/login", "/static/img/icon-192.png", "/static/img/icon-512.png"];

self.addEventListener("install", (event) => {
  self.skipWaiting();
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(PRE).catch(() => {})));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  event.respondWith(
    fetch(event.request)
      .then((resp) => {
        const copy = resp.clone();
        caches.open(CACHE).then((c) => c.put(event.request, copy)).catch(() => {});
        return resp;
      })
      .catch(() => caches.match(event.request))
  );
});
