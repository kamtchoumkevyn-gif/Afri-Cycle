// Shared map and location helpers: Leaflet (served from vendor/leaflet) with OpenStreetMap
// tiles. Load after vendor/leaflet/leaflet.js and api.js. If Leaflet didn't load,
// AfriMap.create returns null and the page keeps working without a map.

const AfriMap = (function () {
  const TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
  const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
  const CAMEROON = [5.7, 12.4];

  function create(element) {
    if (typeof window.L === "undefined" || !element) return null;
    const map = L.map(element, { scrollWheelZoom: false, zoomControl: false }).setView(CAMEROON, 6);
    L.control.zoom({ zoomInTitle: t("Zoom in"), zoomOutTitle: t("Zoom out") }).addTo(map);
    L.tileLayer(TILES, { maxZoom: 19, attribution: ATTRIBUTION }).addTo(map);
    // Pop-ups that fit on a small phone: clear of the zoom buttons on the left (which
    // Leaflet draws on top of pop-ups) and inside the map on the right. 50 px covers the
    // pop-up's own frame and margins.
    map.on("popupopen", (event) => {
      const width = map.getSize().x;
      const options = event.popup.options;
      options.autoPanPaddingTopLeft = L.point(56, 10);
      options.autoPanPaddingBottomRight = L.point(10, 10);
      options.maxWidth = Math.max(120, Math.min(300, width - 56 - 10 - 50));
      event.popup.update();
    });
    return map;
  }

  // A coloured dot with an optional label beside it. kind: me, buyer, best, seller or home.
  function pin(kind, label) {
    return L.divIcon({
      className: `map-pin map-pin-${kind}`,
      html: `<span class="map-pin-dot"></span>${label ? `<span class="map-pin-label">${escapeHtml(label)}</span>` : ""}`,
      iconSize: [18, 18],
      iconAnchor: [9, 9],
      popupAnchor: [0, -10]
    });
  }

  // Leaflet measures its box when created, so tell it when a hidden map appears
  function show(map, element) {
    element.hidden = false;
    map.invalidateSize();
  }

  // Room on the left for the zoom buttons (so no pin hides under them), and on the right
  // for the labels beside each dot
  function fit(map, points) {
    const valid = points.filter(Boolean);
    if (valid.length === 1) map.setView(valid[0], 15);
    if (valid.length > 1) {
      map.fitBounds(L.latLngBounds(valid), {
        paddingTopLeft: [56, 30], paddingBottomRight: [120, 30], maxZoom: 16
      });
    }
  }

  function distanceKm(a, b) {
    const rad = Math.PI / 180;
    const dLat = (b[0] - a[0]) * rad;
    const dLng = (b[1] - a[1]) * rad;
    const h = Math.sin(dLat / 2) ** 2 +
      Math.cos(a[0] * rad) * Math.cos(b[0] * rad) * Math.sin(dLng / 2) ** 2;
    return 2 * 6371 * Math.asin(Math.sqrt(h));
  }

  // 850 m, 1.2 km (1,2 km in French...)
  function formatDistance(km) {
    return km < 1 ? AfriI18n.formatUnit(Math.round(km * 1000), "meter") : AfriI18n.formatUnit(km, "kilometer", 1);
  }

  function timeAgo(isoString) {
    if (!isoString) return "";
    const value = isoString.endsWith("Z") ? isoString : `${isoString}Z`;
    const seconds = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 1000));
    if (seconds < 3600) return AfriI18n.formatAgo(seconds);
    return formatDate(isoString);
  }

  function directionsUrl(point) {
    return `https://www.google.com/maps/dir/?api=1&destination=${Number(point[0])},${Number(point[1])}`;
  }

  // The device's position as [lat, lng]. Asks for GPS first; when that is slow (indoors,
  // or a phone with a weak GPS), falls back to the quicker position from mobile networks
  // and Wi-Fi, which is accurate enough to find buyers nearby.
  function locate() {
    return new Promise((resolve, reject) => {
      if (!navigator.geolocation) {
        reject({ code: 0 });
        return;
      }
      const found = (position) => resolve([position.coords.latitude, position.coords.longitude]);
      navigator.geolocation.getCurrentPosition(found, (error) => {
        if (error.code === 1) {
          reject(error); // permission refused: asking again won't help
          return;
        }
        navigator.geolocation.getCurrentPosition(found, reject,
          { enableHighAccuracy: false, timeout: 20000, maximumAge: 120000 });
      }, { enableHighAccuracy: true, timeout: 12000, maximumAge: 10000 });
    });
  }

  // What to tell the person when locate() fails
  function locationErrorMessage(error) {
    if (window.isSecureContext === false) {
      return t("Location only works on a secure address. Open Africycle with https:// at the start.");
    }
    if (!error || !error.code) {
      return t("This browser can't share your location. Try Chrome, Firefox, Safari or Samsung Internet.");
    }
    if (error.code === 1) {
      // In the Android app, location is the app's own permission (not the browser's)
      if (typeof inAndroidApp === "function" && inAndroidApp()) {
        return t("Location is blocked for Africycle. In your phone's settings, open Apps, then Africycle, then Permissions, and allow Location. Then try again.");
      }
      return t("Location is blocked for Africycle. Allow it in your browser's settings for this site (the icon beside the address), then try again.");
    }
    if (error.code === 2) {
      return t("Your position isn't available. Turn on location (GPS) in your phone's settings, then try again.");
    }
    return t("Finding your position took too long. Move near a window or outside, then try again.");
  }

  // ---- Road directions (the server asks OpenStreetMap's routing service; see /directions) ----

  async function fetchRoute(from, to, mode) {
    const query = `from=${from[0]},${from[1]}&to=${to[0]},${to[1]}&mode=${mode}`;
    const response = await authFetch(`/directions?${query}`);
    const data = await readJson(response);
    if (!response.ok) {
      throw new Error(data.message || t("Directions aren't available right now. Try again in a minute."));
    }
    return prepareRoute(data);
  }

  // Flat x/y in km around a point: accurate enough over the few km of a trip
  function toKm(origin, point) {
    const kmPerDegLng = 111.32 * Math.cos(origin[0] * Math.PI / 180);
    return [(point[1] - origin[1]) * kmPerDegLng, (point[0] - origin[0]) * 110.574];
  }

  // Adds the distance from the start to every point of the line and every turn
  function prepareRoute(route) {
    const along = [0];
    for (let i = 1; i < route.line.length; i++) {
      along.push(along[i - 1] + distanceKm(route.line[i - 1], route.line[i]));
    }
    route.along = along;
    route.totalKm = along[along.length - 1] || route.distance / 1000;
    route.steps.forEach((step) => { step.alongKm = nearestOnRoute(route, step.at).alongKm; });
    return route;
  }

  // The closest point of the route to `point`: how far off the route it is, and how far along
  function nearestOnRoute(route, point) {
    let best = { offKm: Infinity, alongKm: 0 };
    for (let i = 1; i < route.line.length; i++) {
      const a = toKm(point, route.line[i - 1]);
      const b = toKm(point, route.line[i]);
      const dx = b[0] - a[0];
      const dy = b[1] - a[1];
      const lengthSq = dx * dx + dy * dy;
      const share = lengthSq ? Math.max(0, Math.min(1, -(a[0] * dx + a[1] * dy) / lengthSq)) : 0; // of the segment
      const off = Math.hypot(a[0] + share * dx, a[1] + share * dy);
      if (off < best.offKm) {
        best = { offKm: off, alongKm: route.along[i - 1] + share * (route.along[i] - route.along[i - 1]) };
      }
    }
    return best;
  }

  // Where the traveller is on the route: distance left, the next turn, and whether they've strayed
  function progress(route, point) {
    const here = nearestOnRoute(route, point);
    const leftKm = Math.max(0, route.totalKm - here.alongKm);
    const next = route.steps.find((step) => step.type !== "depart" && step.alongKm > here.alongKm + 0.005) || null;
    return {
      offRouteKm: here.offKm,
      leftKm,
      leftSeconds: route.totalKm ? route.duration * (leftKm / route.totalKm) : 0,
      next,
      nextKm: next ? Math.max(0, next.alongKm - here.alongKm) : 0
    };
  }

  // 13 min, 1 h 5 min, in the units' local names
  function formatDuration(seconds) {
    const minutes = Math.max(1, Math.round(seconds / 60));
    if (minutes < 60) return AfriI18n.formatUnit(minutes, "minute");
    return `${AfriI18n.formatUnit(Math.floor(minutes / 60), "hour")} ${AfriI18n.formatUnit(minutes % 60, "minute")}`;
  }

  // The credit the routing service asks for beside a route, with its "fix the map" link
  // (where anyone can report a missing or wrong road). Hidden when no route is shown.
  function showRouteCredit(element, route) {
    if (!element) return;
    element.hidden = !route;
    element.textContent = route ? `${t(route.credit)} · ` : "";
    if (!route) return;
    const link = document.createElement("a");
    link.href = "https://www.openstreetmap.org/fixthemap";
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = t("Fix the map");
    element.appendChild(link);
  }

  return {
    create, pin, show, fit, distanceKm, formatDistance, formatDuration, timeAgo, directionsUrl,
    locate, locationErrorMessage, fetchRoute, progress, showRouteCredit
  };
})();
