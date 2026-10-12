// Runs on every page right after probe.js. Written in old-style JavaScript (ES5) on
// purpose, so that even browsers too old for the app can run it and explain the problem,
// instead of showing a page whose buttons do nothing.
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

  var text = operaMiniExtreme
    ? "Opera Mini's Extreme data saving can't run Africycle. In Opera Mini, open Settings, then Data savings, choose High or Off, and reload this page."
    : "This browser is too old to run Africycle. Update it, or open Africycle in Chrome, Firefox, Samsung Internet or Safari.";
  var box = document.createElement("div");
  box.className = "compat-notice";
  box.setAttribute("role", "alert");
  box.appendChild(document.createTextNode(text));
  document.body.insertBefore(box, document.body.firstChild);
})();
