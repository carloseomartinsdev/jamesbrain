from __future__ import annotations

import json

from jamescore.presentation.contract import from_capability_envelope, llm_payload
from jamescore.presentation.presenter import ResponsePresenter
from jamescore.presentation.prompts import PRESENTER_SYSTEM_PROMPT
from jamescore.presentation.provider import (
    PresenterLlmResult,
    PresenterProviderError,
    PresenterTimeout,
)
from jamescore.presentation.validate import validate_presenter_text


class ScriptedProvider:
    def __init__(self, text: str | None = None, fn=None, error: Exception | None = None) -> None:
        self.text = text
        self.fn = fn
        self.error = error
        self.calls: list[dict] = []

    def complete(self, *, system: str, user: str, timeout_seconds: float) -> PresenterLlmResult:
        self.calls.append({"system": system, "user": user, "timeout": timeout_seconds})
        if self.error is not None:
            raise self.error
        text = self.fn(system, user) if self.fn else (self.text or "")
        return PresenterLlmResult(
            text=text, model="fake-presenter", latency_ms=4, provider_request_id="prv-1"
        )


def _payload(user: str) -> dict:
    return json.loads(user[user.index("{") :])


def _present(provider, user_message: str, **envelope) -> tuple:
    fallback = envelope.pop("_fallback", None) or "FALLBACK"
    presenter = ResponsePresenter(provider, enabled=True, model="fake-presenter")
    inp = from_capability_envelope(user_message, **envelope)
    outcome = presenter.present(inp, fallback_text=fallback)
    return inp, outcome


def test_prompt_is_not_interpreter():
    assert "response presenter" in PRESENTER_SYSTEM_PROMPT.lower()
    assert "semantic ir" not in PRESENTER_SYSTEM_PROMPT.lower()
    assert "must not" in PRESENTER_SYSTEM_PROMPT.lower()


def test_answered_attribute_luna():
    provider = ScriptedProvider(text="O nome dela é Luna.")
    inp, out = _present(
        provider,
        "qual o nome da minha gata?",
        type_="answer",
        operation={"kind": "knowledge_query", "outcome": "answered"},
        data={"status": "answered", "kind": "attribute", "items": [{"label": "name", "value": "Luna"}]},
        _fallback="Encontrei Luna.",
    )
    assert out.fallback_used is False
    assert "Luna" in out.text
    assert "siamesa" not in out.text
    assert inp.result.status == "answered"
    assert inp.result.value == "Luna"
    assert "registr" not in out.text.lower()


def test_answered_boolean_true_with_name():
    provider = ScriptedProvider(text="Sim, você tem a Luna.")
    _, out = _present(
        provider,
        "eu tenho uma gata?",
        type_="answer",
        operation={"kind": "knowledge_query", "outcome": "answered"},
        data={
            "status": "answered",
            "kind": "relation",
            "relation_answer": "yes",
            "matched_entities": [{"canonical_name": "Luna"}],
        },
        _fallback="Sim.",
    )
    assert out.fallback_used is False
    assert "Luna" in out.text
    assert out.text.lower().startswith("sim")


def test_answered_boolean_false_not_unknown():
    provider = ScriptedProvider(text="Pelo que sei, não.")
    inp, out = _present(
        provider,
        "eu tenho cachorro?",
        type_="answer",
        operation={"kind": "knowledge_query", "outcome": "answered"},
        data={"status": "answered", "kind": "relation", "relation_answer": "no"},
        _fallback="Não.",
    )
    assert inp.result.relation_answer is False
    assert out.fallback_used is False
    assert "ainda não sei" not in out.text.lower()


def test_false_flipped_to_unknown_is_rejected():
    provider = ScriptedProvider(text="Ainda não sei.")
    _, out = _present(
        provider,
        "eu tenho cachorro?",
        type_="answer",
        data={"status": "answered", "kind": "relation", "relation_answer": "no"},
        _fallback="Não.",
    )
    assert out.fallback_used is True
    assert out.status == "malformed"
    assert "não" in out.text.casefold()
    assert "ainda não sei" not in out.text.casefold()


def test_no_results_not_false():
    provider = ScriptedProvider(text="Ainda não sei a cor da sua bicicleta.")
    inp, out = _present(
        provider,
        "qual a cor da minha bicicleta?",
        type_="answer",
        operation={"kind": "knowledge_query", "outcome": "answered"},
        data={"status": "no_results", "kind": "absence"},
        _fallback="Não encontrei um registro sobre isso.",
    )
    assert inp.result.status == "no_results"
    assert out.fallback_used is False
    assert "ainda não sei" in out.text.lower()
    assert out.text.strip().lower() != "não."


