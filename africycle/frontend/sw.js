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
  if (!isPage && !FILES.includes(path)) return; // API calls and photos go straight to the server

  event.respondWith(
    caches.open(CACHE)
      .then((cache) => cache.match(path))
      .then((saved) => saved || fetch(request).catch(() => (isPage
        ? caches.match("/offline.html").then((page) => page || Response.error())
        : Response.error())))
  );
});
