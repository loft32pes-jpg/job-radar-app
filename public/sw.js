/* Service worker minimo: serve a rendere Job Radar installabile come app e ad aprirla anche con rete lenta.
   I dati (annunci, preferiti) non vengono mai messi in memoria qui: si chiedono sempre freschi. */
const CACHE = "job-radar-v1";
const SHELL = ["/", "/app.js", "/masc.js", "/icon.svg", "/manifest.webmanifest"];
self.addEventListener("install", e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting())); });
self.addEventListener("activate", e => { e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())); });
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin || url.pathname.startsWith("/api/")) return;
  // prima la rete (così gli aggiornamenti arrivano subito), la copia in memoria solo se la rete non risponde
  e.respondWith(fetch(e.request).then(r => { const copy = r.clone(); caches.open(CACHE).then(c => c.put(e.request, copy)); return r; }).catch(() => caches.match(e.request).then(r => r || caches.match("/"))));
});
