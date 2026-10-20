// Seller dashboard: find buyers on a map, tell one you're coming (or tap their photo of the
// material you carry), then follow the way there by road on a map that stays until you
// arrive. Your live location is shared with the buyer while the delivery is in transit.

AfriI18n.whenReady(function () {
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
  const routeCredit = document.getElementById("routeCredit");

  const NEXT_STATUS = { "pending": "in transit", "in transit": "arrived" };
  const MARK_AS = { "in transit": t("Mark in transit"), "arrived": t("Mark arrived") };
  const LOCATION_PING_MS = 10000;
  const TRIP_KEY = "africycle_trip";          // the delivery the trip map shows
  const MODE_KEY = "africycle_travel_mode";   // on foot, or by motorbike/car

  let activeDeliveryIds = [];
  let watchId = null;
  let lastPingAt = 0;
  let modalBuyerId = null;
  let locked = false; // a child's account still waiting for its guardian's approval

  let map = null;
  let buyerLayer = null;
  let myMarker = null;
  let routeLine = null;
  let roadPreview = null; // {buyerId, route}: the way by road to the buyer tapped on the search map
  let myPosition = null; // [lat, lng], kept up to date while the page is open
  let myPositionAt = 0;
  let buyers = [];
  let selectedBuyer = null;
  let travelMode = readSetting(MODE_KEY) === "car" ? "car" : "foot";

  if (user.role === "both") {
    document.getElementById("switchLink").hidden = false;
  }

  function readSetting(key) {
    try {
      return localStorage.getItem(key);
    } catch (err) {
      return null;
    }
  }

  function writeSetting(key, value) {
    try {
      localStorage.setItem(key, String(value));
    } catch (err) {
      // Not remembered on this browser; everything still works
    }
  }

  function serverError() {
    showMessage(pageMsg, t("Can't reach the server. Check your connection, then try again."), "error");
  }

  // ---- Account: guardian approval for children, "My children" link for parents ----

  async function checkAccount() {
    const me = await loadMe();
    if (!me) return;
    if (me.childrenCount > 0) document.getElementById("childrenLink").hidden = false;
    if (!me.isMinor) return;

    if (me.guardianStatus === "approved") {
      guardianBanner.textContent = t("Your guardian {name} can see your deliveries, sales and messages.", { name: me.guardianName });
    } else {
      locked = true;
      findBtn.disabled = true;
      guardianBanner.textContent = me.guardianStatus === "declined"
        ? t("Your guardian declined this account, so it can't be used to sell.")
        : t("Your guardian {name} ({phone}) needs to approve your account before you can sell. Ask them to log in to Africycle with that phone number.",
          { name: me.guardianName, phone: AfriPhone.format(me.guardianPhone) });
      if (me.guardianStatus === "pending") showApprovalCode(me.approvalCode, me.approvalCodeBlocked);
    }
    guardianBanner.hidden = false;
  }

  // The code the guardian types to approve this child: phone numbers aren't confirmed,
  // so the number alone doesn't prove who is approving. After too many wrong codes the
  // child asks for a new one.
  const approvalCodeBox = document.getElementById("approvalCodeBox");
  const newCodeBtn = document.getElementById("newCodeBtn");

  function showApprovalCode(code, blocked) {
    approvalCodeBox.hidden = false;
    document.getElementById("approvalCodeLabel").hidden = blocked;
    // Two groups of 3 digits are easier to read out and type
    document.getElementById("approvalCode").textContent = blocked || !code ? "" : code.replace(/^(\d{3})(\d{3})$/, "$1 $2");
    document.getElementById("approvalCode").hidden = blocked;
    document.getElementById("approvalBlocked").hidden = !blocked;
    newCodeBtn.hidden = !blocked;
  }

  newCodeBtn.addEventListener("click", async () => {
    newCodeBtn.disabled = true;
    try {
      const response = await authFetch("/me/approval-code", { method: "POST" });
      const data = await readJson(response);
      if (!response.ok) {
        showMessage(pageMsg, data.message || t("That didn't work. Try again."), "error");
        return;
      }
      showApprovalCode(data.approvalCode, false);
    } catch (err) {
      serverError();
    } finally {
      newCodeBtn.disabled = false;
    }
  });

  // ---- Materials ----

  async function loadMaterials() {
    const response = await authFetch("/material-categories");
    const data = await readJson(response);
    (data.categories || []).forEach((category) => {
      materialSelect.add(new Option(materialName(category.name), category.id));
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
      showMessage(pageMsg, t("Choose a material first."), "error");
      return;
    }

    findBtn.disabled = true;
    buyersBody.innerHTML = `<tr><td colspan="5" class="empty-row">${t("Finding your location...")}</td></tr>`;

    let position;
    try {
      position = await getPosition();
    } catch (err) {
      buyersBody.innerHTML = `<tr><td colspan="5" class="empty-row">${t("We couldn't find your position.")}</td></tr>`;
      showMessage(pageMsg, AfriMap.locationErrorMessage(err), "error");
      findBtn.disabled = false;
      return;
    }

    buyersBody.innerHTML = `<tr><td colspan="5" class="empty-row">${t("Searching...")}</td></tr>`;
    const [latitude, longitude] = position;
    myPosition = position;
    myPositionAt = Date.now();
    const query = `lat=${latitude}&lng=${longitude}&materialCategoryId=${materialId}&radiusKm=${radiusSelect.value}`;

    try {
      const response = await authFetch(`/seller/nearby-buyers?${query}`);
      const data = await readJson(response);
      if (!response.ok) {
        showMessage(pageMsg, data.message || t("Buyers could not be loaded."), "error");
        return;
      }
      buyers = data.buyers || [];
      renderBuyers();
      showBuyersOnMap();
    } catch (err) {
      serverError();
    } finally {
      findBtn.disabled = false;
    }
  });

  function renderBuyers() {
    if (buyers.length === 0) {
      buyersBody.innerHTML = `<tr><td colspan="5" class="empty-row">${t("No buyers for this material in that distance. Try a wider search.")}</td></tr>`;
      return;
    }
    buyersBody.innerHTML = buyers.map((b) => `
      <tr>
        <td data-label="${t("Buyer")}">${escapeHtml(b.buyerName)}</td>
        <td data-label="${t("Price per kg")}"><strong>${formatMoney(b.pricePerKg)}</strong></td>
        <td data-label="${t("Distance")}">${AfriI18n.formatUnit(b.distanceKm, "kilometer", 1)}</td>
        <td data-label="${t("Hours")}">${escapeHtml(b.workingHours || t("Not set"))}</td>
        <td>
          <div class="row-actions">
            <button class="btn btn-quiet" data-action="view" data-id="${b.buyerId}" type="button">${t("Details")}</button>
            <button class="btn btn-primary" data-action="notify" data-id="${b.buyerId}" type="button">${t("I'm coming")}</button>
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
    if (button.dataset.action === "route") previewRoad(buyerId);
  }

  buyersBody.addEventListener("click", handleBuyerAction);

  // ---- Search map: the buyers around you, and you as you move ----

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
    roadPreview = null;

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
      <div>${formatMoney(b.pricePerKg)}/kg &middot; ${escapeHtml(b.workingHours || t("Hours not set"))}</div>
      <div class="row-actions">
        <button class="btn btn-quiet" data-action="view" data-id="${b.buyerId}" type="button">${t("Details")}</button>
        <button class="btn btn-primary" data-action="notify" data-id="${b.buyerId}" type="button">${t("I'm coming")}</button>
        <button class="btn btn-quiet" data-action="route" data-id="${b.buyerId}" type="button">${t("Route")}</button>
      </div>`;
  }

  function updateMyMarker() {
    if (!map || !myPosition) return;
    if (myMarker) {
      myMarker.setLatLng(myPosition);
    } else {
      myMarker = L.marker(myPosition, { icon: AfriMap.pin("me", t("You")), zIndexOffset: 1000, keyboard: false }).addTo(map);
    }
    drawRoute();
  }

  // The buyer you tapped: the way by road once worked out, otherwise a straight dashed line
  function drawRoute() {
    if (routeLine) {
      routeLine.remove();
      routeLine = null;
    }
    AfriMap.showRouteCredit(routeCredit, null);
    if (!map || !myPosition) return;
    if (!selectedBuyer) {
      mapStatus.textContent = buyers.length
        ? t("The orange dot pays the most. Tap a buyer to see how far they are.")
        : t("No buyers for this material near you yet.");
      return;
    }
    const name = selectedBuyer.buyerName;
    if (roadPreview && roadPreview.buyerId === selectedBuyer.buyerId) {
      routeLine = L.polyline(roadPreview.route.line, { color: "#1565c0", weight: 5, opacity: 0.85 }).addTo(map);
      AfriMap.showRouteCredit(routeCredit, roadPreview.route);
      const left = AfriMap.progress(roadPreview.route, myPosition);
      const values = { name, distance: AfriMap.formatDistance(left.leftKm), time: AfriMap.formatDuration(left.leftSeconds) };
      mapStatus.textContent = travelMode === "car"
        ? t("{name} is {distance} away by road, about {time} by motorbike or car. Tap \"I'm coming\" to be guided there.", values)
        : t("{name} is {distance} away by road, about {time} on foot. Tap \"I'm coming\" to be guided there.", values);
      return;
    }
    const target = [selectedBuyer.latitude, selectedBuyer.longitude];
    routeLine = L.polyline([myPosition, target], { color: "#1565c0", weight: 3, dashArray: "6 8" }).addTo(map);
    const distance = AfriMap.formatDistance(AfriMap.distanceKm(myPosition, target));
    mapStatus.textContent = t("{name} is {distance} away in a straight line. Tap Route for the way by road.", { name, distance });
  }

  async function previewRoad(buyerId) {
    const buyer = buyers.find((b) => b.buyerId === buyerId);
    if (!buyer || !myPosition) return;
    selectedBuyer = buyer;
    mapStatus.textContent = t("Working out the way to {name} by road...", { name: buyer.buyerName });
    try {
      const route = await AfriMap.fetchRoute(myPosition, [buyer.latitude, buyer.longitude], travelMode);
      roadPreview = { buyerId, route };
      if (map) map.closePopup();
      selectedBuyer = buyer;
      drawRoute();
      if (map) AfriMap.fit(map, route.line.concat([myPosition, [buyer.latitude, buyer.longitude]]));
    } catch (err) {
      mapStatus.textContent = `${err.message} ${t("The dashed line points straight at {name}.", { name: buyer.buyerName })}`;
    }
  }

  // ---- Your position: drives the maps and, during a delivery, what the buyer sees ----

  function startWatching() {
    if (watchId !== null || !navigator.geolocation) return;
    watchId = navigator.geolocation.watchPosition(onPosition, () => {}, {
      enableHighAccuracy: true,
      maximumAge: 10000
    });
  }

  function stopWatchingIfIdle() {
    const needed = !mapEl.hidden || activeDeliveryIds.length > 0 || trip !== null;
    if (!needed && watchId !== null) {
      navigator.geolocation.clearWatch(watchId);
      watchId = null;
    }
  }

  function onPosition(position) {
    myPosition = [position.coords.latitude, position.coords.longitude];
    myPositionAt = Date.now();
    updateMyMarker();
    updateTrip();
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
    if (activeDeliveryIds.length > 0 || trip) {
      startWatching();
      shareLocation();
    } else {
      stopWatchingIfIdle();
    }
    sharingHint.textContent = activeDeliveryIds.length > 0
      ? t("Sharing your live location with the buyer while you are in transit.")
      : t("Your location is shared with the buyer only while a delivery is in transit.");
  }

  // ---- Your trip: a map that stays until you arrive, showing the way by road ----

  const tripPanel = document.getElementById("tripPanel");
  const tripMapEl = document.getElementById("tripMap");
  const tripSummary = document.getElementById("tripSummary");
  const tripNext = document.getElementById("tripNext");
  const tripNextDistance = document.getElementById("tripNextDistance");
  const tripNextText = document.getElementById("tripNextText");
  const tripFollowBtn = document.getElementById("tripFollowBtn");
  const tripStartBtn = document.getElementById("tripStartBtn");
  const tripArrivedBtn = document.getElementById("tripArrivedBtn");
  const tripStepsBox = document.getElementById("tripStepsBox");
  const tripSteps = document.getElementById("tripSteps");
  const tripCredit = document.getElementById("tripCredit");
  const ARRIVED_KM = 0.05;      // within 50 m of the buying point
  const OFF_ROUTE_KM = 0.06;     // more than 60 m away from the road route: work out a new one
  const REROUTE_GAP_MS = 20000;  // at most every 20 seconds

  let trip = null;        // the delivery being guided
  let tripMap = null;
  let tripLayer = null;   // the buyer's pin and the line to follow
  let tripMe = null;
  let tripRoute = null;   // the way by road; null while unknown (a straight line is shown)
  let tripRouteError = "";
  let routeAskedAt = 0;
  let routeLoading = false;
  let following = true;
  const NEAR_TURN_KM = 0.05;    // a turn this close is said again, as it is reached
  let saidStep = null;          // the next turn, once said aloud
  let saidNearStep = null;      // the turn, once said as it is reached
  let saidArrival = null;       // the trip whose arrival was said

  tripPanel.querySelectorAll("[data-mode]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.mode === travelMode));
    button.addEventListener("click", () => {
      if (button.dataset.mode === travelMode) return;
      travelMode = button.dataset.mode;
      writeSetting(MODE_KEY, travelMode);
      tripPanel.querySelectorAll("[data-mode]").forEach((b) => b.setAttribute("aria-pressed", String(b === button)));
      roadPreview = null;
      drawRoute(); // the search map's road route was for the other way of travelling
      tripRoute = null;
      routeAskedAt = 0; // ask again now, even if a request for the old way is still out
      drawTripLine(false);
      listSteps(); // the old way's directions no longer apply
      requestRoute();
    });
  });

  tripFollowBtn.addEventListener("click", () => {
    following = true;
    tripFollowBtn.hidden = true;
    updateTrip();
  });

  tripStartBtn.addEventListener("click", () => setTripStatus("in transit"));
  tripArrivedBtn.addEventListener("click", () => setTripStatus("arrived"));

  // The trip to show: the one you just started or picked, else one in transit, else pending
  function chooseTrip(deliveries) {
    const active = deliveries.filter((d) =>
      (d.status === "pending" || d.status === "in transit") && d.buyerLatitude != null);
    const chosen = Number(readSetting(TRIP_KEY));
    return active.find((d) => d.id === chosen) || active.find((d) => d.status === "in transit") || active[0] || null;
  }

  function showTrip(delivery) {
    if (!delivery) {
      trip = null;
      tripPanel.hidden = true;
      return;
    }
    const isNew = !trip || trip.id !== delivery.id;
    const wasPending = trip && trip.status === "pending";
    trip = {
      id: delivery.id,
      buyerId: delivery.buyerId,
      buyerName: delivery.buyerName,
      status: delivery.status,
      target: [delivery.buyerLatitude, delivery.buyerLongitude]
    };
    tripPanel.hidden = false;
    document.getElementById("tripBuyerName").textContent = trip.buyerName;
    document.getElementById("tripChatLink").href = `chat.html?with=${trip.buyerId}`;
    document.getElementById("tripMapsLink").href = AfriMap.directionsUrl(trip.target);
    tripStartBtn.hidden = trip.status !== "pending";
    tripArrivedBtn.hidden = trip.status !== "in transit";

    if (isNew) {
      tripRoute = null;
      tripRouteError = "";
      routeAskedAt = 0;
      following = trip.status === "in transit";
      loadTripPhone(trip.buyerId);
      setUpTripMap();
      drawTripLine(true);
      listSteps();
    } else if (wasPending && trip.status === "in transit") {
      following = true; // just set off: keep the map on you
    }
    tripFollowBtn.hidden = following || trip.status !== "in transit";
    startWatching();
    updateTrip();
  }

  function setUpTripMap() {
    if (!tripMap) {
      tripMap = AfriMap.create(tripMapEl);
      if (!tripMap) return; // no map library: the panel still gives the distance and turns
      tripLayer = L.layerGroup().addTo(tripMap);
      tripMap.on("dragstart", () => {
        following = false;
        tripFollowBtn.hidden = !trip || trip.status !== "in transit";
      });
    }
    AfriMap.show(tripMap, tripMapEl);
  }

  function drawTripLine(fit) {
    AfriMap.showRouteCredit(tripCredit, tripRoute); // also without a map, beside the directions
    if (!tripMap || !trip) return;
    tripLayer.clearLayers();
    L.marker(trip.target, { icon: AfriMap.pin("home", trip.buyerName), keyboard: false }).addTo(tripLayer);
    if (tripRoute) {
      L.polyline(tripRoute.line, { color: "#1565c0", weight: 6, opacity: 0.85 }).addTo(tripLayer);
    } else if (myPosition) {
      L.polyline([myPosition, trip.target], { color: "#1565c0", weight: 3, dashArray: "6 8" }).addTo(tripLayer);
    }
    if (fit) {
      AfriMap.fit(tripMap, tripRoute ? tripRoute.line.concat(myPosition ? [myPosition] : []) : [myPosition, trip.target]);
    }
  }

  async function requestRoute() {
    if (!trip || !myPosition || routeLoading) return;
    routeLoading = true;
    routeAskedAt = Date.now();
    const forTrip = trip.id;
    const forMode = travelMode;
    try {
      const route = await AfriMap.fetchRoute(myPosition, trip.target, travelMode);
      if (!trip || trip.id !== forTrip || forMode !== travelMode) return; // changed meanwhile
      const first = !tripRoute;
      tripRoute = route;
      tripRouteError = "";
      drawTripLine(first && !following);
      listSteps();
    } catch (err) {
      if (trip && trip.id === forTrip) {
        tripRouteError = err.message;
        drawTripLine(false);
      }
    } finally {
      routeLoading = false;
      updateTrip();
    }
  }

  function listSteps() {
    tripStepsBox.hidden = !tripRoute;
    if (!tripRoute) return;
    tripSteps.innerHTML = tripRoute.steps.map((step) => {
      const text = step.type === "arrive" ? t("Arrive at {name}'s buying point", { name: trip.buyerName }) : step.text;
      const distance = step.distance ? ` <span class="step-distance">${AfriMap.formatDistance(step.distance / 1000)}</span>` : "";
      return `<li>${escapeHtml(text)}${distance}</li>`;
    }).join("");
  }

  // Runs on every position update: where you are, the next turn, what's left
  function updateTrip() {
    if (!trip) return;
    if (!myPosition) {
      tripSummary.textContent = t("Finding your position...");
      tripNext.hidden = true;
      return;
    }
    if (tripMap) {
      if (tripMe) {
        tripMe.setLatLng(myPosition);
      } else {
        tripMe = L.marker(myPosition, { icon: AfriMap.pin("me", t("You")), zIndexOffset: 1000, keyboard: false }).addTo(tripMap);
      }
      if (!tripRoute) drawTripLine(false); // keep the straight line starting where you are
    }

    const info = tripRoute ? AfriMap.progress(tripRoute, myPosition) : null;
    const due = Date.now() - routeAskedAt > REROUTE_GAP_MS;
    if (!tripRoute && (routeAskedAt === 0 || due)) requestRoute();
    if (info && info.offRouteKm > OFF_ROUTE_KM && due) requestRoute(); // took another way

    const straightKm = AfriMap.distanceKm(myPosition, trip.target);
    tripPanel.classList.toggle("trip-arrived", straightKm <= ARRIVED_KM);
    if (straightKm <= ARRIVED_KM) {
      tripSummary.textContent = t("You're there.");
      tripNext.hidden = false;
      tripNextDistance.textContent = t("Here");
      tripNextText.textContent = trip.status === "in transit"
        ? t("You're at {name}'s buying point. Tap \"I've arrived\".", { name: trip.buyerName })
        : t("You're at {name}'s buying point.", { name: trip.buyerName });
    } else if (info) {
      const left = { distance: AfriMap.formatDistance(info.leftKm), time: AfriMap.formatDuration(info.leftSeconds) };
      tripSummary.textContent = travelMode === "car"
        ? t("{distance} to go, about {time} by motorbike or car.", left)
        : t("{distance} to go, about {time} on foot.", left);
      tripNext.hidden = !info.next;
      if (info.next) {
        const arriving = info.next.type === "arrive";
        const distance = AfriMap.formatDistance(info.nextKm);
        tripNextDistance.textContent = arriving ? distance : t("In {distance}", { distance });
        tripNextText.textContent = arriving ? t("Arrive at {name}'s buying point", { name: trip.buyerName }) : info.next.text;
      }
    } else {
      tripNext.hidden = true;
      tripSummary.textContent = t("{name} is {distance} away in a straight line.",
        { name: trip.buyerName, distance: AfriMap.formatDistance(straightKm) }) +
        " " + (routeLoading ? t("Working out the way by road...") : tripRouteError);
    }

    speakTheWay(straightKm, info);

    if (following && tripMap && trip.status === "in transit") {
      tripMap.setView(myPosition, Math.max(tripMap.getZoom(), 16));
    }
  }

  // On the way, the turns are said aloud for people who can't read them (js/guide.js,
  // "Read messages and directions aloud"): each turn when it becomes the next one ("In
  // 300 m, turn left onto..."), again just before it, and the arrival.
  function speakTheWay(straightKm, info) {
    if (typeof AfriGuide === "undefined" || !trip || trip.status !== "in transit") return;
    if (straightKm <= ARRIVED_KM) {
      if (saidArrival !== trip.id) {
        saidArrival = trip.id;
        AfriGuide.announce([{ key: "You're at {name}'s buying point. Tap \"I've arrived\".", values: { name: trip.buyerName } }]);
      }
      return;
    }
    if (!info || !info.next) return;
    const step = info.next;
    const turn = step.type === "arrive"
      ? { key: "Arrive at {name}'s buying point", values: { name: trip.buyerName } }
      : { text: step.text };
    if (saidStep !== step) {
      saidStep = step;
      if (info.nextKm <= NEAR_TURN_KM) saidNearStep = step; // already there: once is enough
      AfriGuide.announce([{ key: "In {distance}", values: { distance: AfriMap.formatDistance(info.nextKm) } }, turn]);
    } else if (info.nextKm <= NEAR_TURN_KM && saidNearStep !== step) {
      saidNearStep = step;
      AfriGuide.announce([turn]);
    }
  }

  async function loadTripPhone(buyerId) {
    const link = document.getElementById("tripCallLink");
    link.hidden = true;
    try {
      const response = await authFetch(`/seller/contact-buyer/${buyerId}`);
      const data = await readJson(response);
      if (response.ok && data.phoneNumber && trip && trip.buyerId === buyerId) {
        link.href = `tel:${data.phoneNumber}`;
        link.textContent = t("Call");
        link.hidden = false;
      }
    } catch (err) {
      // No phone link; "Message" still works
    }
  }

  async function setTripStatus(status) {
    if (!trip) return;
    const button = status === "arrived" ? tripArrivedBtn : tripStartBtn;
    const name = trip.buyerName;
    button.disabled = true;
    try {
      const response = await authFetch(`/notifications/${trip.id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status })
      });
      const data = await readJson(response);
      if (!response.ok) {
        showMessage(pageMsg, data.message || t("Status not updated."), "error");
      } else if (status === "arrived") {
        showMessage(pageMsg, t("{name} has been told you've arrived. Weigh the material together, then they record the purchase.", { name }), "success");
      }
      await loadDeliveries();
    } catch (err) {
      serverError();
    } finally {
      button.disabled = false;
    }
  }

  function guideTo(notificationId) {
    writeSetting(TRIP_KEY, notificationId);
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
        showMessage(pageMsg, profile.message || t("Buyer details could not be loaded."), "error");
        return;
      }

      modalBuyerId = buyerId;
      const prices = profile.prices || [];
      document.getElementById("modalName").textContent = profile.name;
      document.getElementById("modalMeta").textContent = t("Open: {hours}", { hours: profile.workingHours || t("hours not set") });
      document.getElementById("modalPrices").innerHTML = prices.map((p) => `
        <li><span>${escapeHtml(materialName(p.materialName))}</span><strong>${formatMoney(p.pricePerKg)}/kg</strong></li>
      `).join("");

      const withPhotos = prices.filter((p) => p.photoId);
      modalPhotos.innerHTML = withPhotos.map((p) => `
        <button type="button" class="photo-tap" data-material="${p.materialCategoryId}">
          <img data-photo-id="${p.photoId}" alt="${escapeHtml(t("{material} this buyer accepts", { material: materialName(p.materialName) }))}">
          <span>${escapeHtml(materialName(p.materialName))} &middot; ${formatMoney(p.pricePerKg)}/kg</span>
        </button>`).join("");
      document.getElementById("modalPhotosHint").hidden = withPhotos.length === 0;
      loadPhotos(modalPhotos);

      const callLink = document.getElementById("modalCallLink");
      callLink.href = contact.phoneNumber ? `tel:${contact.phoneNumber}` : "#";
      callLink.textContent = contact.phoneNumber
        ? t("Call {phone}", { phone: AfriPhone.format(contact.phoneNumber) }) : t("Phone not available");
      document.getElementById("modalChatLink").href = `chat.html?with=${buyerId}`;

      modal.hidden = false;
      document.getElementById("closeModalBtn").focus();
    } catch (err) {
      serverError();
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
      showMessage(pageMsg, t("Choose the material you are carrying first."), "error");
      return;
    }
    try {
      const response = await authFetch("/seller/notify-buyer", {
        method: "POST",
        body: JSON.stringify({ buyerId, materialCategoryId: materialId, onTheWay })
      });
      const data = await readJson(response);
      if (!response.ok) {
        showMessage(pageMsg, data.message || t("The buyer was not notified. Try again."), "error");
        return;
      }
      showMessage(pageMsg, data.status === "in transit"
        ? t("The buyer knows you're on your way. Follow the map below; your live location is shared with them until you arrive.")
        : t("Buyer notified. The map below shows the way; tap \"I'm leaving now\" when you set off."), "success");
      guideTo(data.notificationId);
      await loadDeliveries();
      if (!tripPanel.hidden) tripPanel.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      serverError();
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
        deliveriesBody.innerHTML = `<tr><td colspan="5" class="empty-row">${t("No deliveries yet. Find a buyer above to start one.")}</td></tr>`;
      } else {
        deliveriesBody.innerHTML = mine.map((n) => {
          const next = NEXT_STATUS[n.status];
          const action = next
            ? `<button class="btn btn-quiet" data-id="${n.id}" data-status="${next}" type="button">${MARK_AS[next]}</button>`
            : "";
          const route = next && n.buyerLatitude != null
            ? `<button class="btn btn-quiet" data-trip="${n.id}" type="button">${t("Map")}</button>`
            : "";
          return `
            <tr>
              <td data-label="${t("Buyer")}">${escapeHtml(n.buyerName)}</td>
              <td data-label="${t("Material")}">${escapeHtml(materialName(n.materialName))}</td>
              <td data-label="${t("Status")}">${statusPill(n.status)}</td>
              <td data-label="${t("Sent")}">${formatDate(n.createdAt)}</td>
              <td><div class="row-actions">${route}${action}
                <a class="btn btn-quiet" href="chat.html?with=${n.buyerId}">${t("Message")}</a></div></td>
            </tr>`;
        }).join("");
      }

      activeDeliveryIds = mine.filter((n) => n.status === "in transit").map((n) => n.id);
      showTrip(chooseTrip(mine));
      updateLocationSharing();
    } catch (err) {
      deliveriesBody.innerHTML = `<tr><td colspan="5" class="empty-row">${t("Deliveries could not be loaded.")}</td></tr>`;
    }
  }

  deliveriesBody.addEventListener("click", async (event) => {
    const mapButton = event.target.closest("button[data-trip]");
    if (mapButton) {
      guideTo(mapButton.dataset.trip);
      await loadDeliveries();
      tripPanel.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
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
        showMessage(pageMsg, data.message || t("Status not updated."), "error");
      }
      loadDeliveries();
    } catch (err) {
      serverError();
      button.disabled = false;
    }
  });

  // ---- Sales: the purchases buyers recorded, with their receipts ----

  const salesBody = document.getElementById("salesBody");

  async function loadSales() {
    try {
      const response = await authFetch("/seller/sales");
      const data = await readJson(response);
      if (!response.ok) throw new Error(data.message);
      const rows = data.sales || [];
      salesBody.innerHTML = rows.length
        ? rows.map((row) => `
            <tr>
              <td data-label="${t("Buyer")}">${escapeHtml(row.buyerName)}</td>
              <td data-label="${t("Material")}">${escapeHtml(materialName(row.materialName))}</td>
              <td data-label="${t("Weight")}">${AfriI18n.formatUnit(row.weightKg, "kilogram", 2)}</td>
              <td data-label="${t("Total")}"><strong>${formatMoney(row.totalAmount)}</strong></td>
              <td data-label="${t("Date")}">${formatDate(row.createdAt)}</td>
              <td data-label="${t("Receipt")}">${AfriReceipt.button(row.id, row.photoCount)}</td>
            </tr>`).join("")
        : `<tr><td colspan="6" class="empty-row">${t("No sales recorded yet.")}</td></tr>`;
    } catch (err) {
      salesBody.innerHTML = `<tr><td colspan="6" class="empty-row">${t("Sales could not be loaded.")}</td></tr>`;
    }
  }

  checkAccount();
  loadMaterials().catch(() => {
    showMessage(pageMsg, t("Can't reach the server. Check your connection, then reload the page."), "error");
  });
  loadDeliveries();
  loadSales();
  setInterval(shareLocation, LOCATION_PING_MS);
  setInterval(loadDeliveries, 30000);
  setInterval(loadSales, 60000); // a buyer may record the purchase a little after the delivery
});
