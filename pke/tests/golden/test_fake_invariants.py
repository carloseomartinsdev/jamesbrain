from __future__ import annotations

from tests.golden.invariants import (
    assert_case_a,
    assert_case_b,
    assert_case_c,
    assert_case_d1,
    assert_case_d2,
    assert_case_e,
    assert_case_f,
)
from tests.integration.test_ingest import ir_a, ir_b, ir_c, ir_d1, ir_d2, ir_e
from tests.integration.test_ask import _query_ir


def test_fake_cases_a_to_f() -> None:
    assert_case_a(ir_a())
    assert_case_b(ir_b())
    assert_case_c(ir_c())
    assert_case_d1(ir_d1())
    assert_case_d2(ir_d2())
    assert_case_e(ir_e())
    assert_case_f(_query_ir())


def test_fake_d1_matches_literal_text() -> None:
    ir = ir_d1()
    assert ir.raw_input == "Acho que a revisão do Corolla hoje ficou em uns 180 reais."
    assert ir.event is not None
    assert ir.event.time.relative_day is not None
    assert "hoje" in ir.event.time.original_text.lower()


def test_fake_d2_does_not_inject_missing_info() -> None:
    ir = ir_d2()
    assert ir.raw_input == "Acho que a revisão ficou em uns 180 reais."
    assert ir.event is not None
    assert ir.event.time.relative_day is None
    assert ir.entities_mentioned == []
    assert ir.event.time.original_text == ""
