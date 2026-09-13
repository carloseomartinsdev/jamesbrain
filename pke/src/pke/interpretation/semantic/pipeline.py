"""Pipeline proposal → canonical IR."""

from __future__ import annotations

from pke.interpretation.acceptance.correction_guard import (
    AcceptanceOutcome,
    evaluate_correction_acceptance,
    proposal_flags_indicate_correction,
)
from pke.interpretation.models import IngestIR, QueryIR
from pke.interpretation.semantic.models import (
    PrimitiveKind,
    ResolutionResult,
    SemanticEntityMention,
    SemanticProposal,
    SemanticResolutionOutcome,
    SemanticTime,
)
from pke.interpretation.semantic.event_roles import (
    resolve_event_roles,
    wire_role_for_mention,
)
from pke.interpretation.semantic.execution_readiness import (
    ProposalExecutionOutcome,
    assess_execution_readiness,
)
from pke.interpretation.semantic.persistability import assess_persistability, event_type_for_wire
from pke.interpretation.semantic.resolver import resolve_concepts
from pke.interpretation.semantic.router import collect_assertions, route_primitive
from pke.interpretation.semantic.self_repair import apply_e1_self_repairs
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.interpretation.transport.mapper import wire_to_canonical
from pke.interpretation.semantic.query_resolution import proposal_to_query_ir
from pke.interpretation.transport.proposal_wire import WireSemanticEnvelope
from pke.interpretation.transport.wire import (
    WireEnvelope,
    WireEntityMention,
    WireIngestIR,
    WireIrAttribute,
    WireIrCorrection,
    WireIrCorrectionTarget,
    WireIrEvent,
    WireIrMeasurement,
    WireIrRelation,
    WireIrState,
    WireIrTime,
)


def resolve_proposal(proposal: SemanticProposal) -> ResolutionResult:
    primitive, routing_notes = route_primitive(proposal)
    concepts = resolve_concepts(proposal, primitive)
    assertions = collect_assertions(proposal)
    from pke.interpretation.semantic.measurement_resolution import resolve_measurement_value

    non_materialized: list[PrimitiveKind] = []
    non_materialized_reasons: list[str] = []
    for frame in assertions:
        if frame.primitive is PrimitiveKind.MEASUREMENT:
            measured = resolve_measurement_value(proposal)
            subject = proposal.subject or proposal.object
            if measured is None:
                non_materialized.append(PrimitiveKind.MEASUREMENT)
                non_materialized_reasons.append("measurement_dimension_value_required")
            elif subject is None:
                # Semantically valid observation — not materializable without entity
                non_materialized.append(PrimitiveKind.MEASUREMENT)
                non_materialized_reasons.append("measurement_entity_required")
        elif frame.primitive is PrimitiveKind.TYPE:
            non_materialized.append(PrimitiveKind.TYPE)
            non_materialized_reasons.append("classification_not_materializable")
        elif frame.primitive is PrimitiveKind.EVENT:
            from pke.interpretation.semantic.persistability import (
                assess_persistability,
                event_type_for_wire,
            )

            evt_assessment = assess_persistability(
                ResolutionResult(
                    proposal=proposal,
                    primitive=PrimitiveKind.EVENT,
                    concepts=concepts,
                    assertions=assertions,
                )
            )
            wire_type = event_type_for_wire(concepts, proposal)
            if wire_type is None or not evt_assessment.wire_allowed:
                if "event_category_unresolved_safe_partial" in evt_assessment.notes:
                    non_materialized.append(PrimitiveKind.EVENT)
                    non_materialized_reasons.append("event_category_unresolved_safe_partial")
                elif not evt_assessment.wire_allowed:
                    non_materialized.append(PrimitiveKind.EVENT)
                    non_materialized_reasons.append(
                        evt_assessment.notes[0] if evt_assessment.notes else "event_not_materialization_ready"
                    )
    return ResolutionResult(
        proposal=proposal,
        primitive=primitive,
        concepts=concepts,
        primitive_routing_notes=routing_notes,
        assertions=assertions,
        non_materialized_primitives=non_materialized,
        non_materialized_reasons=non_materialized_reasons,
    )


def _wire_time(temporal: SemanticTime) -> WireIrTime:
    return WireIrTime(
        original_text=temporal.original_text,
        relative_day=temporal.relative_day,
        relation_to_reference=temporal.relation_to_reference,
        occurrence_status=temporal.occurrence_aspect,
        unknown_reason=temporal.unknown_reason,
        tense_evidence=temporal.tense_evidence,
        partial_month=temporal.partial_month,
        partial_year=temporal.partial_year,
    )


