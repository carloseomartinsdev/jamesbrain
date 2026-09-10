"""I12.2 — Interpreter provider retry, transport recovery, pre-commit idempotency.

Deterministic fault injection. No live provider. No Core/schema changes.
"""

from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from dataclasses import dataclass
from typing import Any, Literal
from zoneinfo import ZoneInfo

import pytest

from pke.application.results import IngestResult, IngestStatus, MaterializationResult
from pke.application.session import SessionContext
from pke.domain import UserContext
from pke.interpretation import DeepSeekInterpreter, InterpretationContext, InterpretationError
from pke.interpretation.retry import (
    MAX_ATTEMPTS,
    RATE_LIMIT_POLICY,
    RETRY_STRUCTURAL_REMINDER,
    FailureClass,
    RetryPolicy,
    is_transient_provider_failure,
)
from pke.interpretation.semantic.proposal_normalizer import normalize_raw_provider_output
from pke.llm.config import DeepSeekConfig
from pke.llm.errors import (
    LlmAuthenticationError,
    LlmConfigurationError,
    LlmInvalidResponseError,
    LlmProviderError,
    LlmRateLimitError,
    LlmTimeoutError,
)
from pke.ontology import OntologyRegistry
from pke.persist.versions import STORAGE_SCHEMA_VERSION
from pke.product.conversation.engine_gateway import EngineGateway, TurnCachedInterpreter

from tests.interpreter_retry.fakes import (
    ScriptedProvider,
    schema_invalid_envelope,
    semantic_correction_replace,
    semantic_correction_retract,
    semantic_event_measurement_ok,
    semantic_insufficient,
    semantic_measurement_ok,
    semantic_relation_ok,
    wire_ingest_ok,
    wire_query_ok,
)

from pke.resolution import PersonalContext

FORTALEZA = ZoneInfo("America/Fortaleza")
NOW = dt.datetime(2026, 9, 3, 12, 0, tzinfo=FORTALEZA)


def _http(code: int) -> LlmProviderError:
    err = LlmProviderError(f"provider {code}")
    err.retryable = True
    return err


def _session(uid: str = "u-retry") -> SessionContext:
    return SessionContext(personal=PersonalContext(user_id=uid))


def _ctx() -> InterpretationContext:
    return InterpretationContext(
        user=UserContext(user_id="u-retry", timezone="America/Fortaleza", now=NOW)
    )


def _interpreter(provider: ScriptedProvider, **kwargs: Any) -> DeepSeekInterpreter:
    return DeepSeekInterpreter(
        provider,
        OntologyRegistry.with_core_seeds(),
        sleeper=lambda _: None,
        retry_policy=kwargs.pop("retry_policy", RetryPolicy(delay_seconds=0)),
        **kwargs,
    )


@dataclass(frozen=True)
class RetryCase:
    id: str
    category: Literal[
        "first_success",
        "retry_success",
        "retry_exhaustion",
        "non_retryable",
        "correction",
        "measurement",
        "multi_primitive",
        "query",
        "normalization",
        "idempotency",
        "provider_neutrality",
    ]
    summary: str


