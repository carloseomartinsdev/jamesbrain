import { api, ApiError } from "./api/client.js";
import { DEBUG_UI } from "./config.js";
import { renderMessage } from "./renderers/index.js";
import { groupConversations, routeFromPath } from "./state/conversation.js";

const els = {
  sidebar: document.getElementById("sidebar"),
  backdrop: document.getElementById("sidebar-backdrop"),
  toggle: document.getElementById("toggle-sidebar"),
  list: document.getElementById("conversation-list"),
  title: document.getElementById("conversation-title"),
  status: document.getElementById("connection-status"),
  empty: document.getElementById("empty-state"),
  messages: document.getElementById("message-list"),
  processing: document.getElementById("processing"),
  composer: document.getElementById("composer"),
  input: document.getElementById("composer-input"),
  send: document.getElementById("send-button"),
  userChip: document.getElementById("user-chip"),
  debug: document.getElementById("debug-panel"),
  authGate: document.getElementById("auth-gate"),
  authForm: document.getElementById("auth-form"),
  authTitle: document.getElementById("auth-title"),
  authError: document.getElementById("auth-error"),
  authUsername: document.getElementById("auth-username"),
  authPassword: document.getElementById("auth-password"),
  authDisplayWrap: document.getElementById("auth-display-wrap"),
  authDisplay: document.getElementById("auth-display"),
  authSubmit: document.getElementById("auth-submit"),
  authToggle: document.getElementById("auth-toggle"),
  logout: document.getElementById("logout-button"),
  timeline: document.getElementById("timeline"),
};

const state = {
  user: null,
  authState: "unauthenticated",
  registerMode: false,
  conversations: [],
  conversationId: null,
  messages: [],
  pendingClarification: null,
  sending: false,
  pendingByRequest: new Map(),
  draftBeforeAuth: "",
  stickToBottom: true,
};

function go(path) {
  if (window.location.pathname !== path) {
    history.pushState({}, "", path);
  }
  return renderRoute();
}

function closeDrawer() {
  els.sidebar.classList.remove("open");
  els.backdrop.hidden = true;
  els.toggle.setAttribute("aria-expanded", "false");
}

function openDrawer() {
  els.sidebar.classList.add("open");
  els.backdrop.hidden = false;
  els.toggle.setAttribute("aria-expanded", "true");
}

function setOnline(ok) {
  els.status.textContent = ok ? "Conectado" : "Sem conexão";
  els.status.dataset.state = ok ? "ok" : "offline";
}

function clearAuthenticatedUi() {
  state.user = null;
  state.conversations = [];
  state.messages = [];
  state.conversationId = null;
  state.pendingClarification = null;
  state.pendingByRequest.clear();
  state.sending = false;
  if (els.userChip) els.userChip.textContent = "";
  if (els.debug) {
    els.debug.hidden = true;
    els.debug.textContent = "";
  }
  if (els.list) els.list.innerHTML = "";
  if (els.messages) els.messages.innerHTML = "";
  if (els.title) els.title.textContent = "PKE";
}

function renderSidebar() {
  const groups = groupConversations(state.conversations);
  els.list.innerHTML = groups
    .map((group) => {
      const items = group.items
        .map((item) => {
          const active = item.id === state.conversationId ? " active" : "";
          const when = new Date(item.updated_at).toLocaleString("pt-BR", {
            hour: "2-digit",
            minute: "2-digit",
            day: "2-digit",
            month: "short",
          });
          const preview = item.last_message_preview
            ? `<span class="conv-preview">${escapeSidebar(item.last_message_preview)}</span>`
            : "";
          return `<button type="button" class="conv-item${active}" data-id="${item.id}" aria-current="${active ? "true" : "false"}">
            <span class="conv-title">${escapeSidebar(item.title)}</span>
            ${preview}
            <span class="conv-time">${when}</span>
          </button>`;
        })
        .join("");
      return `<p class="group-label">${group.label}</p>${items}`;
    })
    .join("");
}

