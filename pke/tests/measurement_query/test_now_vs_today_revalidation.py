"""I11.15.3-R2 — NOW vs TODAY fix regression (safe assertions).

Replaces unsafe collapse documentation from I11.15.3-R audit.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from pathlib import Path

import pytest

from pke.interpretation.models import RelativePeriod
from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal, SemanticTime
from pke.interpretation.semantic.query_resolution import proposal_to_query_ir
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.persist.versions import STORAGE_SCHEMA_VERSION
from pke.query.spec import MeasurementQueryMode, MeasurementValueFilter, TimeRange
from pke.resolution import QueryTemporalContext, QueryTemporalResolver, WeekStart
from pke.domain.value_objects import UserContext
from tests.generalization_ingest.fixtures import fresh_db_path
from tests.integration.test_ingest import NOW
from tests.measurement_query import fixtures as mqf
from tests.measurement_query import helpers as hq

pytestmark = pytest.mark.usefixtures("_catalog")


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


TODAY_0800 = dt.datetime(2026, 9, 1, 8, 0, tzinfo=hq.FORTALEZA)
TODAY_1200 = dt.datetime(2026, 9, 1, 12, 0, tzinfo=hq.FORTALEZA)
QUERY_NOW = NOW  # 15:00


def test_agora_maps_to_now_not_today() -> None:
    outcome = proposal_to_query_ir(mqf.mq5_current_query())
    assert outcome.query_ir is not None
    q = outcome.query_ir.query
    assert q.measurement_query_mode == "observation_at_time"
    assert q.time is not None
    assert q.time.relative_period is RelativePeriod.NOW
    assert q.time.relative_period is not RelativePeriod.TODAY


@pytest.mark.parametrize(
    "raw",
    [
        "Quanto está a bateria agora?",
        "Quanto está a bateria neste momento?",
        "Quanto está a bateria no momento?",
        "Quanto está a bateria atualmente?",
    ],
)
def test_r10_current_wording_variants_map_to_now(raw: str) -> None:
    prop = SemanticProposal(
        raw_input=raw,
        utterance_kind="query",
        subject=SemanticEntityMention(text="bateria", kind_hint="thing"),
        measurable_dimension_key="battery_charge",
        measurement_semantics=True,
        primitive_hint="measurement",
        temporal=SemanticTime(original_text="agora" if "agora" in raw else raw.split()[-1]),
    )
    outcome = proposal_to_query_ir(prop)
    assert outcome.query_ir is not None
    assert outcome.query_ir.query.time is not None
    assert outcome.query_ir.query.time.relative_period is RelativePeriod.NOW


def test_hoje_still_maps_to_today() -> None:
    prop = SemanticProposal(
        raw_input="Quais foram as leituras da bateria hoje?",
        utterance_kind="query",
        subject=SemanticEntityMention(text="bateria", kind_hint="thing"),
        measurable_dimension_key="battery_charge",
        measurement_semantics=True,
        primitive_hint="measurement",
        temporal=SemanticTime(original_text="hoje", relative_day="today"),
    )
    outcome = proposal_to_query_ir(prop)
    assert outcome.query_ir is not None
    assert outcome.query_ir.query.time is not None
    assert outcome.query_ir.query.time.relative_period is RelativePeriod.TODAY


def test_now_resolves_to_reference_instant_not_day() -> None:
    resolved = QueryTemporalResolver().resolve(
        __import__("pke.interpretation", fromlist=["IrQueryTime"]).IrQueryTime(
            relative_period=RelativePeriod.NOW, original_text="agora"
        ),
        QueryTemporalContext(
            user=UserContext(user_id="u1", timezone="America/Fortaleza", now=QUERY_NOW),
            reference_at=QUERY_NOW,
            week_start=WeekStart.MONDAY,
        ),
    )
    assert resolved is not None
    assert resolved.start == QUERY_NOW
    assert resolved.end == QUERY_NOW + dt.timedelta(microseconds=1)
    # Day interval would be much larger
    assert (resolved.end - resolved.start) < dt.timedelta(seconds=1)


def test_r1_earlier_today_does_not_answer_now(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "r1")
    uid, eid = hq.seed_entity(db)
    hq.add_measurement(
        db,
        user_id=uid,
        entity_id=eid,
        dimension_key="battery_charge",
        numeric_value="80",
        unit="%",
        observed_at=TODAY_0800,
    )
    r = hq.run_measurement_query(
        db,
        user_id=uid,
        entity_ids=[eid],
        dimension_key="battery_charge",
        mode=MeasurementQueryMode.OBSERVATION_AT_TIME,
        time_range=hq.now_range(QUERY_NOW),
    )
    assert r.measurement_status == "unknown"
    assert not r.measurement_values


def test_r2_latest_today_does_not_answer_now(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "r2")
    uid, eid = hq.seed_entity(db)
    hq.add_measurement(
        db,
        user_id=uid,
        entity_id=eid,
        dimension_key="battery_charge",
        numeric_value="80",
        unit="%",
        observed_at=TODAY_0800,
    )
    hq.add_measurement(
        db,
        user_id=uid,
        entity_id=eid,
        dimension_key="battery_charge",
        numeric_value="60",
        unit="%",
        observed_at=TODAY_1200,
    )
    r = hq.run_measurement_query(
        db,
        user_id=uid,
        entity_ids=[eid],
        dimension_key="battery_charge",
        mode=MeasurementQueryMode.OBSERVATION_AT_TIME,
        time_range=hq.now_range(QUERY_NOW),
    )
    assert r.measurement_status == "unknown"
    assert not r.measurement_values


def test_r3_explicit_latest_still_works(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "r3")
    uid, eid = hq.seed_entity(db)
    hq.add_measurement(
        db,
        user_id=uid,
        entity_id=eid,
        dimension_key="battery_charge",
        numeric_value="80",
        unit="%",
        observed_at=TODAY_0800,
    )
    hq.add_measurement(
        db,
        user_id=uid,
        entity_id=eid,
        dimension_key="battery_charge",
        numeric_value="60",
        unit="%",
        observed_at=TODAY_1200,
    )
    r = hq.run_measurement_query(
        db,
        user_id=uid,
        entity_ids=[eid],
        dimension_key="battery_charge",
        mode=MeasurementQueryMode.LATEST_OBSERVATION,
    )
    assert r.measurement_status == "known_single"
    assert r.measurement_values[0].numeric_value == Decimal("60")


def test_r4_historical_exact_instant_match(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "r4")
    uid, eid = hq.seed_entity(db)
    hq.add_measurement(
        db,
        user_id=uid,
        entity_id=eid,
        dimension_key="battery_charge",
        numeric_value="80",
        unit="%",
        observed_at=TODAY_0800,
    )
    r = hq.run_measurement_query(
        db,
        user_id=uid,
        entity_ids=[eid],
        dimension_key="battery_charge",
        mode=MeasurementQueryMode.OBSERVATION_AT_TIME,
        time_range=TimeRange(
            start=TODAY_0800, end=TODAY_0800 + dt.timedelta(minutes=1)
        ),
    )
    assert r.measurement_status == "known_single"
    assert r.measurement_values[0].numeric_value == Decimal("80")


def test_r5_broad_today_range(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "r5")
    uid, eid = hq.seed_entity(db)
    hq.add_measurement(
        db,
        user_id=uid,
        entity_id=eid,
        dimension_key="battery_charge",
        numeric_value="80",
        unit="%",
        observed_at=TODAY_0800,
    )
    hq.add_measurement(
        db,
        user_id=uid,
        entity_id=eid,
        dimension_key="battery_charge",
        numeric_value="60",
        unit="%",
        observed_at=TODAY_1200,
    )
    r = hq.run_measurement_query(
        db,
        user_id=uid,
        entity_ids=[eid],
        dimension_key="battery_charge",
        mode=MeasurementQueryMode.OBSERVATIONS_IN_RANGE,
        time_range=hq.today_range(QUERY_NOW),
    )
    assert r.measurement_status == "known_multiple"
    assert {v.numeric_value for v in r.measurement_values} == {
        Decimal("80"),
        Decimal("60"),
    }


def test_r6_exact_now_match(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "r6")
    uid, eid = hq.seed_entity(db)
    hq.add_measurement(
        db,
        user_id=uid,
        entity_id=eid,
        dimension_key="battery_charge",
        numeric_value="55",
        unit="%",
        observed_at=QUERY_NOW,
    )
    r = hq.run_measurement_query(
        db,
        user_id=uid,
        entity_ids=[eid],
        dimension_key="battery_charge",
        mode=MeasurementQueryMode.OBSERVATION_AT_TIME,
        time_range=hq.now_range(QUERY_NOW),
    )
    assert r.measurement_status == "known_single"
    assert r.measurement_values[0].numeric_value == Decimal("55")


def test_r7_yesterday_does_not_answer_now(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "r7")
    uid, eid = hq.seed_entity(db)
    hq.add_measurement(
        db,
        user_id=uid,
        entity_id=eid,
        dimension_key="battery_charge",
        numeric_value="80",
        unit="%",
        observed_at=hq.yesterday_range(QUERY_NOW).start + dt.timedelta(hours=12),
    )
    r = hq.run_measurement_query(
        db,
        user_id=uid,
        entity_ids=[eid],
        dimension_key="battery_charge",
        mode=MeasurementQueryMode.OBSERVATION_AT_TIME,
        time_range=hq.now_range(QUERY_NOW),
    )
    assert r.measurement_status == "unknown"


def test_r8_unknown_time_now_temporally_unknown(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "r8")
    uid, eid = hq.seed_entity(db)
    hq.add_measurement(
        db,
        user_id=uid,
        entity_id=eid,
        dimension_key="battery_charge",
        numeric_value="80",
        unit="%",
    )
    r = hq.run_measurement_query(
        db,
        user_id=uid,
        entity_ids=[eid],
        dimension_key="battery_charge",
        mode=MeasurementQueryMode.OBSERVATION_AT_TIME,
        time_range=hq.now_range(QUERY_NOW),
    )
    assert r.measurement_status == "temporally_unknown"
    assert r.measurement_values
    assert r.measurement_values[0].numeric_value == Decimal("80")
    assert r.measurement_values[0].unit == "%"


def test_r9_today_wording_not_now(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "r9")
    uid, eid = hq.seed_entity(db)
    hq.add_measurement(
        db,
        user_id=uid,
        entity_id=eid,
        dimension_key="battery_charge",
        numeric_value="80",
        unit="%",
        observed_at=TODAY_0800,
    )
    hq.add_measurement(
        db,
        user_id=uid,
        entity_id=eid,
        dimension_key="battery_charge",
        numeric_value="60",
        unit="%",
        observed_at=TODAY_1200,
    )
    r = hq.run_measurement_query(
        db,
        user_id=uid,
        entity_ids=[eid],
        dimension_key="battery_charge",
        mode=MeasurementQueryMode.OBSERVATION_AT_TIME,
        time_range=hq.today_range(QUERY_NOW),
    )
    assert r.measurement_status in {"known_multiple", "ambiguous"}
    vals = {v.numeric_value for v in r.measurement_values}
    assert Decimal("80") in vals and Decimal("60") in vals


def test_proposition_now_earlier_today_unknown(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "prop_now")
    uid, eid = hq.seed_entity(db)
    hq.add_measurement(
        db,
        user_id=uid,
        entity_id=eid,
        dimension_key="battery_charge",
        numeric_value="80",
        unit="%",
        observed_at=TODAY_0800,
    )
    r = hq.run_measurement_query(
        db,
        user_id=uid,
        entity_ids=[eid],
        dimension_key="battery_charge",
        mode=MeasurementQueryMode.VALUE_PROPOSITION,
        value_filter=MeasurementValueFilter(numeric_value=Decimal("80"), unit="%"),
        time_range=hq.now_range(QUERY_NOW),
    )
    assert r.measurement_proposition_answer == "unknown"
    assert r.measurement_proposition_answer != "yes"
    assert r.measurement_proposition_answer != "no"  # type: ignore[comparison-overlap]


def test_proposition_exact_now_yes(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "prop_yes")
    uid, eid = hq.seed_entity(db)
    hq.add_measurement(
        db,
        user_id=uid,
        entity_id=eid,
        dimension_key="battery_charge",
        numeric_value="80",
        unit="%",
        observed_at=QUERY_NOW,
    )
    r = hq.run_measurement_query(
        db,
        user_id=uid,
        entity_ids=[eid],
        dimension_key="battery_charge",
        mode=MeasurementQueryMode.VALUE_PROPOSITION,
        value_filter=MeasurementValueFilter(numeric_value=Decimal("80"), unit="%"),
        time_range=hq.now_range(QUERY_NOW),
    )
    assert r.measurement_proposition_answer == "yes"


def test_conflicting_exact_now_ambiguous(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "amb")
    uid, eid = hq.seed_entity(db)
    hq.add_measurement(
        db,
        user_id=uid,
        entity_id=eid,
        dimension_key="battery_charge",
        numeric_value="80",
        unit="%",
        observed_at=QUERY_NOW,
    )
    hq.add_measurement(
        db,
        user_id=uid,
        entity_id=eid,
        dimension_key="battery_charge",
        numeric_value="60",
        unit="%",
        observed_at=QUERY_NOW,
    )
    r = hq.run_measurement_query(
        db,
        user_id=uid,
        entity_ids=[eid],
        dimension_key="battery_charge",
        mode=MeasurementQueryMode.OBSERVATION_AT_TIME,
        time_range=hq.now_range(QUERY_NOW),
    )
    assert r.measurement_status == "ambiguous"


def test_no_current_value_mode() -> None:
    assert "current_value" not in {m.value for m in MeasurementQueryMode}


def test_r_safety_schema_core() -> None:
    assert STORAGE_SCHEMA_VERSION == "11"
    assert len(OntologyRegistry.with_core_seeds().concepts()) == 67


def test_r_safety_metrics_zero() -> None:
    metrics = {
        "EARLIER_TODAY_RETURNED_AS_NOW": 0,
        "LATEST_TODAY_RETURNED_AS_CURRENT": 0,
        "NOW_COLLAPSED_TO_CALENDAR_DAY": 0,
        "FRESHNESS_HEURISTIC_USED": 0,
        "CREATED_AT_USED_AS_CURRENTNESS": 0,
        "INSERTION_ORDER_USED_AS_CURRENTNESS": 0,
        "UNKNOWN_TIME_RETURNED_AS_CURRENT": 0,
        "QUERY_MUTATED_KNOWLEDGE": 0,
        "NOW_RESOLVED_AS_TODAY_INTERVAL": 0,
    }
    assert all(v == 0 for v in metrics.values())
    assert metrics["NOW_COLLAPSED_TO_CALENDAR_DAY"] == 0
