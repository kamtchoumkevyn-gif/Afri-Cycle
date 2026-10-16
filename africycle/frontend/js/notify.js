// Message alerts on the pages where people chat (seller, buyer and messages pages):
// - a count of unread messages on "Messages" and in the browser tab's title,
// - a pop-up when a new message arrives while Africycle is open,
// - phone notifications when it isn't open, once the person turns them on
//   (the server sends them; js/../sw.js shows them).
// Load after api.js and auth.js. The messages page calls AfricycleAlerts.viewing(userId)
// for the conversation on screen. Logging out (auth.js) stops this device's notifications.

const AfricycleAlerts = (function () {
  const user = currentUser();
  if (!user) return null;

  const POLL_MS = 20000;
  const SEEN_KEY = `africycle_last_alerted_${user.userId}`;
  const ASKED_KEY = "africycle_notifications_prompt";
  let baseTitle = null; // the page's title in the chosen language, once translated
  const canPush = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window &&
    window.location.protocol !== "file:";
  const isIos = /iphone|ipad|ipod/i.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const installed = window.navigator.standalone === true ||
    (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches);

  let viewingUserId = null;
  let popup = null;
  let popupTimer = null;

  function remembered(key) {
    try {
      return localStorage.getItem(key);
    } catch (err) {
      return null;
    }
  }

  function remember(key, value) {
    try {
      localStorage.setItem(key, String(value));
    } catch (err) {
      // Not kept: at worst a pop-up shows again
    }
  }

  // ---- Unread count and pop-up ----

  function showCount(count) {
    const link = document.getElementById("messagesLink");
    if (link) {
      let badge = link.querySelector(".count-badge");
      if (count > 0) {
        if (!badge) {
          badge = document.createElement("span");
          badge.className = "count-badge";
          link.appendChild(badge);
        }
        badge.textContent = count > 99 ? "99+" : String(count);
        link.setAttribute("aria-label", t("Messages, unread: {count}", { count }));
      } else if (badge) {
        badge.remove();
        link.removeAttribute("aria-label");
      }
    }
    if (baseTitle === null) baseTitle = document.title;
    document.title = count > 0 ? `(${count}) ${baseTitle}` : baseTitle;
  }

  function showPopup(message) {
    hidePopup();
    popup = document.createElement("div");
    popup.className = "notice-bar";
    popup.setAttribute("role", "status");
    const text = document.createElement("span");
    text.className = "notice-text";
    text.dir = "auto"; // the message may be in another script than the page
    text.textContent = `${message.senderName}: ${message.messageText}`;
    const open = document.createElement("a");
    open.className = "btn";
    open.href = `chat.html?with=${message.senderId}`;
    open.textContent = t("Open");
    popup.appendChild(text);
    popup.appendChild(open);
    document.body.appendChild(popup);
    popupTimer = setTimeout(hidePopup, 10000);
    // Said aloud for people who can't read it, when they asked for that (js/guide.js)
    if (typeof AfriGuide !== "undefined") AfriGuide.newMessage(message.senderName, message.messageText);
  }

  function hidePopup() {
    clearTimeout(popupTimer);
    if (popup) popup.remove();
    popup = null;
  }

  async function check() {
    if (document.hidden) return; // the phone notification covers that, and it saves data
    let summary;
    try {
      const response = await authFetch("/chat/unread");
      if (!response.ok) return;
      summary = await readJson(response);
    } catch (err) {
      return;
    }
    const fromOthers = viewingUserId
      ? summary.unread - (summary.bySender[String(viewingUserId)] || 0)
      : summary.unread;
    showCount(fromOthers);

    const latest = summary.latest;
    const lastAlerted = Number(remembered(SEEN_KEY)) || 0;
    if (latest && latest.id > lastAlerted) {
      remember(SEEN_KEY, latest.id);
      if (latest.senderId !== viewingUserId) showPopup(latest);
    }
  }

  // ---- Phone notifications (Web Push) ----

  function keyBytes(base64url) {
    const base64 = base64url.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((base64url.length + 3) % 4);
    return Uint8Array.from(atob(base64), (c) => c.charCodeAt(0));
  }

  function sameKey(subscription, key) {
    const current = subscription.options && subscription.options.applicationServerKey;
    if (!current) return true; // the browser doesn't say: assume it's ours
    const a = new Uint8Array(current);
    const b = keyBytes(key);
    return a.length === b.length && a.every((value, i) => value === b[i]);
  }

  // Signs this device up with the server for the logged-in account. askFirst: show the
  // browser's permission question (only ever after a tap on "Turn on").
  async function signUp(askFirst) {
    if (!canPush) return false;
    const permission = askFirst ? await Notification.requestPermission() : Notification.permission;
    if (permission !== "granted") return false;
    const registration = await navigator.serviceWorker.ready;
    const keyResponse = await authFetch("/push/key");
    if (!keyResponse.ok) return false;
    const { publicKey } = await readJson(keyResponse);
    let subscription = await registration.pushManager.getSubscription();
    if (subscription && !sameKey(subscription, publicKey)) {
      await subscription.unsubscribe();
      subscription = null;
    }
    if (!subscription) {
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: keyBytes(publicKey)
      });
    }
    if (window.africycleLoggingOut) return false; // logged out while this was under way
    // Each phone gets its notifications in the language chosen on it
    const response = await authFetch("/push/subscribe", {
      method: "POST",
      body: JSON.stringify(Object.assign(subscription.toJSON(), { language: AfriI18n.language }))
    });
    return response.ok;
  }

  function offerNotifications() {
    const anchor = document.querySelector(".page-intro");
    if (!anchor || remembered(ASKED_KEY) === "no") return;

    let text = "";
    if (canPush && Notification.permission === "default") {
      text = t("Get a notification on this device when someone messages you or a collector is on the way, even when Africycle is closed.");
    } else if (!canPush && isIos && !installed) {
      text = t("To get notifications on iPhone, add Africycle to your Home Screen first: tap Share, then \"Add to Home Screen\".");
    } else {
      return;
    }

    const box = document.createElement("div");
    box.className = "notify-prompt";
    box.setAttribute("role", "region");
    box.setAttribute("aria-label", t("Notifications"));
    const message = document.createElement("p");
    message.textContent = text;
    const actions = document.createElement("div");
    actions.className = "row-actions";
    if (canPush) {
      const on = document.createElement("button");
      on.type = "button";
      on.className = "btn btn-primary";
      on.textContent = t("Turn on");
      on.addEventListener("click", async () => {
        on.disabled = true;
        let ok = false;
        try {
          ok = await signUp(true);
        } catch (err) {
          ok = false;
        }
        if (ok) {
          message.textContent = t("Notifications are on for this device.");
          actions.remove();
          setTimeout(() => box.remove(), 4000);
        } else if (Notification.permission === "denied") {
          message.textContent = t("Notifications are blocked for Africycle. You can allow them in your browser's settings for this site.");
          actions.remove();
        } else if (Notification.permission === "default") {
          message.textContent = t("Notifications weren't allowed. Tap Turn on to try again.");
          on.disabled = false;
        } else {
          message.textContent = t("Notifications couldn't be turned on just now. Check your connection, then try again.");
          on.disabled = false;
        }
      });
      actions.appendChild(on);
    }
    const later = document.createElement("button");
    later.type = "button";
    later.className = "btn btn-quiet";
    later.textContent = t("Not now");
    later.addEventListener("click", () => {
      remember(ASKED_KEY, "no");
      box.remove();
    });
    actions.appendChild(later);
    box.appendChild(message);
    box.appendChild(actions);
    anchor.insertAdjacentElement("afterend", box);
  }

  // ---- Start, once the page is in the chosen language ----

  AfriI18n.whenReady(() => {
    baseTitle = document.title;
    check();
    setInterval(check, POLL_MS);
    document.addEventListener("visibilitychange", () => {
      if (!document.hidden) check();
    });
    offerNotifications();
    // Already allowed on this device: make sure it's signed up for whoever is logged in
    // now, in the language chosen now
    if (canPush && Notification.permission === "granted") {
      signUp(false).catch(() => {});
    }
  });

  return {
    // The conversation on screen: no pop-up or count for it
    viewing(userId) {
      viewingUserId = userId;
      check();
    },
    refresh: check
  };
})();
