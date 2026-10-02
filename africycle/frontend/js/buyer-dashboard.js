// Buyer dashboard: location, prices, incoming collectors, purchase records

(function () {
  const user = requireAuth(["buyer", "both"]);
  if (!user) return;

  const pageMsg = document.getElementById("pageMsg");
  const locationStatus = document.getElementById("locationStatus");
  const hoursInput = document.getElementById("hoursInput");
  const saveLocationBtn = document.getElementById("saveLocationBtn");
  const priceForm = document.getElementById("priceForm");
  const pricesBody = document.getElementById("pricesBody");
  const incomingBody = document.getElementById("incomingBody");
  const transactionForm = document.getElementById("transactionForm");
  const sellerSelect = document.getElementById("sellerSelect");
  const historyBody = document.getElementById("historyBody");
  const totalPreview = document.getElementById("totalPreview");

  const REFRESH_MS = 20000;
  const BUYER_NEXT_STATUS = { "arrived": "completed" };

  if (user.role === "both") {
    document.getElementById("switchLink").hidden = false;
  }

  function serverError() {
    showMessage(pageMsg, "Can't reach the server. Check your connection and try again.", "error");
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
      hoursInput.value = data.profile.workingHours || "";
      locationStatus.textContent = "Your buying point is saved. Collectors nearby can find you.";
      saveLocationBtn.textContent = "Update to my current location";
    }
  }

  saveLocationBtn.addEventListener("click", () => {
    if (!navigator.geolocation) {
      showMessage(pageMsg, "This browser can't share location. Try another browser or device.", "error");
      return;
    }
    saveLocationBtn.disabled = true;
    locationStatus.textContent = "Finding your location...";

    navigator.geolocation.getCurrentPosition(async (position) => {
      try {
        const response = await authFetch("/buyer/profile", {
          method: "POST",
          body: JSON.stringify({
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
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
    }, () => {
      locationStatus.textContent = "Location is off.";
      showMessage(pageMsg, "Allow location access in your browser, then tap Save again.", "error");
      saveLocationBtn.disabled = false;
    }, { enableHighAccuracy: true, timeout: 15000 });
  });

  // ---- Prices ----

  async function loadPrices() {
    try {
      const response = await authFetch("/buyer/prices");
      const data = await readJson(response);
      const prices = data.prices || [];
      pricesBody.innerHTML = prices.length
        ? prices.map((p) => `
            <tr>
              <td data-label="Material">${escapeHtml(p.materialName)}</td>
              <td data-label="Price per kg">${formatMoney(p.pricePerKg)}</td>
            </tr>`).join("")
        : `<tr><td colspan="2" class="empty-row">No prices yet. Add one above so collectors can see you.</td></tr>`;
    } catch (err) {
      pricesBody.innerHTML = `<tr><td colspan="2" class="empty-row">Prices could not be loaded.</td></tr>`;
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

  // ---- Incoming collectors ----

  let incoming = [];

  async function loadIncoming() {
    try {
      const response = await authFetch("/notifications");
      const data = await readJson(response);
      if (!response.ok) return;
      incoming = (data.notifications || []).filter((n) => n.buyerId === user.userId);
      renderIncoming();
      fillSellerSelect();
    } catch (err) {
      incomingBody.innerHTML = `<tr><td colspan="5" class="empty-row">Updates could not be loaded.</td></tr>`;
    }
  }

  function renderIncoming() {
    if (incoming.length === 0) {
      incomingBody.innerHTML = `<tr><td colspan="5" class="empty-row">No collectors on their way yet.</td></tr>`;
      return;
    }
    incomingBody.innerHTML = incoming.map((n) => {
      const actions = [];
      if (n.sellerLatitude != null && n.status === "in transit") {
        actions.push(`<a class="btn btn-quiet" target="_blank" rel="noopener"
          href="https://www.google.com/maps?q=${n.sellerLatitude},${n.sellerLongitude}">See on map</a>`);
      }
      if (BUYER_NEXT_STATUS[n.status]) {
        actions.push(`<button class="btn btn-quiet" type="button" data-complete="${n.id}">Mark completed</button>`);
      }
      if (n.status === "arrived" || n.status === "completed") {
        actions.push(`<button class="btn btn-quiet" type="button" data-record="${n.id}">Record purchase</button>`);
      }
      actions.push(`<a class="btn btn-quiet" href="chat.html?with=${n.sellerId}">Message</a>`);
      return `
        <tr>
          <td data-label="Collector">${escapeHtml(n.sellerName)}</td>
          <td data-label="Material">${escapeHtml(n.materialName || "")}</td>
          <td data-label="Status">${statusPill(n.status)}</td>
          <td data-label="Received">${formatDate(n.createdAt)}</td>
          <td><div class="row-actions">${actions.join("")}</div></td>
        </tr>`;
    }).join("");
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
    const completeBtn = event.target.closest("button[data-complete]");
    const recordBtn = event.target.closest("button[data-record]");

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

  loadMaterials();
  loadProfile();
  loadPrices();
  loadIncoming();
  loadHistory();
  setInterval(loadIncoming, REFRESH_MS);
})();
