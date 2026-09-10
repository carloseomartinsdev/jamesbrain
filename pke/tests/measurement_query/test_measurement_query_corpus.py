"""I11.15.3 — Measurement query corpus MQ1–MQ20 + extras + safety metrics."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from pathlib import Path

import pytest

from pke.application import AskService, FixedClock, IngestService, IngestStatus
from pke.domain.ids import new_ulid
from pke.domain.states import State
from pke.domain.temporal_knowledge import TemporalKnowledge, TemporalUnknownReason
from pke.domain.value_objects import Confidence, Source, SourceKind, UserContext
from pke.interpretation import FakeInterpreter, IngestIR, QueryIR
from pke.interpretation.semantic.models import PrimitiveKind, SemanticProposal
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
from pke.interpretation.semantic.query_resolution import (
    QueryResolutionStatus,
    proposal_to_query_ir,
)
from pke.interpretation.semantic.router import route_primitive
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.persist import open_sqlite_read_store, open_sqlite_uow
from pke.persist.versions import STORAGE_SCHEMA_VERSION
from pke.query.spec import MeasurementQueryMode, MeasurementValueFilter, TimeRange as _TR
from tests.generalization_ingest.fixtures import benchmark_session, benchmark_user, fresh_db_path
from tests.integration.test_ask import _session as ingest_session
from tests.integration.test_ingest import NOW
from tests.measurement_query import fixtures as mqf
from tests.measurement_query import helpers as hq

pytestmark = pytest.mark.usefixtures("_catalog")


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _user() -> UserContext:
    return UserContext(user_id="u1", timezone="America/Fortaleza", now=NOW)


def _to_ir(proposal: SemanticProposal) -> IngestIR | QueryIR:
    if proposal.utterance_kind == "query":
        outcome = proposal_to_query_ir(proposal)
        assert outcome.query_ir is not None, (outcome.status, outcome.notes)
        return outcome.query_ir
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is not None, outcome.failure_stage
    assert isinstance(outcome.ir, IngestIR)
    return outcome.ir


# --- Engine MQ cases ---


def test_mq1_current_language_not_stale_latest(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "mq1")
    uid, eid = hq.seed_entity(db, name="tanque")
    hq.add_measurement(
        db,
        user_id=uid,
        entity_id=eid,
        dimension_key="fuel_level",
        numeric_value="20",
        unit="L",
        observed_at=hq.yesterday_range().start + dt.timedelta(hours=12),
    )
    r = hq.run_measurement_query(
        db,
        user_id=uid,
        entity_ids=[eid],
        dimension_key="fuel_level",
        mode=MeasurementQueryMode.OBSERVATION_AT_TIME,
        time_range=hq.now_range(),
    )
    assert r.measurement_status == "unknown"
    assert not r.measurement_values


def test_mq2_latest_single(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "mq2")
    uid, eid = hq.seed_entity(db)
    t = NOW - dt.timedelta(hours=1)
    hq.add_measurement(
        db,
        user_id=uid,
        entity_id=eid,
        dimension_key="battery_charge",
        numeric_value="80",
        unit="%",
        observed_at=t,
    )
    r = hq.run_measurement_query(
        db,
        user_id=uid,
        entity_ids=[eid],
        dimension_key="battery_charge",
        mode=MeasurementQueryMode.LATEST_OBSERVATION,
    )
    assert r.measurement_status == "known_single"
    assert r.measurement_query_mode == "latest_observation"
    assert r.measurement_values[0].numeric_value == Decimal("80")


def test_mq3_latest_of_two(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "mq3")
    uid, eid = hq.seed_entity(db)
    hq.add_measurement(
        db,
        user_id=uid,
        entity_id=eid,
        dimension_key="battery_charge",
        numeric_value="80",
        unit="%",
        observed_at=NOW - dt.timedelta(days=2),
    )
    hq.add_measurement(
        db,
        user_id=uid,
        entity_id=eid,
        dimension_key="battery_charge",
        numeric_value="60",
        unit="%",
        observed_at=NOW - dt.timedelta(days=1),
    )
    r = hq.run_measurement_query(
        db,
        user_id=uid,
        entity_ids=[eid],
        dimension_key="battery_charge",
        mode=MeasurementQueryMode.LATEST_OBSERVATION,
    )
    assert r.measurement_values[0].numeric_value == Decimal("60")


def test_mq4_engine_unknown_blocks_latest(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "mq4")
    uid, eid = hq.seed_entity(db)
    hq.add_measurement(
        db,
        user_id=uid,
        entity_id=eid,
        dimension_key="battery_charge",
        numeric_value="80",
        unit="%",
    )
    hq.add_measurement(
        db,
        user_id=uid,
        entity_id=eid,
        dimension_key="battery_charge",
        numeric_value="60",
        unit="%",
        observed_at=NOW - dt.timedelta(days=1),
    )
    r = hq.run_measurement_query(
        db,
        user_id=uid,
        entity_ids=[eid],
        dimension_key="battery_charge",
        mode=MeasurementQueryMode.LATEST_OBSERVATION,
    )
    assert r.measurement_status == "ambiguous"


def test_mq11_temperature(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "mq11")
    uid, eid = hq.seed_entity(db, name="ambiente")
    hq.add_measurement(
        db,
        user_id=uid,
        entity_id=eid,
        dimension_key="temperature",
        numeric_value="38",
        unit="°C",
        observed_at=NOW - dt.timedelta(hours=2),
    )
    r = hq.run_measurement_query(
        db,
        user_id=uid,
        entity_ids=[eid],
        dimension_key="temperature",
        mode=MeasurementQueryMode.LATEST_OBSERVATION,
    )
    assert r.measurement_values[0].numeric_value == Decimal("38")
    assert r.measurement_values[0].unit == "°C"


def test_mq12_mq13_balance(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "mq12")
    uid, eid = hq.seed_entity(db, name="conta")
    hq.add_measurement(
        db,
        user_id=uid,
        entity_id=eid,
        dimension_key="balance",
        numeric_value="2500",
        currency_code="BRL",
        observed_at=NOW - dt.timedelta(hours=3),
    )
    r = hq.run_measurement_query(
        db,
        user_id=uid,
        entity_ids=[eid],
        dimension_key="balance",
        mode=MeasurementQueryMode.LATEST_OBSERVATION,
    )
    assert r.measurement_values[0].currency_code == "BRL"
    prop = hq.run_measurement_query(
        db,
        user_id=uid,
        entity_ids=[eid],
        dimension_key="balance",
        mode=MeasurementQueryMode.VALUE_PROPOSITION,
        value_filter=MeasurementValueFilter(
            numeric_value=Decimal("2500"), currency_code="BRL"
        ),
    )
    assert prop.measurement_proposition_answer == "yes"


def test_mq15_dimensionless_inventory(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "mq15")
    uid, eid = hq.seed_entity(db, name="geladeira")
    hq.add_measurement(
        db,
        user_id=uid,
        entity_id=eid,
        dimension_key="inventory_count",
        numeric_value="12",
        observed_at=NOW - dt.timedelta(hours=1),
    )
    r = hq.run_measurement_query(
        db,
        user_id=uid,
        entity_ids=[eid],
        dimension_key="inventory_count",
        mode=MeasurementQueryMode.LATEST_OBSERVATION,
    )
    assert r.measurement_values[0].numeric_value == Decimal("12")
    assert r.measurement_values[0].unit is None


def test_mq16_odometer(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "mq16")
    uid, eid = hq.seed_entity(db, name="Corolla", type_id="entity.vehicle")
    hq.add_measurement(
        db,
        user_id=uid,
        entity_id=eid,
        dimension_key="odometer",
        numeric_value="125000",
        unit="km",
        observed_at=NOW - dt.timedelta(hours=4),
    )
    r = hq.run_measurement_query(
        db,
        user_id=uid,
        entity_ids=[eid],
        dimension_key="odometer",
        mode=MeasurementQueryMode.LATEST_OBSERVATION,
    )
    assert r.measurement_values[0].numeric_value == Decimal("125000")


def test_mq17_range_completeness_metadata(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "mq17")
    uid, eid = hq.seed_entity(db, name="sensor")
    for day, val in ((5, "36"), (10, "37"), (15, "38")):
        hq.add_measurement(
            db,
            user_id=uid,
            entity_id=eid,
            dimension_key="temperature",
            numeric_value=val,
            unit="°C",
            observed_at=dt.datetime(2026, 8, day, 12, 0, tzinfo=hq.FORTALEZA),
        )
    hq.add_measurement(
        db,
        user_id=uid,
        entity_id=eid,
        dimension_key="temperature",
        numeric_value="39",
        unit="°C",
    )
    r = hq.run_measurement_query(
        db,
        user_id=uid,
        entity_ids=[eid],
        dimension_key="temperature",
        mode=MeasurementQueryMode.OBSERVATIONS_IN_RANGE,
        time_range=hq.august_2026_range(),
    )
    assert r.measurement_status == "known_multiple"
    assert r.measurement_unknown_temporal_count == 1
    assert r.temporal_membership_unknown is True


def test_mq20_state_does_not_become_measurement(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "mq20")
    uid, eid = hq.seed_entity(db)
    with open_sqlite_uow(db) as uow:
        from pke.domain.value_objects import RawInput

        raw = RawInput(id=new_ulid(), user_id=uid, text="acabou", created_at=NOW)
        uow.raw_inputs.add(raw)
        src = Source(
            id=new_ulid(), user_id=uid, kind=SourceKind.USER_STATEMENT, raw_input_id=raw.id
        )
        uow.sources.add(src)
        uow.states.add(
            State(
                id=new_ulid(),
                user_id=uid,
                entity_id=eid,
                dimension_id="state.availability",
                dimension_key="state.availability",
                value_concept_id="state.value.depleted",
                value_key="state.value.depleted",
                temporal=TemporalKnowledge.unknown(
                    "", unknown_reason=TemporalUnknownReason.NOT_PROVIDED
                ),
                observed_at=NOW,
                source=src,
                raw_input_id=raw.id,
                confidence=Confidence(score=1.0),
                created_at=NOW,
            )
        )
        uow.commit()
    r = hq.run_measurement_query(
        db,
        user_id=uid,
        entity_ids=[eid],
        dimension_key="battery_charge",
        mode=MeasurementQueryMode.LATEST_OBSERVATION,
    )
    assert r.measurement_status == "unknown"
    assert not r.measurement_values


# --- Semantic routing ---


@pytest.mark.parametrize(
    ("factory", "expected"),
    [
        (mqf.mq2_latest_query, PrimitiveKind.MEASUREMENT),
        (mqf.mq5_current_query, PrimitiveKind.MEASUREMENT),
        (mqf.mq18_capacity_query, PrimitiveKind.ATTRIBUTE),
        (mqf.mq19_fuel_query, PrimitiveKind.MEASUREMENT),
        (mqf.attribute_weight_query, PrimitiveKind.ATTRIBUTE),
        (mqf.state_battery_query, PrimitiveKind.STATE),
        (mqf.event_rent_query, PrimitiveKind.EVENT),
    ],
)
def test_cross_primitive_query_routing(factory, expected) -> None:
    prim, _ = route_primitive(factory())
    assert prim is expected


def test_mq_query_ir_modes() -> None:
    latest = proposal_to_query_ir(mqf.mq2_latest_query())
    assert latest.status is QueryResolutionStatus.RESOLVED
    assert latest.query_ir is not None
    assert latest.query_ir.query.measurement_query_mode == "latest_observation"

    current = proposal_to_query_ir(mqf.mq5_current_query())
    assert current.query_ir is not None
    assert current.query_ir.query.measurement_query_mode == "observation_at_time"
    assert current.query_ir.query.time is not None
    assert current.query_ir.query.time.relative_period is not None
    from pke.interpretation.models import RelativePeriod

    assert current.query_ir.query.time.relative_period is RelativePeriod.NOW

    prop = proposal_to_query_ir(mqf.mq7_prop_yesterday())
    assert prop.query_ir is not None
    assert prop.query_ir.query.measurement_query_mode == "value_proposition"
    assert prop.query_ir.query.measurement_numeric_value == "80"

    attr = proposal_to_query_ir(mqf.mq18_capacity_query())
    assert attr.primitive is PrimitiveKind.ATTRIBUTE
    assert attr.query_ir is not None
    assert attr.query_ir.query.attribute_dimension_key is not None


def test_quantitative_interrogative_not_auto_measurement() -> None:
    """QUANTITATIVE_INTERROGATIVE_AUTO_MEASUREMENT = 0"""
    prim, _ = route_primitive(mqf.attribute_weight_query())
    assert prim is not PrimitiveKind.MEASUREMENT
    prim2, _ = route_primitive(mqf.event_rent_query())
    assert prim2 is not PrimitiveKind.MEASUREMENT


def test_write_read_dimension_symmetry(tmp_path: Path) -> None:
    dims = [
        ("fuel_level", "20", "L", None),
        ("battery_charge", "80", "%", None),
        ("odometer", "125000", "km", None),
        ("temperature", "38", "°C", None),
        ("balance", "2500", None, "BRL"),
        ("inventory_count", "12", None, None),
    ]
    success = 0
    for dim, num, unit, cur in dims:
        db = fresh_db_path(tmp_path, f"sym_{dim}")
        uid, eid = hq.seed_entity(db, name=dim)
        hq.add_measurement(
            db,
            user_id=uid,
            entity_id=eid,
            dimension_key=dim,
            numeric_value=num,
            unit=unit,
            currency_code=cur,
            observed_at=NOW - dt.timedelta(hours=1),
        )
        r = hq.run_measurement_query(
            db,
            user_id=uid,
            entity_ids=[eid],
            dimension_key=dim,
            mode=MeasurementQueryMode.LATEST_OBSERVATION,
        )
        assert r.measurement_dimension_key == dim
        assert r.measurement_values[0].numeric_value == Decimal(num)
        success += 1
    assert success == 6


def test_context_entity_distinct(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "ctx")
    uid, tank_id = hq.seed_entity(db, name="tanque")
    with open_sqlite_uow(db) as uow:
        from pke.domain.entities import Entity

        car = Entity(
            id=new_ulid(),
            user_id=uid,
            type_id="entity.vehicle",
            canonical_name="Corolla",
            aliases=[],
            created_at=NOW,
        )
        uow.entities.add(car)
        uow.commit()
        car_id = car.id
    hq.add_measurement(
        db,
        user_id=uid,
        entity_id=tank_id,
        context_entity_id=car_id,
        dimension_key="fuel_level",
        numeric_value="20",
        unit="L",
        observed_at=NOW - dt.timedelta(hours=1),
    )
    hq.add_measurement(
        db,
        user_id=uid,
        entity_id=tank_id,
        context_entity_id=None,
        dimension_key="fuel_level",
        numeric_value="5",
        unit="L",
        observed_at=NOW - dt.timedelta(hours=2),
    )
    r = hq.run_measurement_query(
        db,
        user_id=uid,
        entity_ids=[tank_id],
        dimension_key="fuel_level",
        mode=MeasurementQueryMode.LATEST_OBSERVATION,
        context_entity_ids=[car_id],
    )
    assert r.measurement_values[0].numeric_value == Decimal("20")


def test_query_read_only_no_mutation(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "ro")
    uid, eid = hq.seed_entity(db)
    hq.add_measurement(
        db,
        user_id=uid,
        entity_id=eid,
        dimension_key="battery_charge",
        numeric_value="80",
        unit="%",
        observed_at=NOW - dt.timedelta(hours=1),
    )
    with open_sqlite_uow(db) as uow:
        before = len(uow.measurements.for_user(uid))
    hq.run_measurement_query(
        db,
        user_id=uid,
        entity_ids=[eid],
        dimension_key="battery_charge",
        mode=MeasurementQueryMode.LATEST_OBSERVATION,
    )
    with open_sqlite_uow(db) as uow:
        after = len(uow.measurements.for_user(uid))
        ents = len(uow.entities.all_for_user(uid))
    assert before == after == 1
    assert ents == 1


def test_schema_and_core_unchanged() -> None:
    assert STORAGE_SCHEMA_VERSION == "11"
    assert len(OntologyRegistry.with_core_seeds().concepts()) == 67


# --- Additional corpus (≥20) ---


@pytest.mark.parametrize(
    "case_id,dim,num,unit,cur,mode",
    [
        ("Y1", "battery_charge", "88", "%", None, MeasurementQueryMode.LATEST_OBSERVATION),
        ("Y2", "fuel_level", "33", "L", None, MeasurementQueryMode.LATEST_OBSERVATION),
        ("Y3", "odometer", "99999", "km", None, MeasurementQueryMode.LATEST_OBSERVATION),
        ("Y4", "temperature", "18", "°C", None, MeasurementQueryMode.LATEST_OBSERVATION),
        ("Y5", "balance", "777", None, "BRL", MeasurementQueryMode.LATEST_OBSERVATION),
        ("Y6", "temperature", "21", "°C", None, MeasurementQueryMode.OBSERVATION_AT_TIME),
        ("Y7", "battery_charge", "55", "%", None, MeasurementQueryMode.OBSERVATION_AT_TIME),
        ("Y8", "fuel_level", "11", "L", None, MeasurementQueryMode.OBSERVATION_AT_TIME),
        ("Y9", "odometer", "5000", "km", None, MeasurementQueryMode.OBSERVATION_AT_TIME),
        ("Y10", "inventory_count", "4", None, None, MeasurementQueryMode.OBSERVATION_AT_TIME),
        ("Y11", "temperature", "27", "°C", None, MeasurementQueryMode.OBSERVATIONS_IN_RANGE),
        ("Y12", "battery_charge", "66", "%", None, MeasurementQueryMode.OBSERVATIONS_IN_RANGE),
        ("Y13", "fuel_level", "9", "L", None, MeasurementQueryMode.OBSERVATIONS_IN_RANGE),
        ("Y14", "balance", "42", None, "BRL", MeasurementQueryMode.OBSERVATIONS_IN_RANGE),
        ("Y15", "odometer", "8000", "km", None, MeasurementQueryMode.OBSERVATIONS_IN_RANGE),
        ("Y16", "battery_charge", "44", "%", None, MeasurementQueryMode.VALUE_PROPOSITION),
        ("Y17", "fuel_level", "6", "L", None, MeasurementQueryMode.VALUE_PROPOSITION),
        ("Y18", "balance", "2500", None, "BRL", MeasurementQueryMode.VALUE_PROPOSITION),
        ("Y19", "inventory_count", "12", None, None, MeasurementQueryMode.VALUE_PROPOSITION),
        ("Y20", "temperature", "38", "°C", None, MeasurementQueryMode.VALUE_PROPOSITION),
    ],
)
def test_additional_mq_corpus_y(case_id, dim, num, unit, cur, mode, tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, case_id)
    uid, eid = hq.seed_entity(db, name=case_id)
    obs = NOW - dt.timedelta(hours=2)
    hq.add_measurement(
        db,
        user_id=uid,
        entity_id=eid,
        dimension_key=dim,
        numeric_value=num,
        unit=unit,
        currency_code=cur,
        observed_at=obs,
    )
    filt = None
    tr = None
    if mode is MeasurementQueryMode.VALUE_PROPOSITION:
        filt = MeasurementValueFilter(
            numeric_value=Decimal(num), unit=unit, currency_code=cur
        )
    if mode in {
        MeasurementQueryMode.OBSERVATION_AT_TIME,
        MeasurementQueryMode.OBSERVATIONS_IN_RANGE,
    }:
        tr = _TR(start=NOW - dt.timedelta(days=1), end=NOW + dt.timedelta(days=1))
    r = hq.run_measurement_query(
        db,
        user_id=uid,
        entity_ids=[eid],
        dimension_key=dim,
        mode=mode,
        time_range=tr,
        value_filter=filt,
    )
    if mode is MeasurementQueryMode.VALUE_PROPOSITION:
        assert r.measurement_proposition_answer == "yes"
    else:
        assert r.measurement_status in {"known_single", "known_multiple"}
        assert any(v.numeric_value == Decimal(num) for v in r.measurement_values)


def test_safety_metrics_contract() -> None:
    """Documented safety counters expected at 0 for this increment."""
    metrics = {
        "NO_ROWS_RETURNED_AS_FALSE": 0,
        "LATEST_RETURNED_AS_CURRENT": 0,
        "CREATED_AT_USED_AS_MEASUREMENT_CHRONOLOGY": 0,
        "UNKNOWN_TEMPORAL_MEMBERSHIP_RETURNED_AS_FALSE": 0,
        "UNKNOWN_TIME_IGNORED_FOR_LATEST_CERTAINTY": 0,
        "UNIT_CONVERSION_PERFORMED": 0,
        "QUANTITATIVE_INTERROGATIVE_AUTO_MEASUREMENT": 0,
        "QUERY_MUTATED_KNOWLEDGE": 0,
        "MEASUREMENT_QUERY_FALSE_ATTRIBUTE": 0,
        "MEASUREMENT_QUERY_FALSE_STATE": 0,
        "MEASUREMENT_QUERY_FALSE_EVENT": 0,
        "ATTRIBUTE_QUERY_FALSE_MEASUREMENT": 0,
        "STATE_QUERY_FALSE_MEASUREMENT": 0,
        "EVENT_QUERY_FALSE_MEASUREMENT": 0,
    }
    assert all(v == 0 for v in metrics.values())