def _wire_mention(mention: SemanticEntityMention, *, role_override: str | None = None) -> WireEntityMention:
    from pke.interpretation.semantic.entity_kinds import resolve_entity_type, resolve_role

    role = role_override or resolve_role(mention)
    return WireEntityMention(
        text=mention.text,
        entity_type=resolve_entity_type(mention),
        role=role,
        reference_kind=mention.reference_kind,
        confidence=mention.confidence,
        known_entity_id=mention.known_entity_id,
    )


def _wire_attribute_from_concepts(
    subject: WireEntityMention,
    concepts,
    time: WireIrTime,
) -> tuple[WireIrAttribute, list[WireIrAttribute]]:
    primary = WireIrAttribute(
        subject=subject,
        dimension_key=concepts.attribute_dimension_key,
        value_kind=concepts.attribute_value_kind or "text",  # type: ignore[arg-type]
        text_value=concepts.attribute_text_value,
        numeric_value=concepts.attribute_numeric_value,
        unit=concepts.attribute_unit,
        year_value=concepts.attribute_year_value,
        is_current=True if concepts.attribute_is_current is None else concepts.attribute_is_current,
        time=time,
    )
    companions: list[WireIrAttribute] = []
    for slot in concepts.attribute_companions or []:
        companions.append(
            WireIrAttribute(
                subject=subject,
                dimension_key=slot.dimension_key,
                value_kind=slot.value_kind,  # type: ignore[arg-type]
                text_value=slot.text_value,
                numeric_value=slot.numeric_value,
                unit=slot.unit,
                year_value=slot.year_value,
                is_current=slot.is_current,
                time=time,
            )
        )
    return primary, companions


def _build_event_wire_mentions(
    proposal: SemanticProposal,
) -> tuple[list[WireEntityMention], list[WireEntityMention]]:
    roles = resolve_event_roles(proposal)
    participants: list[WireEntityMention] = []
    seen: set[str] = set()

    def add(mention: SemanticEntityMention | None, role_key: str) -> None:
        if mention is None or mention.text in seen:
            return
        seen.add(mention.text)
        participants.append(_wire_mention(mention, role_override=role_key))

    add(roles.actor, "role.actor")
    if roles.object is not None:
        add(roles.object, "role.object")
    elif roles.affected is not None:
        add(roles.affected, "role.patient")
    for ctx in roles.context:
        add(ctx, "role.context")
    for mention in proposal.participants:
        if mention.text in seen:
            continue
        role = wire_role_for_mention(mention, roles)
        add(mention, role or "role.subject")

    return participants, list(participants)


def _measurement_wire(
    proposal: SemanticProposal, time: WireIrTime
) -> WireIrMeasurement | None:
    """Build Measurement wire when dimension/value/entity cues are complete."""
    from pke.interpretation.semantic.measurement_resolution import resolve_measurement_value

    measured = resolve_measurement_value(proposal)
    subject = proposal.subject or proposal.object
    if measured is None or subject is None:
        return None
    ctx = proposal.context
    return WireIrMeasurement(
        subject=_wire_mention(subject),
        context=_wire_mention(ctx) if ctx is not None else None,
        dimension_key=measured.dimension_key,
        numeric_value=format(measured.numeric_value, "f"),
        unit=measured.unit,
        currency_code=measured.currency_code,
        time=time,
    )


def _is_correction_proposal(proposal: SemanticProposal) -> bool:
    return (
        proposal.utterance_kind == "correct"
        or proposal.correction_semantics
        or proposal.correction_operation is not None
    )


