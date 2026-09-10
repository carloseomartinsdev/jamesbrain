"""Conversão explícita domínio ↔ ORM."""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from enum import StrEnum
from typing import Any

from pke.domain.attributes import AttributeValueKind, EntityAttribute
from pke.domain.corrections import (
    Correction,
    CorrectionOperation,
    KnowledgePrimitiveKind,
    KnowledgeReference,
)
from pke.domain.entities import Entity
from pke.domain.event_participants import EventParticipant
from pke.domain.events import Event
from pke.domain.facts import Fact
from pke.domain.ids import new_ulid
from pke.domain.measurements import Measurement
from pke.domain.ontology import ConceptRef
from pke.domain.relations import Relation
from pke.domain.states import State
from pke.domain.temporal_knowledge import (
    OccurrenceStatus,
    RelationToReference,
    TemporalGranularity,
    TemporalKind,
    TemporalKnowledge,
    TemporalSourceKind,
    TemporalUnknownReason,
)
from pke.domain.value_objects import (
    AnchorKind,
    Confidence,
    DayPeriod,
    EpistemicStatus,
    EventStatus,
    Money,
    Qualifier,
    RawInput,
    Recurrence,
    Source,
    SourceKind,
    TimePrecision,
    TimeValue,
)
from pke.persist.sqlite.tables import (
    AliasRow,
    EntityAttributeRow,
    EntityRow,
    EventDomainRow,
    EventParticipantRow,
    EventRow,
    FactRow,
    KnowledgeCorrectionRow,
    MeasurementRow,
    RawInputRow,
    RelationRow,
    SourceRow,
    StateRow,
)
from pke.resolution.normalize import normalize_lexical


class ValueKind(StrEnum):
    NULL = "null"
    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    MONEY = "money"
    CONCEPT_REF = "concept_ref"
    ENTITY_REF = "entity_ref"
    TEMPORAL = "temporal"
    JSON = "json"


def as_utc(value: dt.datetime) -> dt.datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.UTC)
    return value.astimezone(dt.UTC)


def from_stored_dt(value: dt.datetime | None) -> dt.datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=dt.UTC)
    return value


def encode_value(value: Any) -> dict[str, Any]:
    if isinstance(value, Money):
        return {
            "kind": ValueKind.MONEY,
            "money_amount": value.amount,
            "money_currency": value.currency,
        }
    if isinstance(value, bool):
        return {"kind": ValueKind.BOOLEAN, "value_bool": value}
    if isinstance(value, int):
        return {"kind": ValueKind.INTEGER, "value_int": value}
    if isinstance(value, Decimal):
        return {"kind": ValueKind.DECIMAL, "value_decimal": value}
    if isinstance(value, ConceptRef):
        return {"kind": ValueKind.CONCEPT_REF, "ref_id": value.concept_id or value.key}
    if isinstance(value, TimeValue):
        return {"kind": ValueKind.TEMPORAL, "value_json": value.model_dump_json()}
    if isinstance(value, dict) and "currency" in value and "amount" in value:
        return {
            "kind": ValueKind.MONEY,
            "money_amount": Decimal(str(value["amount"])),
            "money_currency": str(value["currency"]),
        }
    if isinstance(value, dict) and "entity_id" in value:
        return {"kind": ValueKind.ENTITY_REF, "ref_id": str(value["entity_id"])}
    if isinstance(value, str):
        return {"kind": ValueKind.STRING, "value_text": value}
    return {"kind": ValueKind.JSON, "value_json": json.dumps(value, default=str)}


def decode_value(kind: str, row: FactRow | StateRow) -> Any:
    k = ValueKind(kind)
    if k is ValueKind.NULL:
        return None
    if k is ValueKind.MONEY:
        return Money(amount=Decimal(str(row.money_amount)), currency=row.money_currency or "BRL")
    if k is ValueKind.BOOLEAN:
        return bool(row.value_bool)
    if k is ValueKind.INTEGER:
        return int(row.value_int) if row.value_int is not None else None
    if k is ValueKind.DECIMAL:
        return Decimal(str(row.value_decimal))
    if k is ValueKind.CONCEPT_REF:
        token = row.ref_id or ""
        if token.startswith("core:") or "." in token:
            key = token.removeprefix("core:") if token.startswith("core:") else token
            cid = token if token.startswith("core:") else None
            return ConceptRef(key=key if "." in key else token, concept_id=cid)
        return ConceptRef(key=token)
    if k is ValueKind.ENTITY_REF:
        return {"entity_id": row.ref_id}
    if k is ValueKind.TEMPORAL:
        return TimeValue.model_validate_json(row.value_json or "{}")
    if k is ValueKind.STRING:
        return row.value_text
    if row.value_json:
        return json.loads(row.value_json)
    return None


def raw_to_row(raw: RawInput) -> RawInputRow:
    return RawInputRow(
        id=raw.id,
        user_id=raw.user_id,
        text=raw.text,
        created_at=as_utc(raw.created_at),
    )


def raw_from_row(row: RawInputRow) -> RawInput:
    created = from_stored_dt(row.created_at)
    assert created is not None
    return RawInput(id=row.id, user_id=row.user_id, text=row.text, created_at=created)


