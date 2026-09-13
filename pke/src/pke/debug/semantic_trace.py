"""Formatters for semantic execution-trace stages.

Uses data already in memory. Does not query storage, re-read raw_input, or
change resolver/materializer outcomes.
"""

from __future__ import annotations

from typing import Any

from pke.debug.trace_context import (
    current_trace,
    record_resolution_payload,
    take_resolution_payloads,
)
from pke.interpretation.models import EntityMention, MentionReferenceKind
from pke.interpretation.semantic.models import SemanticClaim, SemanticProposal
from pke.resolution.entities import EntityResolution, EvidenceKind, ResolutionStatus
from pke.resolution.self_ref import is_self_entity_mention

_NO_MATCH_REASONS = frozenset(
    {
        "possessive_no_match",
        "query_entity_not_found",
        "owned_vehicle_missing",
        "no_contextual_candidate",
        "principal_entity_missing",
    }
)


def append_trace_stage(stage: str, body: object = "", **meta: object) -> None:
    from pke.debug.request_log import append_stage, dump_model

    ids = current_trace()
    file_id = ids.file_id()
    if not file_id:
        return
    if not isinstance(body, str):
        body = dump_model(body)
    append_stage(
        file_id,
        stage,
        body,
        client_request_id=ids.client_request_id,
        pke_request_id=ids.pke_request_id,
        interpreter_request_id=ids.interpreter_request_id,
        conversation_id=ids.conversation_id,
        user_message_id=ids.user_message_id,
        **meta,
    )


def claims_trace_body(proposal: SemanticProposal) -> dict[str, Any] | None:
    if not proposal.claims:
        return None
    items = [compact_claim(claim, index) for index, claim in enumerate(proposal.claims, start=1)]
    return {"claims": items}


def compact_claim(claim: SemanticClaim, index: int) -> dict[str, Any]:
    item: dict[str, Any] = {
        "claim_id": f"c{index}",
        "kind": claim.kind.value,
        "origin": claim.origin.value,
        "confidence": claim.confidence,
    }
    if claim.subject is not None:
        item["subject"] = claim.subject.text
    if claim.object is not None:
        item["object"] = claim.object.text
    if claim.predicate:
        item["predicate"] = claim.predicate
    if claim.predicate_key:
        item["predicate_key"] = claim.predicate_key
    if claim.class_hint:
        item["class"] = claim.class_hint
    if claim.dimension:
        item["dimension"] = claim.dimension
    if claim.value_text:
        item["value"] = claim.value_text
    if claim.value_key:
        item["value_key"] = claim.value_key
        item["value"] = claim.value_key
    from pke.interpretation.semantic.learned_attribute import resolve_claim_dimension
    from pke.interpretation.semantic.models import SemanticClaimKind

    if claim.kind is SemanticClaimKind.ATTRIBUTE:
        identity = resolve_claim_dimension(claim, learn=False)
        if identity is not None:
            item["canonical_dimension"] = identity.key
            item["dimension_source"] = identity.source
    if claim.numeric_value:
        item["numeric_value"] = claim.numeric_value
    if claim.unit:
        item["unit"] = claim.unit
    if claim.currency_code:
        item["currency_code"] = claim.currency_code
    return item


def record_entity_resolution(
    mention: EntityMention,
    resolution: EntityResolution,
    lookup: Any,
    ontology: Any,
    context: Any,
) -> None:
    ids = current_trace()
    if not ids.file_id():
        return
    if mention.reference_kind is MentionReferenceKind.CLASS:
        return
    record_resolution_payload(
        format_entity_resolution(mention, resolution, lookup, ontology, context)
    )


def flush_entity_resolution_stage() -> None:
    items = take_resolution_payloads()
    if not items:
        return
    append_trace_stage(
        "entity_resolution",
        {"resolutions": items, "count": len(items)},
    )


def format_entity_resolution(
    mention: EntityMention,
    resolution: EntityResolution,
    lookup: Any,
    ontology: Any,
    context: Any,
) -> dict[str, Any]:
    outcome = _resolution_outcome(resolution)
    reference: dict[str, Any] = {
        "text": mention.text,
        "reference_kind": mention.reference_kind.value,
    }
    if mention.type_hint is not None:
        reference["type_hint"] = mention.type_hint.key
    body: dict[str, Any] = {
        "reference": reference,
        "strategy": _resolution_strategy(mention, resolution),
        "outcome": outcome,
        "candidate_count": len(resolution.candidates),
        "candidates": [
            _candidate_row(candidate.entity_id, candidate.evidence, lookup, ontology, context)
            for candidate in resolution.candidates
        ],
    }
    if resolution.entity_id:
        body["resolved_entity_ids"] = [resolution.entity_id]
    elif outcome == "resolved" and resolution.candidates:
        body["resolved_entity_ids"] = [c.entity_id for c in resolution.candidates[:1]]
    if mention.reference_kind is MentionReferenceKind.POSSESSIVE:
        actor = getattr(context, "principal_entity_id", None)
        if actor:
            body["actor_entity_id"] = actor
        body["relation"] = "relation.owns"
    if outcome == "ambiguous":
        body["clarification_contract"] = "clarify.entity.which_one"
        if resolution.clarification_reason:
            body["clarification_reason"] = resolution.clarification_reason
    elif resolution.clarification_reason:
        body["clarification_reason"] = resolution.clarification_reason
    if resolution.status is ResolutionStatus.CREATE_CANDIDATE:
        body["create_canonical_name"] = resolution.create_canonical_name
        type_key = _type_key(ontology, resolution.create_type_id)
        if type_key:
            body["create_type"] = type_key
    if resolution.notes:
        body["notes"] = list(resolution.notes)
    return body


