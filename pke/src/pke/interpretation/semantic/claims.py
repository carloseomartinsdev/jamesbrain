"""Map Interpreter atomic claims onto existing WireIngestIR slots.

Does not re-read raw_input. Does not invent domain rules. ASSUMED is dropped;
DERIVED is counted as deferred until ontology hierarchy (future increment).
"""

from __future__ import annotations

from collections.abc import Callable

from pke.interpretation.models import ClaimExecution, ClaimReport
from pke.interpretation.semantic.learned_attribute import (
    claim_attribute_value,
    resolve_claim_dimension,
)
from pke.interpretation.semantic.attribute_registry import (
    get_dimension,
)
from pke.interpretation.semantic.learned_relation import (
    learned_key_from_expression,
    publish_relation_type,
)
from pke.interpretation.semantic.owned_object import (
    actor_mention,
    identity_mentions,
    possessive_mentions,
)
from pke.interpretation.semantic.models import (
    PrimitiveKind,
    ResolutionResult,
    SemanticClaim,
    SemanticClaimKind,
    SemanticClaimOrigin,
    SemanticEntityMention,
    SemanticProposal,
)
from pke.interpretation.transport.wire import (
    WireEntityMention,
    WireIngestIR,
    WireIrAttribute,
    WireIrMeasurement,
    WireIrRelation,
    WireIrTime,
)

INTRINSIC_NAME_KEYS = frozenset({"name"})
WireMentionFn = Callable[[SemanticEntityMention], WireEntityMention]


def relation_key_from_predicate(predicate: str) -> str | None:
    """Canonical or learned relation key from an already-interpreted predicate."""
    text = (predicate or "").strip()
    if not text:
        return None
    if text.startswith("relation."):
        publish_relation_type(text)
        return text
    from pke.interpretation.semantic.aliases import SEMANTIC_ALIASES, normalize_expression
    from pke.interpretation.transport.catalog import ConceptCatalog

    folded = normalize_expression(text)
    if folded in ConceptCatalog.relation_types:
        return folded
    dotted = f"relation.{folded.replace(' ', '_')}"
    if dotted in ConceptCatalog.relation_types:
        return dotted
    for alias in SEMANTIC_ALIASES:
        if alias.primitive is not PrimitiveKind.RELATION or not alias.canonical_key:
            continue
        exprs = {normalize_expression(e) for e in alias.expressions}
        if folded in exprs:
            return alias.canonical_key
        if folded == normalize_expression(alias.canonical_key):
            return alias.canonical_key
        suffix = alias.canonical_key.split(".", 1)[-1]
        if folded == suffix or folded.replace(" ", "_") == suffix:
            return alias.canonical_key
    key = learned_key_from_expression(text)
    if key is None:
        return None
    publish_relation_type(key)
    return key