def entity_to_row(entity: Entity) -> EntityRow:
    return EntityRow(
        id=entity.id,
        user_id=entity.user_id,
        type_id=entity.type_id,
        canonical_name=entity.canonical_name,
        normalized_canonical_name=normalize_lexical(entity.canonical_name),
        created_at=as_utc(entity.created_at),
        aliases=[
            AliasRow(
                entity_id=entity.id,
                user_id=entity.user_id,
                alias=alias,
                normalized_alias=normalize_lexical(alias),
            )
            for alias in entity.aliases
        ],
    )


def entity_from_row(row: EntityRow) -> Entity:
    created = from_stored_dt(row.created_at)
    assert created is not None
    return Entity(
        id=row.id,
        user_id=row.user_id,
        type_id=row.type_id,
        canonical_name=row.canonical_name,
        aliases=[a.alias for a in row.aliases],
        created_at=created,
    )


def source_to_row(source: Source) -> SourceRow:
    return SourceRow(
        id=source.id or new_ulid(),
        user_id=source.user_id,
        kind=source.kind.value,
        raw_input_id=source.raw_input_id,
        rule_id=source.rule_id,
    )


def source_from_row(row: SourceRow) -> Source:
    return Source(
        id=row.id,
        user_id=row.user_id,
        kind=SourceKind(row.kind),
        raw_input_id=row.raw_input_id,
        rule_id=row.rule_id,
    )


def _time_to_columns(time: TimeValue | None, temporal: TemporalKnowledge) -> dict[str, Any]:
    rec = time.recurrence if time else None
    conf = time.confidence if time else None
    precision = time.precision.value if time else temporal.legacy_time_precision().value
    return {
        "time_original_text": temporal.original_text if time is None else time.original_text,
        "time_interpretation": time.interpretation if time else None,
        "time_instant": as_utc(time.instant) if time and time.instant else None,
        "time_date": time.date if time else None,
        "time_of_day": time.time_of_day if time else None,
        "time_period_start": as_utc(time.period_start) if time and time.period_start else None,
        "time_period_end": as_utc(time.period_end) if time and time.period_end else None,
        "time_timezone": time.timezone if time else None,
        "time_precision": precision,
        "time_day_period": time.day_period.value if time and time.day_period else None,
        "time_resolution_rule": time.resolution_rule if time else None,
        "time_reference_at": as_utc(time.reference_at) if time and time.reference_at else None,
        "time_reference_timezone": time.reference_timezone if time else None,
        "time_confidence_score": conf.score if conf else None,
        "time_confidence_qualifier": conf.qualifier.value if conf else None,
        "temporal_kind": temporal.kind.value,
        "temporal_relation": (
            temporal.relation_to_reference.value if temporal.relation_to_reference else None
        ),
        "temporal_occurrence_status": (
            temporal.occurrence_status.value if temporal.occurrence_status else None
        ),
        "temporal_unknown_reason": (
            temporal.unknown_reason.value if temporal.unknown_reason else None
        ),
        "temporal_interval_start": temporal.interval_start,
        "temporal_interval_end": temporal.interval_end,
        "temporal_granularity": (
            temporal.granularity.value
            if temporal.granularity is not TemporalGranularity.UNSPECIFIED
            else None
        ),
        "temporal_tense_evidence": temporal.tense_evidence,
        "temporal_source_kind": temporal.source_kind.value if temporal.source_kind else None,
        "rec_freq": rec.freq if rec else None,
        "rec_interval": rec.interval if rec else None,
        "rec_by_monthday": rec.by_monthday if rec else None,
        "rec_by_weekday": rec.by_weekday if rec else None,
        "rec_until": rec.until if rec else None,
        "rec_count": rec.count if rec else None,
        "rec_rrule": rec.rrule if rec else None,
    }


def _temporal_from_row(row: EventRow) -> TemporalKnowledge:
    calendar = None
    if row.time_precision != TimePrecision.PARTIAL.value:
        calendar = _time_from_row(row)
    kind = TemporalKind(row.temporal_kind) if row.temporal_kind else TemporalKind.EXACT
    if calendar is not None and kind is TemporalKind.UNKNOWN:
        kind = TemporalKnowledge.from_calendar(calendar).kind
    return TemporalKnowledge(
        kind=kind,
        original_text=row.time_original_text,
        calendar=calendar,
        relation_to_reference=(
            RelationToReference(row.temporal_relation) if row.temporal_relation else None
        ),
        occurrence_status=(
            OccurrenceStatus(row.temporal_occurrence_status)
            if row.temporal_occurrence_status
            else None
        ),
        unknown_reason=(
            TemporalUnknownReason(row.temporal_unknown_reason)
            if row.temporal_unknown_reason
            else None
        ),
        interval_start=row.temporal_interval_start,
        interval_end=row.temporal_interval_end,
        granularity=(
            TemporalGranularity(row.temporal_granularity)
            if row.temporal_granularity
            else TemporalGranularity.UNSPECIFIED
        ),
        tense_evidence=row.temporal_tense_evidence,
        source_kind=(
            TemporalSourceKind(row.temporal_source_kind) if row.temporal_source_kind else None
        ),
    )


