// Messages page. Open with chat.html?with=<userId> to start a conversation.

AfriI18n.whenReady(function () {
  const user = requireAuth();
  if (!user) return;

  const pageMsg = document.getElementById("pageMsg");
  const listEl = document.getElementById("conversationList");
  const threadEl = document.getElementById("thread");
  const threadTitle = document.getElementById("threadTitle");
  const chatForm = document.getElementById("chatForm");
  const chatInput = document.getElementById("chatInput");
  const POLL_MS = 5000;

  let activeUserId = null;
  let lastRenderedCount = -1;

  document.getElementById("backLink").href = dashboardFor(user.role);
  document.querySelector(".topbar-brand").href = dashboardFor(user.role);

  async function loadConversations() {
    try {
      const response = await authFetch("/chat/conversations");
      const data = await readJson(response);
      const convos = data.conversations || [];

      if (convos.length === 0 && !activeUserId) {
        listEl.innerHTML = `<p class="panel-hint">${escapeHtml(t("No conversations yet. Open one from a buyer or delivery with \"Message\"."))}</p>`;
        return;
      }
      listEl.innerHTML = convos.map((c) => {
        // The open conversation is being read, so it never shows as unread
        const unread = c.otherUserId === activeUserId ? 0 : c.unread || 0;
        const badge = unread
          ? ` <span class="count-badge" aria-label="${escapeHtml(t("{count} unread", { count: unread }))}">${unread}</span>` : "";
        return `
        <button type="button" class="conversation-item ${c.otherUserId === activeUserId ? "active" : ""} ${unread ? "unread" : ""}"
                data-id="${c.otherUserId}">
          <bdi>${escapeHtml(c.otherUserName || t("User"))}</bdi>${badge}
        </button>`;
      }).join("");
    } catch (err) {
      showMessage(pageMsg, t("Conversations could not be loaded."), "error");
    }
  }

  listEl.addEventListener("click", (event) => {
    const item = event.target.closest(".conversation-item");
    if (item) openConversation(Number(item.dataset.id));
  });

  async function openConversation(otherUserId) {
    if (activeUserId !== otherUserId) {
      lastRenderedCount = -1;
    }
    activeUserId = otherUserId;
    if (typeof AfricycleAlerts !== "undefined" && AfricycleAlerts) AfricycleAlerts.viewing(otherUserId);
    chatForm.hidden = false;
    listEl.querySelectorAll(".conversation-item").forEach((btn) => {
      btn.classList.toggle("active", Number(btn.dataset.id) === otherUserId);
    });
    await loadThread();
  }

  // Conversations with an under-18 seller can be read by their guardian; say so to both sides
  let iAmMinor = false;
  let lastThreadData = null;
  loadMe().then((me) => {
    iAmMinor = Boolean(me && me.isMinor);
    if (lastThreadData) showSupervisionNotice(lastThreadData);
  });

  function showSupervisionNotice(data) {
    lastThreadData = data;
    const notice = document.getElementById("minorNotice");
    if (iAmMinor) {
      notice.textContent = t("Your parent or guardian can read your conversations.");
    } else if (data.otherIsMinor) {
      notice.textContent = t("{name} is under 18. Their parent or guardian can read this conversation.", { name: data.otherUserName });
    }
    notice.hidden = !(iAmMinor || data.otherIsMinor);
  }

  async function loadThread() {
    if (!activeUserId) return;
    try {
      // While the page is in the background, fetching isn't reading: messages stay unread
      const response = await authFetch(`/chat/messages/${activeUserId}${document.hidden ? "?read=0" : ""}`);
      const data = await readJson(response);
      if (!response.ok) {
        showMessage(pageMsg, data.message || t("Messages could not be loaded."), "error");
        return;
      }
      threadTitle.textContent = data.otherUserName;
      showSupervisionNotice(data);
      const messages = data.messages || [];
      if (messages.length === lastRenderedCount) return; // nothing new
      const before = lastRenderedCount;
      lastRenderedCount = messages.length;
      // A message just received in the open conversation: said aloud when asked for (js/guide.js)
      if (before >= 0 && typeof AfriGuide !== "undefined") {
        messages.slice(before).filter((m) => m.senderId !== user.userId)
          .forEach((m) => AfriGuide.newMessage(data.otherUserName, m.messageText));
      }

      threadEl.innerHTML = messages.length
        ? messages.map((m) => `
            <div class="bubble ${m.senderId === user.userId ? "sent" : "received"}">
              <span dir="auto">${escapeHtml(m.messageText)}</span>
              <time>${formatDate(m.createdAt)}</time>
            </div>`).join("")
        : `<p class="panel-hint">${t("No messages yet. Say hello and agree on a pickup time.")}</p>`;
      threadEl.scrollTop = threadEl.scrollHeight;
    } catch (err) {
      showMessage(pageMsg, t("Can't reach the server. Check your connection, then try again."), "error");
    }
  }

  chatForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const messageText = chatInput.value.trim();
    if (!messageText || !activeUserId) return;

    chatInput.disabled = true;
    try {
      const response = await authFetch("/chat/send", {
        method: "POST",
        body: JSON.stringify({ receiverId: activeUserId, messageText })
      });
      const data = await readJson(response);
      if (!response.ok) {
        showMessage(pageMsg, data.message || t("Message not sent."), "error");
        return;
      }
      chatInput.value = "";
      await loadThread();
      loadConversations();
    } catch (err) {
      showMessage(pageMsg, t("Message not sent. Check your connection, then try again."), "error");
    } finally {
      chatInput.disabled = false;
      chatInput.focus();
    }
  });

  const startWith = Number(new URLSearchParams(window.location.search).get("with"));

  loadConversations().then(() => {
    if (startWith) openConversation(startWith);
  });
  setInterval(() => {
    loadThread();
    loadConversations();
  }, POLL_MS);
  // Back to the page: what's on screen is now read
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
      loadThread().then(loadConversations);
    }
  });
});
