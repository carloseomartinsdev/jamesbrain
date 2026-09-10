from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Any

from jamescore import __version__ as JAMESCORE_VERSION
from jamescore.application.envelopes import PublicEnvelope
from jamescore.application.store import ConversationRecord, ConversationStore
from jamescore.capabilities.future import FutureCapabilityRegistry
from jamescore.capabilities.social import SocialCapability
from jamescore.clients.pke import PkeClient
from jamescore.identity.principal import AuthenticatedPrincipal
from jamescore.observability.log import log_turn
from jamescore.tooling.registry import ToolRegistry


def _tools_package_version() -> str:
    env = os.environ.get("TOOLS_VERSION", "").strip()
    if env:
        return env
    brain = Path(__file__).resolve().parents[3].parent
    marker = brain / "tools" / "VERSION"
    if marker.is_file():
        text = marker.read_text(encoding="utf-8").strip()
        if text:
            return text.splitlines()[0].strip()
    return "0.1.0"


class Orchestrator:
    """James decides. Registry resolves. Tool executes. PKE is not a Tool."""

    def __init__(
        self,
        store: ConversationStore,
        pke: PkeClient,
        social: SocialCapability | None = None,
        tooling: ToolRegistry | None = None,
        future: FutureCapabilityRegistry | None = None,
    ) -> None:
        self._store = store
        self._pke = pke
        self._social = social or SocialCapability()
        self._tooling = tooling or ToolRegistry()
        self._future = future or FutureCapabilityRegistry()

    def health(self) -> dict[str, Any]:
        pke = self._pke.health()
        pke_body = pke.get("body") if isinstance(pke.get("body"), dict) else {}
        return {
            "status": "ok",
            "jamescore_version": JAMESCORE_VERSION,
            "pke": {
                "ok": bool(pke.get("ok")),
                "status": pke_body.get("status") if pke.get("ok") else "unavailable",
                "version": pke_body.get("version") if pke.get("ok") else None,
            },
            "tools": {
                "version": _tools_package_version(),
                "registered": self._tooling.registered_count(),
            },
            "tooling": {
                "registered": self._tooling.registered_count(),
                "note": "Tool Registry belongs to jamesCore; Tools are external. Empty in J1.1.",
            },
            "future_capabilities": {"registered": self._future.registered_count()},
        }

    def catalog(self) -> dict[str, Any]:
        result = self._pke.catalog()
        body = result.get("body") if isinstance(result.get("body"), dict) else {}
        if not result.get("ok"):
            return {
                "ok": False,
                "error": {
                    "code": result.get("error_code") or "PKE_UNAVAILABLE",
                    "message": "Catálogo do PKE indisponível.",
                },
            }
        return {"ok": True, "catalog": body}

    def create_conversation(self, principal: AuthenticatedPrincipal, title: str | None = None) -> dict[str, Any]:
        rec = self._store.create(principal.sub, title)
        return {
            "id": rec.id,
            "title": rec.title,
            "created_at": rec.created_at,
            "updated_at": rec.updated_at,
        }

    def list_messages(self, principal: AuthenticatedPrincipal, james_conversation_id: str) -> dict[str, Any]:
        rec = self._store.get(james_conversation_id, principal.sub)
        if rec is None:
            return {"ok": False, "error": {"code": "NOT_FOUND", "message": "Conversa não encontrada."}}
        return {"ok": True, "messages": self._store.list_messages(rec.id)}

    def handle_turn(
        self,
        principal: AuthenticatedPrincipal,
        text: str,
        james_conversation_id: str | None,
        trace: bool = False,
    ) -> PublicEnvelope:
        rec = self._require_conversation(principal, james_conversation_id)
        classified = self._social.classify(text)
        log_turn(
            "social",
            intent=classified.get("intent"),
            has_task=int(bool(classified.get("has_task"))),
            social_only=int(self._social.is_social_only(classified)),
        )

        if self._social.is_social_only(classified):
            reply = self._social.compose(
                classified["intent"],
                principal.display_name,
                classified["social_text"] or text,
            )
            self._store.append_message(rec.id, "user", text, type_="social")
            self._store.append_message(rec.id, "assistant", reply, type_="answer")
            return self._envelope(
                outcome="answer",
                rec=rec,
                text=reply,
                type_="answer",
                trace=self._trace(trace, source="social", social=classified),
            )

        forward = classified["task_text"] if self._social.should_prefix_social(classified) else text
        if not forward:
            forward = text

        pke_env = self._call_pke_send(principal, rec, forward, trace)
        if pke_env.outcome == "technical_error":
            return pke_env

        display = pke_env.text
        if self._social.should_prefix_social(classified):
            prefix = self._social.compose_prefix(
                classified["intent"],
                principal.display_name,
                classified["social_text"] or text,
            )
            display = self._social.merge_prefix(prefix, display)
            pke_env = pke_env.model_copy(update={"text": display})

        self._store.append_message(rec.id, "user", text, type_="user")
        self._store.append_message(rec.id, "assistant", pke_env.text, type_=pke_env.type)
        return pke_env

    def answer_clarification(
        self,
        principal: AuthenticatedPrincipal,
        clarification_id: str,
        text: str,
        option_id: str,
        james_conversation_id: str | None = None,
        trace: bool = False,
    ) -> PublicEnvelope:
        rec = None
        if james_conversation_id:
            rec = self._store.get(james_conversation_id, principal.sub)
        rid = secrets.token_hex(16)
        result = self._pke.answer_clarification(
            principal,
            clarification_id,
            {"text": text, "option_id": option_id},
            rid,
        )
        env = self._map_pke_result(result, rec, trace, path="POST /api/v1/clarifications/{id}/answer")
        if not env.client_request_id:
            env = env.model_copy(update={"client_request_id": rid})
        if rec is not None and env.outcome != "technical_error":
            shown = option_id or text
            self._store.append_message(rec.id, "user", shown, type_="clarification_answer")
            self._store.append_message(rec.id, "assistant", env.text, type_=env.type)
        return env

    def _require_conversation(
        self, principal: AuthenticatedPrincipal, james_conversation_id: str | None
    ) -> ConversationRecord:
        if james_conversation_id:
            rec = self._store.get(james_conversation_id, principal.sub)
            if rec is not None:
                return rec
        return self._store.create(principal.sub)

    def _ensure_pke_conversation(self, principal: AuthenticatedPrincipal, rec: ConversationRecord) -> str | None:
        if rec.pke_conversation_id:
            return rec.pke_conversation_id
        created = self._pke.create_conversation(principal, rec.title)
        if not created.get("ok"):
            return None
        body = created.get("body") or {}
        pke_id = body.get("id") if isinstance(body, dict) else None
        if isinstance(pke_id, str) and pke_id:
            self._store.bind_pke(rec.id, pke_id)
            rec.pke_conversation_id = pke_id
            return pke_id
        return None

    def _call_pke_send(
        self,
        principal: AuthenticatedPrincipal,
        rec: ConversationRecord,
        text: str,
        trace: bool,
    ) -> PublicEnvelope:
        pke_id = self._ensure_pke_conversation(principal, rec)
        if pke_id is None and rec.pke_conversation_id is None:
            # Still attempt send without conversation; PKE may create one.
            pass
        rid = secrets.token_hex(16)
        result = self._pke.send_message(principal, text, rec.pke_conversation_id, rid)
        env = self._map_pke_result(result, rec, trace, path="POST /api/v1/messages")
        if not env.client_request_id:
            env = env.model_copy(update={"client_request_id": rid})
        if env.outcome != "technical_error":
            body = result.get("body") if isinstance(result.get("body"), dict) else {}
            pke_conv = body.get("conversation_id") if isinstance(body, dict) else None
            if isinstance(pke_conv, str) and pke_conv and rec.pke_conversation_id != pke_conv:
                self._store.bind_pke(rec.id, pke_conv)
                rec.pke_conversation_id = pke_conv
        return env

    def _map_pke_result(
        self,
        result: dict[str, Any],
        rec: ConversationRecord | None,
        trace: bool,
        path: str,
    ) -> PublicEnvelope:
        james_id = rec.id if rec else None
        if not result.get("ok"):
            code = result.get("error_code") or "PKE_UNAVAILABLE"
            if code in {"PKE_TIMEOUT", "PKE_UNAVAILABLE", "PKE_ERROR", "PROVIDER_UNAVAILABLE"}:
                msg = "Não foi possível processar sua mensagem agora."
                if code == "PKE_TIMEOUT":
                    msg = "O PKE demorou demais para responder."
                return self._envelope(
                    outcome="technical_error",
                    rec=rec,
                    text=msg,
                    type_="error",
                    status="failed",
                    error={"code": code, "message": msg},
                    trace=self._trace(trace, source="pke", path=path, pke=result),
                )
            body = result.get("body") if isinstance(result.get("body"), dict) else {}
            err = body.get("error") if isinstance(body.get("error"), dict) else {"code": code, "message": "Pedido inválido."}
            return self._envelope(
                outcome="technical_error",
                rec=rec,
                text=str(err.get("message") or "Pedido inválido."),
                type_="error",
                status="failed",
                error=err,
                trace=self._trace(trace, source="pke", path=path, pke=result),
            )

        body = result.get("body") if isinstance(result.get("body"), dict) else {}
        pke_type = str(body.get("type") or "answer")
        text = str(body.get("text") or "")
        if pke_type == "unsupported":
            return self._envelope(
                outcome="safe_abstain",
                rec=rec,
                text=text,
                type_="unsupported",
                clarification=body.get("clarification"),
                data=body.get("data"),
                operation=body.get("operation"),
                message_id=body.get("message_id"),
                user_message_id=body.get("user_message_id"),
                request_id=body.get("request_id"),
                trace=self._trace(trace, source="pke", path=path, pke=result),
            )
        if pke_type == "clarification":
            return self._envelope(
                outcome="clarification",
                rec=rec,
                text=text,
                type_="clarification",
                clarification=body.get("clarification"),
                data=body.get("data"),
                operation=body.get("operation"),
                message_id=body.get("message_id"),
                request_id=body.get("request_id"),
                trace=self._trace(trace, source="pke", path=path, pke=result),
            )
        if pke_type == "error":
            err = body.get("error") if isinstance(body.get("error"), dict) else {"message": text or "Erro no PKE."}
            return self._envelope(
                outcome="technical_error",
                rec=rec,
                text=str(err.get("message") or text),
                type_="error",
                status="failed",
                error=err,
                trace=self._trace(trace, source="pke", path=path, pke=result),
            )
        return self._envelope(
            outcome="answer",
            rec=rec,
            text=text,
            type_=pke_type,
            status=str(body.get("status") or "ok"),
            clarification=body.get("clarification"),
            data=body.get("data"),
            operation=body.get("operation"),
            message_id=body.get("message_id"),
            user_message_id=body.get("user_message_id"),
            request_id=body.get("request_id"),
            trace=self._trace(trace, source="pke", path=path, pke=result),
        )

    def _envelope(
        self,
        *,
        outcome: str,
        rec: ConversationRecord | None,
        text: str,
        type_: str,
        status: str = "ok",
        clarification: Any = None,
        data: Any = None,
        error: Any = None,
        operation: Any = None,
        message_id: Any = None,
        user_message_id: Any = None,
        request_id: Any = None,
        client_request_id: Any = None,
        trace: dict[str, Any] | None = None,
    ) -> PublicEnvelope:
        return PublicEnvelope(
            outcome=outcome,  # type: ignore[arg-type]
            james_conversation_id=rec.id if rec else None,
            text=text,
            type=type_,
            status=status,
            clarification=clarification,
            data=data,
            error=error,
            operation=operation,
            message_id=str(message_id) if message_id else None,
            user_message_id=str(user_message_id) if user_message_id else None,
            request_id=str(request_id) if request_id else None,
            client_request_id=str(client_request_id) if client_request_id else None,
            trace=trace,
        )

    def _trace(self, enabled: bool, **meta: Any) -> dict[str, Any] | None:
        if not enabled:
            return None
        return meta