def _time_from_row(row: EventRow) -> TimeValue:
    rec = None
    if row.rec_freq:
        rec = Recurrence(
            freq=row.rec_freq,
            interval=row.rec_interval or 1,
            by_monthday=row.rec_by_monthday,
            by_weekday=row.rec_by_weekday,
            until=row.rec_until,
            count=row.rec_count,
            rrule=row.rec_rrule,
        )
    conf = None
    if row.time_confidence_score is not None:
        conf = Confidence(
            score=row.time_confidence_score,
            qualifier=Qualifier(row.time_confidence_qualifier or "exact"),
        )
    return TimeValue(
        original_text=row.time_original_text,
        interpretation=row.time_interpretation,
        instant=from_stored_dt(row.time_instant),
        date=row.time_date,
        time_of_day=row.time_of_day,
        period_start=from_stored_dt(row.time_period_start),
        period_end=from_stored_dt(row.time_period_end),
        timezone=row.time_timezone,
        recurrence=rec,
        precision=TimePrecision(row.time_precision),
        confidence=conf,
        reference_at=from_stored_dt(row.time_reference_at),
        reference_timezone=row.time_reference_timezone,
        day_period=DayPeriod(row.time_day_period) if row.time_day_period else None,
        resolution_rule=row.time_resolution_rule,
    )


def event_to_row(event: Event) -> EventRow:
    created = as_utc(event.created_at or dt.datetime.now(dt.UTC))
    row = EventRow(
        id=event.id,
        user_id=event.user_id,
        type_id=event.type_id,
        action_id=event.action_id,
        actor_id=event.actor_id,
        subject_id=event.subject_id,
        status=event.status.value,
        raw_input_id=event.raw_input_id,
        created_at=created,
        domains=[EventDomainRow(event_id=event.id, concept_id=cid) for cid in event.domain_ids],
        participants=[
            EventParticipantRow(
                id=p.id,
                event_id=event.id,
                entity_id=p.entity_id,
                role=p.role,
            )
            for p in event.participants
        ],
        **_time_to_columns(event.temporal.calendar, event.temporal),
    )
    return row


def event_from_row(row: EventRow) -> Event:
    return Event(
        id=row.id,
        user_id=row.user_id,
        type_id=row.type_id,
        action_id=row.action_id,
        actor_id=row.actor_id,
        subject_id=row.subject_id,
        participants=[
            EventParticipant(
                id=p.id,
                event_id=p.event_id,
                entity_id=p.entity_id,
                role=p.role,
            )
            for p in (row.participants or [])
        ],
        temporal=_temporal_from_row(row),
        status=EventStatus(row.status),
        domain_ids=[d.concept_id for d in row.domains],
        raw_input_id=row.raw_input_id,
        created_at=from_stored_dt(row.created_at),
    )


def _apply_encoded(row: FactRow | StateRow, encoded: dict[str, Any]) -> None:
    kind_attr = "payload_kind" if isinstance(row, StateRow) else "value_kind"
    setattr(row, kind_attr, encoded["kind"])
    row.value_text = encoded.get("value_text")
    row.value_int = encoded.get("value_int")
    row.value_decimal = encoded.get("value_decimal")
    row.value_bool = encoded.get("value_bool")
    row.money_amount = encoded.get("money_amount")
    row.money_currency = encoded.get("money_currency")
    row.ref_id = encoded.get("ref_id")
    row.value_json = encoded.get("value_json")


def fact_to_row(fact: Fact, source_id: str) -> FactRow:
    row = FactRow(
        id=fact.id,
        user_id=fact.user_id,
        about_kind=fact.about_kind.value,
        about_id=fact.about_id,
        concept_id=fact.concept_id,
        key=fact.key,
        qualifier=fact.qualifier.value,
        epistemic_status=fact.epistemic_status.value,
        confidence_score=fact.confidence.score,
        confidence_qualifier=fact.confidence.qualifier.value,
        source_id=source_id,
        supersedes_id=fact.supersedes_id,
        created_at=as_utc(fact.created_at),
        superseded_at=as_utc(fact.superseded_at) if fact.superseded_at else None,
        value_kind=ValueKind.STRING.value,
    )
    _apply_encoded(row, encode_value(fact.value))
    return row


def fact_from_row(row: FactRow, source: Source) -> Fact:
    created = from_stored_dt(row.created_at)
    assert created is not None
    return Fact(
        id=row.id,
        user_id=row.user_id,
        about_kind=AnchorKind(row.about_kind),
        about_id=row.about_id,
        concept_id=row.concept_id,
        key=row.key,
        value=decode_value(row.value_kind, row),
        qualifier=Qualifier(row.qualifier),
        epistemic_status=EpistemicStatus(row.epistemic_status),
        source=source,
        confidence=Confidence(
            score=row.confidence_score,
            qualifier=Qualifier(row.confidence_qualifier),
        ),
        supersedes_id=row.supersedes_id,
        created_at=created,
        superseded_at=from_stored_dt(row.superseded_at),
    )


