"""Wire → IR canônica. Mapeamento determinístico."""

from __future__ import annotations

import datetime as dt

from pke.domain.ontology import ConceptRef
from pke.domain.temporal_knowledge import (
    OccurrenceStatus,
    RelationToReference,
    TemporalUnknownReason,
)
from pke.domain.value_objects import EpistemicStatus, EventStatus, Qualifier, Recurrence
from pke.interpretation.models import (
    ClaimReport,
    EntityMention,
    IngestIR,
    IngestIntent,
    IrAttribute,
    IrCorrection,
    IrCorrectionTarget,
    IrEvent,
    IrFact,
    IrMeasurement,
    IrObligation,
    IrRelation,
    IrState,
    IrQueryTime,
    IrTime,
    MentionReferenceKind,
    QueryIR,
    QuerySpec,
    RelationAssertionMode,
    RelativePeriod,
)
from pke.interpretation.transport.wire import (
    WIRE_WEEKDAY_TO_INT,
    WireEntityMention,
    WireEnvelope,
    WireIngestIR,
    WireIrFact,
    WireIrTime,
    WireQueryIR,
    parse_time_of_day,
)


def wire_to_canonical(envelope: WireEnvelope) -> IngestIR | QueryIR:
    if envelope.ir_kind == "ingest":
        return _map_ingest(envelope.parsed_ingest())
    return _map_query(envelope.parsed_query())


def _cref(key: str) -> ConceptRef:
    return ConceptRef(key=key)


def _mention(wire: WireEntityMention) -> EntityMention:
    return EntityMention(
        text=wire.text,
        type_hint=_cref(wire.entity_type) if wire.entity_type else None,
        role=_cref(wire.role) if wire.role else None,
        reference_kind=MentionReferenceKind(wire.reference_kind),
        confidence=wire.confidence,
        known_entity_id=wire.known_entity_id,
    )


def _time(wire: WireIrTime) -> IrTime:
    weekday_int = WIRE_WEEKDAY_TO_INT[wire.weekday] if wire.weekday else None
    tod = parse_time_of_day(wire.time_of_day) if wire.time_of_day else None
    relation = RelationToReference(wire.relation_to_reference) if wire.relation_to_reference else None
    occurrence = OccurrenceStatus(wire.occurrence_status) if wire.occurrence_status else None
    unknown = TemporalUnknownReason(wire.unknown_reason) if wire.unknown_reason else None
    return IrTime(
        original_text=wire.original_text,
        time_of_day=tod,
        precision=wire.precision,  # type: ignore[arg-type]
        timezone=wire.timezone,
        relative_day=wire.relative_day,  # type: ignore[arg-type]
        weekday=weekday_int,
        weekday_policy=wire.weekday_policy,  # type: ignore[arg-type]
        relation_to_reference=relation,
        occurrence_status=occurrence,
        unknown_reason=unknown,
        tense_evidence=wire.tense_evidence,
        partial_month=wire.partial_month,
        partial_year=wire.partial_year,
    )


def _fact(wire: WireIrFact) -> IrFact:
    assert wire.money is not None
    return IrFact(
        attribute=_cref(wire.attribute),
        value={"amount": str(wire.money.amount), "currency": wire.money.currency},
        qualifier=Qualifier(wire.qualifier),
        epistemic_status=EpistemicStatus(wire.epistemic_status),
        confidence=wire.confidence,
    )


