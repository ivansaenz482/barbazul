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

/* --- Notificaciones push --- */
self.addEventListener("push", (event) => {
  let data = { title: "Sistema de Facturación", body: "Nuevo aviso", url: "/dashboard" };
  try { data = event.data.json(); } catch (e) {}
  event.waitUntil(
    self.registration.showNotification(data.title || "Aviso", {
      body: data.body || "",
      icon: "/static/img/icon-192.png",
      badge: "/static/img/icon-192.png",
      data: { url: data.url || "/dashboard" },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/dashboard";
  event.waitUntil(
    clients.matchAll({ type: "window" }).then((list) => {
      for (const c of list) {
        if ("focus" in c) { c.focus(); return; }
      }
      if (clients.openWindow) return clients.openWindow(url);
    })
  );
});
