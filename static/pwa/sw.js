const CACHE = "meu-condominio-v1";
const ESSENCIAIS = [
  "/manifest.webmanifest",
  "/static/pwa/icon-192.png",
  "/static/pwa/icon-512.png",
  "/static/pwa/maskable-512.png",
  "/static/pwa/apple-touch-icon.png",
];

self.addEventListener("install", (evento) => {
  evento.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(ESSENCIAIS))
      .then(() => self.skipWaiting())
      .catch(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (evento) => {
  evento.waitUntil(
    caches
      .keys()
      .then((chaves) =>
        Promise.all(chaves.filter((chave) => chave !== CACHE).map((chave) => caches.delete(chave))),
      )
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (evento) => {
  const requisicao = evento.request;

  if (requisicao.method !== "GET") return;

  const url = new URL(requisicao.url);

  if (url.origin !== self.location.origin) return;

  if (url.pathname.startsWith("/static/")) {
    evento.respondWith(
      caches.match(requisicao).then((cacheado) => {
        if (cacheado) return cacheado;
        return fetch(requisicao).then((resposta) => {
          if (resposta.ok) {
            const copia = resposta.clone();
            caches.open(CACHE).then((cache) => cache.put(requisicao, copia));
          }
          return resposta;
        });
      }),
    );
  }
});
