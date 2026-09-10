"""Semantic query resolution — shared resolver core with ingest path."""

from __future__ import annotations

import calendar
import datetime as dt
import re

from dataclasses import dataclass
from enum import StrEnum

from pke.interpretation.models import (
    ConceptRef,
    EntityMention,
    IrQueryTime,
    QueryIR,
    QuerySpec,
    RelativePeriod,
)
from pke.interpretation.semantic.models import (
    PrimitiveKind,
    ResolutionStatus,
    SemanticEntityMention,
    SemanticProposal,
)
from pke.interpretation.semantic.resolver import resolve_concepts
from pke.interpretation.semantic.router import route_primitive
from pke.interpretation.semantic.sense import recognize_senses, SemanticSense
from pke.interpretation.semantic.entity_kinds import resolve_entity_type
from pke.interpretation.transport.catalog import ConceptCatalog


class QueryResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    SAFE_UNRESOLVED = "safe_unresolved"
    SAFE_AMBIGUOUS = "safe_ambiguous"
    ONTOLOGY_GAP = "ontology_gap"
    INSUFFICIENT = "insufficient"


@dataclass(frozen=True)
class SemanticQueryOutcome:
    proposal: SemanticProposal
    query_ir: QueryIR | None
    status: QueryResolutionStatus
    primitive: PrimitiveKind
    notes: tuple[str, ...] = ()


def _mention(sem: SemanticEntityMention, *, role_key: str | None = None) -> EntityMention:
    type_key = resolve_entity_type(sem)
    type_hint = ConceptRef(key=type_key) if type_key else None
    role = ConceptRef(key=role_key) if role_key else None
    return EntityMention(
        text=sem.text,
        type_hint=type_hint,
        role=role,
        reference_kind=sem.reference_kind,
        confidence=sem.confidence,
    )


def _collect_entities(proposal: SemanticProposal) -> list[EntityMention]:
    seen: set[tuple[str, str | None]] = set()
    out: list[EntityMention] = []

    def add(sem: SemanticEntityMention | None, *, default_role: str) -> None:
        if sem is None:
            return
        role = sem.role_hint or default_role
        if not role.startswith("role."):
            role = f"role.{role}"
        key = (sem.text, role)
        if key in seen:
            return
        seen.add(key)
        out.append(_mention(sem, role_key=role))

    add(proposal.subject, default_role="role.subject")
    add(proposal.object, default_role="role.object")
    for sem in proposal.participants:
        add(sem, default_role="role.participant")
    for sem in proposal.entities_mentioned:
        if sem.kind_hint in {"vehicle", "place"}:
            add(sem, default_role="role.context")
        else:
            add(sem, default_role="role.subject")
    return out


def _event_entity_association(entities: list[EntityMention]) -> str:
    if len(entities) > 1:
        return "event_context"
    return "subject"


def _measurement_surface(proposal: SemanticProposal) -> str:
    return " ".join(
        filter(
            None,
            [
                proposal.raw_input or "",
                proposal.measurement_expression or "",
                proposal.attribute_expression or "",
            ],
        )
    ).lower()


def _is_current_language(surface: str) -> bool:
    return bool(
        re.search(
            r"\bagora\b|\batualmente\b|\bneste\s+momento\b|\bno\s+momento\b|"
            r"\bright\s+now\b|\bcurrently\b",
            surface,
        )
    )


def _proposal_expresses_now(proposal: SemanticProposal) -> bool:
    """Structured NOW/PRESENT intent — must not collapse to calendar TODAY."""
    surface = _measurement_surface(proposal)
    if _is_current_language(surface):
        return True
    orig = (proposal.temporal.original_text or "").lower().strip()
    return bool(
        re.search(
            r"\bagora\b|\batualmente\b|\bneste\s+momento\b|\bno\s+momento\b",
            orig,
        )
    )