def overlay_semantic_claims(
    result: ResolutionResult,
    wire: WireIngestIR | None,
    *,
    wire_mention: WireMentionFn,
    wire_time: WireIrTime,
    measurement_from_proposal: Callable[[SemanticProposal, WireIrTime], WireIrMeasurement | None],
) -> WireIngestIR | None:
    """Attach explicit companion claims without replacing the primary primitive."""
    proposal = result.proposal
    if wire is None:
        if proposal.claims:
            wire = _empty_entity_wire(proposal, wire_mention)
        else:
            return None

    report = ClaimReport(received=len(proposal.claims))
    entities = list(wire.entities_mentioned)
    extra_attrs = list(wire.additional_attributes)
    extra_rels = list(wire.additional_relations)
    extra_meas = list(wire.additional_measurements)
    attribute = wire.attribute
    relation = wire.relation
    measurement = wire.measurement

    def add_entity(mention: SemanticEntityMention | None) -> WireEntityMention | None:
        if mention is None:
            return None
        wm = wire_mention(mention)
        for i, existing in enumerate(entities):
            if existing.text != wm.text:
                continue
            merged = _merge_mentions(existing, wm)
            entities[i] = merged
            return merged
        entities.append(wm)
        return wm

    persistable = identity_mentions(proposal)
    persistable_texts = {mention.text for mention in persistable}
    if proposal.claims:
        entities = [
            item
            for item in entities
            if item.text in persistable_texts or _wire_is_actor(item)
        ]

    for mention in persistable:
        add_entity(mention)

    if proposal.claims:
        if relation is not None and not _wire_identity_ok(relation.object, persistable_texts):
            relation = None
        extra_rels = [
            item for item in extra_rels if _wire_identity_ok(item.object, persistable_texts)
        ]
        if attribute is not None and not _wire_identity_ok(attribute.subject, persistable_texts):
            attribute = None

    if measurement is None:
        measurement = measurement_from_proposal(proposal, wire_time)
        if measurement is not None:
            add_entity(measurement.subject if hasattr(measurement, "subject") else None)
            add_entity(getattr(measurement, "context", None))

    for index, claim in enumerate(proposal.claims, start=1):
        attribute, extra_attrs, relation, extra_rels, measurement, extra_meas = _apply_claim(
            claim,
            claim_id=f"c{index}",
            proposal=proposal,
            time=wire_time,
            add_entity=add_entity,
            report=report,
            attribute=attribute,
            extra_attrs=extra_attrs,
            relation=relation,
            extra_rels=extra_rels,
            measurement=measurement,
            extra_meas=extra_meas,
        )

    relation, extra_rels = _ensure_possessive_owns(
        proposal,
        time=wire_time,
        add_entity=add_entity,
        relation=relation,
        extra_rels=extra_rels,
        report=report,
    )

    intent = _intent_for(
        event=wire.event,
        state=wire.state,
        relation=relation,
        attribute=attribute,
        measurement=measurement,
        fallback=wire.intent,
    )
    payload = report.model_dump(mode="json")
    return wire.model_copy(
        update={
            "intent": intent,
            "entities_mentioned": entities,
            "attribute": attribute,
            "additional_attributes": extra_attrs,
            "relation": relation,
            "additional_relations": extra_rels,
            "measurement": measurement,
            "additional_measurements": extra_meas,
            "claim_report": payload,
        }
    )


def _empty_entity_wire(
    proposal: SemanticProposal, wire_mention: WireMentionFn
) -> WireIngestIR:
    entities: list[WireEntityMention] = []
    seen: set[str] = set()
    for mention in identity_mentions(proposal):
        if mention.text in seen:
            continue
        seen.add(mention.text)
        entities.append(wire_mention(mention))
    return WireIngestIR(
        intent="none",
        raw_input=proposal.raw_input,
        entities_mentioned=entities,
    )


def _merge_mentions(base: WireEntityMention, incoming: WireEntityMention) -> WireEntityMention:
    known = incoming.known_entity_id or base.known_entity_id
    if incoming.entity_type and incoming.entity_type != base.entity_type:
        chosen = incoming if base.entity_type is None else base.model_copy(
            update={"entity_type": incoming.entity_type}
        )
    else:
        chosen = base
    if known and chosen.known_entity_id != known:
        return chosen.model_copy(update={"known_entity_id": known})
    return chosen


def _intent_for(
    *,
    event: object,
    state: object,
    relation: object,
    attribute: object,
    measurement: object,
    fallback: str,
) -> str:
    if event is not None:
        return "record_event"
    if relation is not None:
        return "record_relation"
    if attribute is not None:
        return "record_attribute"
    if measurement is not None:
        return "record_measurement"
    if state is not None:
        return "record_state"
    if fallback in {"correct", "record_obligation", "record_intent"}:
        return fallback
    return "none"