def relation_to_row(relation: Relation) -> RelationRow:
    calendar = relation.temporal.calendar
    precision = (
        calendar.precision.value if calendar else relation.temporal.legacy_time_precision().value
    )
    row = RelationRow(
        id=relation.id,
        user_id=relation.user_id,
        from_id=relation.from_id,
        to_id=relation.to_id,
        type_id=relation.concept_id,
        key=relation.key,
        is_current=relation.is_current,
        valid_from=as_utc(relation.valid_from) if relation.valid_from else None,
        valid_to=as_utc(relation.valid_to) if relation.valid_to else None,
        caused_by_event_id=relation.caused_by_event_id,
        supersedes_id=relation.supersedes_id,
        raw_input_id=relation.raw_input_id,
        source_id=relation.source.id if relation.source else None,
        observed_at=as_utc(relation.observed_at),
        created_at=as_utc(relation.created_at or relation.observed_at),
        confidence_score=relation.confidence.score if relation.confidence else None,
        confidence_qualifier=relation.confidence.qualifier.value if relation.confidence else None,
        time_original_text=relation.temporal.original_text,
        time_date=calendar.date if calendar else None,
        time_instant=as_utc(calendar.instant) if calendar and calendar.instant else None,
        time_precision=precision,
        temporal_kind=relation.temporal.kind.value,
        temporal_relation=(
            relation.temporal.relation_to_reference.value
            if relation.temporal.relation_to_reference
            else None
        ),
        temporal_occurrence_status=(
            relation.temporal.occurrence_status.value
            if relation.temporal.occurrence_status
            else None
        ),
        temporal_unknown_reason=(
            relation.temporal.unknown_reason.value if relation.temporal.unknown_reason else None
        ),
        temporal_interval_start=relation.temporal.interval_start,
        temporal_interval_end=relation.temporal.interval_end,
        temporal_granularity=(
            relation.temporal.granularity.value
            if relation.temporal.granularity is not TemporalGranularity.UNSPECIFIED
            else None
        ),
        temporal_tense_evidence=relation.temporal.tense_evidence,
        temporal_source_kind=(
            relation.temporal.source_kind.value if relation.temporal.source_kind else None
        ),
    )
    _apply_relation_termination_to_row(row, relation)
    return row


def _apply_relation_termination_to_row(row: RelationRow, relation: Relation) -> None:
    term = relation.termination_temporal
    if term is None:
        return
    calendar = term.calendar
    precision = calendar.precision.value if calendar else term.legacy_time_precision().value
    row.term_time_original_text = term.original_text
    row.term_time_date = calendar.date if calendar else None
    row.term_time_instant = as_utc(calendar.instant) if calendar and calendar.instant else None
    row.term_time_precision = precision
    row.term_temporal_kind = term.kind.value
    row.term_temporal_relation = (
        term.relation_to_reference.value if term.relation_to_reference else None
    )
    row.term_temporal_occurrence_status = (
        term.occurrence_status.value if term.occurrence_status else None
    )
    row.term_temporal_unknown_reason = (
        term.unknown_reason.value if term.unknown_reason else None
    )
    row.term_temporal_interval_start = term.interval_start
    row.term_temporal_interval_end = term.interval_end
    row.term_temporal_granularity = (
        term.granularity.value
        if term.granularity is not TemporalGranularity.UNSPECIFIED
        else None
    )
    row.term_temporal_tense_evidence = term.tense_evidence
    row.term_temporal_source_kind = term.source_kind.value if term.source_kind else None
    if relation.termination_observed_at is not None:
        row.termination_observed_at = as_utc(relation.termination_observed_at)
    row.termination_raw_input_id = relation.termination_raw_input_id
    row.termination_source_id = (
        relation.termination_source.id if relation.termination_source else None
    )
    if relation.termination_confidence is not None:
        row.termination_confidence_score = relation.termination_confidence.score
        row.termination_confidence_qualifier = relation.termination_confidence.qualifier.value


def relation_from_row(
    row: RelationRow,
    source: Source | None = None,
    termination_source: Source | None = None,
) -> Relation:
    observed = from_stored_dt(row.observed_at)
    assert observed is not None
    conf = None
    if row.confidence_score is not None:
        conf = Confidence(
            score=row.confidence_score,
            qualifier=Qualifier(row.confidence_qualifier or "exact"),
        )
    term_conf = None
    if row.termination_confidence_score is not None:
        term_conf = Confidence(
            score=row.termination_confidence_score,
            qualifier=Qualifier(row.termination_confidence_qualifier or "exact"),
        )
    return Relation(
        id=row.id,
        user_id=row.user_id,
        from_id=row.from_id,
        to_id=row.to_id,
        concept_id=row.type_id,
        key=row.key or row.type_id.removeprefix("core:"),
        temporal=_relation_temporal_from_row(row),
        observed_at=observed,
        valid_from=from_stored_dt(row.valid_from),
        valid_to=from_stored_dt(row.valid_to),
        caused_by_event_id=row.caused_by_event_id,
        supersedes_id=row.supersedes_id,
        is_current=bool(row.is_current),
        raw_input_id=row.raw_input_id,
        source=source,
        confidence=conf,
        created_at=from_stored_dt(row.created_at),
        termination_temporal=_relation_termination_temporal_from_row(row),
        termination_observed_at=from_stored_dt(row.termination_observed_at),
        termination_raw_input_id=row.termination_raw_input_id,
        termination_source=termination_source,
        termination_confidence=term_conf,
    )