def _temporal_query(proposal: SemanticProposal) -> IrQueryTime | None:
    temporal = proposal.temporal
    # NOW before relative_day=today — fixtures may wrongly pair agora + relative_day=today
    if _proposal_expresses_now(proposal):
        return IrQueryTime(
            original_text=temporal.original_text or "agora",
            relative_period=RelativePeriod.NOW,
        )
    if temporal.partial_month is not None:
        year = temporal.partial_year
        if year is None:
            return IrQueryTime(original_text=temporal.original_text or "")
        last_day = calendar.monthrange(year, temporal.partial_month)[1]
        start = dt.date(year, temporal.partial_month, 1)
        end = dt.date(year, temporal.partial_month, last_day) + dt.timedelta(days=1)
        return IrQueryTime(
            original_text=temporal.original_text,
            date_from=start,
            date_to=end,
        )
    if temporal.partial_year is not None:
        start = dt.date(temporal.partial_year, 1, 1)
        end = dt.date(temporal.partial_year + 1, 1, 1)
        return IrQueryTime(
            original_text=temporal.original_text or str(temporal.partial_year),
            date_from=start,
            date_to=end,
        )
    if temporal.relative_day == "yesterday":
        return IrQueryTime(
            original_text=temporal.original_text or "ontem",
            relative_period=RelativePeriod.YESTERDAY,
        )
    if temporal.relative_day == "today":
        return IrQueryTime(
            original_text=temporal.original_text or "hoje",
            relative_period=RelativePeriod.TODAY,
        )
    if temporal.original_text.strip():
        return IrQueryTime(original_text=temporal.original_text)
    return None


def _blocked_query(proposal: SemanticProposal, primitive: PrimitiveKind) -> SemanticQueryOutcome | None:
    concept_proposal = _proposal_for_resolution(proposal, primitive)
    concepts = resolve_concepts(concept_proposal, primitive)
    senses = recognize_senses(proposal)

    if concepts.resolution_status is ResolutionStatus.BLOCKED:
        return SemanticQueryOutcome(
            proposal=proposal,
            query_ir=None,
            status=QueryResolutionStatus.SAFE_UNRESOLVED,
            primitive=primitive,
            notes=tuple(concepts.notes) or ("blocked",),
        )
    if concepts.resolution_status is ResolutionStatus.AMBIGUOUS or concepts.safe_abstention:
        if SemanticSense.AMBIGUOUS_PASS in senses:
            return SemanticQueryOutcome(
                proposal=proposal,
                query_ir=None,
                status=QueryResolutionStatus.SAFE_AMBIGUOUS,
                primitive=primitive,
                notes=("ambiguous_pass",),
            )
    if concepts.ontology_gap:
        return SemanticQueryOutcome(
            proposal=proposal,
            query_ir=None,
            status=QueryResolutionStatus.ONTOLOGY_GAP,
            primitive=primitive,
            notes=tuple(concepts.notes) or ("ontology_gap",),
        )
    if primitive is PrimitiveKind.UNKNOWN:
        return SemanticQueryOutcome(
            proposal=proposal,
            query_ir=None,
            status=QueryResolutionStatus.SAFE_AMBIGUOUS,
            primitive=primitive,
            notes=("unknown_primitive",),
        )
    return None


def _proposal_for_resolution(proposal: SemanticProposal, primitive: PrimitiveKind) -> SemanticProposal:
    """Queries about past events inherit change semantics for shared concept resolver."""
    if proposal.utterance_kind == "query" and primitive is PrimitiveKind.EVENT:
        if proposal.action_expression or proposal.event_expression:
            return proposal.model_copy(update={"change_semantics": True})
    return proposal