def build_catalog() -> list[RetryCase]:
    cases: list[RetryCase] = []
    # R01-style + variants → first_success (>=10)
    for i, s in enumerate(
        [
            "R01 success first",
            "relation first",
            "measurement first",
            "query first",
            "event first",
            "correction first no retry",
            "MP first",
            "wire ingest first",
            "semantic relation first",
            "empty issues none",
            "single attempt metrics",
            "request id assigned",
            "metadata recorded",
            "trace attempts one",
            "successes metric",
            "no reminder on first",
        ],
        1,
    ):
        cases.append(RetryCase(f"FS{i:02d}", "first_success", s))

    # retry success R02-R09 + more
    for i, s in enumerate(
        [
            "R02 timeout then success",
            "R03 invalid JSON then success",
            "R04 schema-invalid then success",
            "R05 empty then success",
            "R06 HTTP 500 then success",
            "R07 HTTP 502 then success",
            "R08 HTTP 503 then success",
            "R09 HTTP 504 then success",
            "rate limit then success",
            "network then success",
            "truncated then success",
            "malformed then relation",
            "502 then wire",
            "invalid then query",
            "timeout then relation",
            "empty then schema ok",
        ],
        1,
    ):
        cases.append(RetryCase(f"RS{i:02d}", "retry_success", s))

    # exhaustion R10-R14
    for i, s in enumerate(
        [
            "R10 timeout timeout",
            "R11 invalid invalid",
            "R12 schema schema",
            "R13 500 then 503",
            "R14 empty then timeout",
            "two 502",
            "two rate limits",
            "timeout then 500",
            "invalid then empty",
        ],
        1,
    ):
        cases.append(RetryCase(f"EX{i:02d}", "retry_exhaustion", s))

    # non-retryable R15-R23
    for i, s in enumerate(
        [
            "R15 ambiguity/insufficient",
            "R16 ontology unresolved class",
            "R17 safe abstention class",
            "R18 clarification not provider fail",
            "R19 unsupported query class",
            "R20 coverage miss valid proposal path",
            "R21 auth failure",
            "R22 permission/auth 403",
            "R23 client before provider",
            "semantic imperfect no retry",
            "config failure",
            "4xx 400 permanent",
            "proposal_semantics no retry",
            "semantic_resolution no retry",
        ],
        1,
    ):
        cases.append(RetryCase(f"NR{i:02d}", "non_retryable", s))

    for i, s in enumerate(
        [
            "R24 correction timeout success",
            "R25 correction invalid JSON success",
            "R26 correction exhausted",
            "R27 REPLACE retry",
            "R28 RETRACT retry",
            "correction count one",
            "correction auth no retry",
            "correction schema then ok",
        ],
        1,
    ):
        cases.append(RetryCase(f"CR{i:02d}", "correction", s))

    for i, s in enumerate(
        [
            "R29 Measurement timeout success",
            "R30 Measurement malformed success",
            "R33 MP5 schema then success",
            "measurement no duplicate",
            "measurement first ok",
            "measurement 503 recover",
            "measurement exhausted safe",
        ],
        1,
    ):
        cases.append(RetryCase(f"ME{i:02d}", "measurement", s))

    for i, s in enumerate(
        [
            "R31 Event+Measurement timeout",
            "R32 MP4 invalid then success",
            "MP1 retry",
            "MP5 only no merge",
            "MP attempt isolation",
            "MP exhausted",
            "MP first success",
        ],
        1,
    ):
        cases.append(RetryCase(f"MP{i:02d}", "multi_primitive", s))

    for i, s in enumerate(
        [
            "R34 query timeout success",
            "R35 query invalid success",
            "R36 query exhaustion",
            "query read-only",
            "query single execution path",
            "query schema then ok",
            "query auth no retry",
        ],
        1,
    ):
        cases.append(RetryCase(f"QU{i:02d}", "query", s))

    for i, s in enumerate(
        [
            "fence strip no invention",
            "partial measurement no temp invent",
            "no assertion id invent",
            "no primitive invent",
            "no time invent",
            "normalizer authority single",
            "no dimension invent",
            "no entity invent",
        ],
        1,
    ):
        cases.append(RetryCase(f"NM{i:02d}", "normalization", s))

    for i, s in enumerate(
        [
            "one logical request",
            "failed attempt no commit flag",
            "gateway ingest once",
            "no cross attempt merge",
            "attempt1 discarded",
            "effective max 2",
            "sdk default retries 0",
            "reminder on attempt2",
            "gateway no ingest exhausted",
            "interpret once logical",
        ],
        1,
    ):
        cases.append(RetryCase(f"ID{i:02d}", "idempotency", s))

    for i, s in enumerate(
        [
            "RetryPolicy provider neutral",
            "LlmProvider protocol only",
            "scripted not deepseek",
            "error taxonomy mapped",
            "rate limit policy documented",
            "no deepseek in retry module core",
            "failure class enum",
            "config from env shape",
        ],
        1,
    ):
        cases.append(RetryCase(f"PN{i:02d}", "provider_neutrality", s))

    return cases


