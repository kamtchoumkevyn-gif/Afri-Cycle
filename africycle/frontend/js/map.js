// Shared map helpers: Leaflet (served from vendor/leaflet) with OpenStreetMap tiles.
// Load after vendor/leaflet/leaflet.js and api.js. If Leaflet didn't load,
// AfriMap.create returns null and the page keeps working without a map.

const AfriMap = (function () {
  const TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
  const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
  const CAMEROON = [5.7, 12.4];

  function create(element) {
    if (typeof window.L === "undefined" || !element) return null;
    const map = L.map(element, { scrollWheelZoom: false }).setView(CAMEROON, 6);
    L.tileLayer(TILES, { maxZoom: 19, attribution: ATTRIBUTION }).addTo(map);
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

  return { create, pin, show, fit, distanceKm, formatDistance, timeAgo, directionsUrl };
})();