def _relation_termination_temporal_from_row(row: RelationRow) -> TemporalKnowledge | None:
    if row.termination_observed_at is None and row.term_temporal_kind is None:
        return None
    calendar = None
    if row.term_time_precision and row.term_time_precision != TimePrecision.PARTIAL.value and (
        row.term_time_date is not None or row.term_time_instant is not None
    ):
        calendar = TimeValue(
            original_text=row.term_time_original_text or "",
            date=row.term_time_date,
            instant=from_stored_dt(row.term_time_instant),
            precision=TimePrecision(row.term_time_precision),
            resolution_rule="relation.termination",
        )
    kind = (
        TemporalKind(row.term_temporal_kind)
        if row.term_temporal_kind
        else TemporalKind.PARTIAL
    )
    if calendar is not None and kind is TemporalKind.UNKNOWN:
        kind = TemporalKnowledge.from_calendar(calendar).kind
    return TemporalKnowledge(
        kind=kind,
        original_text=row.term_time_original_text or "",
        calendar=calendar,
        relation_to_reference=(
            RelationToReference(row.term_temporal_relation) if row.term_temporal_relation else None
        ),
        occurrence_status=(
            OccurrenceStatus(row.term_temporal_occurrence_status)
            if row.term_temporal_occurrence_status
            else None
        ),
        unknown_reason=(
            TemporalUnknownReason(row.term_temporal_unknown_reason)
            if row.term_temporal_unknown_reason
            else None
        ),
        interval_start=row.term_temporal_interval_start,
        interval_end=row.term_temporal_interval_end,
        granularity=(
            TemporalGranularity(row.term_temporal_granularity)
            if row.term_temporal_granularity
            else TemporalGranularity.UNSPECIFIED
        ),
        tense_evidence=row.term_temporal_tense_evidence,
        source_kind=(
            TemporalSourceKind(row.term_temporal_source_kind)
            if row.term_temporal_source_kind
            else None
        ),
    )


def _relation_temporal_from_row(row: RelationRow) -> TemporalKnowledge:
    calendar = None
    if row.time_precision != TimePrecision.PARTIAL.value and (
        row.time_date is not None or row.time_instant is not None
    ):
        calendar = TimeValue(
            original_text=row.time_original_text,
            date=row.time_date,
            instant=from_stored_dt(row.time_instant),
            precision=TimePrecision(row.time_precision),
            resolution_rule="relation.observed",
        )
    kind = TemporalKind(row.temporal_kind) if row.temporal_kind else TemporalKind.PARTIAL
    if calendar is not None and kind is TemporalKind.UNKNOWN:
        kind = TemporalKnowledge.from_calendar(calendar).kind
    return TemporalKnowledge(
        kind=kind,
        original_text=row.time_original_text,
        calendar=calendar,
        relation_to_reference=(
            RelationToReference(row.temporal_relation) if row.temporal_relation else None
        ),
        occurrence_status=(
            OccurrenceStatus(row.temporal_occurrence_status)
            if row.temporal_occurrence_status
            else None
        ),
        unknown_reason=(
            TemporalUnknownReason(row.temporal_unknown_reason)
            if row.temporal_unknown_reason
            else None
        ),
        interval_start=row.temporal_interval_start,
        interval_end=row.temporal_interval_end,
        granularity=(
            TemporalGranularity(row.temporal_granularity)
            if row.temporal_granularity
            else TemporalGranularity.UNSPECIFIED
        ),
        tense_evidence=row.temporal_tense_evidence,
        source_kind=(
            TemporalSourceKind(row.temporal_source_kind) if row.temporal_source_kind else None
        ),
    )


