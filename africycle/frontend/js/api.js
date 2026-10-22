// Shared network helpers. Load this FIRST on every page (after probe.js and compat.js).

// When Flask serves the pages, the API is on the same address (empty base).
// When a page is opened straight from the file system, fall back to the local server.
const API_BASE_URL = window.location.protocol === "file:" ? "http://localhost:5000" : "";

// On a weak connection, just after mobile data comes on, or while the free server wakes up
// after sleeping (about a minute), requests fail or are slow. Say so after a few seconds.
// Requests that only read (GET) are sent again by themselves until the server answers,
// for up to RETRY_FOR_MS, waiting first for the phone to be back online. Other requests
// are sent again only when the hosting service answered instead of Africycle (its "waking
// up" page), so nothing is ever saved twice. One try gives up after GIVE_UP_AFTER_MS, so a
// stalled request ends with a "check your connection" message instead of a frozen button.
const SLOW_AFTER_MS = 6000;
const GIVE_UP_AFTER_MS = 70000;
const RETRY_FOR_MS = 150000;
const PING_TIMEOUT_MS = 15000;

// Whether the page is shown by the Android app (africycle/android). Its built-in screen
// adds "AfricycleApp/<version>" to the user agent; Chrome opens the app's first page with
// document.referrer "android-app://cm.africycle.app/", which is remembered for the visit.
// Used to word help for the app (its own settings) and not to offer the app download.
const ANDROID_APP_KEY = "africycle_android_app";

function inAndroidApp() {
  if (/\bAfricycleApp\//.test(navigator.userAgent)) return true;
  try {
    if (document.referrer.indexOf("android-app://cm.africycle.app") === 0) {
      sessionStorage.setItem(ANDROID_APP_KEY, "1");
    }
    return sessionStorage.getItem(ANDROID_APP_KEY) === "1";
  } catch (err) {
    return false; // storage blocked
  }
}

inAndroidApp(); // on the app's first page, before it moves on to the dashboard

let pendingRequests = 0;
let slowTimer = null;
let slowNotice = null;

function isOffline() {
  return navigator.onLine === false;
}

function reloadButton(className) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.textContent = t("Try again");
  button.addEventListener("click", () => window.location.reload());
  return button;
}

// The bar at the bottom while requests wait: offline (with Try again), or still working
function showSlowNotice(show) {
  if (show && document.body) {
    if (!slowNotice) {
      slowNotice = document.createElement("div");
      slowNotice.className = "notice-bar";
      slowNotice.setAttribute("role", "status");
      slowNotice.appendChild(document.createElement("span"));
      document.body.appendChild(slowNotice);
    }
    slowNotice.firstChild.textContent = isOffline()
      ? t("You are offline. Africycle needs the internet. Check your mobile data or Wi-Fi, then touch Try again.")
      : t("Still working... The connection is slow, or the server is waking up. This can take up to a minute.");
    const retry = slowNotice.querySelector("button");
    if (isOffline() && !retry) {
      slowNotice.appendChild(reloadButton("btn"));
    } else if (!isOffline() && retry) {
      retry.parentNode.removeChild(retry);
    }
  } else if (!show && slowNotice) {
    slowNotice.parentNode.removeChild(slowNotice);
    slowNotice = null;
  }
}

function contentType(response) {
  return (response.headers && response.headers.get("Content-Type")) || "";
}

// An answer from the hosting service instead of Africycle: Render's page while the free
// server starts, or its gateway errors. Africycle's own answers are never an HTML page
// with status 200 (its pages aren't fetched from here) nor a 502 or 504.
function fromHostingService(response) {
  const html = contentType(response).indexOf("text/html") !== -1;
  return (response.status === 200 && html) || response.status === 502 || response.status === 504 ||
    (response.status === 503 && html);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, Math.max(0, ms)));
}

function untilOnline() {
  return new Promise((resolve) => {
    if (!isOffline()) {
      resolve();
      return;
    }
    const back = () => {
      window.removeEventListener("online", back);
      resolve();
    };
    window.addEventListener("online", back);
  });
}

// Whether Africycle itself answers (GET /ping doesn't touch the database)
function ping() {
  const controller = typeof AbortController === "function" ? new AbortController() : null;
  const timer = controller ? setTimeout(() => controller.abort(), PING_TIMEOUT_MS) : null;
  const settings = controller ? { cache: "no-store", signal: controller.signal } : { cache: "no-store" };
  return fetch(`${API_BASE_URL}/ping`, settings).then(
    (response) => {
      clearTimeout(timer);
      return response.ok && contentType(response).indexOf("application/json") !== -1;
    },
    () => {
      clearTimeout(timer);
      return false;
    }
  );
}

// While the server can't be reached, one shared check asks /ping (every 1, 2, 4, then 8
// seconds, and only while the phone is online) until Africycle answers, and every waiting
// request is then sent again. The check stops when nothing waits any more.
let reachable = null;
let waiting = 0;

async function checkUntilReachable() {
  let pause = 1000;
  try {
    while (waiting > 0) {
      await untilOnline();
      if (await ping()) return;
      await sleep(pause);
      pause = Math.min(pause * 2, 8000);
    }
  } finally {
    reachable = null;
  }
}

// true once the server answers again, false at the deadline
async function whenReachable(deadline) {
  waiting += 1;
  if (!reachable) reachable = checkUntilReachable();
  const answered = await Promise.race([reachable.then(() => true), sleep(deadline - Date.now()).then(() => false)]);
  waiting -= 1;
  return answered;
}

