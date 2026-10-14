// Africycle in the language each person reads best. Every page loads this first, in
// <head>. It picks the language: the one chosen before on this phone, else the phone's
// own language when Africycle has it, else English. Then it loads that language's
// translations and translates the page. Page scripts show their text with
// t("English text", { values }), and start once the translations are in
// (AfriI18n.whenReady).
//
// Translations live in frontend/i18n/<code>.json, keyed by the English text. The server
// reads the same files for its messages (backend/i18n.py). Text missing from a file
// shows in English. Every other language works through the browser's own Translate
// button; the language menu's last entry says how.

const AfriI18n = (function () {
  const STORAGE_KEY = "africycle_language";
  const WAIT_AT_MOST_MS = 4000; // then show the page anyway, in English where needed

  // Each language under its own name, so people find theirs in the menu. English and
  // French first (Cameroon's official languages), then A to Z, other scripts last.
  const LANGUAGES = [
    { code: "en", name: "English" },
    { code: "fr", name: "Français" },
    { code: "om", name: "Afaan Oromoo" },
    { code: "af", name: "Afrikaans" },
    { code: "es", name: "Español" },
    { code: "ff", name: "Fulfulde" },
    { code: "ha", name: "Hausa" },
    { code: "ig", name: "Igbo" },
    { code: "rw", name: "Ikinyarwanda" },
    { code: "rn", name: "Ikirundi" },
    { code: "zu", name: "isiZulu" },
    { code: "sw", name: "Kiswahili" },
    { code: "ln", name: "Lingála" },
    { code: "wes", name: "Pidgin (Kamtok)" },
    { code: "pt", name: "Português" },
    { code: "sg", name: "Sängö" },
    { code: "so", name: "Soomaali" },
    { code: "yo", name: "Yorùbá" },
    { code: "ar", name: "العربية", rtl: true },
    { code: "am", name: "አማርኛ" },
    { code: "zh", name: "中文" }
  ];

  // Other names phones use for these languages
  const ALIASES = {
    pcm: "wes", kin: "rw", run: "rn", ful: "ff", fub: "ff", fuv: "ff", fuf: "ff", ffm: "ff", amh: "am",
    hau: "ha", yor: "yo", ibo: "ig", swa: "sw", swh: "sw", lin: "ln", sag: "sg", som: "so", zul: "zu",
    afr: "af", orm: "om", gaz: "om", ara: "ar", por: "pt", spa: "es", fra: "fr", fre: "fr", eng: "en",
    zho: "zh", chi: "zh", cmn: "zh"
  };

  // Numbers, dates and units are written the language's own way, with everyday digits
  // (0-9), in the phone's region when it has one for that language ("fr-CM", "pt-AO").
  // Pidgin, Sango, Fulfulde, Lingala and Kirundi write them the way the English of
  // Cameroon and the French of the CAR, Cameroon, the DRC and Burundi do, and take their
  // words for "5 min ago" from their translations.
  const BORROWED_FORMATS = { wes: "en-CM", sg: "fr-CF", ff: "fr-CM", ln: "fr-CD", rn: "fr-BI" };
  const USUAL_REGIONS = { en: "en-CM", rw: "rw-RW" };

  function known(code) {
    return LANGUAGES.some((language) => language.code === code);
  }

  function phoneTags() {
    const tags = (navigator.languages && navigator.languages.length) ? navigator.languages : [navigator.language || "en"];
    return Array.from(tags, String);
  }

  function fromPhone() {
    for (const tag of phoneTags()) {
      const lower = tag.toLowerCase();
      const base = lower.split("-")[0];
      const code = ALIASES[lower] || ALIASES[base] || base;
      if (known(code)) return code;
    }
    return "en";
  }

  function saved() {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch (err) {
      return null;
    }
  }

  const language = known(saved()) ? saved() : fromPhone();
  const current = LANGUAGES.find((item) => item.code === language);
  const root = document.documentElement;
  root.lang = language;
  root.dir = current.rtl ? "rtl" : "ltr";
  let strings = {};

  function wait(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  const fileBase = window.location.protocol === "file:" ? "" : "/";
  const loaded = language === "en" ? Promise.resolve() : fetch(`${fileBase}i18n/${language}.json`)
    .then((response) => (response.ok ? response.json() : {}))
    .then((data) => { strings = data || {}; })
    .catch(() => {}); // offline before this language was ever saved: English
  if (language !== "en") root.classList.add("translating"); // css: hidden until translated

  const pageReady = new Promise((resolve) => {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", resolve);
    else resolve();
  });

  const RIGHT_TO_LEFT_LETTERS = /[\u0590-\u08ff\ufb1d-\ufdff\ufe70-\ufefc]/;

  // A name or number set inside a sentence keeps its own direction: "Jean" inside Arabic,
  // or an Arabic name inside English, without moving the punctuation around it
  function isolated(value) {
    const text = String(value);
    return current.rtl || RIGHT_TO_LEFT_LETTERS.test(text) ? `\u2068${text}\u2069` : text;
  }

  // "Hello {name}" with { name: "Awa" } -> "Hello Awa" (or the translation of it)
  function t(text, values) {
    const translated = (language !== "en" && strings[text]) || text;
    if (!values) return translated;
    return translated.replace(/\{(\w+)\}/g, (whole, name) => (name in values ? isolated(values[name]) : whole));
  }

  const ATTRIBUTES = ["placeholder", "aria-label", "title", "alt"];

  function skipped(element) {
    return !element || Boolean(element.closest("script, style, noscript, [translate='no']"));
  }

  // The page's own text, written in English in the HTML
  function translatePage() {
    document.title = t(document.title.replace(/\s+/g, " ").trim());
    if (language === "en") return;
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach((node) => {
      if (skipped(node.parentElement)) return;
      const key = node.nodeValue.replace(/\s+/g, " ").trim();
      const value = key && strings[key];
      if (value) {
        const space = node.nodeValue.match(/^\s*/)[0];
        const end = node.nodeValue.match(/\s*$/)[0];
        node.nodeValue = space + value + end;
      }
    });
    ATTRIBUTES.forEach((attribute) => {
      document.querySelectorAll(`[${attribute}]`).forEach((element) => {
        if (skipped(element)) return;
        const value = strings[element.getAttribute(attribute).trim()];
        if (value) element.setAttribute(attribute, value);
      });
    });
  }

  function choose(code) {
    try {
      localStorage.setItem(STORAGE_KEY, code);
    } catch (err) {
      // Not remembered on this browser: the phone's own language is used next time
    }
    window.location.reload();
  }

  function explainOtherLanguages() {
    if (document.getElementById("otherLanguagesNotice")) return;
    const box = document.createElement("div");
    box.id = "otherLanguagesNotice";
    box.className = "notice-bar";
    box.setAttribute("role", "status");
    const text = document.createElement("span");
    text.className = "notice-text";
    text.textContent = t("For any other language, use your browser's Translate. In Chrome, tap the menu (⋮), then Translate. In Safari, tap aA in the address bar, then Translate.");
    const close = document.createElement("button");
    close.type = "button";
    close.className = "btn btn-quiet";
    close.textContent = t("OK");
    close.addEventListener("click", () => box.remove());
    box.appendChild(text);
    box.appendChild(close);
    document.body.appendChild(box);
  }

  // Every <select data-language-menu> becomes the language menu
  function setUpMenus() {
    document.querySelectorAll("select[data-language-menu]").forEach((select) => {
      LANGUAGES.forEach((item) => {
        const option = new Option(item.name, item.code);
        option.lang = item.code;
        select.appendChild(option);
      });
      select.appendChild(new Option(t("Other languages..."), "other"));
      select.value = language;
      const label = select.parentElement && select.parentElement.querySelector(".language-code");
      if (label) label.textContent = language.toUpperCase();
      select.addEventListener("change", () => {
        if (select.value === "other") {
          select.value = language;
          explainOtherLanguages();
        } else if (select.value !== language) {
          choose(select.value);
        }
      });
    });
  }

  function show() {
    root.classList.remove("translating");
  }

  let shown = false;
  const ready = Promise.all([Promise.race([loaded, wait(WAIT_AT_MOST_MS)]), pageReady]).then(() => {
    try {
      translatePage();
      setUpMenus();
    } finally {
      show(); // whatever happens, never leave the page hidden
      shown = true;
    }
  });
  setTimeout(show, WAIT_AT_MOST_MS + 2000);
  // On a very slow connection the page shows in English first; translate what can be
  // translated once the file does arrive
  loaded.then(() => pageReady).then(() => {
    if (shown) translatePage();
  });

  // Runs fn once the page is translated (straight away on English pages)
  function whenReady(fn) {
    ready.then(fn);
  }

  function browserKnows(kind, tag) {
    try {
      return Intl[kind].supportedLocalesOf([tag]).length > 0;
    } catch (err) {
      return false;
    }
  }

  const FORMAT_LOCALE = (function () {
    if (BORROWED_FORMATS[language]) return BORROWED_FORMATS[language];
    const regional = phoneTags().find((tag) => tag.includes("-") && tag.toLowerCase().split("-")[0] === language);
    const choices = [regional, USUAL_REGIONS[language], language].filter(Boolean);
    // A browser without this language's formats: day/month/year and a 24-hour clock,
    // as most of Africa writes them
    return choices.find((tag) => browserKnows("NumberFormat", tag)) || "en-GB";
  })();

  // Whether the browser has this language's own words for "5 min ago"
  const OWN_RELATIVE_WORDS = FORMAT_LOCALE.split("-")[0] === language && browserKnows("RelativeTimeFormat", language);

  function locale() {
    return `${FORMAT_LOCALE}-u-nu-latn`;
  }

  function formatNumber(value, options) {
    try {
      return Number(value).toLocaleString(locale(), options);
    } catch (err) {
      return Number(value).toLocaleString(undefined, options);
    }
  }

  // 5 min, 1.2 km, 3 h: in the units' local names where the browser knows them
  function formatUnit(value, unit, digits = 0) {
    try {
      return Number(value).toLocaleString(locale(), {
        style: "unit", unit, unitDisplay: "short", maximumFractionDigits: digits
      });
    } catch (err) {
      const short = { minute: "min", hour: "h", second: "s", kilometer: "km", meter: "m" };
      return `${formatNumber(value, { maximumFractionDigits: digits })} ${short[unit] || unit}`;
    }
  }

  function formatDateTime(date) {
    try {
      return date.toLocaleString(locale());
    } catch (err) {
      return date.toLocaleString();
    }
  }

  // "5 min ago": the browser's words for it in this language, else the translation's
  function formatAgo(seconds) {
    const minutes = Math.round(seconds / 60);
    if (OWN_RELATIVE_WORDS) {
      try {
        const relative = new Intl.RelativeTimeFormat(locale(), { numeric: "always", style: "short" });
        const text = seconds < 60 ? relative.format(-seconds, "second") : relative.format(-minutes, "minute");
        if (!/[-−]\s*\d/.test(text)) return text; // "-5 min" means it has no words for it
      } catch (err) {
        // the translation's words, below
      }
    }
    return seconds < 60
      ? t("{count} s ago", { count: formatNumber(seconds) })
      : t("{count} min ago", { count: formatNumber(minutes) });
  }

  return {
    LANGUAGES, language, t, whenReady, locale, formatNumber, formatUnit, formatDateTime, formatAgo,
    isRightToLeft: Boolean(current.rtl)
  };
})();

const t = AfriI18n.t;