def resolve_query_proposal(proposal: SemanticProposal) -> SemanticQueryOutcome:
    """Map semantic proposal → QueryIR using shared PrimitiveRouter + SemanticConceptResolver."""
    from pke.interpretation.semantic.slot_align import align_llm_slots

    proposal = align_llm_slots(proposal)
    primitive, _ = route_primitive(proposal)
    blocked = _blocked_query(proposal, primitive)
    if blocked is not None:
        return blocked

    concept_proposal = _proposal_for_resolution(proposal, primitive)
    concepts = resolve_concepts(concept_proposal, primitive)
    entities = _collect_entities(proposal)
    time = _temporal_query(proposal)

    if primitive is PrimitiveKind.EVENT:
        actions: list[ConceptRef] = []
        if concepts.action and concepts.action in ConceptCatalog.actions:
            actions.append(ConceptRef(key=concepts.action))
        event_types: list[ConceptRef] = []
        if concepts.event_type and concepts.event_type in ConceptCatalog.event_types:
            event_types.append(ConceptRef(key=concepts.event_type))
        if not actions and not event_types and not (
            proposal.change_semantics or proposal.action_expression or proposal.event_expression
        ):
            return SemanticQueryOutcome(
                proposal=proposal,
                query_ir=None,
                status=QueryResolutionStatus.INSUFFICIENT,
                primitive=primitive,
                notes=("event_query_missing_constraints",),
            )
        has_temporal_range = time is not None and (
            time.date_from is not None or time.relative_period is not None
        )
        aggregate = "count" if has_temporal_range else "none"
        query_intent = "aggregate" if aggregate == "count" else "list"
        return SemanticQueryOutcome(
            proposal=proposal,
            query_ir=QueryIR(
                raw_input=proposal.raw_input,
                query=QuerySpec(
                    intent=query_intent,
                    entities=entities,
                    entity_association=_event_entity_association(entities),
                    actions=actions,
                    event_types=event_types,
                    time=time,
                    aggregate=aggregate,
                ),
            ),
            status=QueryResolutionStatus.RESOLVED,
            primitive=primitive,
            notes=tuple(concepts.notes),
        )

    if primitive is PrimitiveKind.STATE:
        if not concepts.state_value:
            return SemanticQueryOutcome(
                proposal=proposal,
                query_ir=None,
                status=QueryResolutionStatus.INSUFFICIENT,
                primitive=primitive,
                notes=("state_value_unresolved",),
            )
        dims: list[ConceptRef] = []
        if concepts.state_dimension and concepts.state_dimension in ConceptCatalog.state_dimensions:
            dims.append(ConceptRef(key=concepts.state_dimension))
        return SemanticQueryOutcome(
            proposal=proposal,
            query_ir=QueryIR(
                raw_input=proposal.raw_input,
                query=QuerySpec(
                    intent="state",
                    entities=entities,
                    entity_association="subject",
                    state_values=[ConceptRef(key=concepts.state_value)],
                    state_dimensions=dims,
                ),
            ),
            status=QueryResolutionStatus.RESOLVED,
            primitive=primitive,
        )

    if primitive is PrimitiveKind.RELATION:
        from pke.interpretation.semantic.likes_query_repair import is_relation_object_placeholder

        if not concepts.relation_type or not proposal.subject:
            return SemanticQueryOutcome(
                proposal=proposal,
                query_ir=None,
                status=QueryResolutionStatus.INSUFFICIENT,
                primitive=primitive,
                notes=("relation_identity_incomplete",),
            )
        subj = _mention(proposal.subject, role_key="role.subject")
        has_object = not is_relation_object_placeholder(proposal.object)
        if has_object:
            obj = _mention(proposal.object, role_key="role.object")
            return SemanticQueryOutcome(
                proposal=proposal,
                query_ir=QueryIR(
                    raw_input=proposal.raw_input,
                    query=QuerySpec(
                        intent="relation",
                        entities=[subj, obj],
                        entity_association="relation_subject",
                        relation_types=[ConceptRef(key=concepts.relation_type)],
                        relation_query_kind="current_boolean",
                    ),
                ),
                status=QueryResolutionStatus.RESOLVED,
                primitive=primitive,
            )
        return SemanticQueryOutcome(
            proposal=proposal,
            query_ir=QueryIR(
                raw_input=proposal.raw_input,
                query=QuerySpec(
                    intent="relation",
                    entities=[subj],
                    entity_association="relation_subject",
                    relation_types=[ConceptRef(key=concepts.relation_type)],
                    relation_query_kind=None,
                ),
            ),
            status=QueryResolutionStatus.RESOLVED,
            primitive=primitive,
            notes=tuple(concepts.notes) + ("relation_inventory",),
        )

    if primitive is PrimitiveKind.ATTRIBUTE:
        return _resolve_attribute_query(proposal, entities, time)

    if primitive is PrimitiveKind.MEASUREMENT:
        return _resolve_measurement_query(proposal, entities, time)

    if primitive is PrimitiveKind.TYPE:
        return SemanticQueryOutcome(
            proposal=proposal,
            query_ir=None,
            status=QueryResolutionStatus.INSUFFICIENT,
            primitive=primitive,
            notes=("type_query_not_attribute",),
        )

    return SemanticQueryOutcome(
        proposal=proposal,
        query_ir=None,
        status=QueryResolutionStatus.INSUFFICIENT,
        primitive=primitive,
        notes=("unsupported_query_primitive",),
    )


