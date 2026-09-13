from pathlib import Path

from jamescore.application.orchestrator import Orchestrator
from jamescore.application.store import ConversationStore
from jamescore.identity.principal import AuthenticatedPrincipal
from jamescore.presentation.presenter import ResponsePresenter
from jamescore.presentation.provider import PresenterLlmResult, PresenterProviderError


class _PkeOk:
    def health(self):
        return {"ok": True, "body": {"status": "ok", "version": "test"}}

    def catalog(self):
        return {"ok": True, "body": {}}

    def create_conversation(self, principal, title=None):
        return {"ok": True, "http": 200, "body": {"id": "pke-conv-1"}}

    def send_message(self, principal, text, pke_conversation_id, client_request_id):
        return {
            "ok": True,
            "http": 200,
            "body": {
                "conversation_id": "pke-conv-1",
                "message_id": "m1",
                "type": "answer",
                "status": "completed",
                "text": "Encontrei Luna.",
                "data": {
                    "status": "answered",
                    "kind": "attribute",
                    "items": [{"label": "name", "value": "Luna"}],
                },
                "operation": {"kind": "knowledge_query", "outcome": "answered"},
                "request_id": "req-1",
            },
            "error_code": None,
        }


class _PkeTimeout:
    def health(self):
        return {"ok": False, "body": {}}

    def create_conversation(self, principal, title=None):
        return {"ok": False, "error_code": "PKE_TIMEOUT", "body": {}}

    def send_message(self, principal, text, pke_conversation_id, client_request_id):
        return {"ok": False, "http": 0, "body": {}, "error_code": "PKE_TIMEOUT"}


class _NaturalProvider:
    def complete(self, *, system, user, timeout_seconds):
        return PresenterLlmResult(
            text="O nome dela é Luna.",
            model="fake-presenter",
            latency_ms=5,
            provider_request_id="prv-orch",
        )


def test_orchestrator_uses_presenter_text(tmp_path: Path):
    orch = Orchestrator(
        store=ConversationStore(tmp_path / "c.sqlite"),
        pke=_PkeOk(),
        presenter=ResponsePresenter(_NaturalProvider(), enabled=True, model="fake-presenter"),
    )
    env = orch.handle_turn(AuthenticatedPrincipal(sub="1", display_name="Carlos"), "qual o nome da minha gata?", None)
    assert env.outcome == "answer"
    assert env.text == "O nome dela é Luna."
    assert "Encontrei" not in env.text


def test_orchestrator_timeout_is_failure_not_unknown(tmp_path: Path):
    orch = Orchestrator(
        store=ConversationStore(tmp_path / "c.sqlite"),
        pke=_PkeTimeout(),
        presenter=ResponsePresenter(None, enabled=False),
    )
    env = orch.handle_turn(AuthenticatedPrincipal(sub="1"), "qual o nome do meu gato?", None)
    assert env.outcome == "technical_error"
    assert env.text == "Não consegui consultar isso agora."
    assert "ainda não sei" not in env.text.lower()
    assert "pke" not in env.text.lower()


class _PkeMeasurement:
    def health(self):
        return {"ok": True, "body": {"status": "ok", "version": "test"}}

    def catalog(self):
        return {"ok": True, "body": {}}

    def create_conversation(self, principal, title=None):
        return {"ok": True, "http": 200, "body": {"id": "pke-conv-m"}}

    def send_message(self, principal, text, pke_conversation_id, client_request_id):
        return {
            "ok": True,
            "http": 200,
            "body": {
                "conversation_id": "pke-conv-m",
                "message_id": "m-m",
                "type": "answer",
                "status": "completed",
                "text": "A Luna pesa 4 kg.",
                "data": {
                    "status": "answered",
                    "kind": "measurement",
                    "entity": {"name": "Luna"},
                    "dimension": "weight",
                    "value": "4",
                    "unit": "kg",
                    "items": [{"label": "weight", "value": "4", "unit": "kg"}],
                },
                "operation": {"kind": "knowledge_query", "outcome": "answered"},
                "request_id": "req-m",
            },
            "error_code": None,
        }


class _FailingProvider:
    def complete(self, *, system, user, timeout_seconds):
        raise PresenterProviderError("presenter llm unavailable")


def test_presenter_failure_does_not_change_knowledge_status(tmp_path: Path):
    orch = Orchestrator(
        store=ConversationStore(tmp_path / "c.sqlite"),
        pke=_PkeMeasurement(),
        presenter=ResponsePresenter(_FailingProvider(), enabled=True, model="fake-presenter"),
    )
    env = orch.handle_turn(
        AuthenticatedPrincipal(sub="1", display_name="Carlos"),
        "qual o peso da Luna?",
        None,
    )
    assert env.outcome == "answer"
    assert env.data["status"] == "answered"
    assert env.data["kind"] == "measurement"
    assert env.data["value"] == "4"
    assert "Luna" in env.text
    assert "4" in env.text
    assert env.trace is None or env.trace.get("presenter", {}).get("fallback_used") is True
