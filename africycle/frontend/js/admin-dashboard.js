// Admin dashboard: counts, weekly activity, and account review

(function () {
  const user = requireAuth(["admin"]);
  if (!user) return;

  const pageMsg = document.getElementById("pageMsg");
  const usersBody = document.getElementById("usersBody");
  const flaggedOnly = document.getElementById("flaggedOnly");
  let users = [];

  function serverError() {
    showMessage(pageMsg, "Can't reach the server. Check your connection and try again.", "error");
  }

  async function loadStats() {
    try {
      const response = await authFetch("/admin/stats");
      const data = await readJson(response);
      if (!response.ok) {
        showMessage(pageMsg, data.message || "Stats could not be loaded.", "error");
        return;
      }
      document.getElementById("statTotal").textContent = data.totalUsers;
      document.getElementById("statSellers").textContent = data.sellerCount;
      document.getElementById("statBuyers").textContent = data.buyerCount;
      document.getElementById("statToday").textContent = data.transactionsToday;
    } catch (err) {
      serverError();
    }
  }

  async function loadActivity() {
    try {
      const response = await authFetch("/admin/activity-stats");
      const data = await readJson(response);
      if (!response.ok) return;

      const completed = (data.notificationsByStatus || {}).completed || 0;
      document.getElementById("activitySummary").textContent =
        `${data.transactionsLast7Days} purchases recorded and ${data.notificationsLast7Days} deliveries started. ` +
        `${completed} deliveries completed in total.`;

      const top = data.topMaterials || [];
      document.getElementById("topMaterialsBody").innerHTML = top.length
        ? top.map((m) => `
            <tr>
              <td data-label="Material">${escapeHtml(m.materialName || "Unknown")}</td>
              <td data-label="Purchases">${m.count}</td>
            </tr>`).join("")
        : `<tr><td colspan="2" class="empty-row">No purchases recorded yet.</td></tr>`;
    } catch (err) {
      serverError();
    }
  }

  async function loadUsers() {
    try {
      const response = await authFetch("/admin/users");
      const data = await readJson(response);
      if (!response.ok) return;
      users = data.users || [];
      renderUsers();
    } catch (err) {
      usersBody.innerHTML = `<tr><td colspan="5" class="empty-row">Accounts could not be loaded.</td></tr>`;
    }
  }

  function renderUsers() {
    const list = flaggedOnly.checked ? users.filter((u) => u.isFlagged) : users;
    if (list.length === 0) {
      usersBody.innerHTML = `<tr><td colspan="5" class="empty-row">${flaggedOnly.checked ? "No flagged accounts." : "No accounts yet."}</td></tr>`;
      return;
    }
    usersBody.innerHTML = list.map((u) => {
      const isSelf = u.userId === user.userId;
      const status = u.isFlagged
        ? `<span class="status status-flagged" title="${escapeHtml(u.flagReason || "")}">Flagged</span>`
        : `<span class="status status-completed">Active</span>`;
      let action = "";
      if (!isSelf && u.role !== "admin") {
        action = u.isFlagged
          ? `<button class="btn btn-quiet" type="button" data-unflag="${u.userId}">Remove flag</button>`
          : `<button class="btn btn-danger" type="button" data-flag="${u.userId}">Flag</button>`;
      }
      return `
        <tr>
          <td data-label="Name">${escapeHtml(u.name)}${u.isFlagged && u.flagReason ? `<br><small>${escapeHtml(u.flagReason)}</small>` : ""}</td>
          <td data-label="Phone">${escapeHtml(u.phoneNumber)}</td>
          <td data-label="Role">${escapeHtml(u.role)}</td>
          <td data-label="Status">${status}</td>
          <td><div class="row-actions">${action}</div></td>
        </tr>`;
    }).join("");
  }

  flaggedOnly.addEventListener("change", renderUsers);

  usersBody.addEventListener("click", async (event) => {
    const flagBtn = event.target.closest("button[data-flag]");
    const unflagBtn = event.target.closest("button[data-unflag]");
    if (!flagBtn && !unflagBtn) return;

    let path;
    let body = {};
    if (flagBtn) {
      const reason = window.prompt("Why are you flagging this account?");
      if (reason === null) return; // cancelled
      path = `/admin/flag-account/${flagBtn.dataset.flag}`;
      body = { reason: reason.trim() || "Flagged by admin" };
    } else {
      path = `/admin/unflag-account/${unflagBtn.dataset.unflag}`;
    }

    try {
      const response = await authFetch(path, { method: "POST", body: JSON.stringify(body) });
      const data = await readJson(response);
      showMessage(pageMsg, data.message || "Done.", response.ok ? "success" : "error");
      loadUsers();
    } catch (err) {
      serverError();
    }
  });

  loadStats();
  loadActivity();
  loadUsers();
})();
