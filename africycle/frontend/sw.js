// Africycle service worker. backend/app.py serves this file with BUILD and FILES filled in.
// BUILD changes whenever any file in frontend/ changes, so each deploy installs a fresh,
// complete copy of the app's pages, styles and scripts, and deletes the old copy.
// API requests and photos are never handled here: they always go to the server.
//
// To switch the worker off for everyone, replace everything below with:
//   self.addEventListener("install", () => self.skipWaiting());
//   self.addEventListener("activate", () => self.registration.unregister());
"use strict";

const BUILD = "__BUILD__";
const FILES = __FILES__;
const CACHE = `africycle-${BUILD}`;

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((cache) => cache.addAll(FILES.map((path) => new Request(path, { cache: "no-cache" }))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys
        .filter((key) => key.startsWith("africycle-") && key !== CACHE)
        .map((key) => caches.delete(key))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return; // map tiles come straight from OpenStreetMap
  const path = url.pathname === "/" ? "/index.html" : url.pathname;
  const isPage = request.mode === "navigate";
  // A language's translations are kept once used, so the app opens in that language offline
  // too. Only the languages a phone uses are downloaded, not all of them.
  const isTranslation = /^\/i18n\/[\w-]+\.json$/.test(path);
  if (!isPage && !isTranslation && !FILES.includes(path)) return; // API calls and photos go straight to the server

  event.respondWith(
    caches.open(CACHE).then((cache) => cache.match(path).then((saved) => saved || fetch(request)
      .then((response) => {
        if (isTranslation && response.ok) cache.put(path, response.clone());
        return response;
      })
      .catch(() => (isPage
        ? caches.match("/offline.html").then((page) => page || Response.error())
        : Response.error()))))
  );
});

// ---- Notifications sent by the server (see backend/webpush.py and backend/alerts.py) ----

self.addEventListener("push", (event) => {
  let message = {};
  try {
    message = event.data ? event.data.json() : {};
  } catch (err) {
    message = { body: event.data ? event.data.text() : "" };
  }
  event.waitUntil(self.registration.showNotification(message.title || "Africycle", {
    body: message.body || "",
    icon: "/icons/icon-192.png",
    badge: "/icons/badge-96.png",
    tag: message.tag || undefined,
    renotify: Boolean(message.tag), // a newer message from the same person still buzzes
    vibrate: [120, 60, 120],
    data: { url: message.url || "/" }
  }));
});

// Tapping a notification opens the right page, reusing an open Africycle window if any
self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL((event.notification.data && event.notification.data.url) || "/", self.location.origin).href;
  event.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
    const same = windows.find((client) => client.url === url);
    if (same) return same.focus();
    const open = windows.find((client) => new URL(client.url).origin === self.location.origin && "navigate" in client);
    if (open) return open.focus().then(() => open.navigate(url)).catch(() => self.clients.openWindow(url));
    return self.clients.openWindow(url);
  }));
});
