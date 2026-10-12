// Shared network helpers. Load this FIRST on every page (after probe.js and compat.js).

// When Flask serves the pages, the API is on the same address (empty base).
// When a page is opened straight from the file system, fall back to the local server.
const API_BASE_URL = window.location.protocol === "file:" ? "http://localhost:5000" : "";

// On a weak connection, or while the free server wakes up after sleeping (up to about a
// minute), requests are slow. Say so after a few seconds, and give up after 70 seconds so
// a stalled request ends with a "check your connection" message instead of a frozen button.
const SLOW_AFTER_MS = 6000;
const GIVE_UP_AFTER_MS = 70000;

let pendingRequests = 0;
let slowTimer = null;
let slowNotice = null;

function showSlowNotice(show) {
  if (show && !slowNotice && document.body) {
    slowNotice = document.createElement("div");
    slowNotice.className = "notice-bar";
    slowNotice.setAttribute("role", "status");
    slowNotice.textContent = "Still working... The connection is slow, or the server is waking up. This can take up to a minute.";
    document.body.appendChild(slowNotice);
  } else if (!show && slowNotice) {
    slowNotice.parentNode.removeChild(slowNotice);
    slowNotice = null;
  }
}

function trackedFetch(url, options) {
  pendingRequests += 1;
  if (!slowTimer) slowTimer = setTimeout(() => showSlowNotice(true), SLOW_AFTER_MS);
  const controller = typeof AbortController === "function" ? new AbortController() : null;
  const giveUp = controller ? setTimeout(() => controller.abort(), GIVE_UP_AFTER_MS) : null;

  function finish() {
    clearTimeout(giveUp);
    pendingRequests -= 1;
    if (pendingRequests === 0) {
      clearTimeout(slowTimer);
      slowTimer = null;
      showSlowNotice(false);
    }
  }

  const settings = controller ? Object.assign({}, options, { signal: controller.signal }) : options;
  return fetch(url, settings).then(
    (response) => { finish(); return response; },
    (error) => { finish(); throw error; }
  );
}

async function readJson(response) {
  try {
    return await response.json();
  } catch (err) {
    return {};
  }
}

async function apiFetch(path, options = {}) {
  const headers = Object.assign({ "Content-Type": "application/json" }, options.headers);
  return trackedFetch(`${API_BASE_URL}${path}`, Object.assign({}, options, { headers }));
}

async function authFetch(path, options = {}) {
  const headers = Object.assign({
    "Content-Type": "application/json",
    "Authorization": `Bearer ${getToken()}`
  }, options.headers);
  return trackedFetch(`${API_BASE_URL}${path}`, Object.assign({}, options, { headers }));
}

// Always escape user-provided text before putting it into innerHTML
function escapeHtml(value) {
  const div = document.createElement("div");
  div.textContent = value == null ? "" : String(value);
  return div.innerHTML;
}

function showMessage(element, text, type) {
  element.textContent = text;
  element.className = `msg msg-${type}`;
  element.hidden = false;
}

function formatMoney(amount) {
  return `${Number(amount).toLocaleString()} FCFA`;
}

function formatDate(isoString) {
  if (!isoString) return "";
  // Stored as UTC without a zone marker, so add one before parsing
  const value = isoString.endsWith("Z") ? isoString : `${isoString}Z`;
  return new Date(value).toLocaleString();
}

// Material photos need the login token, so they're fetched here and shown via blob: URLs.
// Mark images with data-photo-id, then call loadPhotos(container).
const photoCache = new Map();

function loadPhotos(container) {
  container.querySelectorAll("img[data-photo-id]").forEach((img) => {
    const id = img.dataset.photoId;
    if (!photoCache.has(id)) {
      photoCache.set(id, authFetch(`/photos/${id}`)
        .then((response) => (response.ok ? response.blob() : null))
        .then((blob) => (blob ? URL.createObjectURL(blob) : null))
        .catch(() => {
          photoCache.delete(id); // try again next time instead of remembering the failure
          return null;
        }));
    }
    photoCache.get(id).then((url) => {
      if (url) img.src = url;
    });
  });
}

// The logged-in account's details, including a child's guardian approval status
async function loadMe() {
  try {
    const response = await authFetch("/me");
    return response.ok ? await readJson(response) : null;
  } catch (err) {
    return null;
  }
}

function statusPill(status) {
  const cssClass = `status-${String(status).replace(/\s+/g, "-")}`;
  return `<span class="status ${cssClass}">${escapeHtml(status)}</span>`;
}