def _map_ingest(wire: WireIngestIR) -> IngestIR:
    return IngestIR(
        intent=IngestIntent(wire.intent),
        raw_input=wire.raw_input,
        domains=[_cref(k) for k in wire.domains],
        entities_mentioned=[_mention(m) for m in wire.entities_mentioned],
        state=(
            IrState(
                value=_cref(wire.state.value),
                dimension=_cref(wire.state.dimension) if wire.state.dimension else None,
                payload=wire.state.payload,
                time=_time(wire.state.time),
            )
            if wire.state
            else None
        ),
        attribute=(
            IrAttribute(
                subject=_mention(wire.attribute.subject),
                dimension_key=wire.attribute.dimension_key,
                value_kind=wire.attribute.value_kind,
                text_value=wire.attribute.text_value,
                numeric_value=wire.attribute.numeric_value,
                unit=wire.attribute.unit,
                year_value=wire.attribute.year_value,
                date_value=(
                    dt.date.fromisoformat(wire.attribute.date_value)
                    if wire.attribute.date_value
                    else None
                ),
                concept_value_id=wire.attribute.concept_value_id,
                is_current=wire.attribute.is_current,
                time=_time(wire.attribute.time),
            )
            if wire.attribute
            else None
        ),
        additional_attributes=[
            IrAttribute(
                subject=_mention(a.subject),
                dimension_key=a.dimension_key,
                value_kind=a.value_kind,
                text_value=a.text_value,
                numeric_value=a.numeric_value,
                unit=a.unit,
                year_value=a.year_value,
                date_value=(dt.date.fromisoformat(a.date_value) if a.date_value else None),
                concept_value_id=a.concept_value_id,
                is_current=a.is_current,
                time=_time(a.time),
            )
            for a in wire.additional_attributes
        ],
        measurement=(
            IrMeasurement(
                subject=_mention(wire.measurement.subject),
                context=(
                    _mention(wire.measurement.context) if wire.measurement.context else None
                ),
                dimension_key=wire.measurement.dimension_key,
                numeric_value=wire.measurement.numeric_value,
                unit=wire.measurement.unit,
                currency_code=wire.measurement.currency_code,
                time=_time(wire.measurement.time),
            )
            if wire.measurement
            else None
        ),
        additional_measurements=[
            IrMeasurement(
                subject=_mention(m.subject),
                context=_mention(m.context) if m.context else None,
                dimension_key=m.dimension_key,
                numeric_value=m.numeric_value,
                unit=m.unit,
                currency_code=m.currency_code,
                time=_time(m.time),
            )
            for m in wire.additional_measurements
        ],
        relation=(
            IrRelation(
                type=_cref(wire.relation.type),
                subject=_mention(wire.relation.subject),
                object=_mention(wire.relation.object),
                mode=RelationAssertionMode(wire.relation.mode),
                time=_time(wire.relation.time),
            )
            if wire.relation
            else None
        ),
        additional_relations=[
            IrRelation(
                type=_cref(r.type),
                subject=_mention(r.subject),
                object=_mention(r.object),
                mode=RelationAssertionMode(r.mode),
                time=_time(r.time),
            )
            for r in wire.additional_relations
        ],
        event=(
            IrEvent(
                type=_cref(wire.event.type),
                action=_cref(wire.event.action) if wire.event.action else None,
                status=EventStatus(wire.event.status),
                time=_time(wire.event.time),
                participants=[_mention(m) for m in wire.event.participants],
                facts=[_fact(f) for f in wire.event.facts],
            )
            if wire.event
            else None
        ),
        obligation=(
            IrObligation(
                type=_cref(wire.obligation.type),
                cadence=Recurrence.model_validate(wire.obligation.cadence),
                due=_time(wire.obligation.due) if wire.obligation.due else None,
                facts=[_fact(f) for f in wire.obligation.facts],
            )
            if wire.obligation
            else None
        ),
        correction=(
            IrCorrection(
                strategy=wire.correction.strategy,  # type: ignore[arg-type]
                event_id=wire.correction.event_id,
                fact_id=wire.correction.fact_id,
                facts=[_fact(f) for f in wire.correction.facts],
                operation=wire.correction.operation,
                target=(
                    IrCorrectionTarget(
                        kind=wire.correction.target.kind,
                        entity_text=wire.correction.target.entity_text,
                        object_text=wire.correction.target.object_text,
                        dimension_key=wire.correction.target.dimension_key,
                        value_text=wire.correction.target.value_text,
                        numeric_value=wire.correction.target.numeric_value,
                        year=wire.correction.target.year,
                        relation_concept_key=wire.correction.target.relation_concept_key,
                        state_value_key=wire.correction.target.state_value_key,
                        action_key=wire.correction.target.action_key,
                        explicit_assertion_id=wire.correction.target.explicit_assertion_id,
                        conversation_assertion_id=wire.correction.target.conversation_assertion_id,
                    )
                    if wire.correction.target is not None
                    else None
                ),
            )
            if wire.correction
            else None
        ),
        missing_hints=[_cref(k) for k in wire.missing_hints],
        claim_report=(
            ClaimReport.model_validate(wire.claim_report) if wire.claim_report else None
        ),
    )


def _map_query(wire: WireQueryIR) -> QueryIR:
    q = wire.query
    return QueryIR(
        raw_input=wire.raw_input,
        query=QuerySpec(
            intent=q.intent,
            entities=[_mention(m) for m in q.entities],
            entity_association=q.entity_association,
            event_types=[_cref(k) for k in q.event_types],
            state_dimensions=[_cref(k) for k in q.state_dimensions],
            state_values=[_cref(k) for k in q.state_values],
            relation_types=[_cref(k) for k in q.relation_types],
            relation_scope=q.relation_scope,
            relation_query_kind=q.relation_query_kind,
            actions=[_cref(k) for k in q.actions],
            facts=[_cref(k) for k in q.facts],
            domains=[_cref(k) for k in q.domains],
            aggregate=q.aggregate,
            hierarchy=q.hierarchy,
            version_policy=q.version_policy,
            currency=q.currency,
            time=(
                IrQueryTime(
                    original_text=q.time.original_text,
                    relative_period=RelativePeriod(q.time.relative_period)
                    if q.time.relative_period
                    else None,
                )
                if q.time
                else None
            ),
            sort=q.sort,
            limit=q.limit,
        ),
        discourse_decision=wire.discourse_decision,
    )
