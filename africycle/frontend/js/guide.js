// The voice guide: Africycle spoken aloud, for people who can't read (or would rather
// listen), in the language chosen in the language menu. Every page loads it.
//
// - The speaker button (bottom corner, on every page) opens the guide and says what the
//   part of the screen in view is for and what to do there. Parts of a page are marked
//   in the HTML with data-guide="<stage>"; GUIDES below has what is said for each.
// - "Hear before you tap": the first touch on anything says what it is (a button, a box
//   to fill in, a price, a message...); a second touch on a button uses it. Menus open
//   as a spoken list of big choices. When a new part appears (a trip to a buyer, a
//   receipt), it is said straight away.
//
// Where the voice comes from, best first:
//   1. A recording of that sentence in that language, made by the team in the studio on
//      the admin page (backend/routes/guide_routes.py). Phones have no voice for many of
//      Africa's languages, so this is how Fulfulde, Sango or Lingala are heard.
//   2. The phone's own voice for the language (Android's speech service has English,
//      French, Arabic, Spanish, Portuguese, Chinese, Swahili, Afrikaans, Amharic, Hausa).
//      Pidgin is read by an English voice: its words are English-based.
//   3. Otherwise, a language the person understands, chosen under Voice in the guide
//      (by default one of the phone's languages, or French, or English).

