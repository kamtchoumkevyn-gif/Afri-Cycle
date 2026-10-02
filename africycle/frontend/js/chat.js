// Messages page. Open with chat.html?with=<userId> to start a conversation.

(function () {
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
        listEl.innerHTML = `<p class="panel-hint">No conversations yet. Open one from a buyer or delivery with "Message".</p>`;
        return;
      }
      listEl.innerHTML = convos.map((c) => `
        <button type="button" class="conversation-item ${c.otherUserId === activeUserId ? "active" : ""}"
                data-id="${c.otherUserId}">
          ${escapeHtml(c.otherUserName || "User")}
        </button>`).join("");
    } catch (err) {
      showMessage(pageMsg, "Conversations could not be loaded.", "error");
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
    chatForm.hidden = false;
    listEl.querySelectorAll(".conversation-item").forEach((btn) => {
      btn.classList.toggle("active", Number(btn.dataset.id) === otherUserId);
    });
    await loadThread();
  }

  async function loadThread() {
    if (!activeUserId) return;
    try {
      const response = await authFetch(`/chat/messages/${activeUserId}`);
      const data = await readJson(response);
      if (!response.ok) {
        showMessage(pageMsg, data.message || "Messages could not be loaded.", "error");
        return;
      }
      threadTitle.textContent = data.otherUserName;
      const messages = data.messages || [];
      if (messages.length === lastRenderedCount) return; // nothing new
      lastRenderedCount = messages.length;

      threadEl.innerHTML = messages.length
        ? messages.map((m) => `
            <div class="bubble ${m.senderId === user.userId ? "sent" : "received"}">
              ${escapeHtml(m.messageText)}
              <time>${formatDate(m.createdAt)}</time>
            </div>`).join("")
        : `<p class="panel-hint">No messages yet. Say hello and agree on a pickup time.</p>`;
      threadEl.scrollTop = threadEl.scrollHeight;
    } catch (err) {
      showMessage(pageMsg, "Can't reach the server. Check your connection and try again.", "error");
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
        showMessage(pageMsg, data.message || "Message not sent.", "error");
        return;
      }
      chatInput.value = "";
      await loadThread();
      loadConversations();
    } catch (err) {
      showMessage(pageMsg, "Message not sent. Check your connection and try again.", "error");
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
})();