def _correction_wire(result: ResolutionResult) -> WireIngestIR | None:
    """Build intent=correct wire: target semantics + optional replacement sibling fields.

    Does not invent LAST_EVENT targets. Replacement uses ordinary primitive fields.
    """
    proposal = result.proposal
    op = proposal.correction_operation
    if op is None:
        # Explicit correction utterance without operation → still correction IR (unresolved later)
        op = "replace" if (
            proposal.attribute_expression
            or proposal.measurement_expression
            or proposal.state_expression
            or proposal.event_expression
            or proposal.relation_expression
            or proposal.measurement_semantics
            or proposal.stable_property_semantics
            or proposal.condition_semantics
        ) else "retract"

    concepts = result.concepts
    time = _wire_time(proposal.temporal)
    domains = [d for d in (concepts.domains or proposal.domain_hints) if d in ConceptCatalog.domains]
    entities = [_wire_mention(m) for m in proposal.entities_mentioned]
    if proposal.subject is not None:
        sm = _wire_mention(proposal.subject)
        if sm.text not in {e.text for e in entities}:
            entities.append(sm)
    if proposal.object is not None:
        om = _wire_mention(proposal.object)
        if om.text not in {e.text for e in entities}:
            entities.append(om)

    target_kind = proposal.correction_target_kind or (
        result.primitive.value
        if result.primitive
        in {
            PrimitiveKind.EVENT,
            PrimitiveKind.MEASUREMENT,
            PrimitiveKind.RELATION,
            PrimitiveKind.STATE,
            PrimitiveKind.ATTRIBUTE,
        }
        else None
    )
    # Contextual pronouns are not entity identity for target matching.
    subject_entity_text = None
    if proposal.subject is not None and proposal.subject.reference_kind not in {
        "contextual",
        "possessive",
        "class",
    }:
        subject_entity_text = proposal.subject.text
    object_entity_text = None
    if proposal.object is not None and proposal.object.reference_kind not in {
        "contextual",
        "possessive",
        "class",
    }:
        object_entity_text = proposal.object.text
    target = WireIrCorrectionTarget(
        kind=target_kind,  # type: ignore[arg-type]
        entity_text=proposal.correction_target_entity_text or subject_entity_text,
        object_text=proposal.correction_target_object_text or object_entity_text,
        dimension_key=proposal.correction_target_dimension_key
        or concepts.attribute_dimension_key
        or proposal.measurable_dimension_key,
        value_text=proposal.correction_target_value_text,
        numeric_value=proposal.correction_target_numeric_value,
        year=proposal.correction_target_year,
        relation_concept_key=proposal.correction_target_relation_key or concepts.relation_type,
        state_value_key=proposal.correction_target_state_value_key or concepts.state_value,
        action_key=proposal.correction_target_action_key or concepts.action,
        explicit_assertion_id=proposal.correction_target_assertion_id,
        conversation_assertion_id=proposal.correction_conversation_assertion_id,
    )
    correction = WireIrCorrection(
        strategy="explicit",
        operation=op,  # type: ignore[arg-type]
        target=target,
        facts=[],
    )

    attribute = None
    additional_attributes: list[WireIrAttribute] = []
    measurement = None
    state = None
    event = None
    relation = None

    if op == "replace":
        # Exactly one replacement sibling — materializer early-returns on event/measurement.
        # Do not co-emit unrelated primitives from opportunistic concept cues.
        preferred = target_kind
        measurement_candidate = _measurement_wire(proposal, time)
        attribute_ok = (
            concepts.attribute_dimension_key is not None and proposal.subject is not None
        )
        state_ok = concepts.state_value is not None and proposal.subject is not None
        relation_ok = (
            concepts.relation_type is not None
            and proposal.subject is not None
            and proposal.object is not None
        )
        event_type = event_type_for_wire(concepts, proposal)
        event_ok = event_type is not None

        choose = preferred
        if choose is None:
            if measurement_candidate is not None:
                choose = "measurement"
            elif attribute_ok:
                choose = "attribute"
            elif state_ok:
                choose = "state"
            elif relation_ok:
                choose = "relation"
            elif event_ok:
                choose = "event"

        if choose == "measurement" and measurement_candidate is not None:
            measurement = measurement_candidate
        elif choose == "attribute" and attribute_ok:
            attribute, additional_attributes = _wire_attribute_from_concepts(
                _wire_mention(proposal.subject), concepts, time
            )
        elif choose == "state" and state_ok:
            state = WireIrState(
                value=concepts.state_value,
                dimension=concepts.state_dimension,
                time=time,
            )
        elif choose == "relation" and relation_ok:
            relation = WireIrRelation(
                type=concepts.relation_type,
                subject=_wire_mention(proposal.subject),
                object=_wire_mention(proposal.object),
                mode="assert",
                time=time,
            )
        elif choose == "event" and event_ok:
            participants, _ents = _build_event_wire_mentions(proposal)
            for e in _ents:
                if e.text not in {x.text for x in entities}:
                    entities.append(e)
            status = "completed"
            if proposal.temporal.occurrence_aspect == "planned":
                status = "scheduled"
            event = WireIrEvent(
                type=event_type,  # type: ignore[arg-type]
                action=concepts.action if concepts.action in ConceptCatalog.actions else None,
                status=status,  # type: ignore[arg-type]
                time=time,
                participants=participants,
                facts=[],
            )

    return WireIngestIR(
        intent="correct",
        raw_input=proposal.raw_input,
        domains=domains,
        entities_mentioned=entities,
        event=event,
        state=state,
        attribute=attribute,
        additional_attributes=additional_attributes,
        measurement=measurement,
        relation=relation,
        correction=correction,
    )


