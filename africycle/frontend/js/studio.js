// The voice guide studio, on the admin page: record each sentence of the voice guide in
// a language, so that everyone using Africycle in that language hears a real voice
// (most phones have no voice for Fulfulde, Sango, Lingala and many other languages).
// Recordings are saved on the server (backend/routes/guide_routes.py); js/guide.js plays
// them. The sentences are the guide's own: AfriGuide.sentences().

AfriI18n.whenReady(function () {
  const languageSelect = document.getElementById("studioLanguage");
  const list = document.getElementById("studioList");
  const progress = document.getElementById("studioProgress");
  const studioMsg = document.getElementById("studioMsg");
  if (!languageSelect || typeof AfriGuide === "undefined") return;

  const MAX_SECONDS = 30;
  const FORMATS = ["audio/webm;codecs=opus", "audio/ogg;codecs=opus", "audio/mp4", "audio/webm"];
  const sentences = Array.from(new Set(AfriGuide.sentences()));
  let recordings = new Map(); // English sentence -> { id }
  let recorder = null; // { item, mediaRecorder, stream, chunks, timer }
  const takes = new Map(); // English sentence -> Blob recorded, not saved yet

  AfriI18n.LANGUAGES.forEach((item) => {
    const option = new Option(item.name, item.code);
    option.lang = item.code;
    languageSelect.add(option);
  });
  languageSelect.value = AfriI18n.language;

  function catalog(code) {
    if (code === "en") return Promise.resolve({});
    return fetch(`/i18n/${code}.json`).then((response) => (response.ok ? response.json() : {})).catch(() => ({}));
  }

  async function loadRecordings(code) {
    const response = await fetch(`/guide/recordings/${code}`, { cache: "no-cache" });
    const data = await readJson(response);
    return new Map((data.recordings || []).map((item) => [item.text, item]));
  }

  function statusFor(text) {
    return recordings.has(text)
      ? `<span class="status status-completed">${escapeHtml(t("Recorded"))}</span>`
      : `<span class="status status-pending">${escapeHtml(t("Not recorded yet"))}</span>`;
  }

  function showProgress() {
    progress.textContent = t("{done} of {total} sentences recorded", {
      done: AfriI18n.formatNumber(sentences.filter((text) => recordings.has(text)).length),
      total: AfriI18n.formatNumber(sentences.length)
    });
  }

  function buttons(text) {
    const recorded = recordings.has(text);
    const take = takes.has(text);
    return `
      ${statusFor(text)}
      <button class="btn btn-secondary" type="button" data-studio="record">${escapeHtml(t("Record"))}</button>
      <button class="btn btn-primary" type="button" data-studio="stop" hidden>${escapeHtml(t("Stop"))}</button>
      <button class="btn btn-quiet" type="button" data-studio="listen" ${recorded || take ? "" : "hidden"}>${escapeHtml(t("Listen"))}</button>
      <button class="btn btn-primary" type="button" data-studio="save" ${take ? "" : "hidden"}>${escapeHtml(t("Save"))}</button>
      <button class="btn btn-danger" type="button" data-studio="remove" ${recorded && !take ? "" : "hidden"}>${escapeHtml(t("Remove"))}</button>`;
  }

  async function show() {
    const code = languageSelect.value;
    list.innerHTML = `<li class="panel-hint">${escapeHtml(t("Loading..."))}</li>`;
    try {
      const [translations, recorded] = await Promise.all([catalog(code), loadRecordings(code)]);
      recordings = recorded;
      takes.clear();
      const dir = code === "ar" ? "rtl" : "ltr";
      list.innerHTML = sentences.map((text, index) => `
        <li class="studio-item" data-index="${index}">
          <p class="studio-sentence" lang="${code}" dir="${dir}">${escapeHtml(translations[text] || text)}</p>
          ${code === "en" ? "" : `<p class="studio-english" lang="en" dir="ltr">${escapeHtml(text)}</p>`}
          <div class="row-actions">${buttons(text)}</div>
        </li>`).join("");
      showProgress();
    } catch (err) {
      list.innerHTML = "";
      showMessage(studioMsg, t("Can't reach the server. Check your connection, then try again."), "error");
    }
  }

  function refreshItem(item) {
    item.querySelector(".row-actions").innerHTML = buttons(sentences[Number(item.dataset.index)]);
  }

  async function startRecording(item) {
    if (recorder) stopRecording();
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia || !window.MediaRecorder) {
      showMessage(studioMsg, t("This browser can't record sound. Use Chrome on a phone or computer."), "error");
      return;
    }
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (err) {
      showMessage(studioMsg, t("Allow the microphone to record."), "error");
      return;
    }
    const format = FORMATS.find((type) => MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(type));
    const mediaRecorder = format ? new MediaRecorder(stream, { mimeType: format, audioBitsPerSecond: 32000 }) : new MediaRecorder(stream);
    const chunks = [];
    mediaRecorder.ondataavailable = (event) => {
      if (event.data && event.data.size) chunks.push(event.data);
    };
    mediaRecorder.onstop = () => {
      stream.getTracks().forEach((track) => track.stop()); // the microphone light goes off
      const text = sentences[Number(item.dataset.index)];
      if (chunks.length) takes.set(text, new Blob(chunks, { type: mediaRecorder.mimeType || format || "audio/webm" }));
      item.classList.remove("studio-recording");
      refreshItem(item);
    };
    recorder = { item, mediaRecorder, timer: setTimeout(stopRecording, MAX_SECONDS * 1000) };
    AfriGuide.stop();
    mediaRecorder.start();
    item.classList.add("studio-recording");
    item.querySelector('[data-studio="record"]').hidden = true;
    item.querySelector('[data-studio="stop"]').hidden = false;
    showMessage(studioMsg, t("Recording... Touch Stop when you have finished."), "info");
  }

  function stopRecording() {
    if (!recorder) return;
    clearTimeout(recorder.timer);
    if (recorder.mediaRecorder.state !== "inactive") recorder.mediaRecorder.stop();
    recorder = null;
    studioMsg.hidden = true;
  }

  let playing = null;
  function listen(text) {
    if (playing) playing.pause();
    const take = takes.get(text);
    const url = take ? URL.createObjectURL(take) : `/guide/audio/${recordings.get(text).id}`;
    playing = new Audio(url);
    playing.play().catch(() => {});
  }

  function readAsDataUrl(blob) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(blob);
    });
  }

  async function save(item, text) {
    const take = takes.get(text);
    if (!take) return;
    try {
      const response = await authFetch("/admin/guide-recordings", {
        method: "POST",
        body: JSON.stringify({ language: languageSelect.value, text, audio: await readAsDataUrl(take) })
      });
      const data = await readJson(response);
      if (!response.ok) {
        showMessage(studioMsg, data.message || t("Recording not saved."), "error");
        return;
      }
      takes.delete(text);
      recordings.set(text, { id: data.id });
      showMessage(studioMsg, data.message || t("Recording saved"), "success");
      refreshItem(item);
      showProgress();
    } catch (err) {
      showMessage(studioMsg, t("Can't reach the server. Check your connection, then try again."), "error");
    }
  }

  async function remove(item, text) {
    try {
      const response = await authFetch(`/admin/guide-recordings/${recordings.get(text).id}`, { method: "DELETE" });
      const data = await readJson(response);
      if (!response.ok) {
        showMessage(studioMsg, data.message || t("Recording not found"), "error");
        return;
      }
      recordings.delete(text);
      showMessage(studioMsg, data.message || t("Recording removed"), "success");
      refreshItem(item);
      showProgress();
    } catch (err) {
      showMessage(studioMsg, t("Can't reach the server. Check your connection, then try again."), "error");
    }
  }

  list.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-studio]");
    if (!button) return;
    const item = button.closest(".studio-item");
    const text = sentences[Number(item.dataset.index)];
    const action = button.dataset.studio;
    if (action === "record") startRecording(item);
    else if (action === "stop") stopRecording();
    else if (action === "listen") listen(text);
    else if (action === "save") save(item, text);
    else if (action === "remove") remove(item, text);
  });

  languageSelect.addEventListener("change", () => {
    stopRecording();
    show();
  });

  show();
});
