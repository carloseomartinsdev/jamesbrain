"""I12-R — Engine v1 final revalidation (deterministic freeze suite).

NO feature / Core / schema / prompt / model / Proposal / Wire / Retry changes.
"""

from __future__ import annotations

from collections import Counter

import pytest

from pke.interpretation.prompts import PROMPT_VERSION_V4
from pke.interpretation.retry import MAX_ATTEMPTS, RetryPolicy
from pke.interpretation.semantic.capability_strategy import CapabilityOutcome, decide_capability
from pke.interpretation.semantic.event_preservation import (
    event_assertion_present,
    event_false_canonicalization,
)
from pke.interpretation.semantic.execution_readiness import assess_execution_readiness
from pke.interpretation.semantic.models import PrimitiveKind
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir, resolve_proposal
from pke.interpretation.semantic.router import collect_assertions
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.llm.config import DeepSeekConfig
from pke.ontology import OntologyRegistry
from pke.persist.versions import STORAGE_SCHEMA_VERSION
from tests.engine_v1_freeze.anchors import FREEZE_ANCHORS
from tests.engine_v1_freeze.corpus import I12R_FREEZE_CORPUS, FreezeCase
from tests.multi_primitive_routing_hardening.corpus import mp1, mp2, mp3, mp4, mp5