def _apply_claim(
    claim: SemanticClaim,
    *,
    claim_id: str,
    proposal: SemanticProposal,
    time: WireIrTime,
    add_entity: Callable[[SemanticEntityMention | None], WireEntityMention | None],
    report: ClaimReport,
    attribute: WireIrAttribute | None,
    extra_attrs: list[WireIrAttribute],
    relation: WireIrRelation | None,
    extra_rels: list[WireIrRelation],
    measurement: WireIrMeasurement | None,
    extra_meas: list[WireIrMeasurement],
) -> tuple[
    WireIrAttribute | None,
    list[WireIrAttribute],
    WireIrRelation | None,
    list[WireIrRelation],
    WireIrMeasurement | None,
    list[WireIrMeasurement],
]:
    if claim.origin is SemanticClaimOrigin.ASSUMED:
        report.assumed_dropped += 1
        report.notes.append("assumed_dropped")
        report.executions.append(
            ClaimExecution(
                claim_id=claim_id,
                kind=claim.kind.value,
                status="rejected",
                predicate=claim.predicate,
                reason="assumed_dropped",
            )
        )
        return attribute, extra_attrs, relation, extra_rels, measurement, extra_meas
    if claim.origin is SemanticClaimOrigin.DERIVED:
        report.derived_deferred += 1
        report.notes.append("derived_deferred")
        report.executions.append(
            ClaimExecution(
                claim_id=claim_id,
                kind=claim.kind.value,
                status="deferred",
                predicate=claim.predicate,
                reason="derived_not_materialized",
            )
        )
        return attribute, extra_attrs, relation, extra_rels, measurement, extra_meas

    if claim.kind is SemanticClaimKind.ENTITY:
        add_entity(claim.subject or claim.object)
        report.executions.append(
            ClaimExecution(claim_id=claim_id, kind=claim.kind.value, status="bound")
        )
        return attribute, extra_attrs, relation, extra_rels, measurement, extra_meas

    if claim.kind is SemanticClaimKind.CLASSIFICATION:
        target = claim.subject or claim.object
        if target is not None and claim.class_hint:
            hinted = target.model_copy(update={"class_hint": claim.class_hint})
            add_entity(hinted)
        elif target is not None:
            add_entity(target)
        report.executions.append(
            ClaimExecution(claim_id=claim_id, kind=claim.kind.value, status="bound")
        )
        return attribute, extra_attrs, relation, extra_rels, measurement, extra_meas

    if claim.kind is SemanticClaimKind.INTRINSIC_PROPERTY:
        dim = (claim.dimension or claim.predicate or "name").strip().lower()
        if dim in INTRINSIC_NAME_KEYS:
            add_entity(claim.subject or _owned_subject(proposal) or proposal.subject)
            report.notes.append("intrinsic_name_via_entity")
            report.executions.append(
                ClaimExecution(
                    claim_id=claim_id,
                    kind=claim.kind.value,
                    status="bound",
                    canonical_dimension="name",
                    dimension_source="core",
                )
            )
            return attribute, extra_attrs, relation, extra_rels, measurement, extra_meas
        report.unsupported += 1
        report.notes.append(f"unsupported_intrinsic:{dim}")
        report.executions.append(
            ClaimExecution(
                claim_id=claim_id,
                kind=claim.kind.value,
                status="unsupported",
                predicate=claim.predicate,
                reason="unsupported_intrinsic",
            )
        )
        return attribute, extra_attrs, relation, extra_rels, measurement, extra_meas

    if claim.kind is SemanticClaimKind.ATTRIBUTE:
        built = _attribute_from_claim(claim, proposal, time, add_entity)
        if built is None:
            report.unsupported += 1
            report.notes.append("unsupported_attribute_dimension")
            report.executions.append(
                ClaimExecution(
                    claim_id=claim_id,
                    kind=claim.kind.value,
                    status="unsupported",
                    predicate=claim.predicate,
                    reason="unsupported_attribute_dimension",
                )
            )
            return attribute, extra_attrs, relation, extra_rels, measurement, extra_meas
        identity = resolve_claim_dimension(claim, learn=False)
        if built.dimension_key in INTRINSIC_NAME_KEYS:
            report.notes.append("intrinsic_name_via_entity")
            report.executions.append(
                ClaimExecution(
                    claim_id=claim_id,
                    kind=claim.kind.value,
                    status="bound",
                    canonical_dimension="name",
                    dimension_source="core",
                )
            )
            return attribute, extra_attrs, relation, extra_rels, measurement, extra_meas
        text, numeric, _unit = claim_attribute_value(claim)
        report.executions.append(
            ClaimExecution(
                claim_id=claim_id,
                kind=claim.kind.value,
                status="overlayed",
                predicate=claim.predicate,
                canonical_dimension=built.dimension_key,
                dimension_source=identity.source if identity is not None else None,
                value=text or numeric,
                materialized_as="attribute",
            )
        )
        if attribute is None:
            attribute = built
        elif not _attr_dup(built, attribute, extra_attrs):
            extra_attrs.append(built)
        return attribute, extra_attrs, relation, extra_rels, measurement, extra_meas

    if claim.kind is SemanticClaimKind.RELATION:
        built_rel = _relation_from_claim(claim, proposal, time, add_entity)
        if built_rel is None:
            report.unsupported += 1
            report.notes.append("unsupported_relation_predicate")
            report.executions.append(
                ClaimExecution(
                    claim_id=claim_id,
                    kind=claim.kind.value,
                    status="unsupported",
                    predicate=claim.predicate,
                    reason="unsupported_relation_predicate",
                )
            )
            return attribute, extra_attrs, relation, extra_rels, measurement, extra_meas
        report.executions.append(
            ClaimExecution(
                claim_id=claim_id,
                kind=claim.kind.value,
                status="overlayed",
                predicate=claim.predicate,
                canonical_dimension=built_rel.type,
                materialized_as="relation",
            )
        )
        if relation is None:
            relation = built_rel
        elif not _rel_dup(built_rel, relation, extra_rels):
            extra_rels.append(built_rel)
        return attribute, extra_attrs, relation, extra_rels, measurement, extra_meas

    if claim.kind is SemanticClaimKind.MEASUREMENT:
        built_m = _measurement_from_claim(claim, proposal, time, add_entity)
        if built_m is None:
            report.unsupported += 1
            report.notes.append("unsupported_measurement")
            report.executions.append(
                ClaimExecution(
                    claim_id=claim_id,
                    kind=claim.kind.value,
                    status="unsupported",
                    predicate=claim.predicate,
                    reason="unsupported_measurement",
                )
            )
            return attribute, extra_attrs, relation, extra_rels, measurement, extra_meas
        report.executions.append(
            ClaimExecution(
                claim_id=claim_id,
                kind=claim.kind.value,
                status="overlayed",
                predicate=claim.predicate,
                canonical_dimension=built_m.dimension_key,
                materialized_as="measurement",
                value=built_m.numeric_value,
            )
        )
        if measurement is None:
            measurement = built_m
        elif not _meas_dup(built_m, measurement, extra_meas):
            extra_meas.append(built_m)
        return attribute, extra_attrs, relation, extra_rels, measurement, extra_meas

    # STATE / EVENT companions stay on the primary primitive path this increment.
    report.notes.append(f"claim_kind_deferred:{claim.kind.value}")
    report.executions.append(
        ClaimExecution(
            claim_id=claim_id,
            kind=claim.kind.value,
            status="deferred",
            predicate=claim.predicate,
            reason=f"claim_kind_deferred:{claim.kind.value}",
        )
    )
    return attribute, extra_attrs, relation, extra_rels, measurement, extra_meas