def _measurement_query_mode(
    proposal: SemanticProposal, time: IrQueryTime | None
) -> str:
    """Structural mode detection — quanto alone never selects Measurement (routing already did)."""
    surface = _measurement_surface(proposal)
    # Value proposition: yes/no style with numeric cue
    if proposal.measurement_numeric_value is not None and re.search(
        r"\besta|\besta[vr]|\bera\b|\btinha\b|\bficou\b|\bj[aá]\s+(esteve|ficou|foi)\b|"
        r"\bwas\b|\bwere\b|\bhad\b",
        surface,
    ):
        return "value_proposition"
    if re.search(
        r"\b[uú]ltim[ao]\s+(leitura|medi[cç][aã]o|observa[cç][aã]o|valor)\b|"
        r"\blast\s+(reading|measurement|observation)\b",
        surface,
    ):
        return "latest_observation"
    if re.search(
        r"\bquais\b|\bqu[aá]is\s+(foram|as)\b|\bleituras\b|\bmedi[cç][oõ]es\b|"
        r"\bwhich\s+(were|readings)\b",
        surface,
    ):
        return "observations_in_range"
    # Current-language → observation_at_time (never latest-as-current)
    if _is_current_language(surface):
        return "observation_at_time"
    if time is not None and (
        time.relative_period is not None
        or time.date_from is not None
        or time.start is not None
    ):
        return "observation_at_time"
    # Present-tense "quanto tem/está" without "última" → at-time (current scope), not latest
    if re.search(r"\b(tem|est[aá]|is|are)\b", surface) and re.search(
        r"\bquanto\b|\bquantos\b|\bquanta\b|\bqual\b", surface
    ):
        return "observation_at_time"
    return "latest_observation"


def _resolve_measurement_query(
    proposal: SemanticProposal,
    entities: list,
    time: IrQueryTime | None,
) -> SemanticQueryOutcome:
    from pke.interpretation.semantic.measurement_resolution import resolve_measurement_value

    dimension = (proposal.measurable_dimension_key or "").strip()
    if not dimension:
        measured = resolve_measurement_value(proposal)
        dimension = measured.dimension_key if measured else ""
    if not dimension:
        return SemanticQueryOutcome(
            proposal=proposal,
            query_ir=None,
            status=QueryResolutionStatus.INSUFFICIENT,
            primitive=PrimitiveKind.MEASUREMENT,
            notes=("measurement_dimension_unresolved",),
        )
    if not entities:
        return SemanticQueryOutcome(
            proposal=proposal,
            query_ir=None,
            status=QueryResolutionStatus.INSUFFICIENT,
            primitive=PrimitiveKind.MEASUREMENT,
            notes=("measurement_entity_missing",),
        )

    mode = _measurement_query_mode(proposal, time)
    surface = _measurement_surface(proposal)
    # Current / present-tense without structured time → NOW instant (≠ calendar TODAY)
    query_time = time
    if mode == "observation_at_time" and query_time is None and (
        _is_current_language(surface)
        or re.search(r"\b(tem|est[aá])\b", surface)
    ):
        query_time = IrQueryTime(
            original_text="agora",
            relative_period=RelativePeriod.NOW,
        )

    value_fields: dict = {}
    if mode == "value_proposition":
        measured = resolve_measurement_value(proposal)
        if measured is None and proposal.measurement_numeric_value is not None:
            # Dimension already known; allow filter from structured cues
            from decimal import Decimal, InvalidOperation

            try:
                num = Decimal(str(proposal.measurement_numeric_value).replace(",", "."))
            except (InvalidOperation, ValueError):
                num = None
            if num is not None:
                unit = proposal.measurement_unit
                currency = proposal.measurement_currency_code
                if unit and currency:
                    return SemanticQueryOutcome(
                        proposal=proposal,
                        query_ir=None,
                        status=QueryResolutionStatus.INSUFFICIENT,
                        primitive=PrimitiveKind.MEASUREMENT,
                        notes=("measurement_unit_currency_coexist",),
                    )
                value_fields = {
                    "measurement_numeric_value": str(num),
                    "measurement_unit": unit,
                    "measurement_currency_code": (
                        currency.upper() if currency else None
                    ),
                }
        elif measured is not None:
            value_fields = {
                "measurement_numeric_value": str(measured.numeric_value),
                "measurement_unit": measured.unit,
                "measurement_currency_code": measured.currency_code,
            }
        else:
            return SemanticQueryOutcome(
                proposal=proposal,
                query_ir=None,
                status=QueryResolutionStatus.INSUFFICIENT,
                primitive=PrimitiveKind.MEASUREMENT,
                notes=("measurement_proposition_value_unresolved",),
            )

    return SemanticQueryOutcome(
        proposal=proposal,
        query_ir=QueryIR(
            raw_input=proposal.raw_input,
            query=QuerySpec(
                intent="measurement",
                entities=entities,
                entity_association="subject",
                measurement_dimension_key=dimension,
                measurement_query_mode=mode,  # type: ignore[arg-type]
                time=query_time,
                **value_fields,
            ),
        ),
        status=QueryResolutionStatus.RESOLVED,
        primitive=PrimitiveKind.MEASUREMENT,
        notes=("measurement_query", mode),
    )