def test_no_results_as_nao_is_rejected():
    provider = ScriptedProvider(text="Não.")
    _, out = _present(
        provider,
        "qual a cor da minha bicicleta?",
        type_="answer",
        data={"status": "no_results", "kind": "absence"},
        _fallback="Não encontrei um registro sobre isso.",
    )
    assert out.fallback_used is True
    assert out.reason == "no_results_as_false"


def test_car_color():
    provider = ScriptedProvider(text="Seu carro é azul.")
    _, out = _present(
        provider,
        "qual a cor do meu carro?",
        type_="answer",
        data={"status": "answered", "kind": "attribute", "items": [{"label": "color", "value": "azul"}]},
        _fallback="Encontrei azul.",
    )
    assert out.fallback_used is False
    assert "azul" in out.text.lower()


def test_committed_acknowledgement():
    provider = ScriptedProvider(text="Entendi, sua gata se chama Luna.")
    _, out = _present(
        provider,
        "eu tenho uma gata chamada Luna",
        type_="acknowledgement",
        operation={"kind": "knowledge_write", "outcome": "committed"},
        data={"status": "committed", "kind": "acknowledgement"},
        _fallback="Certo. Registrei essa informação.",
    )
    assert out.fallback_used is False
    assert "Luna" in out.text
    assert "registr" not in out.text.lower()


def test_clarification_candidates():
    provider = ScriptedProvider(text="Você está falando da Luna ou da Nala?")
    _, out = _present(
        provider,
        "qual o nome da minha gata?",
        type_="clarification",
        operation={"kind": "clarification", "outcome": "needs_clarification"},
        data={
            "status": "needs_clarification",
            "reason": "multiple_entity_candidates",
            "candidates": ["Luna", "Nala"],
        },
        clarification={"id": "c1", "mode": "choice", "options": [{"id": "1", "label": "Luna"}, {"id": "2", "label": "Nala"}]},
        _fallback="Foram encontradas múltiplas entidades candidatas.",
    )
    assert out.fallback_used is False
    assert "Luna" in out.text and "Nala" in out.text


def test_insufficient():
    provider = ScriptedProvider(text="Preciso saber de qual carro você está falando.")
    _, out = _present(
        provider,
        "qual a cor?",
        type_="clarification",
        data={"status": "insufficient", "reason": "carro", "candidates": []},
        _fallback="Semantic roles insufficient.",
    )
    assert out.fallback_used is False
    assert "carro" in out.text.lower()


def test_unsupported():
    provider = ScriptedProvider(text="Não consegui interpretar isso com segurança.")
    _, out = _present(
        provider,
        "blorp ziggle",
        type_="unsupported",
        data={"status": "unsupported", "kind": "interpretation"},
        _fallback="Ainda não consigo responder isso com segurança.",
    )
    assert out.fallback_used is False
    assert "interpret" in out.text.lower() or "entender" in out.text.lower()


def test_error_is_not_unknown():
    provider = ScriptedProvider(text="Não consegui consultar isso agora.")
    inp, out = _present(
        provider,
        "qual o nome do meu gato?",
        type_="error",
        outcome="technical_error",
        error={"code": "PKE_TIMEOUT", "message": "timeout"},
        data={"status": "error", "code": "PKE_TIMEOUT"},
        _fallback="O PKE demorou demais para responder.",
    )
    assert inp.result.status == "error"
    assert out.fallback_used is False
    assert "ainda não sei" not in out.text.lower()
    assert "pke" not in out.text.lower()


def test_error_unknown_wording_rejected():
    provider = ScriptedProvider(text="Ainda não sei.")
    _, out = _present(
        provider,
        "qual o nome do meu gato?",
        outcome="technical_error",
        type_="error",
        error={"code": "PKE_TIMEOUT", "message": "timeout"},
        _fallback="Não consegui consultar isso agora.",
    )
    assert out.fallback_used is True
    assert out.text == "Não consegui consultar isso agora."


def test_anti_hallucination():
    provider = ScriptedProvider(text="O nome da sua gata siamesa de três anos é Luna.")
    _, out = _present(
        provider,
        "qual o nome do meu gato?",
        type_="answer",
        data={"status": "answered", "kind": "attribute", "items": [{"label": "name", "value": "Luna"}]},
        _fallback="Encontrei Luna.",
    )
    assert out.fallback_used is True
    assert out.reason == "unattested_facts"
    assert "Luna" in out.text
    assert "siamesa" not in out.text.lower()


