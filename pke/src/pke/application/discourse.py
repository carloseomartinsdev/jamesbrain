"""Update conversation discourse from Engine results — no raw_input, no NL."""

from __future__ import annotations

from pke.application.ask_results import AskClarification, AskResult, AskStatus
from pke.application.results import IngestResult, IngestStatus
from pke.interpretation.discourse import (
    MAX_IDLE_TURNS,
    MAX_RECENT_REFERENTS,
    DiscourseFocus,
    DiscoursePendingIntent,
    DiscourseReferent,
    DiscourseState,
    allowed_entity_ids,
)
from pke.interpretation.models import IngestIR, QueryIR


def interpret_context_from_session(
    session,
    user,
    *,
    client_request_id: str | None = None,
    pke_request_id: str | None = None,
):
    from pke.interpretation.interpreter import InterpretationContext

    return InterpretationContext(
        user=user,
        recent_event_ids=list(session.recent_event_ids),
        recent_utterances=list(session.recent_utterances),
        discourse=session.discourse.model_copy(deep=True),
        client_request_id=client_request_id,
        pke_request_id=pke_request_id,
    )


def type_keys_from_entities(ontology, entities) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for entity in entities:
        concept = ontology.get_by_id(entity.type_id)
        if concept is not None:
            mapping[entity.id] = concept.key
    return mapping


def names_from_entities(entities) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for entity in entities:
        eid = getattr(entity, "id", None)
        name = getattr(entity, "canonical_name", None)
        if eid and name:
            mapping[str(eid)] = str(name)
    return mapping


def apply_ask_to_discourse(
    state: DiscourseState,
    result: AskResult,
    *,
    principal_id: str | None,
    type_by_entity: dict[str, str] | None = None,
    names: dict[str, str] | None = None,
    clear_pending: bool = True,
) -> DiscourseState:
    if result.status is AskStatus.NEEDS_CLARIFICATION:
        return state
    ids = _ask_focus_ids(result, principal_id)
    primitive = None
    relation_type = None
    result_kind = None
    spec = result.resolved_spec
    if spec is not None:
        primitive = _primitive_from_spec(spec)
        if spec.relation_type_ids and result.query_result is not None:
            rels = [r.relation_key for r in result.query_result.current_relations if r.relation_key]
            relation_type = rels[0] if rels else None
        if result.query_result is not None and result.query_result.relation_answer is not None:
            result_kind = "boolean"
        elif result.query_result is not None and result.query_result.attribute_values:
            result_kind = "attribute"
    if not ids:
        return _idle(state)
    target_type = None
    mapping = type_by_entity or {}
    for eid in ids:
        if mapping.get(eid):
            target_type = mapping[eid]
            break
    return _commit_focus(
        state,
        ids=ids,
        primitive=primitive,
        relation_type=relation_type,
        target_type=target_type,
        result_kind=result_kind,
        types=mapping,
        names=names or {},
        reason="successful_query",
        clear_pending=clear_pending,
    )


def apply_ingest_to_discourse(
    state: DiscourseState,
    result: IngestResult,
    *,
    principal_id: str | None,
    type_by_entity: dict[str, str] | None = None,
    names: dict[str, str] | None = None,
    ir: IngestIR | None = None,
    clear_pending: bool | None = None,
) -> DiscourseState:
    if result.status not in {IngestStatus.COMMITTED, IngestStatus.PARTIAL}:
        return _idle(state)
    mapping = type_by_entity or {}
    label_by_id = names or {}
    ids = _ingest_focus_ids(result, principal_id, ir, names=label_by_id, types=mapping)
    if not ids:
        return _idle(state)
    target_type = None
    for eid in ids:
        if mapping.get(eid):
            target_type = mapping[eid]
            break
    if clear_pending is None:
        clear_pending = ir is None or ir.discourse_decision != "continue"
    reason = "successful_write"
    if ir is not None and (ir.attribute is not None or ir.measurement is not None):
        reason = "successful_attribute_write"
    return _commit_focus(
        state,
        ids=ids,
        primitive="ingest",
        relation_type=_ingest_relation_key(ir),
        target_type=target_type,
        result_kind="write",
        types=mapping,
        names=label_by_id,
        reason=reason,
        clear_pending=clear_pending,
    )


def store_pending_query(
    state: DiscourseState,
    ir: QueryIR,
    clarification: AskClarification | None,
    *,
    types: dict[str, str] | None = None,
    names: dict[str, str] | None = None,
) -> DiscourseState:
    """Keep the unresolved attribute query so a later subject can complete it."""
    candidates = list(clarification.candidate_entity_ids) if clarification is not None else []
    pending = DiscoursePendingIntent(
        operation="attribute_query",
        attribute_dimension_key=ir.query.attribute_dimension_key,
        missing_role="subject",
        candidate_entity_ids=candidates,
        query_dump=ir.model_dump(mode="json"),
    )
    referents = list(state.recent_referents)
    mapping = types or {}
    label_by_id = names or {}
    for eid in candidates:
        referents = _upsert(
            referents,
            DiscourseReferent(
                entity_id=eid,
                type_key=mapping.get(eid) or _type_of(eid, mapping, state),
                display_name=label_by_id.get(eid) or _name_of(eid, label_by_id, state),
                role="clarification_candidate",
                salience=0.9,
            ),
        )
    return state.model_copy(
        update={
            "pending_intent": pending,
            "recent_referents": referents[:MAX_RECENT_REFERENTS],
            "last_update_reason": "pending_query_stored",
        }
    )


