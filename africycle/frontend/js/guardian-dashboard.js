// Guardian page: approve a child's account, then follow their deliveries (with a live map
// while they're on the way), sales and messages. Any adult account can be a guardian.

AfriI18n.whenReady(function () {
  const user = requireAuth([]);
  if (!user) return;

  const pageMsg = document.getElementById("pageMsg");
  const pendingBody = document.getElementById("pendingBody");
  const noChildren = document.getElementById("noChildren");
  const childPicker = document.getElementById("childPicker");
  const childSelect = document.getElementById("childSelect");
  const childView = document.getElementById("childView");
  const tripStatus = document.getElementById("tripStatus");
  const mapEl = document.getElementById("childMap");
  const deliveriesBody = document.getElementById("deliveriesBody");
  const salesBody = document.getElementById("salesBody");
  const conversationList = document.getElementById("conversationList");
  const thread = document.getElementById("thread");

  const REFRESH_MS = 15000;
  // How the child said they're related to you (saved in English), as on the sign-up page
  const RELATIONS = { "mother": t("Mother"), "father": t("Father"), "grandparent": t("Grandparent"),
    "aunt or uncle": t("Aunt or uncle"), "older sibling": t("Older brother or sister"), "other guardian": t("Other guardian") };

  let children = [];
  let currentChild = null;
  let currentConversation = null;
  let lastThread = "";
  let map = null;
  let mapLayer = null;
  let shownTrips = "";

  function serverError() {
    showMessage(pageMsg, t("Can't reach the server. Check your connection, then try again."), "error");
  }

  function childName() {
    const child = children.find((c) => c.id === currentChild);
    return child ? child.name : t("Your child");
  }

  // ---- Children waiting for approval, and children you supervise ----

  async function loadChildren() {
    try {
      const response = await authFetch("/guardian/children");
      const data = await readJson(response);
      if (!response.ok) {
        showMessage(pageMsg, data.message || t("Your children could not be loaded."), "error");
        return;
      }
      renderPending(data.pending || []);
      children = data.children || [];
      renderChildPicker();
    } catch (err) {
      serverError();
    }
  }

  function renderPending(pending) {
    pendingBody.innerHTML = pending.length
      ? pending.map((c) => `
          <tr>
            <td data-label="${t("Name")}"><bdi>${escapeHtml(c.name)}</bdi></td>
            <td data-label="${t("Phone")}"><bdi dir="ltr">… ${escapeHtml(c.phoneEnd || "")}</bdi></td>
            <td data-label="${t("You are their")}">${escapeHtml(RELATIONS[c.guardianRelation] || c.guardianRelation || "")}</td>
            <td data-label="${t("Code")}">
              <input class="code-input" type="text" inputmode="numeric" autocomplete="off" maxlength="7"
                     data-code="${c.id}" aria-label="${t("Code from your child's phone")}" translate="no">
            </td>
            <td>
              <div class="row-actions">
                <button class="btn btn-primary" type="button" data-approve="${c.id}">${t("Approve")}</button>
                <button class="btn btn-danger" type="button" data-decline="${c.id}">${t("Decline")}</button>
              </div>
            </td>
          </tr>`).join("")
      : `<tr><td colspan="5" class="empty-row">${t("No children are waiting for your approval.")}</td></tr>`;
  }

  pendingBody.addEventListener("click", async (event) => {
    const approve = event.target.closest("button[data-approve]");
    const decline = event.target.closest("button[data-decline]");
    const button = approve || decline;
    if (!button) return;

    const id = approve ? approve.dataset.approve : decline.dataset.decline;
    // The 6 digits shown on the child's phone: they prove this is really the child's guardian
    const codeInput = pendingBody.querySelector(`input[data-code="${id}"]`);
    const code = codeInput ? codeInput.value.replace(/\D/g, "") : "";
    if (code.length !== 6) {
      showMessage(pageMsg, t("Type the 6-digit code shown on your child's phone first."), "error");
      if (codeInput) codeInput.focus();
      return;
    }
    if (decline && !window.confirm(t("Decline this account? The child won't be able to sell on Africycle."))) return;
    button.disabled = true;
    try {
      const response = await authFetch(`/guardian/children/${id}/${approve ? "approve" : "decline"}`,
        { method: "POST", body: JSON.stringify({ code }) });
      const data = await readJson(response);
      showMessage(pageMsg, data.message || t("That didn't work. Try again."), response.ok ? "success" : "error");
      await loadChildren();
    } catch (err) {
      serverError();
      button.disabled = false;
    }
  });

  function renderChildPicker() {
    noChildren.hidden = children.length > 0;
    childPicker.hidden = children.length === 0;
    if (children.length === 0) {
      childView.hidden = true;
      currentChild = null;
      return;
    }
    const keep = children.some((c) => c.id === currentChild);
    childSelect.length = 0;
    children.forEach((c) => childSelect.add(new Option(c.name, c.id)));
    currentChild = keep ? currentChild : children[0].id;
    childSelect.value = String(currentChild);
    loadActivity();
  }

  childSelect.addEventListener("change", () => {
    currentChild = Number(childSelect.value);
    currentConversation = null;
    lastThread = "";
    shownTrips = "";
    thread.innerHTML = `<p class="panel-hint">${t("Choose a conversation.")}</p>`;
    loadActivity();
  });

  // ---- The chosen child's activity ----

  async function loadActivity() {
    if (!currentChild) return;
    try {
      const response = await authFetch(`/guardian/children/${currentChild}/activity`);
      const data = await readJson(response);
      if (!response.ok) {
        showMessage(pageMsg, data.message || t("Activity could not be loaded."), "error");
        return;
      }
      childView.hidden = false;
      const deliveries = data.deliveries || [];
      renderTrip(deliveries);
      renderDeliveries(deliveries);
      renderSales(data.sales || []);
      renderConversations(data.conversations || []);
      if (currentConversation) loadThread();
    } catch (err) {
      serverError();
    }
  }

  // Where the child is during a delivery, and where they're heading
  function renderTrip(deliveries) {
    const trips = deliveries.filter((d) => d.status === "in transit");
    const name = childName();
    if (trips.length === 0) {
      tripStatus.textContent = t("{name} is not on a delivery right now.", { name });
      mapEl.hidden = true;
      return;
    }
    if (!map) {
      map = AfriMap.create(mapEl);
      if (map) mapLayer = L.layerGroup().addTo(map);
    }

    const points = [];
    const lines = [];
    if (mapLayer) mapLayer.clearLayers();
    trips.forEach((d) => {
      const buyerPoint = d.buyerLatitude != null ? [d.buyerLatitude, d.buyerLongitude] : null;
      if (buyerPoint && mapLayer) {
        L.marker(buyerPoint, { icon: AfriMap.pin("home", d.buyerName) }).addTo(mapLayer);
        points.push(buyerPoint);
      }
      if (d.sellerLatitude == null) {
        lines.push(t("{name} is on the way to {buyer}; waiting for the first location update.", { name, buyer: d.buyerName }));
        return;
      }
      const childPoint = [d.sellerLatitude, d.sellerLongitude];
      points.push(childPoint);
      const seen = AfriMap.timeAgo(d.locationUpdatedAt);
      if (mapLayer) {
        L.marker(childPoint, { icon: AfriMap.pin("seller", name), zIndexOffset: 500 }).addTo(mapLayer);
        if (buyerPoint) {
          L.polyline([childPoint, buyerPoint], { color: "#1565c0", weight: 3, dashArray: "6 8" }).addTo(mapLayer);
        }
      }
      lines.push(buyerPoint
        ? t("{name} is {distance} from {buyer} (updated {time}).",
          { name, distance: AfriMap.formatDistance(AfriMap.distanceKm(childPoint, buyerPoint)), buyer: d.buyerName, time: seen })
        : t("{name} was seen {time} on the way to {buyer}.", { name, time: seen, buyer: d.buyerName }));
    });
    tripStatus.textContent = lines.join(" ");

    if (map && points.length) {
      AfriMap.show(map, mapEl);
      const key = trips.map((d) => d.id).join(",");
      if (key !== shownTrips) {
        shownTrips = key;
        AfriMap.fit(map, points);
      }
    }
  }

  function renderDeliveries(deliveries) {
    deliveriesBody.innerHTML = deliveries.length
      ? deliveries.map((d) => `
          <tr>
            <td data-label="${t("Buyer")}"><bdi>${escapeHtml(d.buyerName)}</bdi></td>
            <td data-label="${t("Material")}">${escapeHtml(materialName(d.materialName))}</td>
            <td data-label="${t("Status")}">${statusPill(d.status)}</td>
            <td data-label="${t("Started")}">${formatDate(d.createdAt)}</td>
          </tr>`).join("")
      : `<tr><td colspan="4" class="empty-row">${t("No deliveries yet.")}</td></tr>`;
  }

  function renderSales(sales) {
    salesBody.innerHTML = sales.length
      ? sales.map((sale) => `
          <tr>
            <td data-label="${t("Buyer")}"><bdi>${escapeHtml(sale.buyerName)}</bdi></td>
            <td data-label="${t("Material")}">${escapeHtml(materialName(sale.materialName))}</td>
            <td data-label="${t("Weight")}">${AfriI18n.formatUnit(sale.weightKg, "kilogram", 2)}</td>
            <td data-label="${t("Total")}"><strong>${formatMoney(sale.totalAmount)}</strong></td>
            <td data-label="${t("Date")}">${formatDate(sale.createdAt)}</td>
            <td data-label="${t("Receipt")}">${AfriReceipt.button(sale.id, sale.photoCount)}</td>
          </tr>`).join("")
      : `<tr><td colspan="6" class="empty-row">${t("No sales recorded yet.")}</td></tr>`;
  }

  // ---- Messages (read-only) ----

  function renderConversations(conversations) {
    conversationList.innerHTML = conversations.length
      ? conversations.map((c) => `
          <button type="button" class="conversation-item ${c.otherUserId === currentConversation ? "active" : ""}"
                  data-id="${c.otherUserId}">
            <bdi>${escapeHtml(c.otherUserName || t("User"))}</bdi>
          </button>`).join("")
      : `<p class="panel-hint">${t("No conversations yet.")}</p>`;
  }

  conversationList.addEventListener("click", (event) => {
    const item = event.target.closest("button[data-id]");
    if (!item) return;
    currentConversation = Number(item.dataset.id);
    lastThread = "";
    conversationList.querySelectorAll(".conversation-item").forEach((el) => {
      el.classList.toggle("active", el === item);
    });
    loadThread();
  });

  async function loadThread() {
    try {
      const response = await authFetch(`/guardian/children/${currentChild}/messages/${currentConversation}`);
      const data = await readJson(response);
      if (!response.ok) return;
      const messages = data.messages || [];
      const key = messages.map((m) => m.id).join(",");
      if (key === lastThread) return; // unchanged: keep the reader's scroll position
      lastThread = key;
      const name = childName();
      thread.innerHTML = messages.length
        ? messages.map((m) => `
            <div class="bubble ${m.senderId === currentChild ? "sent" : "received"}">
              <strong><bdi>${escapeHtml(m.senderId === currentChild ? name : data.otherUserName)}</bdi></strong><br>
              <span dir="auto">${escapeHtml(m.messageText)}</span>
              <time>${formatDate(m.createdAt)}</time>
            </div>`).join("")
        : `<p class="panel-hint">${t("No messages yet.")}</p>`;
      thread.scrollTop = thread.scrollHeight;
    } catch (err) {
      serverError();
    }
  }

  // ---- Start ----

  async function start() {
    const me = await loadMe();
    if (me && me.isMinor) {
      window.location.replace(dashboardFor(user.role)); // children can't supervise
      return;
    }
    if (user.role !== "guardian") {
      const link = document.getElementById("ownDashboardLink");
      link.href = dashboardFor(user.role);
      link.hidden = false;
    }
    await loadChildren();
    setInterval(loadChildren, REFRESH_MS);
  }

  start();
});