def test_implementation_terms_rejected_in_normal_chat():
    provider = ScriptedProvider(text="Encontrei o registro da entidade Luna no PKE.")
    _, out = _present(
        provider,
        "qual o nome do meu gato?",
        type_="answer",
        data={"status": "answered", "kind": "attribute", "items": [{"label": "name", "value": "Luna"}]},
        _fallback="Encontrei Luna.",
    )
    assert out.fallback_used is True
    assert out.reason == "implementation_term"


def test_technical_question_allows_internal_terms():
    text = "No PKE, o registro de Luna tem o nome Luna."
    inp = from_capability_envelope(
        "o que está registrado no PKE sobre Luna?",
        type_="answer",
        data={"status": "answered", "kind": "attribute", "items": [{"label": "name", "value": "Luna"}]},
    )
    assert inp.technical_question is True
    assert validate_presenter_text(text, inp) is None


def test_languages_pt_en_es():
    def fn(system, user):
        payload = _payload(user)
        lang = payload["language_hint"]
        if lang == "en":
            return "Her name is Luna."
        if lang == "es":
            return "Se llama Luna."
        return "O nome dela é Luna."

    provider = ScriptedProvider(fn=fn)
    presenter = ResponsePresenter(provider, enabled=True, model="fake-presenter")
    data = {"status": "answered", "kind": "attribute", "items": [{"label": "name", "value": "Luna"}]}
    cases = [
        ("Qual o nome da minha gata?", "pt", "luna"),
        ("What is my cat's name?", "en", "luna"),
        ("¿Cómo se llama mi gata?", "es", "luna"),
    ]
    for message, lang, needle in cases:
        inp = from_capability_envelope(message, type_="answer", data=data)
        assert inp.language_hint == lang
        out = presenter.present(inp, fallback_text="Encontrei Luna.")
        assert out.fallback_used is False
        assert needle in out.text.lower()
        dumped = llm_payload(inp)
        assert dumped["structured_result"]["value"] == "Luna"


def test_timeout_uses_fallback():
    provider = ScriptedProvider(error=PresenterTimeout("timeout"))
    _, out = _present(
        provider,
        "qual o nome do meu gato?",
        type_="answer",
        data={"status": "answered", "kind": "attribute", "items": [{"label": "name", "value": "Luna"}]},
        _fallback="Encontrei Luna.",
    )
    assert out.fallback_used is True
    assert out.status == "timeout"
    assert "Luna" in out.text
    assert "encontrei" not in out.text.casefold()


def test_malformed_empty_uses_fallback():
    provider = ScriptedProvider(text="   ")
    _, out = _present(
        provider,
        "qual o nome do meu gato?",
        type_="answer",
        data={"status": "answered", "kind": "attribute", "items": [{"label": "name", "value": "Luna"}]},
        _fallback="Encontrei Luna.",
    )
    assert out.fallback_used is True
    assert out.status == "malformed"


def test_disabled_presenter_keeps_template():
    presenter = ResponsePresenter(None, enabled=False)
    inp = from_capability_envelope(
        "qual o nome do meu gato?",
        type_="answer",
        data={"status": "answered", "kind": "attribute", "items": [{"label": "name", "value": "Luna"}]},
    )
    out = presenter.present(inp, fallback_text="Encontrei Luna.")
    assert out.fallback_used is True
    assert out.text == "Luna."


def test_no_results_heuristic_without_data():
    inp = from_capability_envelope(
        "qual a cor da minha bicicleta?",
        type_="answer",
        operation={"kind": "knowledge_query", "outcome": "answered"},
        data=None,
    )
    assert inp.result.status == "no_results"


def test_llm_payload_does_not_include_graph_or_logs():
    inp = from_capability_envelope(
        "qual o nome do meu gato?",
        type_="answer",
        data={"status": "answered", "kind": "attribute", "items": [{"label": "name", "value": "Luna"}]},
    )
    dumped = json.dumps(llm_payload(inp))
    assert "knowledge_graph" not in dumped
    assert "logs" not in dumped
    assert PRESENTER_SYSTEM_PROMPT not in dumped