const AfriGuide = (function () {
  const PREFS_KEY = "africycle_guide";
  const STAND_IN_VOICES = { wes: "en" };
  const ARMED_FOR_MS = 8000; // a second touch within 8 seconds uses the button
  const NO_VOICE = "none";

  // Each text below is written t("English") so the translation tools find it, but kept
  // in English here: recordings are looked up by the English text, then the guide says
  // it in the person's language (AfriI18n.t).
  const english = (text) => text;

  // What is said for each part of a page (data-guide="...")
  const GUIDES = ((t) => ({
    "landing": () => t("Welcome to Africycle. It helps you sell your scrap, water or organic waste to the buyer who pays the best price near you. If you have an account, touch the green button, Log in. If you are new, touch Create an account."),
    "login": () => t("Log in. Choose your country and type your phone number. Choose who you are: seller, buyer or parent. Type your password, then touch the green button, Log in."),
    "register": () => t("Create your account. Type your name, choose your country and type your phone number. If you are under 18, tick the box and give your parent's details. Choose what you will do, type a password twice, then touch Create account."),
    "seller.page": () => t("Your selling page: find a buyer, your deliveries and your sales."),
    "seller.find": () => t("Find a buyer. Choose the material you are carrying, then touch the green button, Find buyers. The buyers near you appear on the map and in the list, the best price first. Touch a buyer to see their prices."),
    "seller.buyer": () => t("This buyer's prices and photos. Touch the photo of your material to tell the buyer you are coming with it. You can also call the buyer or send a message."),
    "seller.trip": () => t("Your trip to the buyer. The map shows the way. When you set off, touch I'm leaving now. When you get there, touch I've arrived. You can also call the buyer or send a message."),
    "seller.deliveries": () => t("Your deliveries: each buyer you told you were coming, and how far each delivery has gone."),
    "seller.sales": () => t("Your sales: what buyers recorded buying from you. Touch Receipt to see the weight, the price, the total and the photos."),
    "buyer.page": () => t("Your buying page: your buying point, your prices, the collectors coming, recording a purchase, and your purchases."),
    "buyer.location": () => t("Your buying point. Stand where you buy, then touch the green button to save your location, so collectors near you can find you."),
    "buyer.prices": () => t("Your prices. Choose a material, type your price for one kilo, then touch Save price. Then add a photo of the material: collectors touch it to tell you they are coming."),
    "buyer.incoming": () => t("Collectors coming to you. The map shows where they are. When a collector has arrived and you have weighed the material, touch Record purchase."),
    "buyer.record": () => t("Record a purchase. Choose the collector and the material. Type the weight in kilos and the price for one kilo. Touch Take a photo to add pictures of what you bought. Then touch Record purchase."),
    "buyer.history": () => t("Your purchases. Touch Receipt to see a receipt and its photos, or to add a photo."),
    "receipt.buyer": () => t("This is the receipt: who sold, what, how many kilos, the price per kilo and the total paid. Below are the photos of the material. Touch Take a photo to add one."),
    "receipt.view": () => t("This is the receipt: who sold, what, how many kilos, the price per kilo and the total paid. Below are the photos the buyer took of the material."),
    "chat.list": () => t("Your conversations. Touch a name to open the conversation."),
    "chat.thread": () => t("The conversation. The newest message is at the bottom. Write your message in the box, then touch Send."),
    "guardian.page": () => t("Your children's accounts. Approve your child's account, then follow their deliveries, sales and messages."),
    "guardian.pending": () => t("Children waiting for your approval. Approve only a child you are responsible for."),
    "guardian.children": () => t("Your child's activity: deliveries, sales with their receipts, and messages."),
    "admin.page": () => t("The platform overview: the number of users and purchases, and the accounts to check."),
    "admin.recordings": () => t("The voice guide studio. Choose a language. For each sentence, touch Record and say it in that language, then touch Stop, listen, and touch Save."),
    "offline": () => t("You are offline. Africycle needs the internet. Check your mobile data or Wi-Fi, then touch Try again."),
    "picker": () => t("Touch a choice once to hear it. Touch it again to choose it.")
  }))(english);

  // What the guide itself says
  const SAY = ((t) => ({
    anyTime: t("Touch the speaker button at any time to hear about the part of the page you are looking at."),
    tapOn: t("Hear before you tap is on. Touch anything once to hear it. Touch a button a second time to use it."),
    tapOff: t("Hear before you tap is off. Buttons work with one touch again."),
    tapHint: t("To hear each button before you use it, turn on Hear before you tap."),
    slowOn: t("I will speak slowly."),
    slowOff: t("I will speak at the normal speed."),
    again: t("Touch it again to use it."),
    noVoice: t("There is no voice for this language on this phone yet. Choose a language you understand under Voice."),
    ticked: t("Ticked"),
    notTicked: t("Not ticked"),
    chosen: t("Chosen: {choice}")
  }))(english);

  // Buttons and words worth recording in every language, after the sentences above: what
  // people touch most. Material names are said in the spoken list of materials.
  const LABELS = ((t) => [
    t("Log in"), t("Create an account"), t("Create account"), t("Find buyers"), t("Tell this buyer I'm coming"),
    t("I'm leaving now"), t("I've arrived"), t("Call"), t("Message"), t("Messages"), t("Send"),
    t("Save price"), t("Record purchase"), t("Take a photo"), t("Receipt"), t("Log out"), t("Language"),
    t("Material"), t("Close"), t("Scrap Iron"), t("Plastic"), t("Water Bidon"), t("Organic Waste")
  ])(english);

  // ---- Preferences (kept on this phone) ----

  const prefs = { tap: false, slow: false, listen: "", opened: false };
  try {
    Object.assign(prefs, JSON.parse(localStorage.getItem(PREFS_KEY) || "{}"));
  } catch (err) {
    // storage blocked: the defaults, for this page only
  }
  function savePrefs() {
    try {
      localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
    } catch (err) {
      // not remembered next time
    }
  }

  const language = AfriI18n.language;
  const fileBase = window.location.protocol === "file:" ? "" : "/";

  // ---- Voices: recordings, the phone's own voices ----

  const synth = window.speechSynthesis || null;
  let voices = [];
  function loadVoices() {
    try {
      voices = synth ? synth.getVoices() : [];
    } catch (err) {
      voices = [];
    }
  }
  loadVoices();
  if (synth && "onvoiceschanged" in synth) synth.addEventListener("voiceschanged", loadVoices);
  // Chrome lists its voices a moment after the page opens
  const voicesReady = new Promise((resolve) => {
    if (voices.length || !synth) {
      resolve();
      return;
    }
    const done = () => {
      loadVoices();
      resolve();
    };
    if ("onvoiceschanged" in synth) synth.addEventListener("voiceschanged", done, { once: true });
    setTimeout(done, 1500);
  });

  function baseOf(tag) {
    return String(tag || "").toLowerCase().replace("_", "-").split("-")[0];
  }

  // The phone's voice for a language: its own, or Pidgin's stand-in; null when it has none.
  // Chinese is read in Mandarin (the translation is in simplified characters).
  function voiceFor(code) {
    const wanted = STAND_IN_VOICES[code] || code;
    const matching = voices.filter((voice) => {
      const base = baseOf(voice.lang);
      return base === wanted || (wanted === "zh" && base === "cmn");
    });
    if (wanted === "zh") {
      const mandarin = matching.filter((voice) => !/hk|yue/i.test(voice.lang));
      return mandarin.find((voice) => /cn|hans/i.test(voice.lang)) || mandarin[0] || null;
    }
    return matching.find((voice) => voice.localService) || matching[0] || null;
  }

  const recorded = {}; // language -> Promise of Map(English text -> audio address)
  function recordingsFor(code) {
    if (!recorded[code]) {
      const probe = document.createElement("audio");
      recorded[code] = fetch(`${fileBase}guide/recordings/${code}`)
        .then((response) => (response.ok ? response.json() : { recordings: [] }))
        .then((data) => new Map((data.recordings || [])
          .filter((item) => probe.canPlayType && probe.canPlayType(item.mimeType) !== "")
          .map((item) => [item.text, `${fileBase}guide/audio/${item.id}`])))
        .catch(() => new Map()); // offline: the phone's voices still work
    }
    return recorded[code];
  }

  let recordedLanguages = null; // Promise of { code: number of recordings }
  function languagesWithRecordings() {
    if (!recordedLanguages) {
      recordedLanguages = fetch(`${fileBase}guide/recorded-languages`)
        .then((response) => (response.ok ? response.json() : {}))
        .then((data) => data.languages || {})
        .catch(() => ({}));
    }
    return recordedLanguages;
  }

  // Other languages' translations, for the language the person chose to listen in
  const catalogs = {};
  function catalogFor(code) {
    if (code === "en") return Promise.resolve({});
    if (!catalogs[code]) {
      catalogs[code] = fetch(`${fileBase}i18n/${code}.json`)
        .then((response) => (response.ok ? response.json() : {}))
        .catch(() => ({}));
    }
    return catalogs[code];
  }

  function languageName(code) {
    const item = AfriI18n.LANGUAGES.find((entry) => entry.code === code);
    return item ? item.name : code;
  }

  // The language to listen in when the page's own language has no voice: the one chosen
  // under Voice, else the phone's own language, else French, else English
  function listeningLanguage() {
    const candidates = [prefs.listen]
      .concat(Array.from(navigator.languages || [navigator.language || ""], baseOf))
      .concat(["fr", "en"]);
    return candidates.find((code) => code && code !== language && voiceFor(code)) || "";
  }

  // ---- Speaking ----

  let turn = 0; // each new thing said cancels the one before
  let audio = null;
  let captionEl = null;
  let fab = null;

  function stop() {
    turn += 1;
    if (synth) synth.cancel();
    if (audio) {
      audio.pause();
      audio = null;
    }
    if (fab) fab.classList.remove("guide-fab-speaking");
  }

  function play(url, myTurn) {
    return new Promise((resolve) => {
      if (myTurn !== turn) {
        resolve("stopped");
        return;
      }
      const sound = new Audio(url);
      audio = sound;
      sound.playbackRate = prefs.slow ? 0.85 : 1;
      sound.onended = () => resolve("done");
      sound.onerror = () => resolve("failed");
      const started = sound.play();
      if (started && started.catch) {
        started.catch((err) => resolve(err && err.name === "NotAllowedError" ? "blocked" : "failed"));
      }
    });
  }

  // Sentence by sentence: some phones stop a long text half-way
  function sentences(text) {
    return String(text).match(/[^.!?。！？]+[.!?。！？]*\s*/g) || [String(text)];
  }

  function utter(text, voice, myTurn) {
    return new Promise((resolve) => {
      if (myTurn !== turn) {
        resolve("stopped");
        return;
      }
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.voice = voice;
      utterance.lang = voice.lang;
      utterance.rate = prefs.slow ? 0.75 : 0.95;
      let finished = false;
      const finish = (result) => {
        if (!finished) {
          finished = true;
          resolve(result);
        }
      };
      utterance.onend = () => finish("done");
      utterance.onerror = (event) => {
        const kind = event && event.error;
        finish(kind === "not-allowed" ? "blocked" : (kind === "interrupted" || kind === "canceled") ? "stopped" : "failed");
      };
      synth.speak(utterance);
      // Some phones never say they finished: move on after a generous time
      setTimeout(() => finish("done"), 3000 + text.length * (prefs.slow ? 160 : 120));
    });
  }

  async function sayWithVoice(text, voice, myTurn) {
    for (const part of sentences(text)) {
      const result = await utter(part.trim(), voice, myTurn);
      if (result !== "done") return result;
    }
    return "done";
  }

  function showCaption(text, inLanguage) {
    if (!captionEl) return;
    captionEl.textContent = text;
    captionEl.lang = inLanguage;
    captionEl.dir = inLanguage === "ar" ? "rtl" : "auto";
    captionEl.hidden = !text;
  }

  // One thing to say: { key } an English text (said in the person's language, recorded
  // when possible), or { text } already in their language (a name, a price, a message)
  async function sayOne(part, myTurn) {
    const key = part.key || null;
    const text = part.text != null ? part.text : AfriI18n.t(key, part.values);
    if (!text) return "done";
    if (key && !part.values) {
      const recording = (await recordingsFor(language)).get(key);
      if (recording) {
        showCaption(text, language);
        const result = await play(recording, myTurn);
        if (result !== "failed") return result;
      }
    }
    await voicesReady;
    const own = voiceFor(language);
    if (own) {
      showCaption(text, language);
      return sayWithVoice(text, own, myTurn);
    }
    // No voice for this language on this phone: say it in the language chosen to listen in
    const other = listeningLanguage();
    if (!other) return NO_VOICE;
    let otherText = text;
    if (key) {
      const catalog = await catalogFor(other);
      otherText = (catalog[key] || key);
      if (part.values) {
        otherText = otherText.replace(/\{(\w+)\}/g, (whole, name) => (name in part.values ? part.values[name] : whole));
      }
      const recording = !part.values && (await recordingsFor(other)).get(key);
      if (recording) {
        showCaption(otherText, other);
        const result = await play(recording, myTurn);
        if (result !== "failed") return result;
      }
    }
    showCaption(otherText, other);
    return sayWithVoice(otherText, voiceFor(other), myTurn);
  }

  // Says the parts one after the other. Resolves with "done", "stopped", "blocked" (the
  // browser wants a touch first) or NO_VOICE.
  async function say(parts) {
    stop();
    const myTurn = turn;
    if (fab) fab.classList.add("guide-fab-speaking");
    let result = "done";
    for (const part of parts) {
      if (myTurn !== turn) return "stopped";
      result = await sayOne(part, myTurn);
      if (result === "blocked" || result === NO_VOICE || result === "stopped") break;
    }
    if (myTurn === turn && fab) fab.classList.remove("guide-fab-speaking");
    if (result === NO_VOICE) {
      // Nothing can be heard: show why, and where to choose a voice
      openPanel();
      showCaption(AfriI18n.t(SAY.noVoice), language);
    }
    if (result === "blocked" && fab) fab.classList.add("guide-fab-waiting");
    return result;
  }

  // ---- What is on screen ----

  function visible(element) {
    if (!element || element.closest("[hidden]")) return false;
    const box = element.getBoundingClientRect();
    return box.width > 0 && box.height > 0;
  }

  function areaInView(element) {
    const box = element.getBoundingClientRect();
    const width = Math.min(box.right, window.innerWidth) - Math.max(box.left, 0);
    const height = Math.min(box.bottom, window.innerHeight) - Math.max(box.top, 0);
    return width > 0 && height > 0 ? width * height : 0;
  }

  // The part of the page to talk about: an open window first (the spoken list, a receipt,
  // a buyer's details), else the part taking up most of the screen
  function currentStage() {
    const stages = Array.from(document.querySelectorAll("[data-guide]")).filter(visible);
    const open = stages.filter((element) => element.closest(".modal-overlay, .guide-picker"));
    if (open.length) return open[open.length - 1];
    let best = null;
    let bestArea = 0;
    stages.forEach((element) => {
      if (element.tagName === "MAIN" && stages.length > 1) return; // the page's intro is said separately
      const area = areaInView(element);
      if (area > bestArea) {
        best = element;
        bestArea = area;
      }
    });
    return best;
  }

  function guideFor(element) {
    const make = element && GUIDES[element.dataset.guide];
    return make ? { key: make() } : null;
  }

  let introduced = false; // the page's intro, said with the first explanation on each page

  function explainScreen() {
    const parts = [];
    const stage = currentStage();
    const intro = document.querySelector("main[data-guide]");
    if (!introduced && intro && intro !== stage && visible(intro)) parts.push(guideFor(intro));
    introduced = true;
    if (stage) parts.push(guideFor(stage));
    if (!prefs.tap && !sessionFlag("tapHint")) parts.push({ key: SAY.tapHint });
    if (!sessionFlag("anyTime")) parts.push({ key: SAY.anyTime });
    return say(parts.filter(Boolean));
  }

  // Said once per visit, not on every page
  function sessionFlag(name) {
    try {
      const key = `${PREFS_KEY}_${name}`;
      if (sessionStorage.getItem(key)) return true;
      sessionStorage.setItem(key, "1");
    } catch (err) {
      // said each time instead
    }
    return false;
  }

  // ---- What a touched thing is ----

  const CONTROLS = "a[href], button, input, select, textarea, summary, label, [role='button'], [role='switch']";
  const TEXTS = "td, th, li, p, h1, h2, h3, h4, dt, dd, legend, figcaption, .bubble, .stat, .status, .badge, .trip-next, .modal-meta, .map-status";

  function clean(text) {
    return String(text || "").replace(/\s+/g, " ").trim();
  }

  // An English key for text shown in the page's language, so recordings can say it
  function part(text) {
    const shown = clean(text);
    if (!shown) return null;
    const key = AfriI18n.englishOf(shown);
    return key ? { key } : { text: shown };
  }

  function labelOf(control) {
    if (control.getAttribute("aria-label")) return control.getAttribute("aria-label");
    if (control.labels && control.labels.length) return control.labels[0].textContent;
    if (control.id) {
      const label = document.querySelector(`label[for="${control.id}"]`);
      if (label) return label.textContent;
    }
    const container = control.closest("label");
    if (container) return container.textContent;
    return control.getAttribute("placeholder") || control.getAttribute("title") || "";
  }

  function describe(element) {
    const parts = [];
    if (element.tagName === "LABEL" && element.control) {
      return describe(element.control);
    }
    if (element.tagName === "SELECT") {
      parts.push(part(labelOf(element)));
      const chosen = element.selectedOptions && element.selectedOptions[0];
      if (chosen && chosen.value) parts.push(part(chosen.textContent));
      return parts.filter(Boolean);
    }
    if (element.tagName === "INPUT" || element.tagName === "TEXTAREA") {
      parts.push(part(labelOf(element)));
      if (element.type === "checkbox" || element.type === "radio") {
        parts.push({ key: element.checked ? SAY.ticked : SAY.notTicked });
      } else if (element.type !== "password" && element.value) {
        parts.push({ text: element.value });
      }
      return parts.filter(Boolean);
    }
    const name = element.getAttribute("aria-label") || element.textContent ||
      (element.querySelector("img[alt]") && element.querySelector("img[alt]").alt) || element.getAttribute("title");
    return [part(name)].filter(Boolean);
  }

  function describeText(element) {
    if (element.tagName === "TD" && element.dataset.label) {
      return [part(element.dataset.label), { text: clean(element.textContent) }];
    }
    if (element.tagName === "TR") {
      return Array.from(element.cells).map((cell) => describeText(cell)).flat();
    }
    return [part(element.textContent)].filter(Boolean);
  }

  // ---- Hear before you tap ----

  let armed = null;
  let armedAt = 0;
  let armedTimes = 0; // "touch it again to use it" is said the first few times only

  function arm(element) {
    disarm();
    armed = element;
    armedAt = Date.now();
    element.classList.add("guide-armed");
  }

  function disarm() {
    if (armed) armed.classList.remove("guide-armed");
    armed = null;
  }

  function inGuide(element) {
    return Boolean(element.closest(".guide-ui"));
  }

  // The menu (select) under the touch: in this mode menus don't take touches themselves
  // (css), so the touch lands on what holds them
  function selectAt(event, target) {
    if (target.tagName === "SELECT") return target;
    if (target.tagName === "LABEL" && target.control && target.control.tagName === "SELECT") return target.control;
    const x = event.clientX;
    const y = event.clientY;
    return Array.from(target.querySelectorAll("select")).find((select) => {
      const box = select.getBoundingClientRect();
      return x >= box.left && x <= box.right && y >= box.top && y <= box.bottom;
    }) || null;
  }

  function onTouch(event) {
    if (!prefs.tap || !event.isTrusted) return;
    const target = event.target;
    if (!(target instanceof Element) || inGuide(target) || target.closest(".leaflet-container")) return;

    const select = selectAt(event, target);
    if (select && !select.disabled) {
      event.preventDefault();
      event.stopImmediatePropagation();
      openPicker(select);
      return;
    }

    const control = target.closest(CONTROLS);
    if (control && !control.disabled) {
      const type = control.tagName === "INPUT" ? control.type : "";
      if ((control.tagName === "INPUT" && !["checkbox", "radio", "submit", "button", "reset", "file"].includes(type)) ||
          control.tagName === "TEXTAREA") {
        return; // boxes to type in are said when they get the keyboard (focusin)
      }
      if (armed === control && Date.now() - armedAt < ARMED_FOR_MS) {
        // The second touch: let it do what it does
        disarm();
        if (control.tagName === "LABEL" && control.control) secondTouchFor = control.control;
        return;
      }
      if (secondTouchFor === control) {
        secondTouchFor = null; // the click a label passes on to its checkbox
        return;
      }
      event.preventDefault();
      event.stopImmediatePropagation();
      arm(control);
      const parts = describe(control);
      armedTimes += 1;
      if (armedTimes <= 3) parts.push({ key: SAY.again });
      say(parts);
      return;
    }

    const text = target.closest(TEXTS);
    if (text && !text.closest(".leaflet-container")) say(describeText(text));
  }
  let secondTouchFor = null;

  function onFocus(event) {
    if (!prefs.tap) return;
    const field = event.target;
    if (!(field instanceof Element) || inGuide(field)) return;
    const typing = (field.tagName === "INPUT" &&
      !["checkbox", "radio", "submit", "button", "reset", "file", "hidden"].includes(field.type)) ||
      field.tagName === "TEXTAREA";
    if (typing) say(describe(field));
  }

  // ---- The spoken list (menus) ----

  let picker = null;
  const MATERIAL_ICONS = {
    "Scrap Iron": '<path d="M12 2l8.66 5v10L12 22l-8.66-5V7z"/><circle cx="12" cy="12" r="3.5"/>',
    "Plastic": '<path d="M10 2h4v3l2 3v12a2 2 0 0 1-2 2h-4a2 2 0 0 1-2-2V8l2-3z"/><path d="M8 12h8"/>',
    "Water Bidon": '<path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z"/>',
    "Organic Waste": '<path d="M5 19c0-8 5-13 15-14-1 10-6 15-14 15"/><path d="M5 19l7-7"/>'
  };

  function optionIcon(option) {
    const key = AfriI18n.englishOf(clean(option.textContent)) || clean(option.textContent);
    const shape = MATERIAL_ICONS[key];
    return shape
      ? `<svg class="guide-option-icon" viewBox="0 0 24 24" width="28" height="28" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${shape}</svg>`
      : "";
  }

  function buildPicker() {
    picker = document.createElement("div");
    picker.className = "guide-picker guide-ui";
    picker.hidden = true;
    picker.innerHTML = `
      <div class="guide-picker-box" role="dialog" aria-modal="true" aria-labelledby="guidePickerTitle" data-guide="picker">
        <button class="guide-close" type="button" data-picker-close aria-label="${escapeText(t("Close"))}">&times;</button>
        <h3 id="guidePickerTitle"></h3>
        <div class="guide-options" role="listbox" aria-labelledby="guidePickerTitle"></div>
      </div>`;
    document.body.appendChild(picker);
    picker.addEventListener("click", (event) => {
      if (event.target === picker || event.target.closest("[data-picker-close]")) {
        closePicker();
        return;
      }
      const choice = event.target.closest(".guide-option");
      if (!choice) return;
      if (picker.armed === choice && Date.now() - picker.armedAt < ARMED_FOR_MS) {
        choose(choice);
        return;
      }
      picker.querySelectorAll(".guide-option").forEach((item) => item.classList.remove("guide-armed"));
      choice.classList.add("guide-armed");
      picker.armed = choice;
      picker.armedAt = Date.now();
      sayOption(choice);
    });
  }

  function escapeText(value) {
    const div = document.createElement("div");
    div.textContent = value == null ? "" : String(value);
    return div.innerHTML;
  }

  // A language in the list is said in its own voice when the phone has one
  function sayOption(choice) {
    const code = choice.dataset.lang;
    const voice = code && voiceFor(code);
    if (voice && code !== language) {
      stop();
      const myTurn = turn;
      showCaption(choice.textContent, code);
      sayWithVoice(clean(choice.textContent), voice, myTurn);
      return;
    }
    say([part(choice.textContent)].filter(Boolean));
  }

  let pickerFor = null; // the select, or a function given the chosen value

  function openPicker(select, title, options, onChoose) {
    if (!picker) buildPicker();
    disarm();
    pickerFor = onChoose || select;
    const list = options || Array.from(select.options)
      .filter((option) => !option.disabled && option.value !== "")
      .map((option) => ({ value: option.value, text: option.textContent, lang: option.lang, option }));
    const current = select ? select.value : null;
    picker.querySelector("#guidePickerTitle").textContent = clean(title || (select && labelOf(select)));
    picker.querySelector(".guide-options").innerHTML = list.map((item) => `
      <button type="button" class="guide-option" role="option" data-value="${escapeText(item.value)}"
        ${item.lang ? `data-lang="${escapeText(item.lang)}" lang="${escapeText(item.lang)}"` : ""}
        aria-selected="${item.value === current ? "true" : "false"}">
        ${item.option ? optionIcon(item.option) : ""}<span>${escapeText(clean(item.text))}</span>
      </button>`).join("");
    picker.armed = null;
    picker.hidden = false;
    const heading = select ? part(labelOf(select)) : (title ? { text: clean(title) } : null);
    say([heading, { key: GUIDES.picker() }].filter(Boolean));
  }

  function closePicker() {
    if (picker) picker.hidden = true;
    stop();
  }

  function choose(choice) {
    const value = choice.dataset.value;
    const text = clean(choice.textContent);
    picker.hidden = true;
    if (typeof pickerFor === "function") {
      pickerFor(value);
    } else if (pickerFor) {
      pickerFor.value = value;
      pickerFor.dispatchEvent(new Event("input", { bubbles: true }));
      pickerFor.dispatchEvent(new Event("change", { bubbles: true }));
    }
    say([{ key: SAY.chosen, values: { choice: text } }]);
  }

  // ---- The guide's button and panel ----

  const ICONS = {
    speaker: '<path d="M11 5L6 9H2v6h4l5 4z"/><path d="M15.5 8.5a5 5 0 0 1 0 7"/><path d="M19 5a10 10 0 0 1 0 14"/>',
    play: '<path d="M7 4l13 8-13 8z"/>',
    stop: '<rect x="6" y="6" width="12" height="12" rx="1"/>',
    hand: '<path d="M9 11V5a1.5 1.5 0 0 1 3 0v6"/><path d="M12 10V3.5a1.5 1.5 0 0 1 3 0V11"/><path d="M15 10.5V6a1.5 1.5 0 0 1 3 0v8a7 7 0 0 1-7 7h-.5a6.5 6.5 0 0 1-5.6-3.2L3 14.2a1.5 1.5 0 0 1 2.6-1.5L9 16"/>',
    slow: '<path d="M4 16c0-4.4 3.6-8 8-8s8 3.6 8 8z"/><path d="M8 16l-1.5 3M16 16l1.5 3"/><path d="M20 14h1.5a1.5 1.5 0 0 0 0-3H20"/>',
    globe: '<circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>'
  };

  function icon(name, size = 24) {
    return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONS[name]}</svg>`;
  }

  let panel = null;

  function buildButton() {
    fab = document.createElement("button");
    fab.type = "button";
    fab.className = "guide-fab guide-ui";
    fab.setAttribute("aria-label", t("Voice guide"));
    fab.setAttribute("aria-expanded", "false");
    fab.innerHTML = icon("speaker", 30);
    if (!prefs.opened) fab.classList.add("guide-fab-hello");
    document.body.appendChild(fab);
    document.body.classList.add("has-guide");
    fab.addEventListener("click", () => {
      fab.classList.remove("guide-fab-hello", "guide-fab-waiting");
      if (!prefs.opened) {
        prefs.opened = true;
        savePrefs();
      }
      openPanel();
      explainScreen();
    });
  }

  function switchButton(action, iconName, label, on) {
    return `
      <button type="button" class="guide-switch-row" role="switch" aria-checked="${on}" data-guide-action="${action}">
        ${icon(iconName)}<span class="guide-row-text">${escapeText(label)}</span><span class="guide-switch" aria-hidden="true"></span>
      </button>`;
  }

  function buildPanel() {
    panel = document.createElement("div");
    panel.className = "guide-panel guide-ui";
    panel.id = "guidePanel";
    panel.hidden = true;
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-label", t("Voice guide"));
    panel.innerHTML = `
      <div class="guide-panel-head">
        <button type="button" class="guide-big" data-guide-action="listen">${icon("play", 28)}<span>${escapeText(t("Listen again"))}</span></button>
        <button type="button" class="guide-big" data-guide-action="stop">${icon("stop", 28)}<span>${escapeText(t("Stop"))}</span></button>
        <button type="button" class="guide-close" data-guide-action="close" aria-label="${escapeText(t("Close"))}">&times;</button>
      </div>
      ${switchButton("tap", "hand", t("Hear before you tap"), prefs.tap)}
      ${switchButton("slow", "slow", t("Speak slowly"), prefs.slow)}
      <button type="button" class="guide-switch-row guide-voice" data-guide-action="voice" hidden>
        ${icon("globe")}<span class="guide-row-text"></span>
      </button>
      <p class="guide-caption" aria-live="polite" hidden></p>`;
    document.body.appendChild(panel);
    captionEl = panel.querySelector(".guide-caption");
    panel.addEventListener("click", onPanel);
    updateVoiceRow();
  }

  async function updateVoiceRow() {
    await voicesReady;
    const row = panel.querySelector(".guide-voice");
    if (voiceFor(language)) {
      row.hidden = true;
      return;
    }
    const other = listeningLanguage();
    row.hidden = false;
    row.querySelector(".guide-row-text").textContent = t("Voice: {language}", { language: other ? languageName(other) : "-" });
  }

  function openPanel() {
    if (!panel) buildPanel();
    panel.hidden = false;
    fab.setAttribute("aria-expanded", "true");
  }

  function closePanel() {
    if (panel) panel.hidden = true;
    if (fab) fab.setAttribute("aria-expanded", "false");
    stop();
  }

  function setSwitch(action, on) {
    const button = panel && panel.querySelector(`[data-guide-action="${action}"]`);
    if (button) button.setAttribute("aria-checked", on ? "true" : "false");
  }

  function setTap(on) {
    prefs.tap = on;
    savePrefs();
    document.documentElement.classList.toggle("guide-tap", on);
    setSwitch("tap", on);
    disarm();
  }

  async function chooseVoice() {
    const counts = await languagesWithRecordings();
    const choices = AfriI18n.LANGUAGES
      .filter((item) => item.code !== language && (voiceFor(item.code) || counts[item.code]))
      .map((item) => ({ value: item.code, text: item.name, lang: item.code }));
    openPicker(null, t("Voice"), choices, (code) => {
      prefs.listen = code;
      savePrefs();
      updateVoiceRow();
    });
  }

  function onPanel(event) {
    const button = event.target.closest("[data-guide-action]");
    if (!button) return;
    const action = button.dataset.guideAction;
    if (action === "listen") {
      fab.classList.remove("guide-fab-waiting");
      explainScreen();
    } else if (action === "stop") {
      stop();
    } else if (action === "close") {
      closePanel();
    } else if (action === "tap") {
      setTap(!prefs.tap);
      say([{ key: prefs.tap ? SAY.tapOn : SAY.tapOff }]);
    } else if (action === "slow") {
      prefs.slow = !prefs.slow;
      savePrefs();
      setSwitch("slow", prefs.slow);
      say([{ key: prefs.slow ? SAY.slowOn : SAY.slowOff }]);
    } else if (action === "voice") {
      chooseVoice();
    }
  }

  // ---- New parts of the page, said as they appear ----

  let watching = false;
  function watchStages() {
    let pending = null;
    const observer = new MutationObserver((changes) => {
      if (!prefs.tap || !watching) return;
      for (const change of changes) {
        const element = change.target;
        if (!(element instanceof Element) || element.hidden || inGuide(element)) continue;
        const stage = element.matches("[data-guide]") ? element : element.querySelector("[data-guide]");
        if (stage && stage.tagName !== "MAIN" && visible(stage)) {
          clearTimeout(pending);
          pending = setTimeout(() => say([guideFor(stage)].filter(Boolean)), 300);
          return;
        }
      }
    });
    observer.observe(document.body, { attributes: true, attributeFilter: ["hidden"], subtree: true });
  }

  // ---- Start ----

  function start() {
    buildButton();
    document.documentElement.classList.toggle("guide-tap", prefs.tap);
    document.addEventListener("click", onTouch, true);
    document.addEventListener("focusin", onFocus, true);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        if (picker && !picker.hidden) closePicker();
        else if (panel && !panel.hidden) closePanel();
      }
    });
    watchStages();
    recordingsFor(language); // ready before the first touch
    // With Hear before you tap on, each page explains itself as it opens. Browsers may
    // want a touch first: the speaker button then waits, ringing.
    if (prefs.tap) {
      setTimeout(async () => {
        const result = await explainScreen();
        if (result === "blocked") introduced = false;
        watching = true;
      }, 700);
    } else {
      watching = true;
    }
  }

  AfriI18n.whenReady(start);

  return {
    say: (keys) => say(keys.map((key) => ({ key }))),
    stop,
    explainScreen,
    openPicker,
    sentences: () => Object.keys(GUIDES).map((stage) => GUIDES[stage]())
      .concat(Object.keys(SAY).map((name) => SAY[name]), LABELS),
    voiceFor,
    hasVoice: (code) => Boolean(voiceFor(code)),
    voicesReady
  };
})();
