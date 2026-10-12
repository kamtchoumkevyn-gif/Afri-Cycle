// Seller dashboard: find buyers on a map, tell one you're coming (or tap their photo of the
// material you carry), and share your live location while a delivery is in transit.

(function () {
  const user = requireAuth(["seller", "both"]);
  if (!user) return;

  const pageMsg = document.getElementById("pageMsg");
  const guardianBanner = document.getElementById("guardianBanner");
  const materialSelect = document.getElementById("materialSelect");
  const radiusSelect = document.getElementById("radiusSelect");
  const findBtn = document.getElementById("findBuyersBtn");
  const buyersBody = document.getElementById("buyersBody");
  const deliveriesBody = document.getElementById("deliveriesBody");
  const sharingHint = document.getElementById("sharingHint");
  const modal = document.getElementById("buyerModal");
  const modalPhotos = document.getElementById("modalPhotos");
  const mapEl = document.getElementById("sellerMap");
  const mapStatus = document.getElementById("mapStatus");

  const NEXT_STATUS = { "pending": "in transit", "in transit": "arrived" };
  const LOCATION_PING_MS = 10000;

  let activeDeliveryIds = [];
  let watchId = null;
  let lastPingAt = 0;
  let modalBuyerId = null;
  let locked = false; // a child's account still waiting for its guardian's approval

  let map = null;
  let buyerLayer = null;
  let myMarker = null;
  let routeLine = null;
  let myPosition = null; // [lat, lng], kept up to date while the page is open
  let myPositionAt = 0;
  let buyers = [];
  let selectedBuyer = null;

  if (user.role === "both") {
    document.getElementById("switchLink").hidden = false;
  }

  // ---- Account: guardian approval for children, "My children" link for parents ----

  async function checkAccount() {
    const me = await loadMe();
    if (!me) return;
    if (me.childrenCount > 0) document.getElementById("childrenLink").hidden = false;
    if (!me.isMinor) return;

    if (me.guardianStatus === "approved") {
      guardianBanner.textContent = `Your guardian ${me.guardianName} can see your deliveries, sales and messages.`;
    } else {
      locked = true;
      findBtn.disabled = true;
      guardianBanner.textContent = me.guardianStatus === "declined"
        ? "Your guardian declined this account, so it can't be used to sell."
        : `Your guardian ${me.guardianName} (${me.guardianPhone}) needs to approve your account before you can sell. Ask them to log in to Africycle with that phone number.`;
    }
    guardianBanner.hidden = false;
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

  // [lat, lng]. Reuses the live position when the page is already following you.
  function getPosition() {
    if (myPosition && Date.now() - myPositionAt < 15000) return Promise.resolve(myPosition);
    return AfriMap.locate();
  }

  findBtn.addEventListener("click", async () => {
    if (locked) return;
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
      buyersBody.innerHTML = `<tr><td colspan="5" class="empty-row">We couldn't find your position.</td></tr>`;
      showMessage(pageMsg, AfriMap.locationErrorMessage(err), "error");
      findBtn.disabled = false;
      return;
    }

    buyersBody.innerHTML = `<tr><td colspan="5" class="empty-row">Searching...</td></tr>`;
    const [latitude, longitude] = position;
    myPosition = position;
    myPositionAt = Date.now();
    const query = `lat=${latitude}&lng=${longitude}&materialCategoryId=${materialId}&radiusKm=${radiusSelect.value}`;

    try {
      const response = await authFetch(`/seller/nearby-buyers?${query}`);
      const data = await readJson(response);
      if (!response.ok) {
        showMessage(pageMsg, data.message || "Buyers could not be loaded.", "error");
        return;
      }
      buyers = data.buyers || [];
      renderBuyers();
      showBuyersOnMap();
    } catch (err) {
      showMessage(pageMsg, "Can't reach the server. Check your connection and try again.", "error");
    } finally {
      findBtn.disabled = false;
    }
  });

  function renderBuyers() {
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

  // Same buttons in the table and in the map pop-ups
  function handleBuyerAction(event) {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const buyerId = Number(button.dataset.id);
    if (button.dataset.action === "view") openBuyer(buyerId);
    if (button.dataset.action === "notify") notifyBuyer(buyerId, Number(materialSelect.value));
  }

  buyersBody.addEventListener("click", handleBuyerAction);

  // ---- Map: the buyers around you, and you as you move ----

  function showBuyersOnMap() {
    if (!map) {
      map = AfriMap.create(mapEl);
      if (!map) return; // the map library didn't load; the table still works
      buyerLayer = L.layerGroup().addTo(map);
      mapEl.addEventListener("click", handleBuyerAction);
      map.on("popupopen", (event) => {
        selectedBuyer = buyers.find((b) => b.buyerId === event.popup.options.buyerId) || null;
        drawRoute();
      });
    }
    AfriMap.show(map, mapEl);
    mapStatus.hidden = false;
    buyerLayer.clearLayers();
    selectedBuyer = null;

    const bestId = buyers.length ? buyers[0].buyerId : null; // highest price comes first
    buyers.forEach((b) => {
      L.marker([b.latitude, b.longitude], {
        icon: AfriMap.pin(b.buyerId === bestId ? "best" : "buyer", `${formatMoney(b.pricePerKg)}/kg`),
        title: b.buyerName
      }).bindPopup(popupHtml(b), { buyerId: b.buyerId }).addTo(buyerLayer);
    });

    updateMyMarker();
    AfriMap.fit(map, [myPosition, ...buyers.map((b) => [b.latitude, b.longitude])]);
    startWatching();
  }

  function popupHtml(b) {
    return `
      <div class="popup-title">${escapeHtml(b.buyerName)}</div>
      <div>${formatMoney(b.pricePerKg)}/kg &middot; ${escapeHtml(b.workingHours || "Hours not set")}</div>
      <div class="row-actions">
        <button class="btn btn-quiet" data-action="view" data-id="${b.buyerId}" type="button">Details</button>
        <button class="btn btn-primary" data-action="notify" data-id="${b.buyerId}" type="button">I'm coming</button>
        <a class="btn btn-quiet" href="${AfriMap.directionsUrl([b.latitude, b.longitude])}" target="_blank" rel="noopener">Directions</a>
      </div>`;
  }

  function updateMyMarker() {
    if (!map || !myPosition) return;
    if (myMarker) {
      myMarker.setLatLng(myPosition);
    } else {
      myMarker = L.marker(myPosition, { icon: AfriMap.pin("me", "You"), zIndexOffset: 1000, keyboard: false }).addTo(map);
    }
    drawRoute();
  }

  // A dashed line to the buyer you tapped, with the distance updating as you move
  function drawRoute() {
    if (routeLine) {
      routeLine.remove();
      routeLine = null;
    }
    if (!map || !myPosition) return;
    if (selectedBuyer) {
      const target = [selectedBuyer.latitude, selectedBuyer.longitude];
      routeLine = L.polyline([myPosition, target], { color: "#1565c0", weight: 3, dashArray: "6 8" }).addTo(map);
      const distance = AfriMap.formatDistance(AfriMap.distanceKm(myPosition, target));
      mapStatus.textContent = `${selectedBuyer.buyerName} is ${distance} away in a straight line. This updates as you move.`;
    } else {
      mapStatus.textContent = buyers.length
        ? "The orange dot pays the most. Tap a buyer to follow your distance to them."
        : "No buyers for this material near you yet.";
    }
  }

  // ---- Your position: drives the map and, during a delivery, what the buyer sees ----

  function startWatching() {
    if (watchId !== null || !navigator.geolocation) return;
    watchId = navigator.geolocation.watchPosition(onPosition, () => {}, {
      enableHighAccuracy: true,
      maximumAge: 10000
    });
  }

  function stopWatchingIfIdle() {
    const needed = !mapEl.hidden || activeDeliveryIds.length > 0;
    if (!needed && watchId !== null) {
      navigator.geolocation.clearWatch(watchId);
      watchId = null;
    }
  }

  function onPosition(position) {
    myPosition = [position.coords.latitude, position.coords.longitude];
    myPositionAt = Date.now();
    updateMyMarker();
    if (Date.now() - lastPingAt >= LOCATION_PING_MS) shareLocation();
  }

  // Sent every 10 seconds while in transit, even when standing still, so the buyer
  // knows the position is current
  function shareLocation() {
    if (!activeDeliveryIds.length || !myPosition) return;
    lastPingAt = Date.now();
    const body = JSON.stringify({ latitude: myPosition[0], longitude: myPosition[1] });
    activeDeliveryIds.forEach((id) => {
      authFetch(`/notifications/${id}/location`, { method: "PATCH", body }).catch(() => {});
    });
  }

  function updateLocationSharing() {
    if (activeDeliveryIds.length > 0) {
      startWatching();
      shareLocation();
    } else {
      stopWatchingIfIdle();
    }
    sharingHint.textContent = activeDeliveryIds.length > 0
      ? "Sharing your live location with the buyer while you are in transit."
      : "Your location is shared with the buyer only while a delivery is in transit.";
  }

  // ---- Buyer details pop-up, with their material photos ----

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
      const prices = profile.prices || [];
      document.getElementById("modalName").textContent = profile.name;
      document.getElementById("modalMeta").textContent = `Open: ${profile.workingHours || "hours not set"}`;
      document.getElementById("modalPrices").innerHTML = prices.map((p) => `
        <li><span>${escapeHtml(p.materialName || "Material")}</span><strong>${formatMoney(p.pricePerKg)}/kg</strong></li>
      `).join("");

      const withPhotos = prices.filter((p) => p.photoId);
      modalPhotos.innerHTML = withPhotos.map((p) => `
        <button type="button" class="photo-tap" data-material="${p.materialCategoryId}">
          <img data-photo-id="${p.photoId}" alt="${escapeHtml(p.materialName || "Material")} this buyer accepts">
          <span>${escapeHtml(p.materialName || "Material")} &middot; ${formatMoney(p.pricePerKg)}/kg</span>
        </button>`).join("");
      document.getElementById("modalPhotosHint").hidden = withPhotos.length === 0;
      loadPhotos(modalPhotos);

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
    if (buyerId) notifyBuyer(buyerId, Number(materialSelect.value));
  });

  // Tapping a photo = "I'm coming with this material": the trip starts in transit
  modalPhotos.addEventListener("click", (event) => {
    const tile = event.target.closest("button[data-material]");
    if (!tile || !modalBuyerId) return;
    const buyerId = modalBuyerId;
    closeModal();
    notifyBuyer(buyerId, Number(tile.dataset.material), true);
  });

  // ---- Notify ----

  async function notifyBuyer(buyerId, materialId, onTheWay = false) {
    if (locked) return;
    if (!materialId) {
      showMessage(pageMsg, "Choose the material you are carrying first.", "error");
      return;
    }
    try {
      const response = await authFetch("/seller/notify-buyer", {
        method: "POST",
        body: JSON.stringify({ buyerId, materialCategoryId: materialId, onTheWay })
      });
      const data = await readJson(response);
      if (!response.ok) {
        showMessage(pageMsg, data.message || "The buyer was not notified. Try again.", "error");
        return;
      }
      showMessage(pageMsg, data.status === "in transit"
        ? "The buyer knows you're on your way. Your live location is shared with them until you mark the delivery as arrived."
        : "Buyer notified. Mark the delivery as in transit when you leave.", "success");
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

  checkAccount();
  loadMaterials().catch(() => {
    showMessage(pageMsg, "Can't reach the server. Check your connection, then reload the page.", "error");
  });
  loadDeliveries();
  setInterval(shareLocation, LOCATION_PING_MS);
  setInterval(loadDeliveries, 30000);
})();
