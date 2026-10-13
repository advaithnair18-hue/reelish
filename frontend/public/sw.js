// Service worker: makes the app installable and receives shares from other apps.
//
// The manifest's share_target POSTs whatever was shared (a TikTok link, or a video
// file) to /share-target. That request has no auth header, so instead of hitting the
// API we stash the shared data in the Cache API and open /share, where the logged-in
// app picks it up and sends it to the server.

const SHELL = "rg-shell-v2";
const INBOX = "share-inbox";

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(SHELL).then((c) => c.addAll(["/", "/manifest.webmanifest", "/icons/icon-192.png"])));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k.startsWith("rg-shell-") && k !== SHELL).map((k) => caches.delete(k))),
    ),
  );
  self.clients.claim();
});

async function receiveShare(request) {
  const form = await request.formData();
  const file = form.get("video");
  const meta = {
    title: form.get("title") || "",
    text: form.get("text") || "",
    url: form.get("url") || "",
    fileName: file && typeof file !== "string" ? file.name : "",
    fileType: file && typeof file !== "string" ? file.type : "",
  };
  const inbox = await caches.open(INBOX);
  await inbox.put("/inbox/meta", new Response(JSON.stringify(meta), { headers: { "Content-Type": "application/json" } }));
  if (file && typeof file !== "string" && file.size > 0) {
    await inbox.put("/inbox/file", new Response(file));
  } else {
    await inbox.delete("/inbox/file");
  }
  return Response.redirect("/share?incoming=1", 303);
}

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (event.request.method === "POST" && url.pathname === "/share-target") {
    event.respondWith(receiveShare(event.request));
    return;
  }
  // App navigations: network first, cached shell when offline. API calls are never cached.
  if (event.request.mode === "navigate" && !url.pathname.startsWith("/api/")) {
    event.respondWith(fetch(event.request).catch(() => caches.match("/")));
  }
});
