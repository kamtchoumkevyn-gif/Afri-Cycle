// Admin dashboard: counts, weekly activity, and account review

AfriI18n.whenReady(function () {
  const user = requireAuth(["admin"]);
  if (!user) return;

  const pageMsg = document.getElementById("pageMsg");
  const usersBody = document.getElementById("usersBody");
  const flaggedOnly = document.getElementById("flaggedOnly");
  let users = [];

  // Role and approval names as saved, in the reader's language
  const ROLE_NAMES = { seller: t("seller"), buyer: t("buyer"), both: t("buyer and seller"),
    admin: t("admin"), guardian: t("parent or guardian") };
  const APPROVAL_NAMES = { pending: t("pending"), approved: t("approved"), declined: t("declined") };

  function serverError() {
    showMessage(pageMsg, t("Can't reach the server. Check your connection, then try again."), "error");
  }

  async function loadStats() {
    try {
      const response = await authFetch("/admin/stats");
      const data = await readJson(response);
      if (!response.ok) {
        showMessage(pageMsg, data.message || t("Stats could not be loaded."), "error");
        return;
      }
      document.getElementById("statTotal").textContent = AfriI18n.formatNumber(data.totalUsers);
      document.getElementById("statSellers").textContent = AfriI18n.formatNumber(data.sellerCount);
      document.getElementById("statBuyers").textContent = AfriI18n.formatNumber(data.buyerCount);
      document.getElementById("statToday").textContent = AfriI18n.formatNumber(data.transactionsToday);
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
      // "Label: number" reads right in every language, whatever the number
      document.getElementById("activitySummary").textContent = t(
        "Purchases recorded: {purchases}. Deliveries started: {started}. Deliveries completed (all time): {completed}.",
        { purchases: AfriI18n.formatNumber(data.transactionsLast7Days), started: AfriI18n.formatNumber(data.notificationsLast7Days),
          completed: AfriI18n.formatNumber(completed) });

      const top = data.topMaterials || [];
      document.getElementById("topMaterialsBody").innerHTML = top.length
        ? top.map((m) => `
            <tr>
              <td data-label="${t("Material")}">${escapeHtml(m.materialName ? materialName(m.materialName) : t("Unknown"))}</td>
              <td data-label="${t("Purchases")}">${AfriI18n.formatNumber(m.count)}</td>
            </tr>`).join("")
        : `<tr><td colspan="2" class="empty-row">${t("No purchases recorded yet.")}</td></tr>`;
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
      usersBody.innerHTML = `<tr><td colspan="5" class="empty-row">${t("Accounts could not be loaded.")}</td></tr>`;
    }
  }

  function renderUsers() {
    const list = flaggedOnly.checked ? users.filter((u) => u.isFlagged) : users;
    if (list.length === 0) {
      usersBody.innerHTML = `<tr><td colspan="5" class="empty-row">${flaggedOnly.checked ? t("No flagged accounts.") : t("No accounts yet.")}</td></tr>`;
      return;
    }
    usersBody.innerHTML = list.map((u) => {
      const isSelf = u.userId === user.userId;
      const status = u.isFlagged
        ? `<span class="status status-flagged" title="${escapeHtml(u.flagReason || "")}">${t("Flagged")}</span>`
        : `<span class="status status-completed">${t("Active")}</span>`;
      let action = "";
      if (!isSelf && u.role !== "admin") {
        action = u.isFlagged
          ? `<button class="btn btn-quiet" type="button" data-unflag="${u.userId}">${t("Remove flag")}</button>`
          : `<button class="btn btn-danger" type="button" data-flag="${u.userId}">${t("Flag")}</button>`;
      }
      return `
        <tr>
          <td data-label="${t("Name")}"><bdi>${escapeHtml(u.name)}</bdi>${u.isFlagged && u.flagReason ? `<br><small dir="auto">${escapeHtml(u.flagReason)}</small>` : ""}</td>
          <td data-label="${t("Phone")}"><bdi>${escapeHtml(AfriPhone.format(u.phoneNumber))}</bdi></td>
          <td data-label="${t("Role")}">${escapeHtml(ROLE_NAMES[u.role] || u.role)}${u.isMinor
            ? ` <span class="badge" title="${t("Guardian approval")}">${t("Under 18")} &middot; ${escapeHtml(APPROVAL_NAMES[u.guardianStatus || "pending"] || u.guardianStatus)}</span>`
            : ""}</td>
          <td data-label="${t("Status")}">${status}</td>
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
      const reason = window.prompt(t("Why are you flagging this account?"));
      if (reason === null) return; // cancelled
      path = `/admin/flag-account/${flagBtn.dataset.flag}`;
      body = { reason: reason.trim() || t("Flagged by admin") };
    } else {
      path = `/admin/unflag-account/${unflagBtn.dataset.unflag}`;
    }

    try {
      const response = await authFetch(path, { method: "POST", body: JSON.stringify(body) });
      const data = await readJson(response);
      showMessage(pageMsg, data.message || t("Done."), response.ok ? "success" : "error");
      loadUsers();
    } catch (err) {
      serverError();
    }
  });

  loadStats();
  loadActivity();
  loadUsers();
});
