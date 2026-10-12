// Buyer dashboard: location, prices and material photos, collectors on their way (with a
// live map), purchase records

(function () {
  const user = requireAuth(["buyer", "both"]);
  if (!user) return;

  const pageMsg = document.getElementById("pageMsg");
  const locationStatus = document.getElementById("locationStatus");
  const hoursInput = document.getElementById("hoursInput");
  const saveLocationBtn = document.getElementById("saveLocationBtn");
  const priceForm = document.getElementById("priceForm");
  const pricesBody = document.getElementById("pricesBody");
  const photoInput = document.getElementById("photoInput");
  const incomingBody = document.getElementById("incomingBody");
  const transactionForm = document.getElementById("transactionForm");
  const sellerSelect = document.getElementById("sellerSelect");
  const historyBody = document.getElementById("historyBody");
  const totalPreview = document.getElementById("totalPreview");
  const mapEl = document.getElementById("buyerMap");
  const mapStatus = document.getElementById("buyerMapStatus");

  const REFRESH_MS = 20000;
  const LIVE_REFRESH_MS = 10000; // while a collector is in transit
  const BUYER_NEXT_STATUS = { "arrived": "completed" };
  const MAX_UPLOAD_BYTES = 380000;

  let homePoint = null; // the saved buying point, [lat, lng]

  if (user.role === "both") {
    document.getElementById("switchLink").hidden = false;
  }

  function serverError() {
    showMessage(pageMsg, "Can't reach the server. Check your connection and try again.", "error");
  }

  async function checkAccount() {
    const me = await loadMe();
    if (me && me.childrenCount > 0) document.getElementById("childrenLink").hidden = false;
  }

  // ---- Materials ----

  async function loadMaterials() {
    const response = await authFetch("/material-categories");
    const data = await readJson(response);
    ["priceMaterialSelect", "txMaterialSelect"].forEach((id) => {
      const select = document.getElementById(id);
      (data.categories || []).forEach((c) => select.add(new Option(c.name, c.id)));
    });
  }

  // ---- Location and hours ----

  async function loadProfile() {
    const response = await authFetch("/buyer/profile");
    const data = await readJson(response);
    if (data.profile) {
      homePoint = [data.profile.latitude, data.profile.longitude];
      hoursInput.value = data.profile.workingHours || "";
      locationStatus.textContent = "Your buying point is saved. Collectors nearby can find you.";
      saveLocationBtn.textContent = "Update to my current location";
    }
  }

  saveLocationBtn.addEventListener("click", async () => {
    saveLocationBtn.disabled = true;
    locationStatus.textContent = "Finding your location...";

    let position;
    try {
      position = await AfriMap.locate();
    } catch (err) {
      locationStatus.textContent = "We couldn't find your position.";
      showMessage(pageMsg, AfriMap.locationErrorMessage(err), "error");
      saveLocationBtn.disabled = false;
      return;
    }

    try {
      const response = await authFetch("/buyer/profile", {
        method: "POST",
        body: JSON.stringify({
          latitude: position[0],
          longitude: position[1],
          workingHours: hoursInput.value.trim()
        })
      });
      const data = await readJson(response);
      if (!response.ok) {
        showMessage(pageMsg, data.message || "Location not saved.", "error");
      } else {
        showMessage(pageMsg, "Buying point saved.", "success");
        loadProfile();
      }
    } catch (err) {
      serverError();
    } finally {
      saveLocationBtn.disabled = false;
    }
  });

  // ---- Prices and material photos ----

  async function loadPrices() {
    try {
      const response = await authFetch("/buyer/prices");
      const data = await readJson(response);
      const prices = data.prices || [];
      pricesBody.innerHTML = prices.length
        ? prices.map((p) => {
            const name = escapeHtml(p.materialName);
            const photo = p.photoId
              ? `<img class="thumb" data-photo-id="${p.photoId}" alt="Your photo of ${name}">
                 <button class="btn btn-quiet" type="button" data-photo="add" data-material="${p.materialCategoryId}">Change</button>
                 <button class="btn btn-quiet" type="button" data-photo="remove" data-material="${p.materialCategoryId}">Remove</button>`
              : `<button class="btn btn-secondary" type="button" data-photo="add" data-material="${p.materialCategoryId}">Add photo</button>`;
            return `
              <tr>
                <td data-label="Material">${name}</td>
                <td data-label="Price per kg">${formatMoney(p.pricePerKg)}</td>
                <td data-label="Photo"><div class="photo-cell">${photo}</div></td>
              </tr>`;
          }).join("")
        : `<tr><td colspan="3" class="empty-row">No prices yet. Add one above so collectors can see you.</td></tr>`;
      loadPhotos(pricesBody);
    } catch (err) {
      pricesBody.innerHTML = `<tr><td colspan="3" class="empty-row">Prices could not be loaded.</td></tr>`;
    }
  }

  priceForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const materialCategoryId = Number(document.getElementById("priceMaterialSelect").value);
    const pricePerKg = Number(document.getElementById("priceInput").value);
    if (!materialCategoryId || !(pricePerKg > 0)) {
      showMessage(pageMsg, "Choose a material and enter a price above zero.", "error");
      return;
    }
    try {
      const response = await authFetch("/buyer/set-price", {
        method: "POST",
        body: JSON.stringify({ materialCategoryId, pricePerKg })
      });
      const data = await readJson(response);
      if (!response.ok) {
        showMessage(pageMsg, data.message || "Price not saved.", "error");
        return;
      }
      showMessage(pageMsg, "Price saved.", "success");
      priceForm.reset();
      loadPrices();
    } catch (err) {
      serverError();
    }
  });

  let photoMaterialId = null;

  pricesBody.addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-photo]");
    if (!button) return;
    const materialId = Number(button.dataset.material);
    if (button.dataset.photo === "add") {
      photoMaterialId = materialId;
      photoInput.value = "";
      photoInput.click();
      return;
    }
    try {
      const response = await authFetch(`/buyer/material-photo/${materialId}`, { method: "DELETE" });
      if (!response.ok) {
        const data = await readJson(response);
        showMessage(pageMsg, data.message || "Photo not removed.", "error");
      }
      loadPrices();
    } catch (err) {
      serverError();
    }
  });

  photoInput.addEventListener("change", async () => {
    const file = photoInput.files[0];
    if (!file || !photoMaterialId) return;
    showMessage(pageMsg, "Preparing your photo...", "info");
    let photo;
    try {
      photo = await shrinkPhoto(file);
    } catch (err) {
      showMessage(pageMsg, "That file couldn't be read as a photo. Choose a JPG or PNG photo, or take a new one with the camera.", "error");
      return;
    }
    try {
      const response = await authFetch("/buyer/material-photo", {
        method: "POST",
        body: JSON.stringify({ materialCategoryId: photoMaterialId, photo })
      });
      const data = await readJson(response);
      if (!response.ok) {
        showMessage(pageMsg, data.message || "Photo not saved.", "error");
        return;
      }
      showMessage(pageMsg, "Photo saved. Collectors can now tap it to tell you they're coming.", "success");
      loadPrices();
    } catch (err) {
      serverError();
    }
  });

  function readImage(file) {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file);
      const image = new Image();
      image.onload = () => {
        URL.revokeObjectURL(url);
        resolve(image);
      };
      image.onerror = () => {
        URL.revokeObjectURL(url);
        reject(new Error("not an image"));
      };
      image.src = url;
    });
  }

  // Phone photos are several MB; shrink to a JPEG small enough for slow connections
  async function shrinkPhoto(file) {
    const image = await readImage(file);
    let side = 1024;
    for (let attempt = 0; attempt < 6; attempt++) {
      const scale = Math.min(1, side / Math.max(image.naturalWidth, image.naturalHeight));
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
      canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
      canvas.getContext("2d").drawImage(image, 0, 0, canvas.width, canvas.height);
      const dataUrl = canvas.toDataURL("image/jpeg", 0.75);
      if ((dataUrl.length - dataUrl.indexOf(",") - 1) * 0.75 <= MAX_UPLOAD_BYTES) return dataUrl;
      side = Math.round(side * 0.75);
    }
    throw new Error("photo too large");
  }

  // ---- Collectors on their way (list + live map) ----

  let incoming = [];
  let map = null;
  let mapLayer = null;
  let homeMarker = null;
  let shownSellers = ""; // which collectors the map was last zoomed to
  const sellerMarkers = new Map();

  async function loadIncoming() {
    try {
      const response = await authFetch("/notifications");
      const data = await readJson(response);
      if (!response.ok) return;
      incoming = (data.notifications || []).filter((n) => n.buyerId === user.userId);
      renderIncoming();
      renderMap();
      fillSellerSelect();
    } catch (err) {
      incomingBody.innerHTML = `<tr><td colspan="5" class="empty-row">Updates could not be loaded.</td></tr>`;
    }
  }

  // Check every 10 seconds while someone is on the way, otherwise every 20
  function scheduleIncoming() {
    const live = incoming.some((n) => n.status === "in transit");
    setTimeout(async () => {
      await loadIncoming();
      scheduleIncoming();
    }, live ? LIVE_REFRESH_MS : REFRESH_MS);
  }

  function renderIncoming() {
    if (incoming.length === 0) {
      incomingBody.innerHTML = `<tr><td colspan="5" class="empty-row">No collectors on their way yet.</td></tr>`;
      return;
    }
    incomingBody.innerHTML = incoming.map((n) => {
      const actions = [];
      if (n.sellerLatitude != null && n.status === "in transit" && map) {
        actions.push(`<button class="btn btn-quiet" type="button" data-focus="${n.id}">Show on map</button>`);
      }
      if (BUYER_NEXT_STATUS[n.status]) {
        actions.push(`<button class="btn btn-quiet" type="button" data-complete="${n.id}">Mark completed</button>`);
      }
      if (n.status === "arrived" || n.status === "completed") {
        actions.push(`<button class="btn btn-quiet" type="button" data-record="${n.id}">Record purchase</button>`);
      }
      actions.push(`<a class="btn btn-quiet" href="chat.html?with=${n.sellerId}">Message</a>`);
      const minor = n.sellerIsMinor ? `<span class="badge" title="Supervised by a parent or guardian">Under 18</span>` : "";
      return `
        <tr>
          <td data-label="Collector">${escapeHtml(n.sellerName)}${minor}</td>
          <td data-label="Material">${escapeHtml(n.materialName || "")}</td>
          <td data-label="Status">${statusPill(n.status)}</td>
          <td data-label="Received">${formatDate(n.createdAt)}</td>
          <td><div class="row-actions">${actions.join("")}</div></td>
        </tr>`;
    }).join("");
  }

  function renderMap() {
    const coming = incoming.filter((n) => n.status === "in transit");
    if (coming.length === 0) {
      mapEl.hidden = true;
      mapStatus.hidden = true;
      return;
    }
    if (!map) {
      map = AfriMap.create(mapEl);
      if (!map) return;
      mapLayer = L.layerGroup().addTo(map);
      renderIncoming(); // now that the map exists, offer "Show on map"
    }
    AfriMap.show(map, mapEl);
    mapStatus.hidden = false;

    if (homePoint && !homeMarker) {
      homeMarker = L.marker(homePoint, { icon: AfriMap.pin("home", "You"), keyboard: false }).addTo(map);
    }

    mapLayer.clearLayers();
    sellerMarkers.clear();
    const lines = [];
    coming.forEach((n) => {
      if (n.sellerLatitude == null) {
        lines.push(`${n.sellerName} is on the way; waiting for their first location update.`);
        return;
      }
      const point = [n.sellerLatitude, n.sellerLongitude];
      const marker = L.marker(point, { icon: AfriMap.pin("seller", n.sellerName), zIndexOffset: 500 })
        .bindPopup(`<div class="popup-title">${escapeHtml(n.sellerName)}</div>
                    <div>${escapeHtml(n.materialName || "")} &middot; updated ${escapeHtml(AfriMap.timeAgo(n.locationUpdatedAt))}</div>`)
        .addTo(mapLayer);
      sellerMarkers.set(n.id, marker);
      if (homePoint) {
        L.polyline([point, homePoint], { color: "#1565c0", weight: 3, dashArray: "6 8" }).addTo(mapLayer);
        const distance = AfriMap.formatDistance(AfriMap.distanceKm(point, homePoint));
        lines.push(`${n.sellerName} is ${distance} away (updated ${AfriMap.timeAgo(n.locationUpdatedAt)}).`);
      } else {
        lines.push(`${n.sellerName} was seen ${AfriMap.timeAgo(n.locationUpdatedAt)}. Save your buying point to see the distance.`);
      }
    });
    mapStatus.textContent = lines.join(" ");

    // Zoom to fit only when the set of collectors changes, so your own zooming isn't undone
    const key = coming.map((n) => n.id).join(",");
    if (key !== shownSellers) {
      shownSellers = key;
      AfriMap.fit(map, [homePoint, ...coming.filter((n) => n.sellerLatitude != null)
        .map((n) => [n.sellerLatitude, n.sellerLongitude])]);
    }
  }

  function fillSellerSelect() {
    const current = sellerSelect.value;
    const seen = new Map();
    incoming.forEach((n) => seen.set(n.sellerId, n.sellerName));
    sellerSelect.length = 1; // keep the placeholder
    seen.forEach((name, id) => sellerSelect.add(new Option(name, id)));
    if (current) sellerSelect.value = current;
  }

  incomingBody.addEventListener("click", async (event) => {
    const focusBtn = event.target.closest("button[data-focus]");
    const completeBtn = event.target.closest("button[data-complete]");
    const recordBtn = event.target.closest("button[data-record]");

    if (focusBtn) {
      const marker = sellerMarkers.get(Number(focusBtn.dataset.focus));
      if (marker) {
        mapEl.scrollIntoView({ behavior: "smooth", block: "center" });
        map.setView(marker.getLatLng(), 16);
        marker.openPopup();
      }
    }

    if (completeBtn) {
      completeBtn.disabled = true;
      try {
        const response = await authFetch(`/notifications/${completeBtn.dataset.complete}/status`, {
          method: "PATCH",
          body: JSON.stringify({ status: "completed" })
        });
        if (!response.ok) {
          const data = await readJson(response);
          showMessage(pageMsg, data.message || "Status not updated.", "error");
        }
        loadIncoming();
      } catch (err) {
        serverError();
      }
    }

    if (recordBtn) {
      const n = incoming.find((item) => item.id === Number(recordBtn.dataset.record));
      if (!n) return;
      sellerSelect.value = String(n.sellerId);
      document.getElementById("txMaterialSelect").value = String(n.materialCategoryId);
      document.getElementById("weightInput").focus();
      document.getElementById("logHeading").scrollIntoView({ behavior: "smooth" });
    }
  });

  // ---- Record a purchase ----

  function updateTotal() {
    const weight = Number(document.getElementById("weightInput").value);
    const price = Number(document.getElementById("txPriceInput").value);
    totalPreview.textContent = weight > 0 && price > 0 ? `Total to pay in cash: ${formatMoney(weight * price)}` : "";
  }
  document.getElementById("weightInput").addEventListener("input", updateTotal);
  document.getElementById("txPriceInput").addEventListener("input", updateTotal);

  transactionForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const body = {
      sellerId: Number(sellerSelect.value),
      materialCategoryId: Number(document.getElementById("txMaterialSelect").value),
      weightKg: Number(document.getElementById("weightInput").value),
      pricePerKg: Number(document.getElementById("txPriceInput").value)
    };
    if (!body.sellerId || !body.materialCategoryId || !(body.weightKg > 0) || !(body.pricePerKg > 0)) {
      showMessage(pageMsg, "Choose the collector and material, then enter weight and price.", "error");
      return;
    }
    try {
      const response = await authFetch("/buyer/log-transaction", {
        method: "POST",
        body: JSON.stringify(body)
      });
      const data = await readJson(response);
      if (!response.ok) {
        showMessage(pageMsg, data.message || "Purchase not recorded.", "error");
        return;
      }
      showMessage(pageMsg, "Purchase recorded.", "success");
      transactionForm.reset();
      totalPreview.textContent = "";
      loadHistory();
    } catch (err) {
      serverError();
    }
  });

  // ---- History ----

  async function loadHistory() {
    try {
      const response = await authFetch("/buyer/transaction-history");
      const data = await readJson(response);
      const rows = data.transactions || [];
      historyBody.innerHTML = rows.length
        ? rows.map((t) => `
            <tr>
              <td data-label="Collector">${escapeHtml(t.sellerName)}</td>
              <td data-label="Material">${escapeHtml(t.materialName || "")}</td>
              <td data-label="Weight">${t.weightKg} kg</td>
              <td data-label="Total"><strong>${formatMoney(t.totalAmount)}</strong></td>
              <td data-label="Date">${formatDate(t.createdAt)}</td>
            </tr>`).join("")
        : `<tr><td colspan="5" class="empty-row">No purchases recorded yet.</td></tr>`;
    } catch (err) {
      historyBody.innerHTML = `<tr><td colspan="5" class="empty-row">History could not be loaded.</td></tr>`;
    }
  }

  checkAccount();
  loadMaterials().catch(serverError);
  loadPrices();
  loadHistory();
  // The buying point is needed before the map draws collectors' distances
  (async () => {
    try {
      await loadProfile();
    } catch (err) {
      // No buying point yet, or no connection: the list still loads; distances appear later
    }
    await loadIncoming();
    scheduleIncoming();
  })();
})();
