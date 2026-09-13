"""Wire models for semantic proposal — relaxed vs canonical WireIngestIR."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from pke.interpretation.semantic.llm_vocab import (
    coerce_class_hint,
    coerce_discourse_decision,
    coerce_kind_hint,
    coerce_lifecycle_cue,
    coerce_occurrence_aspect,
    coerce_primitive_hint,
    coerce_reference_kind,
    coerce_relation_to_reference,
    coerce_relative_day,
    coerce_temporal_selection,
    coerce_utterance_kind,
)
from pke.interpretation.semantic.models import (
    SemanticClaim,
    SemanticEntityMention,
    SemanticProposal,
    SemanticTime,
)
from pke.interpretation.transport.wire import WireEntityMention, WireQueryIR, WireQuerySpec


class WireSemanticEntity(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str
    kind_hint: Annotated[
        Literal[
            "person",
            "organization",
            "place",
            "thing",
            "appliance",
            "vehicle",
            "document",
            "medication",
            "unknown",
        ]
        | None,
        BeforeValidator(coerce_kind_hint),
    ] = None
    role_hint: str | None = None
    reference_kind: Annotated[
        Literal["named", "contextual", "possessive", "class"],
        BeforeValidator(coerce_reference_kind),
    ] = "named"
    class_hint: Annotated[str | None, BeforeValidator(coerce_class_hint)] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    known_entity_id: str | None = None


class WireSemanticClaim(BaseModel):
    model_config = ConfigDict(extra="ignore")

    kind: str
    subject: WireSemanticEntity | None = None
    object: WireSemanticEntity | None = None
    predicate: str | None = None
    predicate_key: str | None = None
    class_hint: Annotated[str | None, BeforeValidator(coerce_class_hint)] = None
    dimension: str | None = None
    value_text: str | None = None
    value_key: str | None = None
    numeric_value: str | None = None
    unit: str | None = None
    currency_code: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    origin: str = "explicit"


class WireSemanticTime(BaseModel):
    model_config = ConfigDict(extra="ignore")

    original_text: str = ""
    relative_day: Annotated[
        Literal["today", "yesterday", "tomorrow"] | None,
        BeforeValidator(coerce_relative_day),
    ] = None
    occurrence_aspect: Annotated[
        Literal["happened", "ongoing", "planned", "habitual"] | None,
        BeforeValidator(coerce_occurrence_aspect),
    ] = None
    relation_to_reference: Annotated[
        Literal["before", "after", "during", "habitual"] | None,
        BeforeValidator(coerce_relation_to_reference),
    ] = None
    selection: Annotated[
        Literal["current", "previous", "first", "last"] | None,
        BeforeValidator(coerce_temporal_selection),
    ] = None
    tense_evidence: str | None = None
    partial_month: int | None = Field(default=None, ge=1, le=12)
    partial_year: int | None = None
    unknown_reason: Literal["not_provided", "forgotten", "unresolved", "unknown"] | None = None


class WireSemanticProposal(BaseModel):
    model_config = ConfigDict(extra="ignore")

    raw_input: str
    utterance_kind: Annotated[
        Literal["assert", "describe", "change", "query", "correct", "none"],
        BeforeValidator(coerce_utterance_kind),
    ] = "assert"
    primitive_hint: Annotated[
        Literal[
            "event", "state", "relation", "attribute", "type", "measurement", "unknown"
        ],
        BeforeValidator(coerce_primitive_hint),
    ] = "unknown"
    subject: WireSemanticEntity | None = None
    object: WireSemanticEntity | None = None
    context: WireSemanticEntity | None = None
    participants: list[WireSemanticEntity] = Field(default_factory=list)
    entities_mentioned: list[WireSemanticEntity] = Field(default_factory=list)
    action_expression: str | None = None
    relation_expression: str | None = None
    state_expression: str | None = None
    attribute_expression: str | None = None
    event_expression: str | None = None
    measurement_expression: str | None = None
    measurable_dimension_key: str | None = None
    measurement_numeric_value: str | None = None
    measurement_unit: str | None = None
    measurement_currency_code: str | None = None
    temporal: WireSemanticTime = Field(default_factory=WireSemanticTime)
    negation: bool = False
    lifecycle_cue: Annotated[
        Literal["start", "end", "ongoing", "deny", "none"] | None,
        BeforeValidator(coerce_lifecycle_cue),
    ] = None
    change_semantics: bool = False
    condition_semantics: bool = False
    link_semantics: bool = False
    stable_property_semantics: bool = False
    classification_semantics: bool = False
    measurement_semantics: bool = False
    domain_hints: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    correction_semantics: bool = False
    correction_operation: Literal["retract", "replace"] | None = None
    correction_target_kind: Literal[
        "event", "measurement", "relation", "state", "attribute"
    ] | None = None
    correction_target_entity_text: str | None = None
    correction_target_object_text: str | None = None
    correction_target_dimension_key: str | None = None
    correction_target_value_text: str | None = None
    correction_target_numeric_value: str | None = None
    correction_target_year: int | None = None
    correction_target_relation_key: str | None = None
    correction_target_state_value_key: str | None = None
    correction_target_action_key: str | None = None
    correction_target_assertion_id: str | None = None
    correction_conversation_assertion_id: str | None = None
    claims: list[WireSemanticClaim] = Field(default_factory=list)
    discourse_decision: Annotated[
        Literal["continue", "new_topic", "ambiguous", "none"] | None,
        BeforeValidator(coerce_discourse_decision),
    ] = None


class WireSemanticQuery(BaseModel):
    model_config = ConfigDict(extra="ignore")

    raw_input: str
    query_kind: Literal["list", "aggregate", "state", "relation"] = "list"
    state_expression: str | None = None
    relation_expression: str | None = None
    condition_semantics: bool = False
    link_semantics: bool = False
    entities: list[WireSemanticEntity] = Field(default_factory=list)


class WireSemanticEnvelope(BaseModel):
    """Envelope: semantic proposal before canonicalization."""

    model_config = ConfigDict(extra="ignore")

    ir_kind: Literal["semantic_proposal", "semantic_query", "ingest", "query"]
    ir: dict[str, Any]

    @classmethod
    def parse_json(cls, content: str) -> WireSemanticEnvelope:
        from pke.interpretation.semantic.envelope_dispatch import ProviderRoute, dispatch_provider_payload

        dispatched = dispatch_provider_payload(content)
        if dispatched.route is not ProviderRoute.SEMANTIC_V3 or dispatched.payload is None:
            if dispatched.failure_category is not None:
                raise ValueError(dispatched.failure_category.value)
            raise ValueError("expected semantic v3 envelope")
        payload = dispatched.payload
        if not isinstance(payload, dict):
            raise ValueError("envelope deve ser objeto JSON")
        return cls.model_validate(payload)

    def parsed_proposal(self) -> SemanticProposal:
        wire = WireSemanticProposal.model_validate(self.ir)

        def ent(w: WireSemanticEntity | None) -> SemanticEntityMention | None:
            if w is None:
                return None
            return SemanticEntityMention(
                text=w.text,
                kind_hint=w.kind_hint,
                role_hint=w.role_hint,
                reference_kind=w.reference_kind,
                class_hint=w.class_hint,
                confidence=w.confidence,
                known_entity_id=w.known_entity_id,
            )

        return SemanticProposal(
            raw_input=wire.raw_input,
            utterance_kind=wire.utterance_kind,
            primitive_hint=wire.primitive_hint,
            subject=ent(wire.subject),
            object=ent(wire.object),
            context=ent(wire.context),
            participants=[ent(p) for p in wire.participants if ent(p)],
            entities_mentioned=[ent(e) for e in wire.entities_mentioned if ent(e)],
            action_expression=wire.action_expression,
            relation_expression=wire.relation_expression,
            state_expression=wire.state_expression,
            attribute_expression=wire.attribute_expression,
            event_expression=wire.event_expression,
            measurement_expression=wire.measurement_expression,
            measurable_dimension_key=wire.measurable_dimension_key,
            measurement_numeric_value=wire.measurement_numeric_value,
            measurement_unit=wire.measurement_unit,
            measurement_currency_code=wire.measurement_currency_code,
            temporal=SemanticTime.model_validate(wire.temporal.model_dump()),
            negation=wire.negation,
            lifecycle_cue=wire.lifecycle_cue,
            change_semantics=wire.change_semantics,
            condition_semantics=wire.condition_semantics,
            link_semantics=wire.link_semantics,
            stable_property_semantics=wire.stable_property_semantics,
            classification_semantics=wire.classification_semantics,
            measurement_semantics=wire.measurement_semantics,
            domain_hints=wire.domain_hints,
            confidence=wire.confidence,
            correction_semantics=wire.correction_semantics,
            correction_operation=wire.correction_operation,
            correction_target_kind=wire.correction_target_kind,
            correction_target_entity_text=wire.correction_target_entity_text,
            correction_target_object_text=wire.correction_target_object_text,
            correction_target_dimension_key=wire.correction_target_dimension_key,
            correction_target_value_text=wire.correction_target_value_text,
            correction_target_numeric_value=wire.correction_target_numeric_value,
            correction_target_year=wire.correction_target_year,
            correction_target_relation_key=wire.correction_target_relation_key,
            correction_target_state_value_key=wire.correction_target_state_value_key,
            correction_target_action_key=wire.correction_target_action_key,
            correction_target_assertion_id=wire.correction_target_assertion_id,
            correction_conversation_assertion_id=wire.correction_conversation_assertion_id,
            discourse_decision=wire.discourse_decision,
            claims=[
                SemanticClaim(
                    kind=c.kind,  # type: ignore[arg-type]
                    subject=ent(c.subject),
                    object=ent(c.object),
                    predicate=c.predicate,
                    predicate_key=c.predicate_key,
                    class_hint=c.class_hint,
                    dimension=c.dimension,
                    value_text=c.value_text,
                    value_key=c.value_key,
                    numeric_value=c.numeric_value,
                    unit=c.unit,
                    currency_code=c.currency_code,
                    confidence=c.confidence,
                    origin=c.origin,  # type: ignore[arg-type]
                )
                for c in wire.claims
            ],
        )

    def parsed_query_proposal(self) -> SemanticProposal:
        """Full semantic proposal shape preferred; legacy WireSemanticQuery supported."""
        ir = self.ir
        if any(
            key in ir
            for key in (
                "primitive_hint",
                "action_expression",
                "change_semantics",
                "condition_semantics",
                "link_semantics",
                "event_expression",
                "state_expression",
                "relation_expression",
            )
        ):
            return self.parsed_proposal().model_copy(update={"utterance_kind": "query"})
        wire_q = WireSemanticQuery.model_validate(ir)
        entities = [
            SemanticEntityMention(
                text=e.text,
                kind_hint=e.kind_hint,
                role_hint=e.role_hint,
                reference_kind=e.reference_kind,
                class_hint=e.class_hint,
                confidence=e.confidence,
            )
            for e in wire_q.entities
        ]
        subject = entities[0] if entities and wire_q.link_semantics else None
        obj = entities[1] if len(entities) > 1 and wire_q.link_semantics else None
        if wire_q.relation_expression and len(entities) >= 2:
            subject = entities[0]
            obj = entities[1]
        return SemanticProposal(
            raw_input=wire_q.raw_input,
            utterance_kind="query",
            subject=subject,
            object=obj,
            entities_mentioned=entities if not wire_q.link_semantics else [],
            state_expression=wire_q.state_expression,
            relation_expression=wire_q.relation_expression,
            condition_semantics=wire_q.condition_semantics,
            link_semantics=wire_q.link_semantics,
            primitive_hint=(
                "relation"
                if wire_q.link_semantics or wire_q.relation_expression
                else "state"
                if wire_q.condition_semantics or wire_q.state_expression
                else "unknown"
            ),
        )


def proposal_query_to_wire(query: WireSemanticQuery) -> WireQueryIR:
    """Map semantic query proposal to canonical wire query (minimal)."""
    relation_types: list[str] = []
    state_dimensions: list[str] = []
    state_values: list[str] = []
    if query.link_semantics or query.relation_expression:
        relation_types = ["relation.employed_by"]
    if query.condition_semantics or query.state_expression:
        state_dimensions = ["state.operational_condition"]
        if query.state_expression and "funcion" in (query.state_expression or "").lower():
            state_values = ["state.value.working"]
    entities = [
        WireEntityMention(text=e.text, entity_type=None, role=None) for e in query.entities
    ]
    return WireQueryIR(
        intent="query",
        raw_input=query.raw_input,
        query=WireQuerySpec(
            intent=query.query_kind,
            entities=entities,
            relation_types=relation_types,
            state_dimensions=state_dimensions,
            state_values=state_values,
        ),
    )