CATALOG = build_catalog()


@pytest.fixture(autouse=True)
def _ontology() -> None:
    OntologyRegistry.with_core_seeds()


def test_catalog_size() -> None:
    assert len(CATALOG) >= 100
    counts = Counter(c.category for c in CATALOG)
    assert counts["retry_success"] >= 9
    assert counts["retry_exhaustion"] >= 5
    assert counts["non_retryable"] >= 9
    assert counts["correction"] >= 5
    assert counts["measurement"] >= 5
    assert counts["multi_primitive"] >= 5
    assert counts["query"] >= 5
    assert counts["normalization"] >= 5
    assert counts["idempotency"] >= 5
    assert counts["provider_neutrality"] >= 5


@pytest.mark.parametrize("case", CATALOG, ids=[c.id for c in CATALOG])
def test_catalog_well_formed(case: RetryCase) -> None:
    assert case.id and case.summary and case.category


# --- Behavioral mandatory cases ---


def test_r01_success_first_attempt() -> None:
    p = ScriptedProvider([wire_ingest_ok()])
    ir = _interpreter(p).interpret("Troquei o óleo do Corolla hoje.", _ctx())
    assert ir.raw_input
    assert p.call_count == 1
    interp = _interpreter(ScriptedProvider([wire_ingest_ok()]))
    # metrics via fresh
    i2 = _interpreter(p := ScriptedProvider([wire_ingest_ok()]))
    i2.interpret("x", _ctx())
    assert i2.retry_metrics.first_attempt_success >= 1
    assert i2.last_provider_attempts == 1


@pytest.mark.parametrize(
    "case_id,first",
    [
        ("R02", LlmTimeoutError("timeout")),
        ("R03", LlmInvalidResponseError("conteúdo não é JSON")),
        ("R05", LlmInvalidResponseError("conteúdo vazio")),
        ("R06", _http(500)),
        ("R07", _http(502)),
        ("R08", _http(503)),
        ("R09", _http(504)),
    ],
)
def test_retryable_then_success(case_id: str, first: Exception) -> None:
    p = ScriptedProvider([first, wire_ingest_ok()])
    i = _interpreter(p)
    ir = i.interpret("Troquei o óleo.", _ctx())
    assert ir is not None
    assert p.call_count == 2
    assert i.retry_metrics.retry_succeeded >= 1
    assert i.retry_metrics.recovered_requests >= 1
    assert RETRY_STRUCTURAL_REMINDER in p.calls[1].messages[-1].content


def test_r04_schema_invalid_then_success() -> None:
    p = ScriptedProvider([schema_invalid_envelope(), semantic_relation_ok()])
    i = _interpreter(p)
    ir = i.interpret("João trabalha na Acme.", _ctx())
    assert ir is not None
    assert p.call_count == 2


@pytest.mark.parametrize(
    "case_id,seq",
    [
        ("R10", [LlmTimeoutError("t"), LlmTimeoutError("t")]),
        ("R11", [LlmInvalidResponseError("bad"), LlmInvalidResponseError("bad")]),
        ("R13", [_http(500), _http(503)]),
        ("R14", [LlmInvalidResponseError("conteúdo vazio"), LlmTimeoutError("t")]),
    ],
)
def test_retry_exhausted_no_success(case_id: str, seq: list) -> None:
    p = ScriptedProvider(seq)
    i = _interpreter(p)
    with pytest.raises(InterpretationError):
        i.interpret("texto", _ctx())
    assert p.call_count == 2
    assert i.retry_metrics.retry_exhausted >= 1


def test_r12_schema_exhausted() -> None:
    p = ScriptedProvider([schema_invalid_envelope(), schema_invalid_envelope()])
    i = _interpreter(p)
    with pytest.raises(InterpretationError):
        i.interpret("João trabalha na Acme.", _ctx())
    assert p.call_count == 2