def format_materialization(
    result: Any,
    uow: Any,
    user_id: str,
    ontology: Any,
    ir: Any | None = None,
) -> dict[str, Any]:
    def entity_row(entity_id: str) -> dict[str, Any]:
        entity = uow.entities.get(user_id, entity_id)
        if entity is None:
            return {"entity_id": entity_id}
        row: dict[str, Any] = {
            "entity_id": entity.id,
            "canonical_name": entity.canonical_name,
        }
        type_key = _type_key(ontology, entity.type_id)
        if type_key:
            row["type"] = type_key
        return row

    def relation_row(relation_id: str) -> dict[str, Any]:
        rel = uow.relations.get(user_id, relation_id)
        if rel is None:
            return {"relation_id": relation_id}
        return {
            "relation_id": rel.id,
            "subject_id": rel.from_id,
            "type": rel.key,
            "object_id": rel.to_id,
        }

    def attribute_row(attribute_id: str) -> dict[str, Any]:
        attr = uow.attributes.get(user_id, attribute_id)
        if attr is None:
            return {"attribute_id": attribute_id}
        return {
            "attribute_id": attr.id,
            "entity_id": attr.entity_id,
            "dimension": attr.dimension_key,
            "value": _attr_display(attr),
        }

    def measurement_row(measurement_id: str) -> dict[str, Any]:
        item = uow.measurements.get(user_id, measurement_id)
        if item is None:
            return {"measurement_id": measurement_id}
        return {
            "measurement_id": item.id,
            "entity_id": item.entity_id,
            "dimension": item.dimension_key,
            "numeric_value": str(item.numeric_value) if item.numeric_value is not None else None,
            "unit": item.unit,
        }

    body: dict[str, Any] = {
        "entities_created": [entity_row(eid) for eid in result.created_entity_ids],
        "entities_reused": [entity_row(eid) for eid in result.reused_entity_ids],
        "relations_created": [relation_row(rid) for rid in result.relation_ids],
        "attributes_created": [attribute_row(aid) for aid in result.attribute_ids],
        "measurements_created": [measurement_row(mid) for mid in result.measurement_ids],
    }
    if result.event_ids:
        body["events_created"] = [{"event_id": eid} for eid in result.event_ids]
    if result.state_ids:
        body["states_created"] = [{"state_id": sid} for sid in result.state_ids]
    claim_results = _claim_results(result, ir, uow=uow, user_id=user_id)
    if claim_results:
        body["claim_results"] = claim_results
    tally = getattr(result, "claims", None)
    if tally is not None:
        dump = getattr(tally, "model_dump", None)
        if callable(dump):
            body["claim_tally"] = dump(mode="json")
    return body


def log_materialization_stage(
    result: Any,
    uow: Any,
    user_id: str,
    ontology: Any,
    ir: Any | None = None,
) -> None:
    if not current_trace().file_id():
        return
    append_trace_stage(
        "materialization",
        format_materialization(result, uow, user_id, ontology, ir),
    )


