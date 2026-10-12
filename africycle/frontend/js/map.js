// Shared map and location helpers: Leaflet (served from vendor/leaflet) with OpenStreetMap
// tiles. Load after vendor/leaflet/leaflet.js and api.js. If Leaflet didn't load,
// AfriMap.create returns null and the page keeps working without a map.

const AfriMap = (function () {
  const TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
  const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
  const CAMEROON = [5.7, 12.4];

  function create(element) {
    if (typeof window.L === "undefined" || !element) return null;
    const map = L.map(element, { scrollWheelZoom: false }).setView(CAMEROON, 6);
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

  // Extra room on the right, where the labels sit beside each dot
  function fit(map, points) {
    const valid = points.filter(Boolean);
    if (valid.length === 1) map.setView(valid[0], 15);
    if (valid.length > 1) {
      map.fitBounds(L.latLngBounds(valid), {
        paddingTopLeft: [30, 30], paddingBottomRight: [120, 30], maxZoom: 16
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

  function formatDistance(km) {
    return km < 1 ? `${Math.round(km * 1000)} m` : `${km.toFixed(1)} km`;
  }

  function timeAgo(isoString) {
    if (!isoString) return "";
    const value = isoString.endsWith("Z") ? isoString : `${isoString}Z`;
    const seconds = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 1000));
    if (seconds < 60) return `${seconds} s ago`;
    if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
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
      return "Location only works on a secure address. Open Africycle with https:// at the start.";
    }
    if (!error || !error.code) {
      return "This browser can't share your location. Try Chrome, Firefox, Safari or Samsung Internet.";
    }
    if (error.code === 1) {
      return "Location is blocked for Africycle. Allow it in your browser's settings for this site (the icon beside the address), then try again.";
    }
    if (error.code === 2) {
      return "Your position isn't available. Turn on location (GPS) in your phone's settings, then try again.";
    }
    return "Finding your position took too long. Move near a window or outside, then try again.";
  }

  return { create, pin, show, fit, distanceKm, formatDistance, timeAgo, directionsUrl, locate, locationErrorMessage };
})();
