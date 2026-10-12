/* Service Worker del Sistema Barbazul (PWA).
   Estrategia SEGURA: solo se cachean los recursos estaticos propios
   (imagenes, css, js). Las PAGINAS (que contienen datos de clientes)
   NUNCA se guardan en cache, para no dejar informacion en el equipo. */
const CACHE = "barbazul-v2";
const PRE = ["/static/img/icon-192.png", "/static/img/icon-512.png"];

self.addEventListener("install", (event) => {
  self.skipWaiting();
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(PRE).catch(() => {})));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  let url;
  try { url = new URL(event.request.url); } catch (e) { return; }
  // Solo cachear estaticos del propio dominio; el resto va directo a la red.
  if (url.origin !== self.location.origin || !url.pathname.startsWith("/static/")) {
    return;
  }
  event.respondWith(
    caches.match(event.request).then((cached) => {
      const red = fetch(event.request).then((resp) => {
        const copy = resp.clone();
        caches.open(CACHE).then((c) => c.put(event.request, copy)).catch(() => {});
        return resp;
      }).catch(() => cached);
      return cached || red;
    })
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
