// Makes Africycle installable like an app and quick to open on slow connections.
// The service worker (/sw.js, built by the server) keeps a copy of the pages, styles,
// scripts and map library on the device. Data (buyers, prices, messages, locations) is
// never stored by it: that always comes live from the server.

(function () {
  if (!("serviceWorker" in navigator) || window.location.protocol === "file:") return;

  const startedWithWorker = Boolean(navigator.serviceWorker.controller);
  let reloading = false;

  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // Not available (private browsing, old browser): the site works normally without it
    });
  });

  // A new version was installed while this page was open: offer to load it
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (!startedWithWorker || reloading) return;
    showBar("Africycle has been updated.", "Reload", () => {
      reloading = true;
      window.location.reload();
    });
  });

  function showBar(text, actionText, onAction) {
    const bar = document.createElement("div");
    bar.className = "notice-bar";
    bar.setAttribute("role", "status");
    const message = document.createElement("span");
    message.textContent = text;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn";
    button.textContent = actionText;
    button.addEventListener("click", onAction);
    bar.appendChild(message);
    bar.appendChild(button);
    document.body.appendChild(bar);
  }

  // "Install the app" on the landing page (Chrome, Edge, Samsung Internet, Opera)
  const installBtn = document.getElementById("installBtn");
  let installPrompt = null;
  if (installBtn) {
    window.addEventListener("beforeinstallprompt", (event) => {
      event.preventDefault();
      installPrompt = event;
      installBtn.hidden = false;
    });
    installBtn.addEventListener("click", () => {
      if (!installPrompt) return;
      installPrompt.prompt();
      installPrompt.userChoice.then(() => {
        installBtn.hidden = true;
        installPrompt = null;
      });
    });
    window.addEventListener("appinstalled", () => {
      installBtn.hidden = true;
    });
  }

  // iPhone and iPad: Safari has no install button, so explain "Add to Home Screen"
  const iosHint = document.getElementById("iosInstallHint");
  const isIos = /iphone|ipad|ipod/i.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const installed = window.navigator.standalone === true ||
    (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches);
  if (iosHint && isIos && !installed) iosHint.hidden = false;
})();