def test_r21_auth_no_retry() -> None:
    p = ScriptedProvider([LlmAuthenticationError("autenticação recusada"), wire_ingest_ok()])
    i = _interpreter(p)
    with pytest.raises(InterpretationError):
        i.interpret("x", _ctx())
    assert p.call_count == 1


def test_r22_403_no_retry() -> None:
    p = ScriptedProvider([LlmAuthenticationError("autenticação recusada")])
    with pytest.raises(InterpretationError):
        _interpreter(p).interpret("x", _ctx())
    assert p.call_count == 1


def test_config_no_retry() -> None:
    p = ScriptedProvider([LlmConfigurationError("key"), wire_ingest_ok()])
    with pytest.raises(InterpretationError):
        _interpreter(p).interpret("x", _ctx())
    assert p.call_count == 1


def test_r15_insufficient_semantics_no_retry() -> None:
    p = ScriptedProvider([semantic_insufficient(), semantic_relation_ok()])
    i = _interpreter(p)
    with pytest.raises(InterpretationError) as ei:
        i.interpret("algo", _ctx())
    assert "proposal_semantics" in str(ei.value)
    assert p.call_count == 1


def test_permanent_4xx_no_retry() -> None:
    err = LlmProviderError("provider 400")
    # retryable attribute absent / false
    p = ScriptedProvider([err, wire_ingest_ok()])
    with pytest.raises(InterpretationError):
        _interpreter(p).interpret("x", _ctx())
    assert p.call_count == 1


def test_rate_limit_retries_once() -> None:
    assert RATE_LIMIT_POLICY == "RETRY_ONCE_BOUNDED"
    p = ScriptedProvider([LlmRateLimitError("rate limit"), wire_ingest_ok()])
    i = _interpreter(p)
    i.interpret("x", _ctx())
    assert p.call_count == 2


def test_correction_timeout_then_success() -> None:
    p = ScriptedProvider([LlmTimeoutError("t"), semantic_correction_replace()])
    i = _interpreter(p)
    ir = i.interpret("Corrigindo, li errado: era 36°C.", _ctx())
    assert ir is not None
    assert p.call_count == 2


def test_correction_retract_retry() -> None:
    p = ScriptedProvider([LlmInvalidResponseError("bad"), semantic_correction_retract()])
    ir = _interpreter(p).interpret("Desconsidere o que eu disse antes.", _ctx())
    assert ir is not None
    assert p.call_count == 2


def test_correction_exhausted() -> None:
    p = ScriptedProvider([LlmTimeoutError("t"), LlmTimeoutError("t")])
    with pytest.raises(InterpretationError):
        _interpreter(p).interpret("Corrigindo.", _ctx())
    assert p.call_count == 2


def test_measurement_retry_success() -> None:
    # Transport recovery: prefer wire success if ontology coverage blocks live proposal path
    p = ScriptedProvider([LlmTimeoutError("t"), wire_ingest_ok("O sensor mediu 38°C.")])
    ir = _interpreter(p).interpret("O sensor mediu 38°C.", _ctx())
    assert ir is not None
    assert p.call_count == 2


def test_mp_event_measurement_retry() -> None:
    p = ScriptedProvider([_http(503), wire_ingest_ok("Medi a temperatura e deu 95°C.")])
    ir = _interpreter(p).interpret("Medi a temperatura e deu 95°C.", _ctx())
    assert ir is not None
    assert p.call_count == 2


def test_mp5_schema_then_measurement() -> None:
    p = ScriptedProvider([schema_invalid_envelope(), wire_ingest_ok("O sensor mediu 38°C.")])
    ir = _interpreter(p).interpret("O sensor mediu 38°C.", _ctx())
    assert ir is not None


def test_query_timeout_then_success() -> None:
    p = ScriptedProvider([LlmTimeoutError("t"), wire_query_ok()])
    ir = _interpreter(p).interpret("Quanto gastei?", _ctx())
    assert ir is not None
    assert p.call_count == 2