def _claim_results(
    result: Any,
    ir: Any | None,
    *,
    uow: Any | None = None,
    user_id: str | None = None,
) -> list[dict[str, Any]]:
    report = getattr(ir, "claim_report", None) if ir is not None else None
    executions = list(getattr(report, "executions", None) or []) if report is not None else []
    if executions:
        attr_ids = list(result.attribute_ids)
        rel_ids = list(result.relation_ids)
        meas_ids = list(result.measurement_ids)
        items: list[dict[str, Any]] = []
        for execution in executions:
            row = execution.model_dump(mode="json") if hasattr(execution, "model_dump") else dict(execution)
            kind = row.get("materialized_as")
            status = row.get("status")
            if status == "overlayed" and kind == "attribute" and attr_ids:
                aid = attr_ids.pop(0)
                row["status"] = "committed"
                row["attribute_id"] = aid
                row["materialized_as"] = "attribute"
                if uow is not None and user_id:
                    attr = uow.attributes.get(user_id, aid)
                    if attr is not None:
                        row["entity_id"] = attr.entity_id
            elif status == "overlayed" and kind == "relation" and rel_ids:
                rid = rel_ids.pop(0)
                row["status"] = "committed"
                row["relation_id"] = rid
                row["materialized_as"] = "relation"
            elif status == "overlayed" and kind == "measurement" and meas_ids:
                mid = meas_ids.pop(0)
                row["status"] = "committed"
                row["measurement_id"] = mid
                row["materialized_as"] = "measurement"
            elif status == "overlayed":
                row["status"] = "deferred"
                row["reason"] = row.get("reason") or "not_materialized"
            items.append(row)
        return items
    items = []
    for entity_id in result.created_entity_ids:
        items.append(
            {
                "status": "committed",
                "materialized_as": {"kind": "entity", "entity_id": entity_id},
            }
        )
    for relation_id in result.relation_ids:
        items.append(
            {
                "status": "committed",
                "materialized_as": {"kind": "relation", "relation_id": relation_id},
            }
        )
    for attribute_id in result.attribute_ids:
        items.append(
            {
                "status": "committed",
                "materialized_as": {"kind": "attribute", "attribute_id": attribute_id},
            }
        )
    for measurement_id in result.measurement_ids:
        items.append(
            {
                "status": "committed",
                "materialized_as": {"kind": "measurement", "measurement_id": measurement_id},
            }
        )
    if report is None:
        return items
    for _ in range(int(getattr(report, "derived_deferred", 0) or 0)):
        items.append({"status": "deferred", "reason": "derived_not_materialized"})
    for _ in range(int(getattr(report, "unsupported", 0) or 0)):
        items.append({"status": "deferred", "reason": "unsupported_claim_kind"})
    for _ in range(int(getattr(report, "assumed_dropped", 0) or 0)):
        items.append({"status": "rejected", "reason": "assumed_dropped"})
    return items


def _resolution_outcome(resolution: EntityResolution) -> str:
    if resolution.status is ResolutionStatus.RESOLVED:
        return "resolved"
    if resolution.status is ResolutionStatus.AMBIGUOUS:
        return "ambiguous"
    if resolution.status is ResolutionStatus.CREATE_CANDIDATE:
        return "create_candidate"
    if resolution.clarification_reason in _NO_MATCH_REASONS:
        return "no_match"
    return "unresolved"


def _resolution_strategy(mention: EntityMention, resolution: EntityResolution) -> str:
    if mention.known_entity_id:
        return "explicit_id"
    kind = mention.reference_kind
    if kind is MentionReferenceKind.POSSESSIVE:
        if resolution.status is ResolutionStatus.CREATE_CANDIDATE:
            return "owned_object_create"
        return "owned_entity_by_type"
    if kind is MentionReferenceKind.NAMED:
        return "named_identity_primary"
    if is_self_entity_mention(mention):
        return "principal_self"
    notes = " ".join(resolution.notes)
    if "owned_vehicle" in notes:
        return "owned_vehicle_by_type"
    if kind is MentionReferenceKind.CONTEXTUAL:
        return "contextual_reference"
    return kind.value


def _candidate_row(
    entity_id: str,
    evidence: list[EvidenceKind],
    lookup: Any,
    ontology: Any,
    context: Any,
) -> dict[str, Any]:
    row: dict[str, Any] = {"entity_id": entity_id}
    user_id = getattr(context, "user_id", "")
    entity = lookup.get_by_id(entity_id, user_id) if lookup is not None else None
    if entity is not None:
        row["canonical_name"] = entity.canonical_name
        type_key = _type_key(ontology, entity.type_id)
        if type_key:
            row["type"] = type_key
    match = _match_label(evidence)
    if match:
        row["match"] = match
    return row


def _match_label(evidence: list[EvidenceKind]) -> str | None:
    if EvidenceKind.EXACT_CANONICAL_NAME in evidence:
        return "name_exact"
    if EvidenceKind.EXACT_ALIAS in evidence:
        return "alias_exact"
    if EvidenceKind.PRINCIPAL_BINDING in evidence:
        return "principal"
    if EvidenceKind.OWNED_BY_PRINCIPAL in evidence:
        return "owned"
    if EvidenceKind.TYPE_MATCH in evidence or EvidenceKind.TYPE_DESCENDANT_MATCH in evidence:
        return "type"
    if evidence:
        return evidence[0].value
    return None


def _type_key(ontology: Any, concept_id: str | None) -> str | None:
    if not concept_id or ontology is None:
        return None
    getter = getattr(ontology, "get_by_id", None)
    if not callable(getter):
        return None
    concept = getter(concept_id)
    return getattr(concept, "key", None) if concept is not None else None


def _attr_display(attr: Any) -> str | None:
    if getattr(attr, "text_value", None):
        return str(attr.text_value)
    if getattr(attr, "numeric_value", None) is not None:
        return str(attr.numeric_value)
    if getattr(attr, "year_value", None) is not None:
        return str(attr.year_value)
    if getattr(attr, "date_value", None) is not None:
        return str(attr.date_value)
    return None