def test_presenter_request_response_trace(tmp_path, monkeypatch):
    monkeypatch.setenv("PKE_REQUEST_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("PKE_REQUEST_LOG", "1")
    provider = ScriptedProvider(text="O nome dela é Luna.")
    presenter = ResponsePresenter(provider, enabled=True, model="fake-presenter")
    inp = from_capability_envelope(
        "qual o nome do meu gato?",
        type_="answer",
        operation={"kind": "knowledge_query", "outcome": "answered"},
        data={"status": "answered", "kind": "attribute", "items": [{"label": "name", "value": "Luna"}]},
    )
    out = presenter.present(
        inp,
        fallback_text="Encontrei Luna.",
        request_id="pke-1",
        client_request_id="req-presenter",
        conversation_id="conv-1",
    )
    assert out.fallback_used is False
    text = next(tmp_path.glob("*_req-presenter.log")).read_text(encoding="utf-8")
    assert "stage=presenter_request" in text
    assert "stage=presenter_response" in text
    assert '"value": "Luna"' in text
    assert "O nome dela é Luna." in text
    assert '"fallback_used": false' in text
    assert "PRESENTER_SYSTEM_PROMPT" not in text
    assert "Authorization" not in text
    assert inp.result.value == "Luna"


def test_presenter_fallback_trace(tmp_path, monkeypatch):
    monkeypatch.setenv("PKE_REQUEST_LOG_DIR", str(tmp_path))
    monkeypatch.setenv("PKE_REQUEST_LOG", "1")
    provider = ScriptedProvider(error=PresenterTimeout("boom"))
    presenter = ResponsePresenter(provider, enabled=True, model="fake-presenter")
    inp = from_capability_envelope(
        "qual o nome do meu gato?",
        type_="answer",
        data={"status": "answered", "kind": "attribute", "items": [{"label": "name", "value": "Luna"}]},
    )
    out = presenter.present(
        inp,
        fallback_text="Encontrei Luna.",
        client_request_id="req-presenter-fb",
    )
    assert out.fallback_used is True
    assert "Luna" in out.text
    assert "encontrei" not in out.text.casefold()
    text = next(tmp_path.glob("*_req-presenter-fb.log")).read_text(encoding="utf-8")
    assert "stage=presenter_response" in text
    assert '"status": "failed"' in text
    assert '"fallback_used": true' in text
    assert '"fallback_template": "answered"' in text


def _measurement_data(**extra):
    body = {
        "status": "answered",
        "kind": "measurement",
        "entity": {"name": "Luna", "entity_id": "e-luna"},
        "dimension": "weight",
        "value": "4",
        "unit": "kg",
        "items": [{"label": "weight", "value": "4", "unit": "kg"}],
    }
    body.update(extra)
    return body


def test_measurement_envelope_keeps_value_and_unit():
    inp = from_capability_envelope(
        "qual o peso da Luna?",
        type_="answer",
        operation={"kind": "knowledge_query", "outcome": "answered"},
        data=_measurement_data(),
    )
    assert inp.result.status == "answered"
    assert inp.result.kind == "measurement"
    assert inp.result.value == "4"
    assert inp.result.unit == "kg"
    assert inp.result.dimension == "weight"
    dumped = llm_payload(inp)
    structured = dumped["structured_result"]
    assert structured["kind"] == "measurement"
    assert structured["value"] == "4"
    assert structured["unit"] == "kg"
    assert structured["items"]


def test_measurement_zero_is_not_no_results():
    inp = from_capability_envelope(
        "qual a temperatura da Luna?",
        type_="answer",
        operation={"kind": "knowledge_query", "outcome": "answered"},
        data={
            "status": "answered",
            "kind": "measurement",
            "entity": {"name": "Luna"},
            "dimension": "temperature",
            "value": "0",
            "unit": "°C",
            "items": [{"label": "temperature", "value": "0", "unit": "°C"}],
        },
    )
    assert inp.result.status == "answered"
    assert inp.result.value == "0"
    assert inp.result.kind != "absence"


def test_relation_false_is_not_no_results():
    inp = from_capability_envelope(
        "eu tenho cachorro?",
        type_="answer",
        data={"status": "answered", "kind": "relation", "relation_answer": False},
    )
    assert inp.result.status == "answered"
    assert inp.result.relation_answer is False


def test_answered_engine_payload_not_demoted_from_empty_value():
    inp = from_capability_envelope(
        "qual o peso da Luna?",
        type_="answer",
        operation={"kind": "knowledge_query", "outcome": "answered"},
        data={
            "status": "answered",
            "kind": "measurement",
            "dimension": "weight",
            "value": None,
            "items": [{"label": "weight", "value": "4", "unit": "kg"}],
        },
    )
    assert inp.result.status == "answered"
    assert "4" in inp.result.values


def test_presenter_measurement_success():
    provider = ScriptedProvider(text="A Luna pesa 4 kg.")
    inp, out = _present(
        provider,
        "qual o peso da Luna?",
        type_="answer",
        operation={"kind": "knowledge_query", "outcome": "answered"},
        data=_measurement_data(),
        _fallback="A Luna pesa 4 kg.",
    )
    assert out.fallback_used is False
    assert out.status == "ok"
    folded = out.text.casefold()
    assert "luna" in folded
    assert "4" in out.text
    assert "kg" in folded or "quilo" in folded
    assert inp.result.status == "answered"


def test_presenter_measurement_unavailable_keeps_fact():
    provider = ScriptedProvider(error=PresenterProviderError("presenter llm unavailable"))
    inp, out = _present(
        provider,
        "qual o peso da Luna?",
        type_="answer",
        operation={"kind": "knowledge_query", "outcome": "answered"},
        data=_measurement_data(),
        _fallback="Encontrei 4.",
    )
    assert out.fallback_used is True
    assert out.status == "provider_error"
    assert "Luna" in out.text
    assert "4" in out.text
    assert "kg" in out.text
    assert inp.result.status == "answered"
    assert inp.result.kind == "measurement"


def test_presenter_measurement_timeout_keeps_fact():
    provider = ScriptedProvider(error=PresenterTimeout("presenter llm timeout"))
    inp, out = _present(
        provider,
        "qual o peso da Luna?",
        type_="answer",
        data=_measurement_data(),
        _fallback="Encontrei 4.",
    )
    assert out.fallback_used is True
    assert out.status == "timeout"
    assert "Luna" in out.text
    assert "4 kg" in out.text
    assert inp.result.status == "answered"


def test_write_deferred_fallback_does_not_say_entendi():
    provider = ScriptedProvider(error=PresenterProviderError("presenter llm unavailable"))
    inp, out = _present(
        provider,
        "a luna tem pelos brancos",
        type_="acknowledgement",
        operation={"kind": "knowledge_write", "outcome": "deferred"},
        data={
            "status": "deferred",
            "kind": "acknowledgement",
            "claims": {"received": 1, "committed": 0, "deferred": 1, "rejected": 0},
        },
        _fallback="Entendi.",
    )
    assert inp.result.status == "deferred"
    assert inp.result.claims == {"received": 1, "committed": 0, "deferred": 1, "rejected": 0}
    assert out.fallback_used is True
    assert out.text != "Entendi."
    assert "guardar" in out.text


def test_write_partial_fallback():
    provider = ScriptedProvider(error=PresenterTimeout("presenter llm timeout"))
    inp, out = _present(
        provider,
        "várias coisas",
        type_="acknowledgement",
        operation={"kind": "knowledge_write", "outcome": "partial"},
        data={
            "status": "partial",
            "kind": "acknowledgement",
            "claims": {"received": 3, "committed": 2, "deferred": 1},
        },
        _fallback="Entendi.",
    )
    assert inp.result.status == "partial"
    assert out.fallback_used is True
    assert "parte" in out.text


def test_write_committed_unavailable_uses_entendi():
    presenter = ResponsePresenter(None, enabled=False, model="none")
    inp = from_capability_envelope(
        "a luna tem pelos brancos",
        type_="acknowledgement",
        operation={"kind": "knowledge_write", "outcome": "committed"},
        data={"status": "committed", "kind": "acknowledgement", "claims": {"received": 1, "committed": 1}},
    )
    out = presenter.present(inp, fallback_text="FALLBACK")
    assert inp.result.status == "committed"
    assert out.fallback_used is True
    assert out.text == "Entendi."
    assert out.status == "unavailable"


def test_presenter_success_does_not_mutate_structured_status():
    provider = ScriptedProvider(text="Entendi, pelos brancos.")
    inp, out = _present(
        provider,
        "a luna tem pelos brancos",
        type_="acknowledgement",
        operation={"kind": "knowledge_write", "outcome": "committed"},
        data={"status": "committed", "kind": "acknowledgement"},
        _fallback="Entendi.",
    )
    assert out.fallback_used is False
    assert inp.result.status == "committed"


def test_presenter_malformed_keeps_write_status():
    provider = ScriptedProvider(text="")
    inp, out = _present(
        provider,
        "a luna tem pelos brancos",
        type_="acknowledgement",
        operation={"kind": "knowledge_write", "outcome": "deferred"},
        data={"status": "deferred", "kind": "acknowledgement"},
        _fallback="Entendi.",
    )
    assert out.fallback_used is True
    assert out.status == "malformed"
    assert inp.result.status == "deferred"
    assert out.text != "Entendi."


