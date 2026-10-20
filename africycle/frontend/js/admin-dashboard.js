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

  // ---- Two-step login: admins turn it on before the admin tools open ----

  const twoStepPanel = document.getElementById("twoStepPanel");
  const twoStepMsg = document.getElementById("twoStepMsg");

  async function showTwoStepSetup() {
    // Only the setup panel shows until two-step login is on
    document.querySelectorAll("main > section").forEach((section) => {
      section.hidden = section !== twoStepPanel;
    });
    twoStepPanel.hidden = false;
    try {
      const response = await authFetch("/admin/two-step/setup", { method: "POST" });
      const data = await readJson(response);
      if (!response.ok) {
        showMessage(twoStepMsg, data.message || t("Can't reach the server. Check your connection, then try again."), "error");
        return;
      }
      // Groups of 4 letters are easier to copy into the app
      document.getElementById("twoStepKey").textContent = data.secret.replace(/(.{4})/g, "$1 ").trim();
      document.getElementById("twoStepLink").href = data.link;
    } catch (err) {
      showMessage(twoStepMsg, t("Can't reach the server. Check your connection, then try again."), "error");
    }
  }

  document.getElementById("twoStepBtn").addEventListener("click", async () => {
    const code = document.getElementById("twoStepCode").value.trim();
    try {
      const response = await authFetch("/admin/two-step/enable", { method: "POST", body: JSON.stringify({ code }) });
      const data = await readJson(response);
      if (!response.ok) {
        showMessage(twoStepMsg, data.message || t("Done."), "error");
        return;
      }
      // The new login counts the code; keep it where the old one was kept
      saveToken(data.token, Boolean(keptStore.getItem(TOKEN_KEY)));
      window.location.reload();
    } catch (err) {
      showMessage(twoStepMsg, t("Can't reach the server. Check your connection, then try again."), "error");
    }
  });

  // A new admin account waits for another admin's approval: only that notice shows
  function showApprovalWait() {
    const approvalPanel = document.getElementById("approvalPanel");
    document.querySelectorAll("main > section").forEach((section) => {
      section.hidden = section !== approvalPanel;
    });
  }

  // What each logged action is called on the page
  const ACTION_NAMES = {
    login: t("Logged in"), wrong_code: t("Wrong two-step code"), flag: t("Flagged an account"),
    unflag: t("Removed a flag"), admin_approved: t("Approved an admin"), two_step_on: t("Turned on two-step login"),
    two_step_reset: t("Reset two-step login"), recording_saved: t("Saved a voice recording"),
    recording_deleted: t("Deleted a voice recording")
  };
  const actionsBody = document.getElementById("actionsBody");

  async function loadActions() {
    try {
      const response = await authFetch("/admin/actions");
      const data = await readJson(response);
      if (!response.ok) throw new Error(data.message);
      const actions = data.actions || [];
      actionsBody.innerHTML = actions.length
        ? actions.map((a) => `
            <tr>
              <td data-label="${t("When")}">${formatDate(a.createdAt)}</td>
              <td data-label="${t("Admin")}"><bdi>${escapeHtml(a.adminName || "")}</bdi></td>
              <td data-label="${t("Action")}">${escapeHtml(ACTION_NAMES[a.action] || a.action)}</td>
              <td data-label="${t("Account")}"><bdi>${escapeHtml(a.targetName || "")}</bdi></td>
              <td data-label="${t("Details")}"><small dir="auto">${escapeHtml(a.details || "")}</small>${a.ipAddress
                ? ` <small translate="no">${escapeHtml(a.ipAddress)}</small>` : ""}</td>
            </tr>`).join("")
        : `<tr><td colspan="5" class="empty-row">${t("No admin activity yet.")}</td></tr>`;
    } catch (err) {
      actionsBody.innerHTML = `<tr><td colspan="5" class="empty-row">${t("Admin activity could not be loaded.")}</td></tr>`;
    }
  }

  async function loadStats() {
    try {
      const response = await authFetch("/admin/stats");
      const data = await readJson(response);
      if (response.status === 403 && data.code === "admin_approval") {
        showApprovalWait();
        return false;
      }
      if (response.status === 403 && data.code === "two_step_setup") {
        showTwoStepSetup();
        return false;
      }
      if (!response.ok) {
        showMessage(pageMsg, data.message || t("Stats could not be loaded."), "error");
        return;
      }
      document.getElementById("secretWarning").hidden = !data.weakSecret;
      document.getElementById("statTotal").textContent = AfriI18n.formatNumber(data.totalUsers);
      document.getElementById("statSellers").textContent = AfriI18n.formatNumber(data.sellerCount);
      document.getElementById("statBuyers").textContent = AfriI18n.formatNumber(data.buyerCount);
      document.getElementById("statToday").textContent = AfriI18n.formatNumber(data.transactionsToday);
    } catch (err) {
      serverError();
    }
    return true;
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
      // An admin account nobody approved yet may not be who it claims: approve it, or flag it
      const waiting = u.role === "admin" && !u.adminApproved;
      let status = `<span class="status status-completed">${t("Active")}</span>`;
      if (u.isFlagged) {
        status = `<span class="status status-flagged" title="${escapeHtml(u.flagReason || "")}">${t("Flagged")}</span>`;
      } else if (waiting) {
        status = `<span class="status status-pending">${t("Waiting for approval")}</span>`;
      }
      let action = "";
      if (!isSelf && waiting && !u.isFlagged) {
        action = `<button class="btn btn-primary" type="button" data-approve="${u.userId}">${t("Approve")}</button>
                  <button class="btn btn-danger" type="button" data-flag="${u.userId}">${t("Flag")}</button>`;
      } else if (!isSelf && u.role === "admin" && !waiting && u.totpEnabled) {
        action = `<button class="btn btn-quiet" type="button" data-reset="${u.userId}">${t("Reset two-step login")}</button>`;
      } else if (!isSelf && (u.role !== "admin" || waiting)) {
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
    const resetBtn = event.target.closest("button[data-reset]");
    const approveBtn = event.target.closest("button[data-approve]");
    if (!flagBtn && !unflagBtn && !resetBtn && !approveBtn) return;

    let path;
    let body = {};
    if (approveBtn) {
      if (!window.confirm(t("Approve this admin account? It will be able to see every account and flag them."))) return;
      path = `/admin/approve-admin/${approveBtn.dataset.approve}`;
    } else if (resetBtn) {
      if (!window.confirm(t("Reset two-step login for this admin? They will set it up again at their next login."))) return;
      path = `/admin/two-step/reset/${resetBtn.dataset.reset}`;
    } else if (flagBtn) {
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
      loadActions();
    } catch (err) {
      serverError();
    }
  });

  loadStats().then((ready) => {
    if (!ready) return; // two-step login isn't on yet: only its setup shows
    loadActivity();
    loadUsers();
    loadActions();
  });
});
