// Guardian page: approve a child's account, then follow their deliveries (with a live map
// while they're on the way), sales and messages. Any adult account can be a guardian.

(function () {
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

  let children = [];
  let currentChild = null;
  let currentConversation = null;
  let lastThread = "";
  let map = null;
  let mapLayer = null;
  let shownTrips = "";

  function serverError() {
    showMessage(pageMsg, "Can't reach the server. Check your connection and try again.", "error");
  }

  function childName() {
    const child = children.find((c) => c.id === currentChild);
    return child ? child.name : "Your child";
  }

  // ---- Children waiting for approval, and children you supervise ----

  async function loadChildren() {
    try {
      const response = await authFetch("/guardian/children");
      const data = await readJson(response);
      if (!response.ok) {
        showMessage(pageMsg, data.message || "Your children could not be loaded.", "error");
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
            <td data-label="Name">${escapeHtml(c.name)}</td>
            <td data-label="Phone">${escapeHtml(AfriPhone.format(c.phoneNumber))}</td>
            <td data-label="You are their">${escapeHtml(c.guardianRelation || "")}</td>
            <td>
              <div class="row-actions">
                <button class="btn btn-primary" type="button" data-approve="${c.id}">Approve</button>
                <button class="btn btn-danger" type="button" data-decline="${c.id}">Decline</button>
              </div>
            </td>
          </tr>`).join("")
      : `<tr><td colspan="4" class="empty-row">No children are waiting for your approval.</td></tr>`;
  }

  pendingBody.addEventListener("click", async (event) => {
    const approve = event.target.closest("button[data-approve]");
    const decline = event.target.closest("button[data-decline]");
    const button = approve || decline;
    if (!button) return;
    if (decline && !window.confirm("Decline this account? The child won't be able to sell on Africycle.")) return;

    const id = approve ? approve.dataset.approve : decline.dataset.decline;
    button.disabled = true;
    try {
      const response = await authFetch(`/guardian/children/${id}/${approve ? "approve" : "decline"}`, { method: "POST" });
      const data = await readJson(response);
      showMessage(pageMsg, data.message || "That didn't work. Try again.", response.ok ? "success" : "error");
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
    thread.innerHTML = `<p class="panel-hint">Choose a conversation.</p>`;
    loadActivity();
  });

  // ---- The chosen child's activity ----

  async function loadActivity() {
    if (!currentChild) return;
    try {
      const response = await authFetch(`/guardian/children/${currentChild}/activity`);
      const data = await readJson(response);
      if (!response.ok) {
        showMessage(pageMsg, data.message || "Activity could not be loaded.", "error");
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
      tripStatus.textContent = `${name} is not on a delivery right now.`;
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
        lines.push(`${name} is on the way to ${d.buyerName}; waiting for the first location update.`);
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
        ? `${name} is ${AfriMap.formatDistance(AfriMap.distanceKm(childPoint, buyerPoint))} from ${d.buyerName} (updated ${seen}).`
        : `${name} was seen ${seen} on the way to ${d.buyerName}.`);
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
            <td data-label="Buyer">${escapeHtml(d.buyerName)}</td>
            <td data-label="Material">${escapeHtml(d.materialName || "")}</td>
            <td data-label="Status">${statusPill(d.status)}</td>
            <td data-label="Started">${formatDate(d.createdAt)}</td>
          </tr>`).join("")
      : `<tr><td colspan="4" class="empty-row">No deliveries yet.</td></tr>`;
  }

  function renderSales(sales) {
    salesBody.innerHTML = sales.length
      ? sales.map((t) => `
          <tr>
            <td data-label="Buyer">${escapeHtml(t.buyerName)}</td>
            <td data-label="Material">${escapeHtml(t.materialName || "")}</td>
            <td data-label="Weight">${t.weightKg} kg</td>
            <td data-label="Total"><strong>${formatMoney(t.totalAmount)}</strong></td>
            <td data-label="Date">${formatDate(t.createdAt)}</td>
          </tr>`).join("")
      : `<tr><td colspan="5" class="empty-row">No sales recorded yet.</td></tr>`;
  }

  // ---- Messages (read-only) ----

  function renderConversations(conversations) {
    conversationList.innerHTML = conversations.length
      ? conversations.map((c) => `
          <button type="button" class="conversation-item ${c.otherUserId === currentConversation ? "active" : ""}"
                  data-id="${c.otherUserId}">
            ${escapeHtml(c.otherUserName || "User")}
          </button>`).join("")
      : `<p class="panel-hint">No conversations yet.</p>`;
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
              <strong>${escapeHtml(m.senderId === currentChild ? name : data.otherUserName)}</strong><br>
              ${escapeHtml(m.messageText)}
              <time>${formatDate(m.createdAt)}</time>
            </div>`).join("")
        : `<p class="panel-hint">No messages yet.</p>`;
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
})();
