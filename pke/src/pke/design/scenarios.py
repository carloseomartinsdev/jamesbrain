"""Cenários conceituais I11.2 — fixtures de design, não produção."""

from __future__ import annotations

from pke.design.behavioral import (
    BehavioralPattern,
    ClarificationPolicy,
    ContextualHypothesis,
    HypothesisStatus,
    InformationValueProfile,
)
from pke.design.semantic_frame import (
    DimensionSlot,
    EnrichmentState,
    EpistemicMetadata,
    EpistemicStatus,
    EvidenceSourceKind,
    Occurrence,
    SemanticFrame,
    SlotStatus,
)
from pke.design.temporal_knowledge import (
    RelationToNow,
    TemporalAspect,
    TemporalKnowledge,
    TemporalUnknownReason,
)


def scenario_a_oil_change() -> Occurrence:
    frame = SemanticFrame(
        actor=DimensionSlot(status=SlotStatus.KNOWN, concept_keys=["entity.person"]),
        action=DimensionSlot(status=SlotStatus.KNOWN, concept_keys=["action.replace"]),
        subject=DimensionSlot(status=SlotStatus.KNOWN, concept_keys=["entity.automobile"], surface_forms=["Corolla"]),
        event_type=DimensionSlot(status=SlotStatus.KNOWN, concept_keys=["event.vehicle_maintenance"]),
        time=DimensionSlot(status=SlotStatus.KNOWN, surface_forms=["hoje"]),
        value=DimensionSlot(status=SlotStatus.MISSING),
        quantity=DimensionSlot(status=SlotStatus.MISSING, concept_keys=["attribute.mileage"]),
        place=DimensionSlot(status=SlotStatus.UNKNOWN),
    )
    temporal = TemporalKnowledge(
        relation_to_now=RelationToNow.PAST,
        aspect=TemporalAspect.COMPLETED,
        relative_time="today",
    )
    enrichment = EnrichmentState(
        known_dimensions=["actor", "action", "subject", "event_type", "time"],
        unknown_dimensions=["place", "value", "quantity"],
        high_value_missing=["quantity"],
        blocking_missing=[],
    )
    return Occurrence(frame=frame, temporal=temporal, enrichment=enrichment)


def scenario_b_bought_oranges() -> Occurrence:
    frame = SemanticFrame(
        action=DimensionSlot(status=SlotStatus.KNOWN, concept_keys=["action.buy"]),
        event_type=DimensionSlot(status=SlotStatus.KNOWN, concept_keys=["event.purchase"]),
        object=DimensionSlot(status=SlotStatus.KNOWN, surface_forms=["laranja"]),
    )
    temporal = TemporalKnowledge(
        relation_to_now=RelationToNow.PAST,
        aspect=TemporalAspect.COMPLETED,
        tense_evidence="pretérito perfeito: comprei",
        unknown_reason=TemporalUnknownReason.NOT_PROVIDED,
    )
    return Occurrence(
        frame=frame,
        temporal=temporal,
        enrichment=EnrichmentState(
            known_dimensions=["action", "object"],
            unknown_dimensions=["time_absolute", "place"],
            blocking_missing=[],
        ),
    )


def scenario_c_cardiologist_forgotten() -> Occurrence:
    frame = SemanticFrame(
        action=DimensionSlot(status=SlotStatus.KNOWN, concept_keys=["action.attend"]),
        event_type=DimensionSlot(status=SlotStatus.KNOWN, concept_keys=["event.appointment"]),
        object=DimensionSlot(status=SlotStatus.KNOWN, surface_forms=["cardiologista"], concept_keys=["role.provider"]),
    )
    temporal = TemporalKnowledge(
        relation_to_now=RelationToNow.PAST,
        aspect=TemporalAspect.COMPLETED,
        unknown_reason=TemporalUnknownReason.FORGOTTEN,
        uncertainty=0.9,
    )
    return Occurrence(
        frame=frame,
        temporal=temporal,
        epistemic=EpistemicMetadata(status=EpistemicStatus.UNCERTAIN, evidence_source=EvidenceSourceKind.EXPLICIT),
        enrichment=EnrichmentState(
            known_dimensions=["action", "event_type", "object"],
            unknown_dimensions=["time_absolute"],
            blocking_missing=[],
        ),
    )


def scenario_g_broken_fridge() -> Occurrence:
    frame = SemanticFrame(
        subject=DimensionSlot(status=SlotStatus.KNOWN, surface_forms=["geladeira"]),
        state_transition=DimensionSlot(
            status=SlotStatus.KNOWN,
            concept_keys=["state.broken"],
            surface_forms=["quebrada"],
        ),
        event_type=DimensionSlot(status=SlotStatus.NOT_APPLICABLE),
        action=DimensionSlot(status=SlotStatus.NOT_APPLICABLE),
    )
    return Occurrence(
        frame=frame,
        temporal=TemporalKnowledge(relation_to_now=RelationToNow.PRESENT),
        enrichment=EnrichmentState(
            known_dimensions=["subject", "state_transition"],
            blocking_missing=[],
        ),
    )


def scenario_e_behavioral_grocery() -> tuple[Occurrence, BehavioralPattern, ContextualHypothesis]:
    occ = Occurrence(
        frame=SemanticFrame(
            action=DimensionSlot(status=SlotStatus.KNOWN, concept_keys=["action.buy"]),
            object=DimensionSlot(status=SlotStatus.KNOWN, surface_forms=["arroz", "detergente"]),
        ),
        temporal=TemporalKnowledge(relation_to_now=RelationToNow.PAST, aspect=TemporalAspect.COMPLETED),
        enrichment=EnrichmentState(known_dimensions=["action", "object"], unknown_dimensions=["place"]),
    )
    pattern = BehavioralPattern(
        pattern_id="pat-shopping-household",
        conditions={"domain": "shopping", "category": "household"},
        prediction={"place": "Supermercado X"},
        support=18,
        confidence=0.86,
    )
    hypothesis = ContextualHypothesis(
        about_dimension="place",
        candidate_value="Supermercado X",
        confidence=0.82,
        basis="behavioral_pattern",
        pattern_id=pattern.pattern_id,
    )
    return occ, pattern, hypothesis


def oil_change_value_profiles() -> list[InformationValueProfile]:
    return [
        InformationValueProfile(dimension="vehicle", required_for_validity="high", future_utility="high"),
        InformationValueProfile(dimension="action", required_for_validity="high"),
        InformationValueProfile(dimension="time", information_value="high"),
        InformationValueProfile(dimension="mileage", future_utility="very_high", query_utility="high"),
        InformationValueProfile(dimension="amount", query_utility="high"),
        InformationValueProfile(dimension="workshop", information_value="medium"),
        InformationValueProfile(dimension="oil_brand", information_value="low"),
    ]


def select_mileage_question() -> str | None:
    policy = ClarificationPolicy()
    return policy.select_dimension(oil_change_value_profiles())
