import { API_BASE_URL } from "../config.js";

const TOKEN_KEY = "pke.session.token";

export class ApiError extends Error {
  constructor(kind, message, payload = null, status = 0) {
    super(message);
    this.kind = kind;
    this.payload = payload;
    this.status = status;
  }
}

export function getStoredToken() {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setStoredToken(token) {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore quota */
  }
}

function clientRequestId() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return `req-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

async function request(path, { method = "GET", body, signal, auth = true } = {}) {
  const headers = {};
  if (body) headers["Content-Type"] = "application/json";
  if (auth) {
    const token = getStoredToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
      signal,
    });
  } catch (err) {
    throw new ApiError("network", "Falha de rede. Sua mensagem não saiu daqui.", null, 0);
  }
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (response.status === 401) {
    throw new ApiError(
      "authentication",
      payload?.error?.message || "Sessão inválida.",
      payload,
      401
    );
  }
  if (response.status === 409) {
    const code = payload?.error?.code || "";
    const retryable = payload?.error?.retryable;
    throw new ApiError(
      code === "OPERATION_RECOVERY_REQUIRED" ? "recovery" : "conflict",
      payload?.error?.message || "Conflito no pedido.",
      payload,
      409
    );
  }
  if (response.status === 422 || response.status === 400) {
    throw new ApiError(
      "validation",
      payload?.error?.message || "Pedido inválido.",
      payload,
      response.status
    );
  }
  if (response.status === 503) {
    throw new ApiError(
      payload?.error?.retryable === false ? "unavailable" : "retryable",
      payload?.text || payload?.error?.message || "Serviço indisponível.",
      payload,
      503
    );
  }
  if (!response.ok && !payload) {
    throw new ApiError("server", "Não foi possível falar com o servidor.", null, response.status);
  }
  return { status: response.status, payload };
}

export const api = {
  clientRequestId,
  getStoredToken,
  setStoredToken,
  async register({ username, password, displayName }) {
    const { payload } = await request("/auth/register", {
      method: "POST",
      auth: false,
      body: {
        username,
        password,
        display_name: displayName || undefined,
      },
    });
    if (payload?.access_token) setStoredToken(payload.access_token);
    return payload;
  },
  async login({ username, password }) {
    const { payload } = await request("/auth/login", {
      method: "POST",
      auth: false,
      body: { username, password },
    });
    if (payload?.access_token) setStoredToken(payload.access_token);
    return payload;
  },
  async logout() {
    try {
      await request("/auth/logout", { method: "POST" });
    } finally {
      setStoredToken(null);
    }
  },
  async getCurrentUser() {
    const { payload } = await request("/me");
    return payload;
  },
  async health() {
    const { payload } = await request("/health", { auth: false });
    return payload;
  },
  async listConversations() {
    const { payload } = await request("/conversations");
    return payload;
  },
  async createConversation() {
    const { payload } = await request("/conversations", { method: "POST", body: {} });
    return payload;
  },
  async getConversation(id) {
    const { payload } = await request(`/conversations/${encodeURIComponent(id)}`);
    return payload;
  },
  async getMessages(id) {
    const { payload } = await request(`/conversations/${encodeURIComponent(id)}/messages`);
    return payload;
  },
  async sendMessage({ conversationId, text, clientRequestId: rid }) {
    const { status, payload } = await request("/messages", {
      method: "POST",
      body: {
        conversation_id: conversationId || undefined,
        text,
        client_request_id: rid || clientRequestId(),
      },
    });
    return classify(status, payload);
  },
  async answerClarification({ clarificationId, text, optionId, clientRequestId: rid }) {
    const { status, payload } = await request(
      `/clarifications/${encodeURIComponent(clarificationId)}/answer`,
      {
        method: "POST",
        body: {
          text: text || undefined,
          option_id: optionId || undefined,
          client_request_id: rid || clientRequestId(),
        },
      }
    );
    return classify(status, payload);
  },
};

function classify(status, payload) {
  if (!payload) {
    throw new ApiError("server", "Resposta vazia.", null, status);
  }
  if (payload.type === "clarification") {
    return { kind: "clarification", payload };
  }
  if (payload.type === "unsupported") {
    return { kind: "unsupported", payload };
  }
  if (payload.type === "error" || payload.status === "failed") {
    return { kind: "error", payload };
  }
  if (payload.type === "answer" || payload.type === "acknowledgement") {
    return { kind: "ok", payload };
  }
  return { kind: "ok", payload };
}
