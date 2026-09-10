"""I11.15.3 — MeasurementResolver epistemic unit tests (MQ corpus core)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from zoneinfo import ZoneInfo

from pke.domain.ids import new_ulid
from pke.domain.measurements import Measurement
from pke.domain.temporal_knowledge import TemporalKnowledge, TemporalUnknownReason
from pke.domain.value_objects import Confidence, TimePrecision, TimeValue
from pke.query.measurement_resolver import (
    MeasurementResolutionStatus,
    observation_instant,
    resolve_measurement_query,
)
from pke.query.spec import MeasurementQueryMode, MeasurementValueFilter, TimeRange

FORTALEZA = ZoneInfo("America/Fortaleza")
T1 = dt.datetime(2026, 8, 1, 10, 0, tzinfo=FORTALEZA)
T2 = dt.datetime(2026, 8, 15, 10, 0, tzinfo=FORTALEZA)
T3 = dt.datetime(2026, 8, 20, 10, 0, tzinfo=FORTALEZA)
YESTERDAY = dt.datetime(2026, 8, 31, 12, 0, tzinfo=FORTALEZA)  # NOW in suite is 2026-09-01


def _m(
    *,
    value: str,
    unit: str | None = "%",
    currency: str | None = None,
    observed_at: dt.datetime | None = None,
    unknown_time: bool = False,
    dimension: str = "battery_charge",
    entity_id: str = "e1",
    created_at: dt.datetime | None = None,
) -> Measurement:
    if unknown_time:
        temporal = TemporalKnowledge.unknown(
            "", unknown_reason=TemporalUnknownReason.NOT_PROVIDED
        )
        observed_at = None
    elif observed_at is not None:
        temporal = TemporalKnowledge.from_calendar(
            TimeValue(
                original_text="",
                instant=observed_at,
                timezone="America/Fortaleza",
                precision=TimePrecision.MINUTE,
            )
        )
    else:
        temporal = TemporalKnowledge.unknown(
            "", unknown_reason=TemporalUnknownReason.NOT_PROVIDED
        )
    return Measurement(
        id=new_ulid(),
        user_id="u1",
        entity_id=entity_id,
        dimension_key=dimension,
        numeric_value=Decimal(value),
        unit=unit,
        currency_code=currency,
        temporal=temporal,
        observed_at=observed_at,
        confidence=Confidence(score=1.0),
        created_at=created_at or T1,
    )


def test_mq2_mq3_latest_known_ordering() -> None:
    rows = [_m(value="80", observed_at=T1), _m(value="60", observed_at=T2)]
    r = resolve_measurement_query(
        rows, dimension_key="battery_charge", mode=MeasurementQueryMode.LATEST_OBSERVATION
    )
    assert r.status is MeasurementResolutionStatus.KNOWN_SINGLE
    assert r.groups[0].identity.numeric_value == Decimal("60")


def test_mq4_unknown_time_blocks_latest() -> None:
    rows = [_m(value="80", unknown_time=True), _m(value="60", observed_at=T2)]
    r = resolve_measurement_query(
        rows, dimension_key="battery_charge", mode=MeasurementQueryMode.LATEST_OBSERVATION
    )
    assert r.status is MeasurementResolutionStatus.AMBIGUOUS
    assert "unknown_time_blocks_latest_certainty" in r.notes


def test_mq5_observation_at_time_not_latest() -> None:
    rows = [_m(value="80", observed_at=YESTERDAY)]
    today = TimeRange(
        start=dt.datetime(2026, 9, 1, tzinfo=FORTALEZA),
        end=dt.datetime(2026, 9, 2, tzinfo=FORTALEZA),
    )
    r = resolve_measurement_query(
        rows,
        dimension_key="battery_charge",
        mode=MeasurementQueryMode.OBSERVATION_AT_TIME,
        time_range=today,
    )
    assert r.status is MeasurementResolutionStatus.UNKNOWN
    assert "not_current_from_latest" in r.notes


def test_mq6_yesterday_match() -> None:
    rows = [_m(value="80", observed_at=YESTERDAY)]
    yrange = TimeRange(
        start=dt.datetime(2026, 8, 31, tzinfo=FORTALEZA),
        end=dt.datetime(2026, 9, 1, tzinfo=FORTALEZA),
    )
    r = resolve_measurement_query(
        rows,
        dimension_key="battery_charge",
        mode=MeasurementQueryMode.OBSERVATION_AT_TIME,
        time_range=yrange,
    )
    assert r.status is MeasurementResolutionStatus.KNOWN_SINGLE
    assert r.groups[0].identity.numeric_value == Decimal("80")


def test_mq7_prop_temporally_unknown() -> None:
    rows = [_m(value="80", unknown_time=True)]
    yrange = TimeRange(
        start=dt.datetime(2026, 8, 31, tzinfo=FORTALEZA),
        end=dt.datetime(2026, 9, 1, tzinfo=FORTALEZA),
    )
    r = resolve_measurement_query(
        rows,
        dimension_key="battery_charge",
        mode=MeasurementQueryMode.VALUE_PROPOSITION,
        value_filter=MeasurementValueFilter(numeric_value=Decimal("80"), unit="%"),
        time_range=yrange,
    )
    assert r.status is MeasurementResolutionStatus.TEMPORALLY_UNKNOWN
    assert r.proposition_answer == "temporally_unknown"


def test_mq8_no_rows_not_no() -> None:
    r = resolve_measurement_query(
        [],
        dimension_key="battery_charge",
        mode=MeasurementQueryMode.VALUE_PROPOSITION,
        value_filter=MeasurementValueFilter(numeric_value=Decimal("80"), unit="%"),
    )
    assert r.status is MeasurementResolutionStatus.UNKNOWN
    assert r.proposition_answer == "unknown"
    assert r.proposition_answer != "no"  # type: ignore[comparison-overlap]


def test_mq9_equal_evidence_support() -> None:
    rows = [
        _m(value="80", observed_at=T1),
        _m(value="80.0", observed_at=T1),
    ]
    r = resolve_measurement_query(
        rows, dimension_key="battery_charge", mode=MeasurementQueryMode.LATEST_OBSERVATION
    )
    assert r.status is MeasurementResolutionStatus.KNOWN_SINGLE
    assert r.groups[0].support_count == 2


def test_mq10_conflicting_same_scope() -> None:
    rows = [_m(value="80", observed_at=T1), _m(value="60", observed_at=T1)]
    r = resolve_measurement_query(
        rows, dimension_key="battery_charge", mode=MeasurementQueryMode.LATEST_OBSERVATION
    )
    assert r.status is MeasurementResolutionStatus.AMBIGUOUS


def test_mq14_incomparable_units() -> None:
    rows = [_m(value="20", unit="L", dimension="fuel_level", observed_at=T1)]
    r = resolve_measurement_query(
        rows,
        dimension_key="fuel_level",
        mode=MeasurementQueryMode.VALUE_PROPOSITION,
        value_filter=MeasurementValueFilter(numeric_value=Decimal("20000"), unit="mL"),
    )
    assert r.status is MeasurementResolutionStatus.UNKNOWN
    assert r.proposition_answer == "unknown"
    assert "unit_or_currency_incomparable" in r.notes


def test_mq17_range_unknown_contributors() -> None:
    rows = [
        _m(value="36", unit="°C", dimension="temperature", observed_at=T1),
        _m(value="37", unit="°C", dimension="temperature", observed_at=T2),
        _m(value="38", unit="°C", dimension="temperature", observed_at=T3),
        _m(value="39", unit="°C", dimension="temperature", unknown_time=True),
    ]
    august = TimeRange(
        start=dt.datetime(2026, 8, 1, tzinfo=FORTALEZA),
        end=dt.datetime(2026, 9, 1, tzinfo=FORTALEZA),
    )
    r = resolve_measurement_query(
        rows,
        dimension_key="temperature",
        mode=MeasurementQueryMode.OBSERVATIONS_IN_RANGE,
        time_range=august,
    )
    assert r.status is MeasurementResolutionStatus.KNOWN_MULTIPLE
    assert len(r.candidate_observations) == 3
    assert len(r.unknown_temporal_contributors) == 1
    assert r.temporal_membership_unknown is True


def test_created_at_never_chronology() -> None:
    # Later created_at but earlier observed_at must not win
    early = _m(value="40", observed_at=T1, created_at=T3)
    late = _m(value="90", observed_at=T2, created_at=T1)
    r = resolve_measurement_query(
        [early, late],
        dimension_key="battery_charge",
        mode=MeasurementQueryMode.LATEST_OBSERVATION,
    )
    assert r.groups[0].identity.numeric_value == Decimal("90")
    assert observation_instant(late) == T2


def test_currency_and_percentage_and_dimensionless() -> None:
    bal = [_m(value="2500", unit=None, currency="BRL", dimension="balance", observed_at=T1)]
    r = resolve_measurement_query(
        bal,
        dimension_key="balance",
        mode=MeasurementQueryMode.VALUE_PROPOSITION,
        value_filter=MeasurementValueFilter(
            numeric_value=Decimal("2500"), currency_code="BRL"
        ),
    )
    assert r.proposition_answer == "yes"

    inv = [_m(value="12", unit=None, currency=None, dimension="inventory_count", observed_at=T1)]
    r2 = resolve_measurement_query(
        inv,
        dimension_key="inventory_count",
        mode=MeasurementQueryMode.LATEST_OBSERVATION,
    )
    assert r2.groups[0].identity.numeric_value == Decimal("12")
    assert r2.groups[0].identity.unit is None

    pct = [_m(value="80", unit="%", observed_at=T1)]
    r3 = resolve_measurement_query(
        pct,
        dimension_key="battery_charge",
        mode=MeasurementQueryMode.VALUE_PROPOSITION,
        value_filter=MeasurementValueFilter(numeric_value=Decimal("80"), unit="%"),
    )
    assert r3.proposition_answer == "yes"