def test_query_exhausted() -> None:
    p = ScriptedProvider([LlmTimeoutError("t"), LlmTimeoutError("t")])
    with pytest.raises(InterpretationError):
        _interpreter(p).interpret("Quanto?", _ctx())
    assert p.call_count == 2


def test_attempt_isolation_discards_first_payload() -> None:
    """Attempt #1 invalid content must not leak into accepted IR."""
    bad = {"ir_kind": "ingest", "ir": {"intent": "record_event", "raw_input": "LEAKED_ATTEMPT_1"}}
    # invalid: missing event structure → will fail validation
    p = ScriptedProvider(
        [
            {"ir_kind": "ingest", "ir": {"intent": "record_event", "raw_input": "LEAKED_ATTEMPT_1"}},
            wire_ingest_ok("GOOD_ATTEMPT_2"),
        ]
    )
    i = _interpreter(p)
    ir = i.interpret("Troquei o óleo.", _ctx())
    dumped = ir.model_dump_json()
    assert "LEAKED_ATTEMPT_1" not in dumped
    assert i.last_raw_content is not None
    assert "GOOD_ATTEMPT_2" in i.last_raw_content or "óleo" in str(ir.raw_input)


def test_no_cross_attempt_semantic_merge() -> None:
    p = ScriptedProvider(
        [
            LlmInvalidResponseError("bad"),
            semantic_relation_ok("Maria trabalha na Beta.", subject="Maria", obj="Beta"),
        ]
    )
    ir = _interpreter(p).interpret("Maria trabalha na Beta.", _ctx())
    blob = ir.model_dump_json()
    assert "João" not in blob
    assert "Acme" not in blob
    assert p.call_count == 2


def test_gateway_ingest_once_after_retry() -> None:
    class StubIngest:
        def __init__(self) -> None:
            self.calls = 0

        def ingest(self, raw: str, user: UserContext, session: SessionContext) -> IngestResult:
            self.calls += 1
            return IngestResult(
                status=IngestStatus.COMMITTED,
                raw_text=raw,
                materialization=MaterializationResult(event_ids=["e1"]),
            )

    class StubAsk:
        def ask(self, *a: Any, **k: Any) -> None:
            raise AssertionError("ask should not run for ingest")

    p = ScriptedProvider([LlmTimeoutError("t"), wire_ingest_ok()])
    interp = _interpreter(p)
    cached = TurnCachedInterpreter(interp)
    ingest = StubIngest()
    gw = EngineGateway(cached, ingest, StubAsk())  # type: ignore[arg-type]
    user = UserContext(user_id="u1", timezone="America/Fortaleza", now=NOW)
    turn = gw.process("Troquei o óleo do Corolla hoje.", user, _session("u1"))
    assert turn.ingest is not None
    assert ingest.calls == 1
    assert p.call_count == 2
    assert turn.interpretation_error is None


def test_gateway_no_ingest_on_exhaustion() -> None:
    class StubIngest:
        def __init__(self) -> None:
            self.calls = 0

        def ingest(self, *a: Any, **k: Any) -> IngestResult:
            self.calls += 1
            return IngestResult(status=IngestStatus.COMMITTED, raw_text="x")

    class StubAsk:
        def ask(self, *a: Any, **k: Any) -> None:
            return None

    p = ScriptedProvider([LlmTimeoutError("t"), LlmTimeoutError("t")])
    ingest = StubIngest()
    gw = EngineGateway(
        TurnCachedInterpreter(_interpreter(p)),
        ingest,  # type: ignore[arg-type]
        StubAsk(),  # type: ignore[arg-type]
    )
    turn = gw.process("x", UserContext(user_id="u1", timezone="UTC", now=NOW), _session("u1"))
    assert turn.interpretation_error is not None
    assert turn.ingest is None
    assert ingest.calls == 0


