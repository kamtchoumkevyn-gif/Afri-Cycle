// Runs on every page right after probe.js. Written in old-style JavaScript (ES5) on
// purpose, so that even browsers too old for the app can run it and explain the problem,
// instead of showing a page whose buttons do nothing. The explanation shows in English
// first, then in the person's language once its translations arrive (i18n/<code>.json;
// the same files as the rest of the app, and the same languages as js/i18n.js).
(function () {
  var operaMiniExtreme = Object.prototype.toString.call(window.operamini) === "[object OperaMini]";
  var canRun = window.__africycleSyntaxOK === true &&
    typeof window.fetch === "function" &&
    typeof window.Promise === "function" &&
    typeof window.Map === "function" &&
    typeof window.URLSearchParams === "function" &&
    typeof Object.assign === "function" &&
    typeof Array.prototype.find === "function" &&
    typeof Array.prototype.includes === "function" &&
    !!window.Element && typeof window.Element.prototype.closest === "function";

  if (canRun && !operaMiniExtreme) return;

  var LANGUAGES = ["en", "fr", "om", "af", "es", "ff", "ha", "ig", "rw", "rn", "zu", "sw", "ln", "wes", "pt", "sg",
    "so", "yo", "ar", "am", "zh"];
  var RIGHT_TO_LEFT = { ar: true };

  // The English text, translated further down. t() marks it as text to translate (for
  // backend/tools/i18n_strings.py), like t() in the rest of the app.
  function t(english) {
    return english;
  }

  var text = operaMiniExtreme
    ? t("Opera Mini's Extreme data saving can't run Africycle. In Opera Mini, open Settings, then Data savings, choose High or Off, and reload this page.")
    : t("This browser is too old to run Africycle. Update it, or open Africycle in Chrome, Firefox, Samsung Internet or Safari.");
  var box = document.createElement("div");
  box.className = "compat-notice";
  box.setAttribute("role", "alert");
  box.appendChild(document.createTextNode(text));
  document.body.insertBefore(box, document.body.firstChild);

  function chosenLanguage() {
    var saved = null;
    try {
      saved = window.localStorage.getItem("africycle_language");
    } catch (err) {
      saved = null;
    }
    var wanted = [saved, navigator.language, navigator.userLanguage];
    for (var i = 0; i < wanted.length; i++) {
      if (!wanted[i]) continue;
      var code = String(wanted[i]).toLowerCase().split("-")[0];
      if (code === "pcm") code = "wes";
      for (var j = 0; j < LANGUAGES.length; j++) {
        if (LANGUAGES[j] === code) return code;
      }
    }
    return "en";
  }

  var language = chosenLanguage();
  if (language === "en" || !window.XMLHttpRequest || !window.JSON) return;
  var request = new XMLHttpRequest();
  request.open("GET", (window.location.protocol === "file:" ? "" : "/") + "i18n/" + language + ".json", true);
  request.onreadystatechange = function () {
    if (request.readyState !== 4 || request.status !== 200) return;
    try {
      var translated = JSON.parse(request.responseText)[text];
      if (!translated) return;
      box.firstChild.nodeValue = translated;
      box.setAttribute("lang", language);
      box.setAttribute("dir", RIGHT_TO_LEFT[language] ? "rtl" : "ltr");
    } catch (err) {
      // Not readable: the English explanation stays
    }
  };
  request.send();
})();