function escapeSidebar(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function renderTimeline() {
  const route = routeFromPath(window.location.pathname);
  if (route.name === "settings") {
    els.empty.hidden = true;
    els.messages.innerHTML = `<li class="settings-page">
      <h2>Configurações</h2>
      <div class="setting-row"><strong>Conta</strong><p>${escapeSidebar(state.user?.display_name || state.user?.username || "—")}</p></div>
      <div class="setting-row"><strong>Aparência</strong>
        <button type="button" class="text-btn" data-theme="system">Sistema</button>
        <button type="button" class="text-btn" data-theme="dark">Escuro</button>
        <button type="button" class="text-btn" data-theme="light">Claro</button>
      </div>
      <div class="setting-row" id="api-status"><strong>Servidor</strong><p>verificando…</p></div>
    </li>`;
    api.health().then((h) => {
      const box = document.getElementById("api-status");
      if (box) box.innerHTML = `<strong>Servidor</strong><p>${h.status === "ok" ? "Operacional" : "Indisponível"}</p>`;
    }).catch(() => {
      const box = document.getElementById("api-status");
      if (box) box.innerHTML = `<strong>Servidor</strong><p>Indisponível</p>`;
    });
    els.title.textContent = "Configurações";
    return;
  }
  const hasConv = Boolean(state.conversationId);
  if (!hasConv) {
    els.empty.hidden = false;
    els.messages.innerHTML = "";
    els.title.textContent = "PKE";
    return;
  }
  els.empty.hidden = state.messages.length > 0;
  const pendingId = state.pendingClarification?.id || null;
  els.messages.innerHTML = state.messages
    .map((m) => renderMessage(m, { pendingClarificationId: pendingId }))
    .join("");
  if (state.stickToBottom) scrollNearLatest();
}

function scrollNearLatest() {
  if (!els.timeline) return;
  requestAnimationFrame(() => {
    els.timeline.scrollTop = els.timeline.scrollHeight;
  });
}

function setProcessing(on) {
  state.sending = on;
  els.processing.hidden = !on;
  els.send.disabled = on;
  els.input.disabled = on;
}

async function loadConversations() {
  state.conversations = await api.listConversations();
  renderSidebar();
}

async function openConversation(id) {
  state.conversationId = id;
  const conv = await api.getConversation(id);
  els.title.textContent = conv.title;
  if (Array.isArray(conv.messages)) {
    state.messages = conv.messages;
  } else {
    state.messages = await api.getMessages(id);
  }
  state.pendingClarification = conv.pending_clarification || null;
  state.stickToBottom = true;
  renderSidebar();
  renderTimeline();
  closeDrawer();
  els.input.focus();
}

async function startNew() {
  if (state.sending) return;
  const created = await api.createConversation();
  await loadConversations();
  await go(`/c/${created.id}`);
  await openConversation(created.id);
}

async function sendText(text, { clarificationId, optionId } = {}) {
  const value = text.trim();
  if ((!value && !optionId) || state.sending) return;
  if (state.authState !== "authenticated") {
    showAuthGate();
    return;
  }
  const rid = api.clientRequestId();
  const optimistic = {
    id: `local-${rid}`,
    localId: rid,
    conversation_id: state.conversationId,
    role: "user",
    type: "text",
    text: value || optionId,
    status: "sending",
    created_at: new Date().toISOString(),
  };
  state.pendingByRequest.set(rid, optimistic);
  state.stickToBottom = true;
  if (state.conversationId) {
    state.messages.push(optimistic);
    els.empty.hidden = true;
    renderTimeline();
  } else {
    els.empty.hidden = true;
    state.messages = [optimistic];
    renderTimeline();
  }
  setProcessing(true);
  let clearComposer = true;
  try {
    const result = clarificationId
      ? await api.answerClarification({
          clarificationId,
          text: value || undefined,
          optionId,
          clientRequestId: rid,
        })
      : await api.sendMessage({
          conversationId: state.conversationId,
          text: value,
          clientRequestId: rid,
        });
    const payload = result.payload;
    state.conversationId = payload.conversation_id;
    if (window.location.pathname !== `/c/${payload.conversation_id}`) {
      history.pushState({}, "", `/c/${payload.conversation_id}`);
    }
    const hydrated = await api.getConversation(payload.conversation_id);
    state.messages = Array.isArray(hydrated.messages)
      ? hydrated.messages
      : await api.getMessages(payload.conversation_id);
    state.pendingClarification = hydrated.pending_clarification || null;
    if (payload.user_message_id) {
      optimistic.id = payload.user_message_id;
      optimistic.status = "completed";
    }
    if (DEBUG_UI && payload.debug) {
      els.debug.hidden = false;
      els.debug.textContent = `${payload.debug.request_id || ""} · ${payload.debug.latency_ms || "?"}ms · ${payload.debug.result_class || ""}`;
    }
    setOnline(true);
    await loadConversations();
    const conv = state.conversations.find((c) => c.id === payload.conversation_id);
    if (conv) els.title.textContent = conv.title;
    renderTimeline();
  } catch (err) {
    optimistic.status = "failed";
    if (err instanceof ApiError && err.kind === "network") setOnline(false);
    else setOnline(true);
    if (err instanceof ApiError && err.kind === "authentication") {
      state.draftBeforeAuth = value || els.input.value;
      clearComposer = false;
      showAuthGate("session expired");
      return;
    }
    if (err instanceof ApiError && err.kind === "recovery") {
      optimistic.error = {
        code: "OPERATION_RECOVERY_REQUIRED",
        message: err.message,
        retryable: false,
      };
      clearComposer = false;
      state.draftBeforeAuth = value || els.input.value;
    } else if (err instanceof ApiError && err.kind === "conflict") {
      optimistic.error = {
        code: err.payload?.error?.code || "conflict",
        message: err.message,
        retryable: false,
      };
    } else if (err instanceof ApiError && (err.kind === "retryable" || err.kind === "unavailable")) {
      optimistic.error = {
        code: err.payload?.error?.code || "unavailable",
        message: err.message,
        retryable: err.payload?.error?.retryable !== false,
      };
      optimistic.uiKind = "technical";
    } else if (err instanceof ApiError) {
      optimistic.error = {
        code: err.payload?.error?.code || err.kind,
        message: err.message,
        retryable: err.payload?.error?.retryable === true,
      };
    }
    renderTimeline();
  } finally {
    setProcessing(false);
    if (state.authState === "authenticated") {
      if (clearComposer) els.input.value = "";
      els.input.focus();
    }
  }
}

async function retry(rid) {
  const pending = state.pendingByRequest.get(rid);
  if (!pending || state.sending) return;
  state.messages = state.messages.filter((m) => m.localId !== rid);
  await sendText(pending.text);
}

async function renderRoute() {
  const route = routeFromPath(window.location.pathname);
  if (route.name === "settings") {
    state.conversationId = null;
    renderTimeline();
    return;
  }
  if (route.name === "conversation") {
    try {
      await openConversation(route.id);
    } catch (err) {
      if (err instanceof ApiError && err.kind === "authentication") {
        showAuthGate("session expired");
        return;
      }
      go("/");
    }
    return;
  }
  state.conversationId = null;
  state.messages = [];
  state.pendingClarification = null;
  renderTimeline();
}

els.composer.addEventListener("submit", (event) => {
  event.preventDefault();
  sendText(els.input.value);
});

els.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    els.composer.requestSubmit();
  }
});