@pytest.fixture(scope="module", autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def test_freeze_corpus_size() -> None:
    assert len(I12R_FREEZE_CORPUS) >= 300
    assert len({c.case_id for c in I12R_FREEZE_CORPUS}) == len(I12R_FREEZE_CORPUS)
    anchors = [c for c in I12R_FREEZE_CORPUS if c.is_anchor]
    assert len(anchors) == 50
    assert [a.anchor_id for a in FREEZE_ANCHORS] == [f"F{i:02d}" for i in range(1, 51)]


def test_core_freeze_invariants() -> None:
    reg = OntologyRegistry.with_core_seeds()
    assert STORAGE_SCHEMA_VERSION == "11"
    assert len(list(reg.concepts())) == 67
    assert reg.core_frozen is True
    assert PROMPT_VERSION_V4 == "pke.interpret.v4" or PROMPT_VERSION_V4.startswith(
        "pke.interpret.v4"
    )
    assert MAX_ATTEMPTS == 2
    assert RetryPolicy().max_attempts == 2
    # SDK/HTTP hidden retries default 0 (I12.2); application RetryPolicy owns attempts
    assert DeepSeekConfig.model_fields["max_retries"].default == 0


@pytest.mark.parametrize(
    "case_id,factory,expect_event",
    [
        ("MP1", mp1, True),
        ("MP2", mp2, True),
        ("MP3", mp3, True),
        ("MP4", mp4, True),
        ("MP5", mp5, False),
    ],
)
def test_mp_anchors_commit_independently(case_id, factory, expect_event) -> None:
    outcome = proposal_to_canonical_ir(factory())
    result = outcome.result
    assertions = {a.primitive for a in collect_assertions(factory())}
    assert event_false_canonicalization(outcome) is False
    if expect_event:
        assert PrimitiveKind.EVENT in assertions
        assert PrimitiveKind.EVENT in result.non_materialized_primitives or (
            outcome.ir is not None and outcome.ir.event is not None
        )
        assert event_assertion_present(result) or event_sem_ok(result)
    else:
        assert PrimitiveKind.EVENT not in result.non_materialized_primitives
        if outcome.ir is not None:
            assert outcome.ir.event is None
            assert outcome.ir.measurement is not None


def event_sem_ok(result) -> bool:
    return event_assertion_present(result)


_EXECUTABLE = [c for c in I12R_FREEZE_CORPUS if c.factory is not None]


@pytest.mark.parametrize("case", _EXECUTABLE, ids=lambda c: c.case_id)
def test_freeze_case_safety(case: FreezeCase) -> None:
    assert case.factory is not None
    proposal = case.factory()
    before = proposal.raw_input
    outcome = proposal_to_canonical_ir(proposal)
    result = outcome.result
    assert result.proposal.raw_input == before
    assert event_false_canonicalization(outcome) is False

    assertions = {a.primitive for a in collect_assertions(proposal)}

    # State / Relation must not invent Event
    if case.family in {"state", "abstain"} and "STATE" in case.case_id:
        if not proposal.change_semantics and not proposal.action_expression:
            assert PrimitiveKind.EVENT not in assertions
    if case.family == "relation" and not proposal.change_semantics:
        assert PrimitiveKind.EVENT not in assertions
    if case.family == "measurement" or (
        case.expect_cap == "auto_execute" and "MEAS" in case.case_id
    ):
        if not proposal.change_semantics and not proposal.event_expression:
            if outcome.ir is not None:
                assert outcome.ir.event is None


def test_aggregate_critical_safety_counters() -> None:
    safety: Counter[str] = Counter()
    for case in _EXECUTABLE:
        assert case.factory is not None
        proposal = case.factory()
        before = proposal.raw_input
        outcome = proposal_to_canonical_ir(proposal)
        result = outcome.result
        assertions = {a.primitive for a in collect_assertions(proposal)}

        if result.proposal.raw_input != before:
            safety["RAW_TEXT_REINTERPRETED_DOWNSTREAM"] += 1
        if event_false_canonicalization(outcome):
            safety["FALSE_CANONICALIZATION"] += 1
        no_change = not proposal.change_semantics
        if case.family == "state" and PrimitiveKind.EVENT in assertions and no_change:
            safety["STATE_FALSE_CAUSAL_EVENT"] += 1
        if case.family == "relation" and PrimitiveKind.EVENT in assertions and no_change:
            safety["RELATION_FALSE_START_EVENT"] += 1
        if case.case_id.startswith("EVT_") and "MEAS_ONLY" in case.case_id:
            if outcome.ir and outcome.ir.event is not None:
                safety["MP5_FALSE_EVENT"] += 1
        if (
            event_assertion_present(result)
            and PrimitiveKind.EVENT not in result.non_materialized_primitives
            and (outcome.ir is None or outcome.ir.event is None)
            and proposal.change_semantics
            and not proposal.measurement_semantics
        ):
            # resolved explicit event lost without non-mat mark
            readiness = assess_execution_readiness(resolve_proposal(proposal))
            d = decide_capability(readiness)
            if d.outcome not in {
                CapabilityOutcome.CLARIFY,
                CapabilityOutcome.SAFE_ABSTAIN,
            }:
                safety["KNOWN_SEMANTICS_DROPPED"] += 1

    assert all(v == 0 for v in safety.values()), dict(safety)


def test_capability_boundary_matrix_representative() -> None:
    """§35 capability boundary scenarios (executable subset)."""
    from tests.semantic_resolution.fixtures import sc4_replace_clutch
    from tests.structured_proposal_reliability.corpus import mp1_missing_subject

    exec_ok = {CapabilityOutcome.AUTO_EXECUTE, CapabilityOutcome.PARTIAL_EXECUTE}
    matrix = [
        ("full", sc4_replace_clutch, exec_ok),
        ("missing_entity", mp1_missing_subject, {CapabilityOutcome.CLARIFY}),
        ("mp1_partial", mp1, exec_ok),
        ("mp5", mp5, exec_ok),
    ]
    for _name, factory, allowed in matrix:
        d = decide_capability(assess_execution_readiness(resolve_proposal(factory())))
        assert d.outcome in allowed, (_name, d.outcome)

    p = _state_ligado()
    d = decide_capability(assess_execution_readiness(resolve_proposal(p)))
    assert d.outcome is CapabilityOutcome.UNSUPPORTED


def _state_ligado():
    from pke.interpretation.semantic.models import (
        SemanticEntityMention,
        SemanticProposal,
        SemanticTime,
    )

    return SemanticProposal(
        raw_input="dispositivo ligado",
        subject=SemanticEntityMention(text="dispositivo"),
        condition_semantics=True,
        state_expression="ligado",
        change_semantics=False,
        primitive_hint="state",
        temporal=SemanticTime(occurrence_aspect="ongoing"),
    )


def test_clarification_supported_families_documented() -> None:
    from pke.application.clarification_recovery import (
        SUPPORTED_DIMENSION_SLOTS,
        SUPPORTED_ENTITY_SLOTS,
        SUPPORTED_VALUE_SLOTS,
    )

    assert "measured_entity" in SUPPORTED_ENTITY_SLOTS
    assert "state_value" in SUPPORTED_VALUE_SLOTS
    assert "measurement_dimension" in SUPPORTED_DIMENSION_SLOTS
    # unsupported families remain out of scope for Engine v1
    unsupported = {"correction_target", "temporal", "state_dimension", "measurement_value"}
    assert unsupported.isdisjoint(SUPPORTED_ENTITY_SLOTS)
    assert unsupported.isdisjoint(SUPPORTED_VALUE_SLOTS)
    assert unsupported.isdisjoint(SUPPORTED_DIMENSION_SLOTS)