def _attribute_query_mode(proposal: SemanticProposal) -> str:
    surface = " ".join(
        filter(
            None,
            [
                proposal.raw_input or "",
                proposal.attribute_expression or "",
            ],
        )
    ).lower()
    if re.search(r"\bj[aá]\s+foi\b|\balready\s+was\b|\bhas\s+been\b", surface):
        return "historical_existence"
    if re.search(r"\bera\b|\bwas\b", surface) and re.search(
        r"\bem\s+\d{4}\b|\bin\s+\d{4}\b", surface
    ):
        return "historical_existence"
    if re.search(
        r"\bqual\b|\bquanto\b|\bquantos\b|\bquanta\b|\bwhat\b|\bhow\s+much\b|\bcomo\b",
        surface,
    ):
        return "value_lookup"
    return "proposition"


def _resolve_attribute_query(
    proposal: SemanticProposal,
    entities: list,
    time: IrQueryTime | None,
) -> SemanticQueryOutcome:
    from pke.interpretation.semantic.attribute_resolution import (
        resolve_attribute_dimension_key,
        resolve_attribute_value,
    )
    from pke.interpretation.semantic.possessive_attribute_repair import SNAPSHOT_EXPRESSION

    if (proposal.attribute_expression or "").strip() == SNAPSHOT_EXPRESSION:
        if not entities:
            return SemanticQueryOutcome(
                proposal=proposal,
                query_ir=None,
                status=QueryResolutionStatus.INSUFFICIENT,
                primitive=PrimitiveKind.ATTRIBUTE,
                notes=("attribute_entity_missing",),
            )
        return SemanticQueryOutcome(
            proposal=proposal,
            query_ir=QueryIR(
                raw_input=proposal.raw_input,
                query=QuerySpec(
                    intent="attribute",
                    entities=entities,
                    entity_association="subject",
                    attribute_query_mode="snapshot",
                    time=time,
                ),
            ),
            status=QueryResolutionStatus.RESOLVED,
            primitive=PrimitiveKind.ATTRIBUTE,
        )

    dimension = resolve_attribute_dimension_key(proposal)
    if not dimension:
        return SemanticQueryOutcome(
            proposal=proposal,
            query_ir=None,
            status=QueryResolutionStatus.INSUFFICIENT,
            primitive=PrimitiveKind.ATTRIBUTE,
            notes=("attribute_dimension_unresolved",),
        )
    if not entities:
        return SemanticQueryOutcome(
            proposal=proposal,
            query_ir=None,
            status=QueryResolutionStatus.INSUFFICIENT,
            primitive=PrimitiveKind.ATTRIBUTE,
            notes=("attribute_entity_missing",),
        )

    mode = _attribute_query_mode(proposal)
    valued = resolve_attribute_value(proposal)
    # VALUE_LOOKUP must not treat dimension word as value ("cor" ≠ color text value)
    value_fields: dict = {}
    if mode in {"proposition", "historical_existence"} and valued is not None:
        value_fields = {
            "attribute_value_kind": valued.value_kind.value,
            "attribute_text_value": valued.text_value,
            "attribute_numeric_value": (
                str(valued.numeric_value) if valued.numeric_value is not None else None
            ),
            "attribute_unit": valued.unit,
            "attribute_year_value": valued.year_value,
            "attribute_concept_value_id": valued.concept_value_id,
        }
    elif mode == "historical_existence":
        # Color/value may appear in raw without being a write-shaped attribute_expression
        from pke.interpretation.semantic.attribute_resolution import _COLOR_WORDS, _strip_accents

        surface = (proposal.raw_input or "").lower()
        for word in _COLOR_WORDS:
            if re.search(rf"(?<!\w){re.escape(word)}(?!\w)", surface):
                value_fields = {
                    "attribute_value_kind": "text",
                    "attribute_text_value": _strip_accents(word),
                }
                break

    return SemanticQueryOutcome(
        proposal=proposal,
        query_ir=QueryIR(
            raw_input=proposal.raw_input,
            query=QuerySpec(
                intent="attribute",
                entities=entities,
                entity_association="subject",
                attribute_dimension_key=dimension,
                attribute_query_mode=mode,  # type: ignore[arg-type]
                time=time,
                **value_fields,
            ),
        ),
        status=QueryResolutionStatus.RESOLVED,
        primitive=PrimitiveKind.ATTRIBUTE,
        notes=("attribute_query",),
    )


def proposal_to_query_ir(proposal: SemanticProposal) -> SemanticQueryOutcome:
    from pke.interpretation.semantic.self_repair import apply_e1_self_repairs

    proposal = apply_e1_self_repairs(proposal)
    query_proposal = proposal.model_copy(update={"utterance_kind": "query"})
    return resolve_query_proposal(query_proposal)