def state_to_row(state: State) -> StateRow:
    calendar = state.temporal.calendar
    precision = (
        calendar.precision.value if calendar else state.temporal.legacy_time_precision().value
    )
    row = StateRow(
        id=state.id,
        user_id=state.user_id,
        entity_id=state.entity_id,
        dimension_concept_id=state.dimension_id,
        dimension_key=state.dimension_key,
        value_concept_id=state.value_concept_id,
        value_key=state.value_key,
        is_current=state.is_current,
        valid_from=as_utc(state.valid_from) if state.valid_from else None,
        valid_to=as_utc(state.valid_to) if state.valid_to else None,
        caused_by_event_id=state.caused_by_event_id,
        supersedes_id=state.supersedes_id,
        raw_input_id=state.raw_input_id,
        source_id=state.source.id if state.source else None,
        observed_at=as_utc(state.observed_at),
        created_at=as_utc(state.created_at or state.observed_at),
        confidence_score=state.confidence.score if state.confidence else None,
        confidence_qualifier=state.confidence.qualifier.value if state.confidence else None,
        time_original_text=state.temporal.original_text,
        time_date=calendar.date if calendar else None,
        time_instant=as_utc(calendar.instant) if calendar and calendar.instant else None,
        time_precision=precision,
        temporal_kind=state.temporal.kind.value,
        temporal_relation=(
            state.temporal.relation_to_reference.value
            if state.temporal.relation_to_reference
            else None
        ),
        temporal_occurrence_status=(
            state.temporal.occurrence_status.value if state.temporal.occurrence_status else None
        ),
        temporal_unknown_reason=(
            state.temporal.unknown_reason.value if state.temporal.unknown_reason else None
        ),
        temporal_interval_start=state.temporal.interval_start,
        temporal_interval_end=state.temporal.interval_end,
        temporal_granularity=(
            state.temporal.granularity.value
            if state.temporal.granularity is not TemporalGranularity.UNSPECIFIED
            else None
        ),
        temporal_tense_evidence=state.temporal.tense_evidence,
        temporal_source_kind=(
            state.temporal.source_kind.value if state.temporal.source_kind else None
        ),
        payload_kind=ValueKind.NULL.value if state.payload is None else ValueKind.JSON.value,
    )
    if state.payload is not None:
        encoded = encode_value(state.payload)
        row.payload_kind = encoded["kind"]
        _apply_encoded(row, encoded)
    return row


def _state_temporal_from_row(row: StateRow) -> TemporalKnowledge:
    calendar = None
    if row.time_precision != TimePrecision.PARTIAL.value and (
        row.time_date is not None or row.time_instant is not None
    ):
        calendar = TimeValue(
            original_text=row.time_original_text,
            date=row.time_date,
            instant=from_stored_dt(row.time_instant),
            precision=TimePrecision(row.time_precision),
            resolution_rule="state.observed",
        )
    kind = TemporalKind(row.temporal_kind) if row.temporal_kind else TemporalKind.PARTIAL
    if calendar is not None and kind is TemporalKind.UNKNOWN:
        kind = TemporalKnowledge.from_calendar(calendar).kind
    return TemporalKnowledge(
        kind=kind,
        original_text=row.time_original_text,
        calendar=calendar,
        relation_to_reference=(
            RelationToReference(row.temporal_relation) if row.temporal_relation else None
        ),
        occurrence_status=(
            OccurrenceStatus(row.temporal_occurrence_status)
            if row.temporal_occurrence_status
            else None
        ),
        unknown_reason=(
            TemporalUnknownReason(row.temporal_unknown_reason)
            if row.temporal_unknown_reason
            else None
        ),
        interval_start=row.temporal_interval_start,
        interval_end=row.temporal_interval_end,
        granularity=(
            TemporalGranularity(row.temporal_granularity)
            if row.temporal_granularity
            else TemporalGranularity.UNSPECIFIED
        ),
        tense_evidence=row.temporal_tense_evidence,
        source_kind=(
            TemporalSourceKind(row.temporal_source_kind) if row.temporal_source_kind else None
        ),
    )


def state_from_row(row: StateRow, source: Source | None = None) -> State:
    observed = from_stored_dt(row.observed_at)
    assert observed is not None
    conf = None
    if row.confidence_score is not None:
        conf = Confidence(
            score=row.confidence_score,
            qualifier=Qualifier(row.confidence_qualifier or "exact"),
        )
    payload = None
    if row.payload_kind != ValueKind.NULL.value:
        payload = decode_value(row.payload_kind, row)
    return State(
        id=row.id,
        user_id=row.user_id,
        entity_id=row.entity_id,
        dimension_id=row.dimension_concept_id,
        dimension_key=row.dimension_key,
        value_concept_id=row.value_concept_id,
        value_key=row.value_key,
        payload=payload,
        temporal=_state_temporal_from_row(row),
        observed_at=observed,
        valid_from=from_stored_dt(row.valid_from),
        valid_to=from_stored_dt(row.valid_to),
        caused_by_event_id=row.caused_by_event_id,
        supersedes_id=row.supersedes_id,
        is_current=bool(row.is_current),
        raw_input_id=row.raw_input_id,
        source=source,
        confidence=conf,
        created_at=from_stored_dt(row.created_at),
    )