function oneTry(url, options) {
  const controller = typeof AbortController === "function" ? new AbortController() : null;
  const giveUp = controller ? setTimeout(() => controller.abort(), GIVE_UP_AFTER_MS) : null;
  const settings = controller ? Object.assign({}, options, { signal: controller.signal }) : options;
  return fetch(url, settings).then(
    (response) => { clearTimeout(giveUp); return response; },
    (error) => { clearTimeout(giveUp); throw error; }
  );
}

function trackedFetch(url, options) {
  const method = String((options && options.method) || "GET").toUpperCase();
  const readOnly = method === "GET" || method === "HEAD";
  const deadline = Date.now() + RETRY_FOR_MS;
  pendingRequests += 1;
  if (!slowTimer) slowTimer = setTimeout(() => showSlowNotice(true), SLOW_AFTER_MS);

  function finish() {
    pendingRequests -= 1;
    if (pendingRequests === 0) {
      clearTimeout(slowTimer);
      slowTimer = null;
      showSlowNotice(false);
    }
  }

  async function send() {
    for (;;) {
      if (readOnly && isOffline()) await whenReachable(deadline);
      let response;
      try {
        response = await oneTry(url, options);
      } catch (error) {
        // No answer at all: offline, the network changed, or the try timed out
        if (readOnly && Date.now() < deadline && await whenReachable(deadline)) continue;
        throw error;
      }
      if (fromHostingService(response) && (readOnly || contentType(response).indexOf("text/html") !== -1) &&
          Date.now() < deadline && await whenReachable(deadline)) {
        continue;
      }
      serverAnswered();
      return response;
    }
  }

  return send().then(
    (response) => { finish(); return response; },
    (error) => { finish(); throw error; }
  );
}

// A page that couldn't load at all ("Can't reach the server" before the server ever
// answered) loads again by itself once the server answers or the phone is back online,
// unless the person is typing something. It also offers a Try again button.
let answeredOnce = false;
let reloadWhenBack = false;
let reloading = false;

function typingSomething() {
  const field = document.activeElement;
  return Boolean(field && /^(INPUT|TEXTAREA|SELECT)$/.test(field.tagName) && field.value);
}

// At most once every 2 minutes, so a page the server can't serve doesn't reload in a loop
const AUTO_RELOAD_KEY = "africycle_auto_reload";
const AUTO_RELOAD_GAP_MS = 120000;

function reloadIfStuck() {
  if (!reloadWhenBack || reloading || typingSomething()) return;
  try {
    const last = Number(sessionStorage.getItem(AUTO_RELOAD_KEY)) || 0;
    if (Date.now() - last < AUTO_RELOAD_GAP_MS) return;
    sessionStorage.setItem(AUTO_RELOAD_KEY, String(Date.now()));
  } catch (err) {
    return; // storage blocked: the Try again button still works
  }
  reloading = true;
  window.location.reload();
}

function serverAnswered() {
  reloadIfStuck();
  answeredOnce = true;
}

window.addEventListener("online", () => {
  if (slowNotice) showSlowNotice(true);
  reloadIfStuck();
});
window.addEventListener("offline", () => {
  if (slowNotice) showSlowNotice(true);
});

const UNREACHABLE = [
  "Can't reach the server. Check your connection, then try again.",
  "Can't reach the server. Check your connection, then reload the page."
];

async function readJson(response) {
  try {
    return await response.json();
  } catch (err) {
    return {};
  }
}

// The server answers in the language chosen on this phone (see i18n.js)
async function apiFetch(path, options = {}) {
  const headers = Object.assign({
    "Content-Type": "application/json",
    "Accept-Language": AfriI18n.language
  }, options.headers);
  return trackedFetch(`${API_BASE_URL}${path}`, Object.assign({}, options, { headers }));
}

async function authFetch(path, options = {}) {
  const headers = Object.assign({
    "Content-Type": "application/json",
    "Accept-Language": AfriI18n.language,
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
  // The page couldn't load (or its message says to reload it): a Try again button, and
  // it loads again by itself once the server answers (see reloadIfStuck)
  const unreachable = type === "error" && element.id === "pageMsg" &&
    UNREACHABLE.some((english) => t(english) === text);
  if (unreachable && (!answeredOnce || text === t(UNREACHABLE[1]))) {
    element.appendChild(reloadButton("btn btn-quiet msg-retry"));
    reloadWhenBack = true;
  }
}

function formatMoney(amount) {
  return `${AfriI18n.formatNumber(amount)} FCFA`;
}

function formatDate(isoString) {
  if (!isoString) return "";
  // Stored as UTC without a zone marker, so add one before parsing
  const value = isoString.endsWith("Z") ? isoString : `${isoString}Z`;
  return AfriI18n.formatDateTime(new Date(value));
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

// A delivery's status, in the reader's language
function statusName(status) {
  const names = {
    "pending": t("pending"),
    "in transit": t("in transit"),
    "arrived": t("arrived"),
    "completed": t("completed")
  };
  return names[status] || status;
}

function statusPill(status) {
  const cssClass = `status-${String(status).replace(/\s+/g, "-")}`;
  return `<span class="status ${cssClass}">${escapeHtml(statusName(status))}</span>`;
}

// A material's name (saved in English, like "Scrap Iron") in the reader's language
function materialName(name) {
  return name ? t(name) : t("Material");
}
