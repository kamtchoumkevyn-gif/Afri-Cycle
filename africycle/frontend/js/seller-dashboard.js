// Seller dashboard: find buyers, notify one, share location during the delivery

(function () {
  const user = requireAuth(["seller", "both"]);
  if (!user) return;

  const pageMsg = document.getElementById("pageMsg");
  const materialSelect = document.getElementById("materialSelect");
  const radiusSelect = document.getElementById("radiusSelect");
  const findBtn = document.getElementById("findBuyersBtn");
  const buyersBody = document.getElementById("buyersBody");
  const deliveriesBody = document.getElementById("deliveriesBody");
  const sharingHint = document.getElementById("sharingHint");
  const modal = document.getElementById("buyerModal");

  const NEXT_STATUS = { "pending": "in transit", "in transit": "arrived" };
  const LOCATION_PING_MS = 15000;

  let activeDeliveryIds = [];
  let watchId = null;
  let lastPingAt = 0;
  let modalBuyerId = null;

  if (user.role === "both") {
    document.getElementById("switchLink").hidden = false;
  }

  // ---- Materials ----

  async function loadMaterials() {
    const response = await authFetch("/material-categories");
    const data = await readJson(response);
    (data.categories || []).forEach((category) => {
      materialSelect.add(new Option(category.name, category.id));
    });
  }

  // ---- Find buyers ----

  function getPosition() {
    return new Promise((resolve, reject) => {
      if (!navigator.geolocation) {
        reject(new Error("unsupported"));
        return;
      }
      navigator.geolocation.getCurrentPosition(resolve, reject, {
        enableHighAccuracy: true,
        timeout: 15000
      });
    });
  }

  findBtn.addEventListener("click", async () => {
    pageMsg.hidden = true;
    const materialId = materialSelect.value;
    if (!materialId) {
      showMessage(pageMsg, "Choose a material first.", "error");
      return;
    }

    findBtn.disabled = true;
    buyersBody.innerHTML = `<tr><td colspan="5" class="empty-row">Finding your location...</td></tr>`;

    let position;
    try {
      position = await getPosition();
    } catch (err) {
      buyersBody.innerHTML = `<tr><td colspan="5" class="empty-row">Location is off.</td></tr>`;
      showMessage(pageMsg, "Allow location access in your browser so we can measure distances to buyers.", "error");
      findBtn.disabled = false;
      return;
    }

    buyersBody.innerHTML = `<tr><td colspan="5" class="empty-row">Searching...</td></tr>`;
    const { latitude, longitude } = position.coords;
    const query = `lat=${latitude}&lng=${longitude}&materialCategoryId=${materialId}&radiusKm=${radiusSelect.value}`;

    try {
      const response = await authFetch(`/seller/nearby-buyers?${query}`);
      const data = await readJson(response);
      if (!response.ok) {
        showMessage(pageMsg, data.message || "Buyers could not be loaded.", "error");
        return;
      }
      renderBuyers(data.buyers || []);
    } catch (err) {
      showMessage(pageMsg, "Can't reach the server. Check your connection and try again.", "error");
    } finally {
      findBtn.disabled = false;
    }
  });

  function renderBuyers(buyers) {
    if (buyers.length === 0) {
      buyersBody.innerHTML = `<tr><td colspan="5" class="empty-row">No buyers for this material in that distance. Try a wider search.</td></tr>`;
      return;
    }
    buyersBody.innerHTML = buyers.map((b) => `
      <tr>
        <td data-label="Buyer">${escapeHtml(b.buyerName)}</td>
        <td data-label="Price per kg"><strong>${formatMoney(b.pricePerKg)}</strong></td>
        <td data-label="Distance">${b.distanceKm} km</td>
        <td data-label="Hours">${escapeHtml(b.workingHours || "Not set")}</td>
        <td>
          <div class="row-actions">
            <button class="btn btn-quiet" data-action="view" data-id="${b.buyerId}" type="button">Details</button>
            <button class="btn btn-primary" data-action="notify" data-id="${b.buyerId}" type="button">I'm coming</button>
          </div>
        </td>
      </tr>
    `).join("");
  }

  buyersBody.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const buyerId = Number(button.dataset.id);
    if (button.dataset.action === "view") openBuyer(buyerId);
    if (button.dataset.action === "notify") notifyBuyer(buyerId);
  });

  // ---- Buyer details modal ----

  async function openBuyer(buyerId) {
    try {
      const [profileRes, contactRes] = await Promise.all([
        authFetch(`/seller/buyer-profile/${buyerId}`),
        authFetch(`/seller/contact-buyer/${buyerId}`)
      ]);
      const profile = await readJson(profileRes);
      const contact = await readJson(contactRes);

      if (!profileRes.ok) {
        showMessage(pageMsg, profile.message || "Buyer details could not be loaded.", "error");
        return;
      }

      modalBuyerId = buyerId;
      document.getElementById("modalName").textContent = profile.name;
      document.getElementById("modalMeta").textContent = `Open: ${profile.workingHours || "hours not set"}`;
      document.getElementById("modalPrices").innerHTML = (profile.prices || []).map((p) => `
        <li><span>${escapeHtml(p.materialName || "Material")}</span><strong>${formatMoney(p.pricePerKg)}/kg</strong></li>
      `).join("");

      const callLink = document.getElementById("modalCallLink");
      callLink.href = contact.phoneNumber ? `tel:${contact.phoneNumber}` : "#";
      callLink.textContent = contact.phoneNumber ? `Call ${contact.phoneNumber}` : "Phone not available";
      document.getElementById("modalChatLink").href = `chat.html?with=${buyerId}`;

      modal.hidden = false;
      document.getElementById("closeModalBtn").focus();
    } catch (err) {
      showMessage(pageMsg, "Can't reach the server. Check your connection and try again.", "error");
    }
  }

  function closeModal() {
    modal.hidden = true;
    modalBuyerId = null;
  }

  document.getElementById("closeModalBtn").addEventListener("click", closeModal);
  modal.addEventListener("click", (event) => {
    if (event.target === modal) closeModal();
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal.hidden) closeModal();
  });
  document.getElementById("modalNotifyBtn").addEventListener("click", () => {
    const buyerId = modalBuyerId;
    closeModal();
    if (buyerId) notifyBuyer(buyerId);
  });

  // ---- Notify ----

  async function notifyBuyer(buyerId) {
    const materialId = Number(materialSelect.value);
    if (!materialId) {
      showMessage(pageMsg, "Choose the material you are carrying first.", "error");
      return;
    }
    try {
      const response = await authFetch("/seller/notify-buyer", {
        method: "POST",
        body: JSON.stringify({ buyerId, materialCategoryId: materialId })
      });
      const data = await readJson(response);
      if (!response.ok) {
        showMessage(pageMsg, data.message || "The buyer was not notified. Try again.", "error");
        return;
      }
      showMessage(pageMsg, "Buyer notified. Mark the delivery as in transit when you leave.", "success");
      loadDeliveries();
    } catch (err) {
      showMessage(pageMsg, "Can't reach the server. Check your connection and try again.", "error");
    }
  }

  // ---- Deliveries ----

  async function loadDeliveries() {
    try {
      const response = await authFetch("/notifications");
      const data = await readJson(response);
      if (!response.ok) return;

      const mine = (data.notifications || []).filter((n) => n.sellerId === user.userId);
      if (mine.length === 0) {
        deliveriesBody.innerHTML = `<tr><td colspan="5" class="empty-row">No deliveries yet. Find a buyer above to start one.</td></tr>`;
      } else {
        deliveriesBody.innerHTML = mine.map((n) => {
          const next = NEXT_STATUS[n.status];
          const action = next
            ? `<button class="btn btn-quiet" data-id="${n.id}" data-status="${next}" type="button">Mark ${next}</button>`
            : "";
          return `
            <tr>
              <td data-label="Buyer">${escapeHtml(n.buyerName)}</td>
              <td data-label="Material">${escapeHtml(n.materialName || "")}</td>
              <td data-label="Status">${statusPill(n.status)}</td>
              <td data-label="Sent">${formatDate(n.createdAt)}</td>
              <td><div class="row-actions">${action}
                <a class="btn btn-quiet" href="chat.html?with=${n.buyerId}">Message</a></div></td>
            </tr>`;
        }).join("");
      }

      activeDeliveryIds = mine.filter((n) => n.status === "in transit").map((n) => n.id);
      updateLocationSharing();
    } catch (err) {
      deliveriesBody.innerHTML = `<tr><td colspan="5" class="empty-row">Deliveries could not be loaded.</td></tr>`;
    }
  }

  deliveriesBody.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-status]");
    if (!button) return;
    button.disabled = true;
    try {
      const response = await authFetch(`/notifications/${button.dataset.id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status: button.dataset.status })
      });
      const data = await readJson(response);
      if (!response.ok) {
        showMessage(pageMsg, data.message || "Status not updated.", "error");
      }
      loadDeliveries();
    } catch (err) {
      showMessage(pageMsg, "Can't reach the server. Check your connection and try again.", "error");
      button.disabled = false;
    }
  });

  // ---- Live location: only while a delivery is in transit ----

  function updateLocationSharing() {
    const shouldShare = activeDeliveryIds.length > 0 && navigator.geolocation;

    if (shouldShare && watchId === null) {
      watchId = navigator.geolocation.watchPosition(sendLocation, () => {}, {
        enableHighAccuracy: true,
        maximumAge: 10000
      });
    }
    if (!shouldShare && watchId !== null) {
      navigator.geolocation.clearWatch(watchId);
      watchId = null;
    }

    sharingHint.textContent = shouldShare
      ? "Sharing your live location with the buyer while you are in transit."
      : "Your location is shared with the buyer only while a delivery is in transit.";
  }

  function sendLocation(position) {
    const now = Date.now();
    if (now - lastPingAt < LOCATION_PING_MS) return; // limit server calls
    lastPingAt = now;

    const body = JSON.stringify({
      latitude: position.coords.latitude,
      longitude: position.coords.longitude
    });
    activeDeliveryIds.forEach((id) => {
      authFetch(`/notifications/${id}/location`, { method: "PATCH", body }).catch(() => {});
    });
  }

  loadMaterials();
  loadDeliveries();
})();