if (els.timeline) {
  els.timeline.addEventListener("scroll", () => {
    const nearBottom =
      els.timeline.scrollHeight - els.timeline.scrollTop - els.timeline.clientHeight < 80;
    state.stickToBottom = nearBottom;
  });
}

document.getElementById("new-conversation").addEventListener("click", () => startNew());
document.getElementById("header-new").addEventListener("click", () => startNew());
els.toggle.addEventListener("click", () => {
  if (els.sidebar.classList.contains("open")) closeDrawer();
  else openDrawer();
});
els.backdrop.addEventListener("click", closeDrawer);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeDrawer();
});

els.list.addEventListener("click", (event) => {
  const btn = event.target.closest("[data-id]");
  if (!btn) return;
  go(`/c/${btn.dataset.id}`);
});

els.messages.addEventListener("click", (event) => {
  const theme = event.target.closest("[data-theme]");
  if (theme) {
    const value = theme.dataset.theme;
    if (value === "system") document.documentElement.removeAttribute("data-theme");
    else document.documentElement.setAttribute("data-theme", value);
    return;
  }
  const retryBtn = event.target.closest("[data-retry]");
  if (retryBtn) {
    retry(retryBtn.dataset.retry);
    return;
  }
  const choice = event.target.closest("[data-option]");
  if (choice) {
    sendText("", { clarificationId: choice.dataset.clarification, optionId: choice.dataset.option });
  }
});

