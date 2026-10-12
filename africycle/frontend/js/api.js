// Shared network helpers. Load this FIRST on every page.

// When Flask serves the pages, the API is on the same address (empty base).
// When a page is opened straight from the file system, fall back to the local server.
const API_BASE_URL = window.location.protocol === "file:" ? "http://localhost:5000" : "";

async function readJson(response) {
  try {
    return await response.json();
  } catch (err) {
    return {};
  }
}

async function apiFetch(path, options = {}) {
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) };
  return fetch(`${API_BASE_URL}${path}`, { ...options, headers });
}

async function authFetch(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    "Authorization": `Bearer ${getToken()}`,
    ...(options.headers || {})
  };
  return fetch(`${API_BASE_URL}${path}`, { ...options, headers });
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
        .catch(() => null));
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
