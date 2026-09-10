/**
 * PUBLIC_OUTCOME_RENDERING_AUTHORITY — Product Web presentation only.
 * Does not inspect Engine IR. Does not decide semantics.
 */

export function renderMessage(message, { pendingClarificationId = null } = {}) {
  if (message.role === "user") return renderUser(message);
  if (message.uiKind === "recovery") return renderRecovery(message);
  if (message.type === "clarification" || message.clarification) {
    return renderClarification(message, { pendingClarificationId });
  }
  if (message.type === "unsupported") return renderUnsupported(message);
  if (message.type === "error" || message.status === "failed" || message.uiKind === "technical") {
    return renderTechnicalError(message);
  }
  return renderAssistant(message);
}

function renderUser(message) {
  const code = message.error?.code || "";
  const isRecovery = code === "OPERATION_RECOVERY_REQUIRED";
  const isConflict = code === "IDEMPOTENCY_KEY_CONFLICT" || code === "CLARIFICATION_ANSWERED";
  const failed = message.status === "failed" && !isRecovery;
  const retryable =
    failed &&
    !isConflict &&
    message.error?.retryable !== false &&
    Boolean(message.localId);
  const retry = retryable
    ? `<button type="button" class="retry-btn" data-retry="${escapeAttr(message.localId || "")}">Tentar de novo</button>`
    : "";
  const note = isRecovery
    ? `<p class="msg-note recovery-note">Não consegui confirmar o resultado desta operação. Verifique o histórico da conversa antes de tentar de novo.</p>`
    : isConflict
      ? `<p class="msg-note">${escapeHtml(message.error?.message || "Este pedido não pode ser reenviado assim.")}</p>`
      : "";
  return `<li class="bubble user${failed || isRecovery ? " failed" : ""}${isRecovery ? " recovery" : ""}" data-role="user">${escapeHtml(message.text)}${note}${retry}</li>`;
}

function renderAssistant(message) {
  const extra = renderData(message.data);
  const body = formatText(message.text);
  return `<li class="bubble assistant" data-role="assistant" data-type="${escapeAttr(message.type || "answer")}">${body}${extra}</li>`;
}

function renderUnsupported(message) {
  const body = formatText(
    message.text || "Não consegui interpretar isso com segurança suficiente para registrar."
  );
  return `<li class="bubble assistant unsupported" data-role="unsupported" data-type="unsupported">${body}</li>`;
}

function renderClarification(message, { pendingClarificationId }) {
  const clar = message.clarification || {};
  const active =
    pendingClarificationId == null ||
    !clar.id ||
    String(clar.id) === String(pendingClarificationId);
  let actions = "";
  if (active && clar.mode === "choice" && Array.isArray(clar.options)) {
    actions = `<div class="choice-row">${clar.options
      .map(
        (opt) =>
          `<button type="button" class="choice-btn" data-clarification="${escapeAttr(clar.id)}" data-option="${escapeAttr(opt.id)}">${escapeHtml(opt.label)}</button>`
      )
      .join("")}</div>`;
  } else if (active && clar.mode === "text") {
    actions = `<form class="clar-text-form" data-clarification="${escapeAttr(clar.id)}">
      <label class="sr-only" for="clar-input-${escapeAttr(clar.id)}">Resposta</label>
      <input id="clar-input-${escapeAttr(clar.id)}" class="clar-input" name="answer" type="text" required placeholder="Sua resposta" autocomplete="off" />
      <button type="submit" class="choice-btn">Enviar</button>
    </form>`;
  } else if (!active) {
    actions = `<p class="msg-note">Esclarecimento já tratado.</p>`;
  }
  return `<li class="bubble assistant clarification-card${active ? "" : " answered"}" data-role="clarification">${formatText(message.text)}${actions}</li>`;
}

function renderTechnicalError(message) {
  const text =
    message.text ||
    message.error?.message ||
    "Não consegui processar isso agora. Pode tentar novamente.";
  const retryable = message.error?.retryable === true && message.localId;
  const retry = retryable
    ? `<button type="button" class="retry-btn" data-retry="${escapeAttr(message.localId)}">Tentar de novo</button>`
    : "";
  return `<li class="bubble assistant technical-error" data-role="error">${escapeHtml(text)}${retry}</li>`;
}

function renderRecovery(message) {
  const text =
    message.text ||
    "Não consegui confirmar o resultado desta operação. Verifique o histórico antes de reenviar.";
  return `<li class="bubble assistant recovery-card" data-role="recovery">${escapeHtml(text)}</li>`;
}

function renderData(data) {
  if (!data || !data.kind) return "";
  if (data.kind === "measurement_list" && data.items?.length) {
    const rows = data.items
      .map(
        (item) =>
          `<li>${escapeHtml(item.value || "")}${item.unit ? " " + escapeHtml(item.unit) : ""}</li>`
      )
      .join("");
    return `<ul class="fact-list">${rows}</ul>`;
  }
  if (data.kind === "fact_summary" && data.items?.length > 1) {
    const rows = data.items
      .map(
        (item) =>
          `<li>${escapeHtml(item.label || "")}: ${escapeHtml(String(item.value ?? ""))}</li>`
      )
      .join("");
    return `<ul class="fact-list">${rows}</ul>`;
  }
  return "";
}

function formatText(value) {
  const raw = String(value ?? "");
  const escaped = escapeHtml(raw);
  return escaped.replaceAll("\n", "<br />");
}

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function escapeAttr(value) {
  return escapeHtml(value).replaceAll("'", "&#39;");
}