def entity_attribute_to_row(attr: EntityAttribute) -> EntityAttributeRow:
    calendar = attr.temporal.calendar
    precision = (
        calendar.precision.value if calendar else attr.temporal.legacy_time_precision().value
    )
    return EntityAttributeRow(
        id=attr.id,
        user_id=attr.user_id,
        entity_id=attr.entity_id,
        dimension_key=attr.dimension_key,
        dimension_concept_id=attr.dimension_concept_id,
        value_kind=attr.value_kind.value,
        concept_value_id=attr.concept_value_id,
        text_value=attr.text_value,
        numeric_value=attr.numeric_value,
        unit=attr.unit,
        date_value=attr.date_value,
        year_value=attr.year_value,
        time_original_text=attr.temporal.original_text,
        time_date=calendar.date if calendar else None,
        time_instant=as_utc(calendar.instant) if calendar and calendar.instant else None,
        time_precision=precision,
        temporal_kind=attr.temporal.kind.value,
        temporal_relation=(
            attr.temporal.relation_to_reference.value
            if attr.temporal.relation_to_reference
            else None
        ),
        temporal_occurrence_status=(
            attr.temporal.occurrence_status.value if attr.temporal.occurrence_status else None
        ),
        temporal_unknown_reason=(
            attr.temporal.unknown_reason.value if attr.temporal.unknown_reason else None
        ),
        temporal_interval_start=attr.temporal.interval_start,
        temporal_interval_end=attr.temporal.interval_end,
        temporal_granularity=(
            attr.temporal.granularity.value
            if attr.temporal.granularity is not TemporalGranularity.UNSPECIFIED
            else None
        ),
        temporal_tense_evidence=attr.temporal.tense_evidence,
        temporal_source_kind=(
            attr.temporal.source_kind.value if attr.temporal.source_kind else None
        ),
        observed_at=as_utc(attr.observed_at),
        valid_from=as_utc(attr.valid_from) if attr.valid_from else None,
        valid_to=as_utc(attr.valid_to) if attr.valid_to else None,
        is_current=attr.is_current,
        supersedes_id=attr.supersedes_id,
        raw_input_id=attr.raw_input_id,
        source_id=attr.source.id if attr.source and attr.source.id else "",
        confidence_score=attr.confidence.score if attr.confidence else None,
        confidence_qualifier=attr.confidence.qualifier.value if attr.confidence else None,
        created_at=as_utc(attr.created_at or attr.observed_at),
    )


def _attribute_temporal_from_row(row: EntityAttributeRow) -> TemporalKnowledge:
    calendar = None
    if row.time_precision != TimePrecision.PARTIAL.value and (
        row.time_date is not None or row.time_instant is not None
    ):
        calendar = TimeValue(
            original_text=row.time_original_text,
            date=row.time_date,
            instant=from_stored_dt(row.time_instant),
            precision=TimePrecision(row.time_precision),
        )
    kind = TemporalKind(row.temporal_kind) if row.temporal_kind else TemporalKind.UNKNOWN
    return TemporalKnowledge(
        kind=kind,
        original_text=row.time_original_text or "",
        calendar=calendar,
        relation_to_reference=(
            RelationToReference(row.temporal_relation) if row.temporal_relation else None
        ),
        occurrence_status=(
            OccurrenceStatus(row.temporal_occurrence_status)
            if row.temporal_occurrence_status
            else None
        ),
        unknown_reason=(
            TemporalUnknownReason(row.temporal_unknown_reason)
            if row.temporal_unknown_reason
            else None
        ),
        interval_start=row.temporal_interval_start,
        interval_end=row.temporal_interval_end,
        granularity=(
            TemporalGranularity(row.temporal_granularity)
            if row.temporal_granularity
            else TemporalGranularity.UNSPECIFIED
        ),
        tense_evidence=row.temporal_tense_evidence,
        source_kind=(
            TemporalSourceKind(row.temporal_source_kind) if row.temporal_source_kind else None
        ),
    )


def entity_attribute_from_row(
    row: EntityAttributeRow, source: Source | None = None
) -> EntityAttribute:
    observed = from_stored_dt(row.observed_at)
    assert observed is not None
    conf = None
    if row.confidence_score is not None:
        conf = Confidence(
            score=row.confidence_score,
            qualifier=Qualifier(row.confidence_qualifier or "exact"),
        )
    return EntityAttribute(
        id=row.id,
        user_id=row.user_id,
        entity_id=row.entity_id,
        dimension_key=row.dimension_key,
        dimension_concept_id=row.dimension_concept_id,
        value_kind=AttributeValueKind(row.value_kind),
        concept_value_id=row.concept_value_id,
        text_value=row.text_value,
        numeric_value=row.numeric_value,
        unit=row.unit,
        date_value=row.date_value,
        year_value=row.year_value,
        temporal=_attribute_temporal_from_row(row),
        observed_at=observed,
        valid_from=from_stored_dt(row.valid_from),
        valid_to=from_stored_dt(row.valid_to),
        is_current=bool(row.is_current),
        supersedes_id=row.supersedes_id,
        source=source,
        raw_input_id=row.raw_input_id,
        confidence=conf,
        created_at=from_stored_dt(row.created_at),
    )