def apply_pending_to_query_ir(ir: QueryIR, pending: DiscoursePendingIntent | None) -> QueryIR:
    """Fill a missing subject or missing attribute from conversation-scoped pending intent."""
    if pending is None or pending.operation != "attribute_query":
        return ir
    current = ir.query
    if (
        ir.discourse_decision == "new_topic"
        and current.attribute_dimension_key
        and current.entities
    ):
        return ir
    base: QueryIR | None = None
    if pending.query_dump:
        try:
            base = QueryIR.model_validate(pending.query_dump)
        except Exception:
            base = None
    entities = current.entities or (base.query.entities if base is not None else [])
    if not entities:
        return ir
    if current.attribute_dimension_key:
        if current.entities:
            return ir
        return ir.model_copy(
            update={
                "query": current.model_copy(update={"entities": entities}),
            }
        )
    if base is not None and not current.attribute_dimension_key:
        restored = base.query.model_copy(
            update={
                "entities": entities,
                "entity_association": current.entity_association
                or base.query.entity_association
                or "subject",
            }
        )
        return ir.model_copy(
            update={
                "query": restored,
                "discourse_decision": ir.discourse_decision or "continue",
            }
        )
    dim = pending.attribute_dimension_key
    if not dim:
        return ir
    filled = current.model_copy(
        update={
            "intent": "attribute",
            "entities": entities,
            "entity_association": current.entity_association or "subject",
            "attribute_dimension_key": dim,
            "attribute_query_mode": current.attribute_query_mode or "value_lookup",
        }
    )
    return ir.model_copy(update={"query": filled, "discourse_decision": ir.discourse_decision or "continue"})


def binding_allowed(state: DiscourseState | None, entity_id: str | None) -> bool:
    if not entity_id:
        return True
    allowed = allowed_entity_ids(state)
    if not allowed:
        return True
    return entity_id in allowed


def _primitive_from_spec(spec) -> str:
    if spec.relation_type_ids:
        return "relation"
    if spec.attribute_dimension_key:
        return "attribute"
    if spec.measurement_dimension_key:
        return "measurement"
    if spec.state_dimension_ids or spec.state_value_ids:
        return "state"
    if spec.event_type_ids or spec.action_ids:
        return "event"
    return "query"


def _ask_focus_ids(result: AskResult, principal_id: str | None) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()

    def add(eid: str | None) -> None:
        if not eid or eid == principal_id or eid in seen:
            return
        seen.add(eid)
        ids.append(eid)

    qr = result.query_result
    if qr is not None:
        for rel in qr.current_relations:
            add(rel.object_entity_id)
    if not ids:
        for eid in result.resolved_entity_ids:
            add(eid)
    if not ids and qr is not None:
        for item in qr.items:
            for eid in item.entity_ids:
                add(eid)
    return ids


def _ingest_focus_ids(
    result: IngestResult,
    principal_id: str | None,
    ir: IngestIR | None,
    *,
    names: dict[str, str],
    types: dict[str, str],
) -> list[str]:
    bound = [eid for eid in result.bound_entity_ids if eid and eid != principal_id]
    created: list[str] = []
    reused: list[str] = []
    if result.materialization is not None:
        created = [eid for eid in result.materialization.created_entity_ids if eid != principal_id]
        reused = [eid for eid in result.materialization.reused_entity_ids if eid != principal_id]

    def pick_mention(mention) -> str | None:
        return _match_mention_to_bound(mention, bound, names)

    if ir is not None:
        if ir.attribute is not None:
            kid = pick_mention(ir.attribute.subject)
            if kid:
                return [kid]
        if ir.measurement is not None:
            kid = pick_mention(ir.measurement.subject)
            if kid:
                return [kid]
        if ir.event is not None:
            for participant in ir.event.participants:
                kid = pick_mention(participant)
                if kid:
                    return [kid]
        if ir.relation is not None:
            kid = pick_mention(ir.relation.object)
            if kid:
                return [kid]
            if _is_owns_key(_concept_key(ir.relation.type)):
                if len(created) == 1:
                    return created
                if len(reused) == 1:
                    return reused
                if created:
                    return created
            kid = pick_mention(ir.relation.subject)
            if kid:
                return [kid]
    primary = created or reused or bound
    return _drop_secondary_participants(primary, types)