def resolution_to_wire_ingest(result: ResolutionResult) -> WireIngestIR | None:
    proposal = result.proposal
    if _is_correction_proposal(proposal):
        return _correction_wire(result)
    wire = _primary_resolution_to_wire(result)
    from pke.interpretation.semantic.claims import overlay_semantic_claims

    return overlay_semantic_claims(
        result,
        wire,
        wire_mention=_wire_mention,
        wire_time=_wire_time(proposal.temporal),
        measurement_from_proposal=_measurement_wire,
    )


def _primary_resolution_to_wire(result: ResolutionResult) -> WireIngestIR | None:
    proposal = result.proposal
    concepts = result.concepts
    primitive = result.primitive
    time = _wire_time(proposal.temporal)
    domains = [d for d in (concepts.domains or proposal.domain_hints) if d in ConceptCatalog.domains]
    measurement = _measurement_wire(proposal, time)

    if primitive is PrimitiveKind.MEASUREMENT:
        if measurement is None:
            return None
        entities = [_wire_mention(m) for m in proposal.entities_mentioned]
        sm = measurement.subject
        if sm.text not in {e.text for e in entities}:
            entities.append(sm)
        if measurement.context is not None and measurement.context.text not in {
            e.text for e in entities
        }:
            entities.append(measurement.context)
        return WireIngestIR(
            intent="record_measurement",
            raw_input=proposal.raw_input,
            domains=domains,
            entities_mentioned=entities,
            measurement=measurement,
        )

    assessment = assess_persistability(result)
    # Event primary with optional Measurement: allow Measurement-only if Event not wireable
    if primitive is PrimitiveKind.EVENT:
        event_type = event_type_for_wire(concepts, proposal)
        event_ok = assessment.wire_allowed and event_type is not None
        if not event_ok and measurement is None:
            return None
        status = "completed"
        if proposal.temporal.occurrence_aspect == "planned":
            status = "scheduled"
        participants: list[WireEntityMention] = []
        entities: list[WireEntityMention] = []
        event_block = None
        if event_ok:
            participants, entities = _build_event_wire_mentions(proposal)
            action = concepts.action if concepts.action in ConceptCatalog.actions else None
            event_block = WireIrEvent(
                type=event_type,  # type: ignore[arg-type]
                action=action,
                status=status,  # type: ignore[arg-type]
                time=time,
                participants=participants,
                facts=[],
            )
        if measurement is not None:
            for m in (measurement.subject, measurement.context):
                if m is not None and m.text not in {e.text for e in entities}:
                    entities.append(m)
        intent = "record_event" if event_block is not None else "record_measurement"
        return WireIngestIR(
            intent=intent,  # type: ignore[arg-type]
            raw_input=proposal.raw_input,
            domains=domains,
            entities_mentioned=entities or participants,
            event=event_block,
            measurement=measurement,
        )

    if not assessment.wire_allowed:
        return None

    if primitive is PrimitiveKind.STATE and concepts.state_value:
        entities = [_wire_mention(m) for m in proposal.entities_mentioned]
        if proposal.subject:
            sm = _wire_mention(proposal.subject)
            if sm.text not in {e.text for e in entities}:
                entities.append(sm)
        return WireIngestIR(
            intent="record_state",
            raw_input=proposal.raw_input,
            domains=domains,
            entities_mentioned=entities,
            state=WireIrState(
                value=concepts.state_value,
                dimension=concepts.state_dimension,
                time=time,
            ),
        )

    if (
        primitive is PrimitiveKind.RELATION
        and concepts.relation_type
        and proposal.subject
        and proposal.object
    ):
        entities = [_wire_mention(m) for m in proposal.entities_mentioned]
        if proposal.subject:
            sm = _wire_mention(proposal.subject)
            if sm.text not in {e.text for e in entities}:
                entities.append(sm)
        if proposal.object:
            om = _wire_mention(proposal.object)
            if om.text not in {e.text for e in entities}:
                entities.append(om)
        mode = "assert"
        if proposal.lifecycle_cue == "end":
            mode = "terminate"
        elif proposal.lifecycle_cue == "deny":
            mode = "deny_current"
        return WireIngestIR(
            intent="record_relation",
            raw_input=proposal.raw_input,
            domains=domains,
            entities_mentioned=entities,
            relation=WireIrRelation(
                type=concepts.relation_type,
                subject=_wire_mention(proposal.subject),
                object=_wire_mention(proposal.object),
                mode=mode,  # type: ignore[arg-type]
                time=time,
            ),
        )

    if primitive is PrimitiveKind.ATTRIBUTE and concepts.attribute_dimension_key:
        if proposal.subject is None:
            return None
        entities = [_wire_mention(m) for m in proposal.entities_mentioned]
        sm = _wire_mention(proposal.subject)
        if sm.text not in {e.text for e in entities}:
            entities.append(sm)
        attribute, companions = _wire_attribute_from_concepts(sm, concepts, time)
        return WireIngestIR(
            intent="record_attribute",
            raw_input=proposal.raw_input,
            domains=domains,
            entities_mentioned=entities,
            attribute=attribute,
            additional_attributes=companions,
        )

    return None


