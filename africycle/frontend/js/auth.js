// Token storage, page protection, and role routing. Load after api.js.

const TOKEN_KEY = "africycle_token";

// localStorage can be missing or blocked: private browsing on older iPhones, the built-in
// browsers of some apps, or storage turned off. Then the token lives in a cookie instead,
// so logging in still works. (The server never reads this cookie; requests send the token
// in the Authorization header as usual.)
function usableStorage(kind) {
  try {
    const store = window[kind];
    store.setItem("africycle_probe", "1");
    store.removeItem("africycle_probe");
    return store;
  } catch (err) {
    return null;
  }
}

function cookieStorage(keepForSeconds) {
  return {
    getItem(key) {
      const match = document.cookie.match(new RegExp(`(?:^|; )${key}=([^;]*)`));
      return match ? decodeURIComponent(match[1]) : null;
    },
    setItem(key, value) {
      const lifetime = keepForSeconds ? `; max-age=${keepForSeconds}` : "";
      const secure = window.location.protocol === "https:" ? "; secure" : "";
      document.cookie = `${key}=${encodeURIComponent(value)}; path=/; samesite=strict${lifetime}${secure}`;
    },
    removeItem(key) {
      document.cookie = `${key}=; path=/; max-age=0`;
    }
  };
}

const keptStore = usableStorage("localStorage") || cookieStorage(24 * 60 * 60);
const sessionStore = usableStorage("sessionStorage") || cookieStorage(0);

function getToken() {
  return keptStore.getItem(TOKEN_KEY) || sessionStore.getItem(TOKEN_KEY);
}

function saveToken(token, remember) {
  clearToken();
  (remember ? keptStore : sessionStore).setItem(TOKEN_KEY, token);
}

function clearToken() {
  keptStore.removeItem(TOKEN_KEY);
  sessionStore.removeItem(TOKEN_KEY);
}

function decodeToken(token) {
  try {
    let base64 = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    base64 += "===".slice((base64.length + 3) % 4); // some browsers need the padding back
    return JSON.parse(atob(base64));
  } catch (err) {
    return null;
  }
}

function currentUser() {
  const token = getToken();
  if (!token) return null;
  const payload = decodeToken(token);
  if (!payload) return null;
  if (payload.exp && Date.now() >= payload.exp * 1000) return null;
  return payload;
}

// Call at the top of a protected page. allowedRoles is an array, or empty for any role.
function requireAuth(allowedRoles = []) {
  const user = currentUser();
  if (!user) {
    clearToken();
    window.location.replace("login.html");
    return null;
  }
  if (allowedRoles.length && !allowedRoles.includes(user.role)) {
    window.location.replace(dashboardFor(user.role));
    return null;
  }
  return user;
}

function dashboardFor(role) {
  if (role === "admin") return "admin-dashboard.html";
  if (role === "buyer") return "buyer-dashboard.html";
  if (role === "guardian") return "guardian-dashboard.html";
  return "seller-dashboard.html"; // seller and "both"
}

// Stops this device from getting the account's phone notifications (see notify.js)
async function forgetThisDevice() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return;
  const registration = await navigator.serviceWorker.getRegistration();
  const subscription = registration && await registration.pushManager.getSubscription();
  if (!subscription) return;
  try {
    await authFetch("/push/subscribe", { method: "DELETE", body: JSON.stringify({ endpoint: subscription.endpoint }) });
  } finally {
    await subscription.unsubscribe();
  }
}

async function logout() {
  window.africycleLoggingOut = true; // notify.js won't sign this device up again from here on
  try {
    // At most 3 seconds: logging out matters more than tidying up
    await Promise.race([forgetThisDevice(), new Promise((resolve) => setTimeout(resolve, 3000))]);
  } catch (err) {
    // Couldn't reach the server; the device is unsubscribed next time it's used
  }
  clearToken();
  window.location.replace("login.html");
}

// Wires the shared Log out button if the page has one
document.addEventListener("DOMContentLoaded", () => {
  const button = document.getElementById("logoutBtn");
  if (button) button.addEventListener("click", logout);
});
