// Receipts: a purchase a buyer recorded, with photos of the material. The buyer takes the
// photos when recording the purchase (or adds them later); the buyer, the seller, and an
// under-18 seller's parent or guardian can all open the receipt.
//
//   AfriReceipt.button(id, photoCount)  the "Receipt" button for a row of purchases or sales
//   AfriReceipt.open(id, onChange)      shows the receipt; onChange runs when photos change
//   AfriReceipt.takePhoto()             opens the camera; resolves with the photo, shrunk
//   AfriReceipt.shrinkPhoto(file, max)  a phone photo as a JPEG data URL of at most max bytes

const AfriReceipt = (function () {
  const PHOTO_BYTES = 190000; // a receipt keeps up to 3 photos: smaller than material photos
  const CAMERA_ICON = '<svg class="btn-icon" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/></svg>';
  const RECEIPT_ICON = '<svg class="btn-icon" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 2v20l3-2 3 2 2-2 2 2 3-2 3 2V2l-3 2-3-2-2 2-2-2-3 2z"/><path d="M8 9h8M8 13h8"/></svg>';

  // ---- Photos ----

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
  async function shrinkPhoto(file, maxBytes = PHOTO_BYTES) {
    const image = await readImage(file);
    let side = 1024;
    for (let attempt = 0; attempt < 6; attempt++) {
      const scale = Math.min(1, side / Math.max(image.naturalWidth, image.naturalHeight));
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
      canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
      canvas.getContext("2d").drawImage(image, 0, 0, canvas.width, canvas.height);
      const dataUrl = canvas.toDataURL("image/jpeg", 0.75);
      if ((dataUrl.length - dataUrl.indexOf(",") - 1) * 0.75 <= maxBytes) return dataUrl;
      side = Math.round(side * 0.75);
    }
    throw new Error("photo too large");
  }

  // The camera straight away (on a computer: choose a picture). Resolves with the shrunk
  // photo, or null when nothing was taken; rejects when the file isn't a photo.
  let cameraInput = null;
  function takePhoto() {
    if (!cameraInput) {
      cameraInput = document.createElement("input");
      cameraInput.type = "file";
      cameraInput.accept = "image/*";
      cameraInput.setAttribute("capture", "environment");
      cameraInput.hidden = true;
      document.body.appendChild(cameraInput);
    }
    return new Promise((resolve, reject) => {
      cameraInput.value = "";
      cameraInput.onchange = () => {
        const file = cameraInput.files[0];
        if (!file) {
          resolve(null);
          return;
        }
        shrinkPhoto(file).then(resolve, reject);
      };
      cameraInput.click();
    });
  }

  async function uploadPhoto(receiptId, photo) {
    try {
      const response = await authFetch(`/receipts/${receiptId}/photos`, {
        method: "POST",
        body: JSON.stringify({ photo })
      });
      const data = await readJson(response);
      return { ok: response.ok, message: data.message };
    } catch (err) {
      return { ok: false, message: t("Can't reach the server. Check your connection, then try again.") };
    }
  }

  // Receipt photos need the login token: fetched here, shown through blob: URLs
  const photoUrls = new Map();
  function showPhotos(container) {
    container.querySelectorAll("img[data-receipt-photo]").forEach((img) => {
      const id = img.dataset.receiptPhoto;
      if (!photoUrls.has(id)) {
        photoUrls.set(id, authFetch(`/receipt-photos/${id}`)
          .then((response) => (response.ok ? response.blob() : null))
          .then((blob) => (blob ? URL.createObjectURL(blob) : null))
          .catch(() => {
            photoUrls.delete(id);
            return null;
          }));
      }
      photoUrls.get(id).then((url) => {
        if (url) img.src = url;
      });
    });
  }

  // ---- The receipt ----

  function button(id, photoCount) {
    const photos = Number(photoCount) || 0;
    const name = photos > 0
      ? `${t("Receipt")}. ${t("Photos: {count}", { count: AfriI18n.formatNumber(photos) })}`
      : t("Receipt");
    const count = photos > 0
      ? `<span class="photo-count" aria-hidden="true">${CAMERA_ICON}${escapeHtml(AfriI18n.formatNumber(photos))}</span>`
      : "";
    return `<button class="btn btn-quiet receipt-btn" type="button" data-receipt="${Number(id)}" aria-label="${escapeHtml(name)}">${RECEIPT_ICON}<span aria-hidden="true">${escapeHtml(t("Receipt"))}</span>${count}</button>`;
  }

  let overlay = null;
  let current = null; // { id, receipt }
  let changed = null; // the page's function that reloads its list when photos change

  // The page's list to reload when the buyer adds or removes a photo
  function onChange(fn) {
    changed = fn;
  }

  function build() {
    overlay = document.createElement("div");
    overlay.className = "modal-overlay";
    overlay.id = "receiptModal";
    overlay.hidden = true;
    overlay.innerHTML = `
      <div class="modal-box receipt-box" role="dialog" aria-modal="true" aria-labelledby="receiptTitle" data-guide="receipt.view">
        <button class="modal-close" type="button" data-receipt-close aria-label="${escapeHtml(t("Close"))}">&times;</button>
        <h3 id="receiptTitle"></h3>
        <p class="modal-meta" id="receiptDate"></p>
        <dl class="receipt-lines" id="receiptLines"></dl>
        <h4 class="receipt-photos-heading">${escapeHtml(t("Photos of the material"))}</h4>
        <div class="photo-grid receipt-photos" id="receiptPhotos"></div>
        <p class="msg" id="receiptMsg" role="status" hidden></p>
        <div class="modal-actions">
          <button class="btn btn-primary btn-block" type="button" id="receiptCameraBtn" hidden>${CAMERA_ICON}<span>${escapeHtml(t("Take a photo"))}</span></button>
          <button class="btn btn-secondary btn-block" type="button" data-receipt-close>${escapeHtml(t("Close"))}</button>
        </div>
      </div>
      <div class="photo-viewer" id="receiptViewer" hidden>
        <img alt="">
        <button class="modal-close" type="button" aria-label="${escapeHtml(t("Close"))}">&times;</button>
      </div>`;
    document.body.appendChild(overlay);

    overlay.addEventListener("click", async (event) => {
      const viewer = overlay.querySelector("#receiptViewer");
      if (!viewer.hidden) {
        viewer.hidden = true;
        return;
      }
      if (event.target === overlay || event.target.closest("[data-receipt-close]")) {
        close();
        return;
      }
      const remove = event.target.closest("[data-remove-photo]");
      if (remove) {
        await removePhoto(Number(remove.dataset.removePhoto));
        return;
      }
      const photo = event.target.closest("img[data-receipt-photo]");
      if (photo && photo.src) {
        viewer.querySelector("img").src = photo.src;
        viewer.querySelector("img").alt = photo.alt;
        viewer.hidden = false;
        return;
      }
      if (event.target.closest("#receiptCameraBtn")) {
        await addPhoto();
      }
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && overlay && !overlay.hidden) close();
    });
  }

  function say(text, type) {
    const message = overlay.querySelector("#receiptMsg");
    if (!text) {
      message.hidden = true;
      return;
    }
    showMessage(message, text, type);
  }

  function line(label, value, extraClass) {
    return `<div class="${extraClass || ""}"><dt>${escapeHtml(label)}</dt><dd>${value}</dd></div>`;
  }

  function render(receipt) {
    const box = overlay.querySelector(".receipt-box");
    if (receipt.canAddPhotos) box.dataset.guide = "receipt.buyer";
    else box.dataset.guide = "receipt.view";
    overlay.querySelector("#receiptTitle").textContent = t("Receipt No. {number}", { number: receipt.id });
    overlay.querySelector("#receiptDate").textContent = formatDate(receipt.createdAt);
    overlay.querySelector("#receiptLines").innerHTML = [
      line(t("Buyer"), escapeHtml(receipt.buyerName)),
      line(t("Collector"), escapeHtml(receipt.sellerName)),
      line(t("Material"), escapeHtml(materialName(receipt.materialName))),
      line(t("Weight"), escapeHtml(AfriI18n.formatUnit(receipt.weightKg, "kilogram", 2))),
      line(t("Price per kg"), escapeHtml(formatMoney(receipt.pricePerKg))),
      line(t("Total paid in cash"), `<strong>${escapeHtml(formatMoney(receipt.totalAmount))}</strong>`, "receipt-total")
    ].join("");

    const photos = overlay.querySelector("#receiptPhotos");
    photos.innerHTML = receipt.photoIds.length
      ? receipt.photoIds.map((id, index) => `
          <figure class="receipt-photo">
            <img data-receipt-photo="${Number(id)}" alt="${escapeHtml(t("Photo {number} of the material", { number: index + 1 }))}">
            ${receipt.canAddPhotos ? `<button class="btn btn-quiet" type="button" data-remove-photo="${Number(id)}">${escapeHtml(t("Remove"))}</button>` : ""}
          </figure>`).join("")
      : `<p class="panel-hint">${escapeHtml(t("No photos yet."))}</p>`;
    showPhotos(photos);
    overlay.querySelector("#receiptCameraBtn").hidden =
      !receipt.canAddPhotos || receipt.photoIds.length >= receipt.maxPhotos;
  }

  async function load() {
    const response = await authFetch(`/receipts/${current.id}`);
    const data = await readJson(response);
    if (!response.ok) throw new Error(data.message || t("Receipt not found"));
    current.receipt = data.receipt;
    render(data.receipt);
  }

  async function open(id) {
    if (!overlay) build();
    current = { id: Number(id) };
    overlay.querySelector("#receiptTitle").textContent = t("Receipt No. {number}", { number: current.id });
    overlay.querySelector("#receiptLines").innerHTML = "";
    overlay.querySelector("#receiptPhotos").innerHTML = "";
    overlay.querySelector("#receiptCameraBtn").hidden = true;
    say(t("Loading..."), "info");
    overlay.hidden = false;
    document.body.classList.add("modal-open");
    try {
      await load();
      say("");
    } catch (err) {
      say(err.message && err.name !== "TypeError" ? err.message : t("Can't reach the server. Check your connection, then try again."), "error");
    }
  }

  function close() {
    if (!overlay) return;
    overlay.hidden = true;
    document.body.classList.remove("modal-open");
    current = null;
  }

  async function addPhoto() {
    const receiptId = current && current.id;
    let photo;
    try {
      photo = await takePhoto();
    } catch (err) {
      say(t("That file couldn't be read as a photo. Choose a JPG or PNG photo, or take a new one with the camera."), "error");
      return;
    }
    if (!photo || !current || current.id !== receiptId) return;
    say(t("Preparing your photo..."), "info");
    const result = await uploadPhoto(receiptId, photo);
    if (!result.ok) {
      say(result.message || t("Photo not saved."), "error");
      return;
    }
    await refresh(t("Photo saved"));
  }

  async function removePhoto(photoId) {
    try {
      const response = await authFetch(`/receipts/${current.id}/photos/${photoId}`, { method: "DELETE" });
      const data = await readJson(response);
      if (!response.ok) {
        say(data.message || t("Photo not removed."), "error");
        return;
      }
      await refresh(t("Photo removed"));
    } catch (err) {
      say(t("Can't reach the server. Check your connection, then try again."), "error");
    }
  }

  async function refresh(message) {
    try {
      await load();
      say(message, "success");
    } catch (err) {
      say(t("Can't reach the server. Check your connection, then try again."), "error");
    }
    if (changed) changed();
  }

  // Any page: a click on a Receipt button opens that receipt
  document.addEventListener("click", (event) => {
    const receiptButton = event.target.closest("button[data-receipt]");
    if (receiptButton) open(receiptButton.dataset.receipt);
  });

  return { button, open, close, onChange, takePhoto, shrinkPhoto, uploadPhoto, MAX_PHOTOS: 3, CAMERA_ICON };
})();