def proposal_to_canonical_ir(
    proposal: SemanticProposal,
    *,
    prior_utterances: list[str] | tuple[str, ...] = (),
) -> SemanticResolutionOutcome:
    proposal = apply_e1_self_repairs(proposal, prior_utterances=prior_utterances)
    result = resolve_proposal(proposal)
    if proposal_flags_indicate_correction(
        utterance_kind=proposal.utterance_kind,
        correction_semantics=proposal.correction_semantics,
        correction_operation=proposal.correction_operation,
    ):
        decision = evaluate_correction_acceptance(
            proposal.raw_input,
            proposed_as_correction=True,
            prior_utterances=prior_utterances,
        )
        if decision.outcome is not AcceptanceOutcome.ACCEPT:
            return SemanticResolutionOutcome(
                result=result,
                ir=None,
                wire_stage="unresolved",
                failure_stage=f"ACCEPTANCE_GUARD:{decision.reason_code.value}",
            )
    readiness = assess_execution_readiness(result)
    wire = resolution_to_wire_ingest(result)
    if wire is None:
        if readiness.outcome is ProposalExecutionOutcome.VALID_EXECUTION_INCOMPLETE:
            return SemanticResolutionOutcome(
                result=result,
                ir=None,
                wire_stage="unresolved",
                failure_stage="EXECUTION_INCOMPLETE",
                execution_outcome=readiness.outcome.value,
                execution_reasons=list(readiness.reasons),
                clarification_eligible=readiness.clarification_eligible,
                materializable_count=readiness.materializable_count,
            )
        return SemanticResolutionOutcome(
            result=result,
            ir=None,
            wire_stage="unresolved",
            failure_stage="CONCEPT_RESOLUTION",
            execution_outcome=readiness.outcome.value,
            execution_reasons=list(readiness.reasons),
            clarification_eligible=readiness.clarification_eligible,
            materializable_count=readiness.materializable_count,
        )
    try:
        envelope = WireEnvelope(ir_kind="ingest", ir=wire.model_dump())
        ir = wire_to_canonical(envelope)
        from pke.interpretation.models import IngestIR

        if isinstance(ir, IngestIR) and proposal.discourse_decision is not None:
            ir = ir.model_copy(update={"discourse_decision": proposal.discourse_decision})
        return SemanticResolutionOutcome(
            result=result,
            ir=ir,
            wire_stage="canonical",
            execution_outcome=readiness.outcome.value,
            execution_reasons=list(readiness.reasons),
            clarification_eligible=readiness.clarification_eligible,
            materializable_count=readiness.materializable_count,
        )
    except Exception:  # noqa: BLE001
        return SemanticResolutionOutcome(
            result=result,
            ir=None,
            wire_stage="proposal",
            failure_stage="CANONICAL_IR",
            execution_outcome=readiness.outcome.value,
            execution_reasons=list(readiness.reasons),
            clarification_eligible=readiness.clarification_eligible,
            materializable_count=readiness.materializable_count,
        )


def envelope_to_canonical_ir(
    envelope: WireSemanticEnvelope,
    *,
    prior_utterances: list[str] | tuple[str, ...] = (),
) -> SemanticResolutionOutcome:
    if envelope.ir_kind == "semantic_query":
        proposal = envelope.parsed_query_proposal()
        outcome = proposal_to_query_ir(proposal)
        result = resolve_proposal(proposal)
        if outcome.query_ir is None:
            stage = "ONTOLOGY_GAP" if outcome.status.value == "ontology_gap" else "CONCEPT_RESOLUTION"
            return SemanticResolutionOutcome(
                result=result,
                ir=None,
                wire_stage="unresolved",
                failure_stage=stage,
            )
        return SemanticResolutionOutcome(result=result, ir=outcome.query_ir, wire_stage="canonical")
    return proposal_to_canonical_ir(
        envelope.parsed_proposal(), prior_utterances=prior_utterances
    )