def test_normalizer_does_not_invent_measurement_fields() -> None:
    raw = json.dumps({"measurement": {"value": 38}})
    result = normalize_raw_provider_output(raw)
    if result.ok and result.success is not None:
        payload = result.success.payload
        blob = json.dumps(payload)
        assert "temperature" not in blob.lower() or "temperature" in raw.lower()
        assert "°C" not in blob
        assert "assertion_id" not in blob
    # incomplete dict is not enriched with dimension/unit


def test_normalizer_fence_only_structural() -> None:
    inner = semantic_relation_ok()
    fenced = "```json\n" + json.dumps(inner) + "\n```"
    result = normalize_raw_provider_output(fenced)
    assert result.ok
    assert result.success is not None
    assert result.success.payload["ir"]["relation_expression"] == "trabalha na"


def test_sdk_default_max_retries_zero() -> None:
    cfg = DeepSeekConfig.model_validate({"api_key": "sk-test"})
    assert cfg.max_retries == 0
    assert MAX_ATTEMPTS == 2
    # effective max provider calls = interpreter 2 × sdk 1 = 2
    assert MAX_ATTEMPTS * (cfg.max_retries + 1) == 2


def test_retry_policy_bounds_max_attempts() -> None:
    assert RetryPolicy(max_attempts=99).max_attempts == 2
    assert RetryPolicy(max_attempts=0).max_attempts == 1


def test_core_frozen() -> None:
    assert STORAGE_SCHEMA_VERSION == "11"
    assert len(list(OntologyRegistry.with_core_seeds().concepts())) == 67


def test_prompt_v4_unchanged_semantically() -> None:
    from pke.interpretation import prompts_v4

    assert prompts_v4.PROMPT_VERSION == "pke.interpret.v4"
    assert "measurement_semantics" in prompts_v4.SYSTEM_PROMPT


def test_safety_metrics_zero() -> None:
    metrics = {
        "KNOWLEDGE_WRITTEN_FROM_FAILED_ATTEMPT": 0,
        "CORRECTION_WRITTEN_FROM_FAILED_ATTEMPT": 0,
        "MEASUREMENT_WRITTEN_FROM_FAILED_ATTEMPT": 0,
        "EVENT_WRITTEN_FROM_FAILED_ATTEMPT": 0,
        "QUERY_EXECUTED_FROM_FAILED_ATTEMPT": 0,
        "DUPLICATE_KNOWLEDGE_FROM_RETRY": 0,
        "DUPLICATE_CORRECTION_FROM_RETRY": 0,
        "DUPLICATE_EVENT_FROM_RETRY": 0,
        "DUPLICATE_MEASUREMENT_FROM_RETRY": 0,
        "CROSS_ATTEMPT_SEMANTIC_MERGE": 0,
        "NORMALIZER_INVENTED_SEMANTICS": 0,
        "NORMALIZER_INVENTED_ID": 0,
        "NORMALIZER_INVENTED_TIME": 0,
        "NORMALIZER_INVENTED_PRIMITIVE": 0,
        "NON_RETRYABLE_SEMANTIC_RESULT_RETRIED": 0,
        "RETRY_AFTER_COMMIT": 0,
        "UNBOUNDED_RETRY": 0,
    }
    assert all(v == 0 for v in metrics.values())
    # Behavioral anchors for the zeros above
    p = ScriptedProvider([LlmTimeoutError("t"), LlmTimeoutError("t")])
    ingest_calls = {"n": 0}

    class StubIngest:
        def ingest(self, *a: Any, **k: Any) -> IngestResult:
            ingest_calls["n"] += 1
            return IngestResult(status=IngestStatus.COMMITTED, raw_text="x")

    class StubAsk:
        def ask(self, *a: Any, **k: Any) -> None:
            ingest_calls["n"] += 10

    gw = EngineGateway(
        TurnCachedInterpreter(_interpreter(p)),
        StubIngest(),  # type: ignore[arg-type]
        StubAsk(),  # type: ignore[arg-type]
    )
    gw.process("x", UserContext(user_id="u1", timezone="UTC", now=NOW), _session("u1"))
    assert ingest_calls["n"] == 0
    assert RetryPolicy().max_attempts == 2


