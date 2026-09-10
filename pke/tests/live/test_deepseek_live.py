"""Smoke live A–F + D1/D2. Não entra no pytest padrão (fora de testpaths)."""

from __future__ import annotations

import datetime as dt
import os
from zoneinfo import ZoneInfo

import pytest

from pke.interpretation import DeepSeekInterpreter, InterpretationContext
from pke.llm import DeepSeekConfig, DeepSeekProvider
from pke.ontology import OntologyRegistry
from pke.domain import UserContext
from tests.golden.invariants import (
    assert_case_a,
    assert_case_b,
    assert_case_c,
    assert_case_d1,
    assert_case_d2,
    assert_case_e,
    assert_case_f,
)

pytestmark = pytest.mark.live

CASES = [
    ("A", "Troquei o óleo do Corolla hoje por 320 reais.", "ingest", assert_case_a),
    ("B", "Tenho dentista quinta às 15h com a Dra. Ana.", "ingest", assert_case_b),
    ("C", "A internet vence todo dia 10 e é 129,90.", "ingest", assert_case_c),
    (
        "D1",
        "Acho que a revisão do Corolla hoje ficou em uns 180 reais.",
        "ingest",
        assert_case_d1,
    ),
    ("D2", "Acho que a revisão ficou em uns 180 reais.", "ingest", assert_case_d2),
    ("E", "Não, achei a nota. Foi 186,50.", "ingest", assert_case_e),
    ("F", "Quanto gastei com o Corolla este mês?", "query", assert_case_f),
]


@pytest.fixture(scope="module")
def live_interpreter() -> DeepSeekInterpreter:
    if not os.environ.get("DEEPSEEK_API_KEY"):
        pytest.skip("DEEPSEEK_API_KEY ausente")
    config = DeepSeekConfig.from_env()
    return DeepSeekInterpreter(DeepSeekProvider(config), OntologyRegistry.with_core_seeds())


def _ctx() -> InterpretationContext:
    now = dt.datetime(2026, 9, 1, 15, 0, tzinfo=ZoneInfo("America/Fortaleza"))
    return InterpretationContext(user=UserContext(user_id="live", timezone="America/Fortaleza", now=now))


@pytest.mark.parametrize("code,raw,kind,check", CASES)
def test_live_semantic_case(live_interpreter: DeepSeekInterpreter, code, raw, kind, check) -> None:
    ir = live_interpreter.interpret(raw, _ctx())
    meta = live_interpreter.last_metadata
    assert meta is not None
    print(
        f"case={code} model={meta.model} status=ok latency_ms={meta.latency_ms:.0f} "
        f"tokens={meta.total_tokens}"
    )
    if kind == "ingest":
        assert ir.__class__.__name__ == "IngestIR"
    else:
        assert ir.__class__.__name__ == "QueryIR"
    check(ir)