def measurement_to_row(m: Measurement) -> MeasurementRow:
    calendar = m.temporal.calendar
    precision = (
        calendar.precision.value if calendar else m.temporal.legacy_time_precision().value
    )
    return MeasurementRow(
        id=m.id,
        user_id=m.user_id,
        entity_id=m.entity_id,
        context_entity_id=m.context_entity_id,
        dimension_key=m.dimension_key,
        dimension_concept_id=m.dimension_concept_id,
        numeric_value=m.numeric_value,
        unit=m.unit,
        currency_code=m.currency_code,
        time_original_text=m.temporal.original_text,
        time_date=calendar.date if calendar else None,
        time_instant=as_utc(calendar.instant) if calendar and calendar.instant else None,
        time_precision=precision,
        temporal_kind=m.temporal.kind.value,
        temporal_relation=(
            m.temporal.relation_to_reference.value if m.temporal.relation_to_reference else None
        ),
        temporal_occurrence_status=(
            m.temporal.occurrence_status.value if m.temporal.occurrence_status else None
        ),
        temporal_unknown_reason=(
            m.temporal.unknown_reason.value if m.temporal.unknown_reason else None
        ),
        temporal_interval_start=m.temporal.interval_start,
        temporal_interval_end=m.temporal.interval_end,
        temporal_granularity=(
            m.temporal.granularity.value
            if m.temporal.granularity is not TemporalGranularity.UNSPECIFIED
            else None
        ),
        temporal_tense_evidence=m.temporal.tense_evidence,
        temporal_source_kind=(
            m.temporal.source_kind.value if m.temporal.source_kind else None
        ),
        observed_at=as_utc(m.observed_at) if m.observed_at else None,
        raw_input_id=m.raw_input_id,
        source_id=m.source.id if m.source and m.source.id else "",
        confidence_score=m.confidence.score if m.confidence else None,
        confidence_qualifier=m.confidence.qualifier.value if m.confidence else None,
        created_at=as_utc(m.created_at) if m.created_at else as_utc(dt.datetime.now(dt.UTC)),
    )


def _measurement_temporal_from_row(row: MeasurementRow) -> TemporalKnowledge:
    calendar = None
    if row.time_precision != TimePrecision.PARTIAL.value and (
        row.time_date is not None or row.time_instant is not None
    ):
        calendar = TimeValue(
            original_text=row.time_original_text,
            date=row.time_date,
            instant=from_stored_dt(row.time_instant),
            precision=TimePrecision(row.time_precision),
        )
    kind = TemporalKind(row.temporal_kind) if row.temporal_kind else TemporalKind.UNKNOWN
    return TemporalKnowledge(
        kind=kind,
        original_text=row.time_original_text or "",
        calendar=calendar,
        relation_to_reference=(
            RelationToReference(row.temporal_relation) if row.temporal_relation else None
        ),
        occurrence_status=(
            OccurrenceStatus(row.temporal_occurrence_status)
            if row.temporal_occurrence_status
            else None
        ),
        unknown_reason=(
            TemporalUnknownReason(row.temporal_unknown_reason)
            if row.temporal_unknown_reason
            else None
        ),
        interval_start=row.temporal_interval_start,
        interval_end=row.temporal_interval_end,
        granularity=(
            TemporalGranularity(row.temporal_granularity)
            if row.temporal_granularity
            else TemporalGranularity.UNSPECIFIED
        ),
        tense_evidence=row.temporal_tense_evidence,
        source_kind=(
            TemporalSourceKind(row.temporal_source_kind) if row.temporal_source_kind else None
        ),
    )


def measurement_from_row(row: MeasurementRow, source: Source | None = None) -> Measurement:
    conf = None
    if row.confidence_score is not None:
        conf = Confidence(
            score=row.confidence_score,
            qualifier=Qualifier(row.confidence_qualifier or "exact"),
        )
    created = from_stored_dt(row.created_at)
    assert created is not None
    return Measurement(
        id=row.id,
        user_id=row.user_id,
        entity_id=row.entity_id,
        context_entity_id=row.context_entity_id,
        dimension_key=row.dimension_key,
        dimension_concept_id=row.dimension_concept_id,
        numeric_value=row.numeric_value,
        unit=row.unit,
        currency_code=row.currency_code,
        temporal=_measurement_temporal_from_row(row),
        observed_at=from_stored_dt(row.observed_at),
        source=source,
        raw_input_id=row.raw_input_id,
        confidence=conf,
        created_at=created,
    )


def correction_to_row(c: Correction) -> KnowledgeCorrectionRow:
    return KnowledgeCorrectionRow(
        id=c.id,
        user_id=c.user_id,
        operation=c.operation.value,
        target_kind=c.target.kind.value,
        target_id=c.target.assertion_id,
        replacement_kind=c.replacement.kind.value if c.replacement else None,
        replacement_id=c.replacement.assertion_id if c.replacement else None,
        raw_input_id=c.raw_input_id,
        source_id=c.source_id,
        recorded_at=c.recorded_at,
    )


def correction_from_row(row: KnowledgeCorrectionRow) -> Correction:
    replacement = None
    if row.replacement_kind is not None and row.replacement_id is not None:
        replacement = KnowledgeReference(
            kind=KnowledgePrimitiveKind(row.replacement_kind),
            assertion_id=row.replacement_id,
            user_id=row.user_id,
        )
    recorded = from_stored_dt(row.recorded_at)
    assert recorded is not None
    return Correction(
        id=row.id,
        user_id=row.user_id,
        operation=CorrectionOperation(row.operation),
        target=KnowledgeReference(
            kind=KnowledgePrimitiveKind(row.target_kind),
            assertion_id=row.target_id,
            user_id=row.user_id,
        ),
        replacement=replacement,
        raw_input_id=row.raw_input_id,
        source_id=row.source_id,
        recorded_at=recorded,
    )