def _attribute_from_claim(
    claim: SemanticClaim,
    proposal: SemanticProposal,
    time: WireIrTime,
    add_entity: Callable[[SemanticEntityMention | None], WireEntityMention | None],
) -> WireIrAttribute | None:
    identity = resolve_claim_dimension(claim, learn=True)
    if identity is None:
        return None
    key = identity.key
    spec = get_dimension(key)
    subject = add_entity(claim.subject or _owned_subject(proposal) or proposal.subject)
    if subject is None:
        return None
    text, numeric, unit = claim_attribute_value(claim)
    if text is None and numeric is None:
        return None
    value_kind = spec.value_kind if spec is not None else "text"
    if numeric and value_kind == "text":
        value_kind = "number"
    if spec is not None and spec.value_kind == "year" and numeric:
        try:
            year_value = int(float(numeric))
        except ValueError:
            year_value = None
        return WireIrAttribute(
            subject=subject,
            dimension_key=key,
            value_kind="year",
            year_value=year_value,
            time=time,
        )
    return WireIrAttribute(
        subject=subject,
        dimension_key=key,
        value_kind=value_kind,  # type: ignore[arg-type]
        text_value=text,
        numeric_value=numeric,
        unit=unit,
        time=time,
    )


def _relation_from_claim(
    claim: SemanticClaim,
    proposal: SemanticProposal,
    time: WireIrTime,
    add_entity: Callable[[SemanticEntityMention | None], WireEntityMention | None],
) -> WireIrRelation | None:
    from pke.interpretation.semantic.identity_naming import is_identity_naming_predicate

    if is_identity_naming_predicate(claim.predicate):
        return None
    key = relation_key_from_predicate(claim.predicate or "")
    if key is None:
        return None
    subject = add_entity(claim.subject or proposal.subject)
    obj = add_entity(claim.object or _owned_subject(proposal) or proposal.object)
    if subject is None or obj is None:
        return None
    return WireIrRelation(
        type=key,
        subject=subject,
        object=obj,
        mode="assert",
        time=time,
    )


