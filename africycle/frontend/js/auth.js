// Token storage, page protection, and role routing. Load after api.js.

const TOKEN_KEY = "africycle_token";

function getToken() {
  return localStorage.getItem(TOKEN_KEY) || sessionStorage.getItem(TOKEN_KEY);
}

function saveToken(token, remember) {
  clearToken();
  (remember ? localStorage : sessionStorage).setItem(TOKEN_KEY, token);
}

function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(TOKEN_KEY);
}

function decodeToken(token) {
  try {
    const base64 = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
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
  return "seller-dashboard.html"; // seller and "both"
}

function logout() {
  clearToken();
  window.location.replace("login.html");
}

// Wires the shared Log out button if the page has one
document.addEventListener("DOMContentLoaded", () => {
  const button = document.getElementById("logoutBtn");
  if (button) button.addEventListener("click", logout);
});
