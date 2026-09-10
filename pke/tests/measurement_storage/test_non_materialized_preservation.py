"""I11.15.2-R — Non-materialized Measurement semantic preservation revalidation."""

from __future__ import annotations

from pathlib import Path

import pytest

from pke.application import FixedClock, IngestService, IngestStatus
from pke.interpretation import FakeInterpreter
from pke.interpretation.semantic.models import (
    PrimitiveKind,
    SemanticEntityMention,
    SemanticProposal,
    SemanticTime,
)
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir, resolve_proposal
from pke.interpretation.semantic.router import collect_assertions, route_primitive
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.persist import open_sqlite_uow
from pke.persist.versions import STORAGE_SCHEMA_VERSION
from tests.attribute_design import fixtures as af
from tests.generalization_ingest.fixtures import benchmark_session, benchmark_user, fresh_db_path
from tests.integration.test_ingest import NOW
from tests.semantic_resolution.fixtures import sc4_replace_clutch


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _happened() -> SemanticTime:
    return SemanticTime(original_text="", occurrence_aspect="happened")


def r1_entityless_measurement() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Está 38 graus.",
        measurement_expression="38 °C",
        measurable_dimension_key="temperature",
        measurement_numeric_value="38",
        measurement_unit="°C",
        measurement_semantics=True,
        primitive_hint="measurement",
    )


def r2_event_ok_measurement_no_entity() -> SemanticProposal:
    base = sc4_replace_clutch()
    return base.model_copy(
        update={
            "raw_input": "Troquei a embreagem e deu 95 °C.",
            "measurement_semantics": True,
            "measurement_expression": "95 °C",
            "measurable_dimension_key": "temperature",
            "measurement_numeric_value": "95",
            "measurement_unit": "°C",
            "subject": None,
            "object": None,
        }
    )


def r3_event_invalid_measurement_ok() -> SemanticProposal:
    """Event cues incomplete (no resolvable action); Measurement complete."""
    return SemanticProposal(
        raw_input="Medi a temperatura e deu 95 °C.",
        subject=SemanticEntityMention(text="temperatura", kind_hint="thing"),
        action_expression="medi",
        change_semantics=True,
        event_expression="medi temperatura",
        measurement_expression="95 °C",
        measurable_dimension_key="temperature",
        measurement_numeric_value="95",
        measurement_unit="°C",
        measurement_semantics=True,
        primitive_hint="event",
        temporal=_happened(),
    )


def r4_both_valid() -> SemanticProposal:
    base = sc4_replace_clutch()
    return base.model_copy(
        update={
            "raw_input": "Troquei a embreagem e o odômetro estava em 125000 km.",
            "measurement_semantics": True,
            "measurement_expression": "125000 km",
            "measurable_dimension_key": "odometer",
            "measurement_numeric_value": "125000",
            "measurement_unit": "km",
            "subject": SemanticEntityMention(text="odômetro", kind_hint="thing"),
        }
    )


def _ingest(proposal: SemanticProposal, db: Path):
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is not None
    user = benchmark_user()
    svc = IngestService(
        FakeInterpreter({proposal.raw_input: outcome.ir}),  # type: ignore[arg-type]
        OntologyRegistry.with_core_seeds(),
        lambda: open_sqlite_uow(db),
        FixedClock(NOW),
    )
    return svc.ingest(proposal.raw_input, user, benchmark_session()), user, outcome


def _meas_count(db: Path, user_id: str) -> int:
    with open_sqlite_uow(db) as uow:
        return len(uow.measurements.for_user(user_id))


def test_r1_semantically_valid_non_materializable_preserved() -> None:
    proposal = r1_entityless_measurement()
    assert route_primitive(proposal)[0] is PrimitiveKind.MEASUREMENT
    result = resolve_proposal(proposal)
    assert any(f.primitive is PrimitiveKind.MEASUREMENT for f in result.assertions)
    assert PrimitiveKind.MEASUREMENT in result.non_materialized_primitives
    assert "measurement_entity_required" in result.non_materialized_reasons
    assert result.concepts.measurement_dimension_key == "temperature"
    assert result.concepts.measurement_numeric_value == "38"
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is None
    # Omitted from IR must not erase semantic result
    assert any(f.primitive is PrimitiveKind.MEASUREMENT for f in outcome.result.assertions)
    assert PrimitiveKind.MEASUREMENT in outcome.result.non_materialized_primitives
    assert "measurement_entity_required" in outcome.result.non_materialized_reasons