els.messages.addEventListener("submit", (event) => {
  const form = event.target.closest(".clar-text-form");
  if (!form) return;
  event.preventDefault();
  const input = form.querySelector(".clar-input");
  const text = input?.value || "";
  sendText(text, { clarificationId: form.dataset.clarification });
});

document.querySelectorAll(".suggestion").forEach((btn) => {
  btn.addEventListener("click", () => sendText(btn.dataset.text));
});

window.addEventListener("popstate", () => renderRoute());
window.addEventListener("online", () => setOnline(true));
window.addEventListener("offline", () => setOnline(false));

function showAuthGate(reason) {
  state.authState = reason === "session expired" ? "session expired" : "unauthenticated";
  clearAuthenticatedUi();
  if (els.authGate) els.authGate.hidden = false;
  if (els.composer) els.composer.hidden = true;
  if (els.authError) {
    if (reason === "session expired") {
      els.authError.hidden = false;
      els.authError.textContent = "Sua sessão expirou. Entre novamente para continuar.";
    } else if (reason === "network") {
      els.authError.hidden = false;
      els.authError.textContent = "Não foi possível conectar ao servidor.";
    } else {
      els.authError.hidden = true;
      els.authError.textContent = "";
    }
  }
  if (els.authUsername) els.authUsername.focus();
}

function hideAuthGate() {
  state.authState = "authenticated";
  if (els.authGate) els.authGate.hidden = true;
  if (els.composer) els.composer.hidden = false;
  if (state.draftBeforeAuth && els.input) {
    els.input.value = state.draftBeforeAuth;
    state.draftBeforeAuth = "";
  }
}

function setRegisterMode(on) {
  state.registerMode = on;
  if (!els.authTitle) return;
  els.authTitle.textContent = on ? "Criar conta" : "Entrar no PKE";
  els.authSubmit.textContent = on ? "Criar conta" : "Entrar";
  els.authToggle.textContent = on ? "Já tenho conta" : "Criar conta";
  els.authDisplayWrap.hidden = !on;
}

if (els.authToggle) {
  els.authToggle.addEventListener("click", () => setRegisterMode(!state.registerMode));
}

if (els.authForm) {
  els.authForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    state.authState = "authenticating";
    els.authError.hidden = true;
    els.authSubmit.disabled = true;
    try {
      const username = els.authUsername.value.trim();
      const password = els.authPassword.value;
      if (state.registerMode) {
        await api.register({
          username,
          password,
          displayName: els.authDisplay.value.trim() || undefined,
        });
      } else {
        await api.login({ username, password });
      }
      state.user = await api.getCurrentUser();
      els.userChip.textContent = state.user.display_name;
      hideAuthGate();
      setOnline(true);
      await loadConversations();
      await renderRoute();
      els.input.focus();
    } catch (err) {
      state.authState = "unauthenticated";
      els.authError.hidden = false;
      if (err instanceof ApiError && err.kind === "network") {
        els.authError.textContent = "Não foi possível conectar ao servidor.";
      } else if (err instanceof ApiError && err.status === 401) {
        els.authError.textContent = "Usuário ou senha inválidos.";
      } else if (err instanceof ApiError) {
        els.authError.textContent = err.message || "Não foi possível autenticar.";
      } else {
        els.authError.textContent = "Não foi possível autenticar.";
      }
    } finally {
      els.authSubmit.disabled = false;
    }
  });
}

if (els.logout) {
  els.logout.addEventListener("click", async () => {
    await api.logout();
    showAuthGate();
    history.replaceState({}, "", "/");
  });
}

async function boot() {
  if (!api.getStoredToken()) {
    showAuthGate();
    return;
  }
  try {
    state.user = await api.getCurrentUser();
    els.userChip.textContent = state.user.display_name;
    hideAuthGate();
    setOnline(true);
    await loadConversations();
    await renderRoute();
  } catch (err) {
    if (err instanceof ApiError && err.kind === "authentication") {
      api.setStoredToken(null);
      showAuthGate("session expired");
      return;
    }
    if (err instanceof ApiError && err.kind === "network") {
      setOnline(false);
      showAuthGate("network");
      return;
    }
    showAuthGate();
  }
}

boot();
