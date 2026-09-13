"""ResponsePresenter — capability-agnostic speech layer. Does not create knowledge."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from jamescore.observability.log import log_turn
from jamescore.observability.request_log import append_stage
from jamescore.presentation.contract import (
    ConversationSnippet,
    PresenterInput,
    from_capability_envelope,
    llm_payload,
)
from jamescore.presentation.prompts import PRESENTER_SYSTEM_PROMPT, presenter_user_payload
from jamescore.presentation.provider import (
    DeepSeekChatProvider,
    PresenterLlmResult,
    PresenterProvider,
    PresenterProviderError,
    PresenterTimeout,
)
from jamescore.presentation.validate import validate_presenter_text
from jamescore.settings import Settings


@dataclass(frozen=True)
class PresenterOutcome:
    text: str
    fallback_used: bool
    status: str
    model: str | None = None
    latency_ms: int = 0
    provider_request_id: str | None = None
    reason: str | None = None
    exception_class: str | None = None
    provider_error_code: str | None = None
    attempt: int = 0
    fallback_reason: str | None = None
    provider: str | None = None

    def trace(self) -> dict[str, Any]:
        return {
            "fallback_used": self.fallback_used,
            "status": self.status,
            "model": self.model,
            "latency_ms": self.latency_ms,
            "provider_request_id": self.provider_request_id,
            "reason": self.reason,
            "exception_class": self.exception_class,
            "provider_error_code": self.provider_error_code,
            "attempt": self.attempt,
            "fallback_reason": self.fallback_reason,
            "provider": self.provider,
        }


_DIM_PT = {
    "weight": "peso",
    "mass": "peso",
    "height": "altura",
    "temperature": "temperatura",
    "length": "comprimento",
}


def _entity_name(inp: PresenterInput) -> str | None:
    entity = inp.result.entity or {}
    name = entity.get("name") if isinstance(entity, dict) else None
    if name:
        return str(name)
    if inp.result.matched_entities:
        return inp.result.matched_entities[0]
    return None


def _measurement_bits(inp: PresenterInput) -> tuple[str | None, str | None]:
    result = inp.result
    unit = result.unit
    value = result.value
    if result.kind == "measurement" or result.dimension:
        if value is not None and result.matched_entities and value == result.matched_entities[0]:
            value = result.values[0] if result.values else value
        if result.values and (value is None or (result.entity and value == _entity_name(inp))):
            value = result.values[0]
    for item in result.items:
        if not isinstance(item, dict):
            continue
        if value is None and item.get("value") is not None:
            value = str(item["value"])
        if not unit and item.get("unit") is not None:
            unit = str(item["unit"])
    return value, unit


def structured_fallback(inp: PresenterInput) -> str | None:
    """Deterministic speech from structured result. Does not reread raw_input."""
    result = inp.result
    status = result.status
    kind = result.kind or ""
    name = _entity_name(inp)
    if status == "error":
        return "Não consegui consultar isso agora."
    if status == "committed":
        return "Entendi."
    if status == "partial":
        return "Entendi parte disso, mas não consegui guardar tudo."
    if status in {"deferred", "unsupported"} and (result.operation or "") == "knowledge_write":
        return (
            "Entendi o que você quis dizer, mas ainda não consigo guardar essa informação corretamente."
        )
    if status == "no_results" or kind == "absence":
        dim = _DIM_PT.get((result.dimension or "").casefold())
        if name and dim:
            return f"Ainda não sei a {dim} da {name}."
        if name:
            return f"Ainda não sei isso sobre {name}."
        return "Ainda não sei isso."
    if status == "needs_clarification" and result.candidates:
        labels = " ou ".join(result.candidates)
        return f"Você está falando da {labels}?"
    if status == "unsupported":
        return "Não consegui interpretar isso com segurança."
    if status == "insufficient":
        return "Preciso de um pouco mais de detalhe para responder."
    if result.relation_answer is True:
        return "Sim."
    if result.relation_answer is False:
        return "Pelo que sei, não."
    if kind == "measurement" or result.dimension in {"weight", "height", "temperature", "mass"}:
        value, unit = _measurement_bits(inp)
        if value is None:
            return None
        unit_s = f" {unit}" if unit else ""
        dim = (result.dimension or "").casefold()
        if name and dim in {"weight", "mass", "peso"}:
            return f"A {name} pesa {value}{unit_s}.".replace("  ", " ")
        if name and dim in {"temperature", "temperatura"}:
            return f"A {name} está a {value}{unit_s}.".replace("  ", " ")
        if name:
            return f"{name}: {value}{unit_s}.".replace("  ", " ")
        return f"{value}{unit_s}.".strip()
    if kind in {"attribute", "intrinsic_property", "state"} and result.value is not None:
        if name and str(result.value).casefold() != name.casefold():
            return f"{name}: {result.value}."
        return f"{result.value}."
    if status == "answered" and result.value is not None:
        return f"{result.value}."
    return None


def deterministic_fallback(inp: PresenterInput, capability_text: str) -> str:
    structured = structured_fallback(inp)
    if structured:
        return structured
    if inp.result.status == "error":
        return "Não consegui consultar isso agora."
    text = (capability_text or "").strip()
    if text:
        return text
    if inp.result.status == "no_results":
        return "Ainda não sei isso."
    if inp.result.status == "needs_clarification" and inp.result.candidates:
        labels = " ou ".join(inp.result.candidates)
        return f"Você está falando da {labels}?"
    if inp.result.status == "committed":
        return "Entendi."
    if inp.result.status == "partial":
        return "Entendi parte disso, mas não consegui guardar tudo."
    if inp.result.status == "deferred":
        return (
            "Entendi o que você quis dizer, mas ainda não consigo guardar essa informação corretamente."
        )
    if inp.result.status == "unsupported":
        if (inp.result.operation or "") == "knowledge_write":
            return (
                "Entendi o que você quis dizer, mas ainda não consigo guardar essa informação corretamente."
            )
        return "Não consegui interpretar isso com segurança."
    if inp.result.status == "insufficient":
        return "Preciso de um pouco mais de detalhe para responder."
    return "Não consegui responder isso agora."


class ResponsePresenter:
    def __init__(
        self,
        provider: PresenterProvider | None,
        *,
        enabled: bool = True,
        timeout_seconds: float = 8.0,
        model: str | None = None,
        base_url: str | None = None,
        credentials_present: bool | None = None,
    ) -> None:
        self._provider = provider
        self._enabled = enabled
        self._timeout_seconds = timeout_seconds if timeout_seconds > 0 else 8.0
        self._model = model
        self._base_url = base_url
        self._credentials_present = (
            bool(provider) if credentials_present is None else bool(credentials_present)
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> ResponsePresenter:
        key = (settings.presenter_api_key or "").strip()
        enabled = bool(settings.presenter_enabled)
        if not enabled or not key:
            return cls(
                None,
                enabled=False,
                timeout_seconds=settings.presenter_timeout_seconds,
                model=settings.presenter_model,
                base_url=settings.presenter_base_url,
                credentials_present=bool(key),
            )
        provider = DeepSeekChatProvider(
            api_key=key,
            base_url=settings.presenter_base_url,
            model=settings.presenter_model,
        )
        return cls(
            provider,
            enabled=True,
            timeout_seconds=settings.presenter_timeout_seconds,
            model=settings.presenter_model,
            base_url=settings.presenter_base_url,
            credentials_present=True,
        )

    @property
    def available(self) -> bool:
        return self._enabled and self._provider is not None

    def health_snapshot(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "enabled": self._enabled,
            "configured": bool(self._model) and bool(self._base_url) and self._credentials_present,
            "model": self._model,
            "base_url": self._base_url,
            "credentials_present": self._credentials_present,
        }

    def present_envelope(
        self,
        *,
        user_message: str,
        fallback_text: str,
        type_: str | None = None,
        outcome: str | None = None,
        operation: Any = None,
        data: Any = None,
        clarification: Any = None,
        error: Any = None,
        conversation_context: list[ConversationSnippet] | None = None,
        request_id: str | None = None,
        client_request_id: str | None = None,
        conversation_id: str | None = None,
        user_message_id: str | None = None,
    ) -> PresenterOutcome:
        inp = from_capability_envelope(
            user_message,
            type_=type_,
            outcome=outcome,
            operation=operation,
            data=data,
            clarification=clarification,
            error=error,
            conversation_context=conversation_context,
        )
        return self.present(
            inp,
            fallback_text=fallback_text,
            request_id=request_id,
            client_request_id=client_request_id,
            conversation_id=conversation_id,
            user_message_id=user_message_id,
        )

    def present(
        self,
        inp: PresenterInput,
        *,
        fallback_text: str,
        request_id: str | None = None,
        client_request_id: str | None = None,
        conversation_id: str | None = None,
        user_message_id: str | None = None,
    ) -> PresenterOutcome:
        fallback = deterministic_fallback(inp, fallback_text)
        model = self._model
        file_id = client_request_id or request_id
        provider_name = _provider_name(self._provider)
        payload = llm_payload(inp)
        structured = payload.get("structured_result") or {}
        log_turn(
            "presenter_request",
            stage="presenter_request",
            request_id=request_id or "-",
            model=model or "-",
            status=inp.result.status,
            available=int(self.available),
        )
        append_stage(
            file_id,
            "presenter_request",
            {
                "user_text": inp.user_message,
                "structured_result": structured,
                "presenter_provider": provider_name,
                "presenter_model": model,
                "attempt": 0 if not self.available else 1,
            },
            request_id=request_id,
            client_request_id=client_request_id,
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            operation=inp.result.operation,
            status=inp.result.status,
        )
        if not self.available:
            outcome = PresenterOutcome(
                text=fallback,
                fallback_used=True,
                status="unavailable",
                model=model,
                reason="presenter_unavailable",
                attempt=0,
                fallback_reason="presenter_unavailable",
                provider=provider_name,
            )
            self._log_response(
                request_id,
                outcome,
                client_request_id=client_request_id,
                conversation_id=conversation_id,
                user_message_id=user_message_id,
                provider_name=provider_name,
                fallback_status=inp.result.status,
            )
            return outcome

        started = time.perf_counter()
        try:
            raw = json.dumps(payload, ensure_ascii=False, indent=2)
            result: PresenterLlmResult = self._provider.complete(  # type: ignore[union-attr]
                system=PRESENTER_SYSTEM_PROMPT,
                user=presenter_user_payload(raw),
                timeout_seconds=self._timeout_seconds,
            )
        except PresenterTimeout:
            outcome = PresenterOutcome(
                text=fallback,
                fallback_used=True,
                status="timeout",
                model=model,
                latency_ms=int((time.perf_counter() - started) * 1000),
                reason="timeout",
                exception_class="PresenterTimeout",
                attempt=1,
                fallback_reason="timeout",
                provider=provider_name,
            )
            self._log_response(
                request_id,
                outcome,
                client_request_id=client_request_id,
                conversation_id=conversation_id,
                user_message_id=user_message_id,
                provider_name=provider_name,
                fallback_status=inp.result.status,
            )
            return outcome
        except PresenterProviderError as exc:
            outcome = PresenterOutcome(
                text=fallback,
                fallback_used=True,
                status="provider_error",
                model=model,
                latency_ms=int((time.perf_counter() - started) * 1000),
                reason=str(exc),
                exception_class=getattr(exc, "exception_class", None) or type(exc).__name__,
                provider_error_code=getattr(exc, "provider_error_code", None),
                attempt=1,
                fallback_reason="provider_error",
                provider=provider_name,
            )
            self._log_response(
                request_id,
                outcome,
                client_request_id=client_request_id,
                conversation_id=conversation_id,
                user_message_id=user_message_id,
                provider_name=provider_name,
                fallback_status=inp.result.status,
            )
            return outcome
        except Exception as extra:
            outcome = PresenterOutcome(
                text=fallback,
                fallback_used=True,
                status="error",
                model=model,
                latency_ms=int((time.perf_counter() - started) * 1000),
                reason="presenter_exception",
                exception_class=type(extra).__name__,
                attempt=1,
                fallback_reason="presenter_exception",
                provider=provider_name,
            )
            self._log_response(
                request_id,
                outcome,
                client_request_id=client_request_id,
                conversation_id=conversation_id,
                user_message_id=user_message_id,
                provider_name=provider_name,
                fallback_status=inp.result.status,
            )
            return outcome

        latency = result.latency_ms or int((time.perf_counter() - started) * 1000)
        text = _clean_reply(result.text)
        reason = validate_presenter_text(text, inp)
        if reason:
            outcome = PresenterOutcome(
                text=fallback,
                fallback_used=True,
                status="malformed",
                model=result.model,
                latency_ms=latency,
                provider_request_id=result.provider_request_id,
                reason=reason,
                attempt=1,
                fallback_reason="malformed_response",
                provider=provider_name,
            )
            self._log_response(
                request_id,
                outcome,
                client_request_id=client_request_id,
                conversation_id=conversation_id,
                user_message_id=user_message_id,
                provider_name=provider_name,
                fallback_status=inp.result.status,
            )
            return outcome
        outcome = PresenterOutcome(
            text=text,
            fallback_used=False,
            status="ok",
            model=result.model,
            latency_ms=latency,
            provider_request_id=result.provider_request_id,
            attempt=1,
            provider=provider_name,
        )
        self._log_response(
            request_id,
            outcome,
            client_request_id=client_request_id,
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            provider_name=provider_name,
        )
        return outcome

    def _log_response(
        self,
        request_id: str | None,
        outcome: PresenterOutcome,
        *,
        client_request_id: str | None = None,
        conversation_id: str | None = None,
        user_message_id: str | None = None,
        provider_name: str | None = None,
        fallback_status: str | None = None,
    ) -> None:
        log_turn(
            "presenter_response",
            stage="presenter_response",
            request_id=request_id or "-",
            provider_request_id=outcome.provider_request_id or "-",
            model=outcome.model or "-",
            latency_ms=outcome.latency_ms,
            status=outcome.status,
            fallback_used=int(outcome.fallback_used),
        )
        body: dict[str, Any] = {
            "text": outcome.text,
            "presenter_provider": provider_name or outcome.provider,
            "presenter_model": outcome.model,
            "provider": provider_name or outcome.provider,
            "model": outcome.model,
            "fallback_used": outcome.fallback_used,
            "latency_ms": outcome.latency_ms,
            "attempt": outcome.attempt,
        }
        if outcome.provider_request_id:
            body["provider_request_id"] = outcome.provider_request_id
        if outcome.exception_class:
            body["exception_class"] = outcome.exception_class
        if outcome.provider_error_code:
            body["provider_error_code"] = outcome.provider_error_code
        if outcome.reason:
            body["safe_error_message"] = outcome.reason
        if outcome.fallback_reason:
            body["fallback_reason"] = outcome.fallback_reason
        if outcome.fallback_used:
            body["status"] = "failed"
            body["reason"] = outcome.reason or outcome.status
            if fallback_status:
                body["fallback_template"] = fallback_status
                body["structured_result_status"] = fallback_status
        else:
            body["status"] = outcome.status
        append_stage(
            client_request_id or request_id,
            "presenter_response",
            body,
            request_id=request_id,
            client_request_id=client_request_id,
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            provider_request_id=outcome.provider_request_id,
            status=body["status"],
        )


def _provider_name(provider: PresenterProvider | None) -> str | None:
    if provider is None:
        return None
    if isinstance(provider, DeepSeekChatProvider):
        return "deepseek"
    return type(provider).__name__


def _clean_reply(text: str) -> str:
    reply = (text or "").strip()
    if reply.startswith("```"):
        reply = reply.strip("`").strip()
    if (reply.startswith('"') and reply.endswith('"')) or (
        reply.startswith("'") and reply.endswith("'")
    ):
        reply = reply[1:-1].strip()
    return " ".join(reply.split())