def test_r2_event_commits_measurement_assertion_preserved(tmp_path: Path) -> None:
    proposal = r2_event_ok_measurement_no_entity()
    frames = collect_assertions(proposal)
    assert {f.primitive for f in frames} == {PrimitiveKind.EVENT, PrimitiveKind.MEASUREMENT}
    result = resolve_proposal(proposal)
    assert PrimitiveKind.MEASUREMENT in result.non_materialized_primitives
    assert "measurement_entity_required" in result.non_materialized_reasons
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is not None
    assert outcome.ir.event is not None
    assert outcome.ir.measurement is None
    assert any(f.primitive is PrimitiveKind.MEASUREMENT for f in outcome.result.assertions)
    db = fresh_db_path(tmp_path, "r2")
    ingest_result, user, _ = _ingest(proposal, db)
    assert ingest_result.status is IngestStatus.COMMITTED
    assert ingest_result.materialization and ingest_result.materialization.event_ids
    assert not ingest_result.materialization.measurement_ids
    assert _meas_count(db, user.user_id) == 0


def test_r3_measurement_commits_partial_event_non_materialized(tmp_path: Path) -> None:
    """I12.7.1: compositional Event non-materialized; Measurement commits independently."""
    proposal = r3_event_invalid_measurement_ok()
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is not None
    assert outcome.ir.event is None
    assert outcome.ir.measurement is not None
    assert PrimitiveKind.EVENT in outcome.result.non_materialized_primitives
    assert "event_category_unresolved_safe_partial" in outcome.result.non_materialized_reasons
    assert any(f.primitive is PrimitiveKind.EVENT for f in outcome.result.assertions)
    assert any(f.primitive is PrimitiveKind.MEASUREMENT for f in outcome.result.assertions)
    db = fresh_db_path(tmp_path, "r3")
    ingest_result, user, _ = _ingest(proposal, db)
    assert ingest_result.status is IngestStatus.COMMITTED
    assert ingest_result.materialization and ingest_result.materialization.measurement_ids
    assert not ingest_result.materialization.event_ids
    assert _meas_count(db, user.user_id) == 1


def test_r4_both_commit_no_duplicate(tmp_path: Path) -> None:
    proposal = r4_both_valid()
    db = fresh_db_path(tmp_path, "r4")
    ingest_result, user, outcome = _ingest(proposal, db)
    assert ingest_result.status is IngestStatus.COMMITTED
    mat = ingest_result.materialization
    assert mat and len(mat.event_ids) == 1 and len(mat.measurement_ids) == 1
    assert _meas_count(db, user.user_id) == 1
    assert outcome.ir is not None
    assert outcome.ir.event is not None and outcome.ir.measurement is not None


def test_ir_omission_does_not_erase_semantic_measurement() -> None:
    """DOES_REMOVING_MEASUREMENT_FROM_MATERIALIZATION_IR_REMOVE_IT_FROM_SEMANTIC_RESULT? NO"""
    outcome = proposal_to_canonical_ir(r2_event_ok_measurement_no_entity())
    assert outcome.ir is not None
    assert outcome.ir.measurement is None
    assert any(f.primitive is PrimitiveKind.MEASUREMENT for f in outcome.result.assertions)


def test_status_classes_distinct() -> None:
    """SEMANTICALLY_VALID_NON_MATERIALIZABLE ≠ SEMANTICALLY_INVALID."""
    r1 = resolve_proposal(r1_entityless_measurement())
    # Valid observation evidence retained
    assert r1.concepts.measurement_numeric_value == "38"
    assert PrimitiveKind.MEASUREMENT in r1.non_materialized_primitives
    # Not routed as UNKNOWN / not dropped from assertions
    assert r1.primitive is PrimitiveKind.MEASUREMENT
    assert r1.assertions


def test_safety_schema_core_unchanged() -> None:
    assert STORAGE_SCHEMA_VERSION == "11"
    assert len(OntologyRegistry.with_core_seeds().concepts()) == 67


def test_attribute_still_not_measurement() -> None:
    assert route_primitive(af.at2_house_area())[0] is PrimitiveKind.ATTRIBUTE