def _drop_secondary_participants(ids: list[str], types: dict[str, str]) -> list[str]:
    if len(ids) <= 1:
        return ids
    kept = [eid for eid in ids if not _is_secondary_type(types.get(eid))]
    return kept or ids


def _is_secondary_type(type_key: str | None) -> bool:
    key = (type_key or "").strip().lower()
    if not key:
        return False
    suffix = key.rsplit(".", 1)[-1]
    return suffix in {"place", "location", "store", "shop", "vendor"}


def _is_owns_key(key: str | None) -> bool:
    text = (key or "").strip().lower()
    return text == "relation.owns" or text.endswith(".owns")


def _concept_key(ref) -> str | None:
    if ref is None:
        return None
    return getattr(ref, "key", None) or str(ref)


def _ingest_relation_key(ir: IngestIR | None) -> str | None:
    if ir is None or ir.relation is None:
        return None
    return _concept_key(ir.relation.type)


def _match_mention_to_bound(mention, bound: list[str], names: dict[str, str]) -> str | None:
    if mention is None:
        return None
    known = getattr(mention, "known_entity_id", None)
    if known and known in bound:
        return known
    text = (getattr(mention, "text", None) or "").strip().casefold()
    if not text:
        return None
    hits = [
        eid
        for eid in bound
        if (names.get(eid) or "").strip().casefold() == text
    ]
    if len(hits) == 1:
        return hits[0]
    return None


def _idle(state: DiscourseState) -> DiscourseState:
    nxt = state.idle_turns + 1
    if nxt > MAX_IDLE_TURNS:
        return DiscourseState(
            active_focus=None,
            recent_referents=_fade(state.recent_referents),
            last_query_primitive=state.last_query_primitive,
            last_relation_type=state.last_relation_type,
            last_result_kind=state.last_result_kind,
            last_update_reason="idle_cleared",
            pending_intent=state.pending_intent,
            idle_turns=nxt,
        )
    return state.model_copy(update={"idle_turns": nxt})


def _commit_focus(
    state: DiscourseState,
    *,
    ids: list[str],
    primitive: str | None,
    relation_type: str | None,
    target_type: str | None,
    result_kind: str | None,
    types: dict[str, str],
    names: dict[str, str],
    reason: str | None = None,
    clear_pending: bool = False,
) -> DiscourseState:
    previous = list(state.active_focus.entity_ids) if state.active_focus else []
    if reason is None:
        reason = "new_focus"
    if previous and set(previous).isdisjoint(set(ids)):
        reason = "topic_switch"
    referents = _fade(state.recent_referents)
    for eid in reversed(previous):
        if eid in ids:
            continue
        referents = _upsert(
            referents,
            DiscourseReferent(
                entity_id=eid,
                type_key=_type_of(eid, types, state),
                display_name=_name_of(eid, names, state),
                role="previous_focus",
                salience=0.6,
            ),
        )
    for eid in ids:
        referents = _upsert(
            referents,
            DiscourseReferent(
                entity_id=eid,
                type_key=types.get(eid) or target_type,
                display_name=_name_of(eid, names, state),
                role="active_focus",
                salience=1.0,
            ),
        )
    display = None
    if len(ids) == 1:
        display = _name_of(ids[0], names, state)
    pending = None if clear_pending else state.pending_intent
    return DiscourseState(
        active_focus=DiscourseFocus(
            primitive=primitive,
            relation_type=relation_type,
            target_type=target_type,
            entity_ids=list(ids),
            display_name=display,
        ),
        recent_referents=referents[:MAX_RECENT_REFERENTS],
        last_query_primitive=primitive,
        last_relation_type=relation_type,
        last_result_kind=result_kind,
        last_update_reason=reason,
        pending_intent=pending,
        idle_turns=0,
    )


def _fade(items: list[DiscourseReferent]) -> list[DiscourseReferent]:
    faded = []
    for item in items:
        salience = round(item.salience * 0.85, 3)
        if salience < 0.2:
            continue
        faded.append(item.model_copy(update={"salience": salience, "role": item.role}))
    return faded


def _upsert(items: list[DiscourseReferent], incoming: DiscourseReferent) -> list[DiscourseReferent]:
    rest = [item for item in items if item.entity_id != incoming.entity_id]
    return [incoming, *rest]


def _type_of(eid: str, types: dict[str, str], state: DiscourseState) -> str | None:
    if eid in types:
        return types[eid]
    for item in state.recent_referents:
        if item.entity_id == eid:
            return item.type_key
    if state.active_focus and eid in state.active_focus.entity_ids:
        return state.active_focus.target_type
    return None


def _name_of(eid: str, names: dict[str, str], state: DiscourseState) -> str | None:
    if eid in names:
        return names[eid]
    for item in state.recent_referents:
        if item.entity_id == eid and item.display_name:
            return item.display_name
    if (
        state.active_focus
        and state.active_focus.display_name
        and eid in state.active_focus.entity_ids
    ):
        return state.active_focus.display_name
    return None