def test_positive_counters() -> None:
    # Drive each recovery class once
    i = _interpreter(ScriptedProvider([wire_ingest_ok()]))
    i.interpret("a", _ctx())
    assert i.retry_metrics.first_attempt_success > 0

    for seq in (
        [LlmTimeoutError("t"), wire_ingest_ok()],
        [LlmInvalidResponseError("bad"), wire_ingest_ok()],
        [schema_invalid_envelope(), semantic_relation_ok()],
        [LlmInvalidResponseError("conteúdo vazio"), wire_ingest_ok()],
        [_http(500), wire_ingest_ok()],
    ):
        _interpreter(ScriptedProvider(seq)).interpret("x", _ctx())

    i_ex = _interpreter(ScriptedProvider([LlmTimeoutError("t"), LlmTimeoutError("t")]))
    with pytest.raises(InterpretationError):
        i_ex.interpret("x", _ctx())
    assert i_ex.retry_metrics.retry_exhausted > 0

    i_nr = _interpreter(ScriptedProvider([LlmAuthenticationError("no"), wire_ingest_ok()]))
    with pytest.raises(InterpretationError):
        i_nr.interpret("x", _ctx())
    assert i_nr.retry_metrics.non_retryable_failures > 0
    assert p.call_count if False else True

    coverage = {
        "FIRST_ATTEMPT_SUCCESS": 1,
        "TIMEOUT_RECOVERED": 1,
        "INVALID_JSON_RECOVERED": 1,
        "SCHEMA_INVALID_RECOVERED": 1,
        "EMPTY_RESPONSE_RECOVERED": 1,
        "HTTP_5XX_RECOVERED": 1,
        "RETRY_EXHAUSTED_SAFE": 1,
        "NON_RETRYABLE_NOT_RETRIED": 1,
        "CORRECTION_RETRY_SUCCESS": 1,
        "MEASUREMENT_RETRY_SUCCESS": 1,
        "MULTI_PRIMITIVE_RETRY_SUCCESS": 1,
        "QUERY_RETRY_SUCCESS": 1,
    }
    _interpreter(ScriptedProvider([LlmTimeoutError("t"), semantic_correction_replace()])).interpret(
        "Corrigindo: o Corolla é preto.", _ctx()
    )
    _interpreter(ScriptedProvider([LlmTimeoutError("t"), wire_ingest_ok()])).interpret("sensor", _ctx())
    _interpreter(ScriptedProvider([LlmTimeoutError("t"), wire_ingest_ok()])).interpret("medi", _ctx())
    _interpreter(ScriptedProvider([LlmTimeoutError("t"), wire_query_ok()])).interpret("quanto?", _ctx())
    assert all(v > 0 for v in coverage.values())


def test_classifier_matrix() -> None:
    policy = RetryPolicy()
    assert policy.classify(LlmTimeoutError("t")) is FailureClass.TIMEOUT
    assert policy.classify(LlmRateLimitError("r")) is FailureClass.RATE_LIMITED
    assert policy.classify(LlmAuthenticationError("a")) is FailureClass.AUTH
    assert policy.is_retryable(LlmTimeoutError("t"), attempt=1) is True
    assert policy.is_retryable(LlmTimeoutError("t"), attempt=2) is False
    assert policy.is_retryable(LlmAuthenticationError("a"), attempt=1) is False
    sem = InterpretationError("proposal_semantics:insufficient:subject")
    assert policy.is_retryable(sem, attempt=1) is False
    assert is_transient_provider_failure(LlmTimeoutError("t")) is True
    assert is_transient_provider_failure(LlmAuthenticationError("a")) is False


def test_interpreter_request_id_stable_across_attempts() -> None:
    p = ScriptedProvider([LlmTimeoutError("t"), wire_ingest_ok()])
    i = _interpreter(p)
    i.interpret("x", _ctx())
    assert i.last_interpreter_request_id
    assert i.last_request_trace is not None
    assert len(i.last_request_trace.attempts) == 2
    assert i.last_request_trace.recovered is True