def _measurement_from_claim(
    claim: SemanticClaim,
    proposal: SemanticProposal,
    time: WireIrTime,
    add_entity: Callable[[SemanticEntityMention | None], WireEntityMention | None],
) -> WireIrMeasurement | None:
    dim = (claim.dimension or claim.predicate or "").strip()
    numeric = (claim.numeric_value or "").strip()
    if not dim or not numeric:
        return None
    subject = add_entity(claim.subject or _owned_subject(proposal) or proposal.subject)
    if subject is None:
        return None
    return WireIrMeasurement(
        subject=subject,
        dimension_key=dim,
        numeric_value=numeric,
        unit=claim.unit,
        currency_code=claim.currency_code,
        time=time,
    )


def _attr_dup(
    item: WireIrAttribute, primary: WireIrAttribute, extras: list[WireIrAttribute]
) -> bool:
    keys = {(primary.subject.text, primary.dimension_key)}
    keys.update((a.subject.text, a.dimension_key) for a in extras)
    return (item.subject.text, item.dimension_key) in keys


def _rel_dup(
    item: WireIrRelation, primary: WireIrRelation, extras: list[WireIrRelation]
) -> bool:
    keys = {(primary.type, primary.subject.text, primary.object.text)}
    keys.update((r.type, r.subject.text, r.object.text) for r in extras)
    return (item.type, item.subject.text, item.object.text) in keys


def _meas_dup(
    item: WireIrMeasurement, primary: WireIrMeasurement, extras: list[WireIrMeasurement]
) -> bool:
    keys = {(primary.subject.text, primary.dimension_key)}
    keys.update((m.subject.text, m.dimension_key) for m in extras)
    return (item.subject.text, item.dimension_key) in keys


def _owned_subject(proposal: SemanticProposal) -> SemanticEntityMention | None:
    owned = possessive_mentions(proposal)
    if owned:
        return owned[0]
    return None


def _wire_is_actor(item: WireEntityMention) -> bool:
    from pke.resolution.self_ref import is_self_lexeme

    return is_self_lexeme(item.text)


def _wire_identity_ok(item: WireEntityMention, persistable_texts: set[str]) -> bool:
    return item.text in persistable_texts or _wire_is_actor(item)


def _ensure_possessive_owns(
    proposal: SemanticProposal,
    *,
    time: WireIrTime,
    add_entity: Callable[[SemanticEntityMention | None], WireEntityMention | None],
    relation: WireIrRelation | None,
    extra_rels: list[WireIrRelation],
    report: ClaimReport,
) -> tuple[WireIrRelation | None, list[WireIrRelation]]:
    """reference_kind=possessive → relation.owns(actor, X). Not from raw_input."""
    owned = possessive_mentions(proposal)
    if not owned:
        return relation, extra_rels
    actor = add_entity(actor_mention())
    if actor is None:
        return relation, extra_rels
    publish_relation_type("relation.owns")
    for mention in owned:
        obj = add_entity(mention)
        if obj is None:
            continue
        built = WireIrRelation(
            type="relation.owns",
            subject=actor,
            object=obj,
            mode="assert",
            time=time,
        )
        if relation is None:
            relation = built
            report.notes.append("possessive_owns_synthesized")
            continue
        if _rel_dup(built, relation, extra_rels):
            continue
        extra_rels.append(built)
        report.notes.append("possessive_owns_synthesized")
    return relation, extra_rels

