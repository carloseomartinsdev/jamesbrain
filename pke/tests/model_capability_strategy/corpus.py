"""I12.12 capability strategy corpus (>=220 deterministic fixtures)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from pke.interpretation.semantic.capability_strategy import CapabilityOutcome
from pke.interpretation.semantic.models import (
    SemanticEntityMention,
    SemanticProposal,
    SemanticTime,
)
from tests.multi_primitive_routing_hardening.corpus import mp1, mp2, mp3, mp4, mp5
from tests.structured_proposal_reliability.corpus import (
    meas_no_entity,
    mp1_missing_subject,
    mp1_with_subject,
)
from tests.semantic_resolution.fixtures import (
    pr1_fridge_broken,
    pr3_employment,
    pr4_color,
    pr5_door_open,
    sc4_replace_clutch,
)

ExpectedCap = Literal[
    "auto_execute",
    "partial_execute",
    "clarify",
    "safe_abstain",
    "invalid",
]


@dataclass(frozen=True)
class CapCase:
    case_id: str
    family: str
    factory: Callable[[], SemanticProposal]
    expected: ExpectedCap
    expect_clarification_slot: str | None = None
    notes: str = ""


def _happened() -> SemanticTime:
    return SemanticTime(occurrence_aspect="happened")


def _ent(text: str, kind: str = "thing") -> SemanticEntityMention:
    return SemanticEntityMention(text=text, kind_hint=kind)  # type: ignore[arg-type]


def _meas(**kwargs) -> SemanticProposal:
    base = dict(
        raw_input="measurement",
        measurement_semantics=True,
        primitive_hint="measurement",
        temporal=_happened(),
    )
    base.update(kwargs)
    return SemanticProposal(**base)


def _event(**kwargs) -> SemanticProposal:
    base = dict(
        raw_input="event",
        change_semantics=True,
        action_expression="fiz",
        event_expression="fiz algo",
        primitive_hint="event",
        temporal=_happened(),
    )
    base.update(kwargs)
    return SemanticProposal(**base)


def _state(**kwargs) -> SemanticProposal:
    base = dict(
        raw_input="state",
        condition_semantics=True,
        state_expression="aberto",
        primitive_hint="state",
        temporal=SemanticTime(occurrence_aspect="ongoing"),
    )
    base.update(kwargs)
    return SemanticProposal(**base)


def _relation(**kwargs) -> SemanticProposal:
    base = dict(
        raw_input="relation",
        link_semantics=True,
        relation_expression="trabalha em",
        primitive_hint="relation",
        temporal=_happened(),
    )
    base.update(kwargs)
    return SemanticProposal(**base)


def _attr(**kwargs) -> SemanticProposal:
    base = dict(
        raw_input="attribute",
        stable_property_semantics=True,
        attribute_expression="azul",
        primitive_hint="attribute",
        temporal=_happened(),
    )
    base.update(kwargs)
    return SemanticProposal(**base)


def build_i1212_corpus() -> list[CapCase]:
    cases: list[CapCase] = []

    # --- Fully / partially executable anchors ---
    cases.append(CapCase("AUTO_MP5", "auto", mp5, "auto_execute"))
    cases.append(CapCase("AUTO_COLOR", "auto", pr4_color, "auto_execute"))
    cases.append(CapCase("AUTO_CLUTCH", "auto", sc4_replace_clutch, "auto_execute"))
    cases.append(CapCase("PARTIAL_MP1", "partial", mp1, "partial_execute"))
    cases.append(CapCase("PARTIAL_MP2", "partial", mp2, "partial_execute"))
    cases.append(CapCase("PARTIAL_MP3", "partial", mp3, "partial_execute"))
    cases.append(CapCase("PARTIAL_MP4", "partial", mp4, "partial_execute"))
    cases.append(CapCase("PARTIAL_MP1_SUBJ", "partial", mp1_with_subject, "partial_execute"))

    # --- Detectable missing entity (CLARIFY) ---
    cases.append(
        CapCase(
            "CLARIFY_MP1_NULL_SUBJECT",
            "detectable_missing_entity",
            mp1_missing_subject,
            "clarify",
            expect_clarification_slot="measured_entity",
        )
    )
    cases.append(
        CapCase(
            "CLARIFY_MEAS_NO_ENTITY",
            "detectable_missing_entity",
            meas_no_entity,
            "clarify",
            expect_clarification_slot="measured_entity",
        )
    )

    for i in range(40):
        cases.append(
            CapCase(
                f"CLARIFY_MEAS_ENT_{i:02d}",
                "detectable_missing_entity",
                lambda i=i: _meas(
                    raw_input=f"leu {i}",
                    measurement_expression=f"{i}",
                    measurable_dimension_key="temperature",
                    measurement_numeric_value=str(i),
                    measurement_unit="C",
                ),
                "clarify",
                expect_clarification_slot="measured_entity",
            )
        )

    # --- Missing measurement dimension / value ---
    for i in range(15):
        cases.append(
            CapCase(
                f"CLARIFY_MEAS_DIM_{i:02d}",
                "detectable_missing_dimension",
                lambda i=i: _meas(
                    subject=_ent(f"sensor{i}"),
                    measurement_expression="valor",
                    measurement_numeric_value=str(10 + i),
                    # no measurable_dimension_key
                ),
                "clarify",
                expect_clarification_slot="measurement_dimension",
            )
        )
    for i in range(15):
        cases.append(
            CapCase(
                f"CLARIFY_MEAS_VAL_{i:02d}",
                "detectable_missing_dimension",
                lambda i=i: _meas(
                    subject=_ent(f"tanque{i}"),
                    measurement_expression="litros",
                    measurable_dimension_key="volume",
                    # no numeric value
                ),
                "clarify",
                expect_clarification_slot="measurement_value",
            )
        )

    # --- Relation missing endpoints ---
    for i in range(20):
        cases.append(
            CapCase(
                f"CLARIFY_REL_OBJ_{i:02d}",
                "detectable_missing_role",
                lambda i=i: _relation(
                    subject=_ent(f"pessoa{i}", "person"),
                    # object missing
                ),
                "clarify",
                expect_clarification_slot="relation_object",
            )
        )
    for i in range(20):
        cases.append(
            CapCase(
                f"CLARIFY_REL_SUBJ_{i:02d}",
                "detectable_missing_role",
                lambda i=i: _relation(
                    object=_ent(f"empresa{i}", "organization"),
                    # subject missing
                ),
                "clarify",
                expect_clarification_slot="relation_subject",
            )
        )

    # --- State / attribute incompleteness ---
    for i in range(12):
        cases.append(
            CapCase(
                f"STATE_INCOMPLETE_{i:02d}",
                "state_incomplete",
                lambda i=i: _state(
                    subject=_ent(f"porta{i}"),
                    state_expression="",  # empty value signal
                    condition_semantics=True,
                ),
                "clarify",  # may be clarify or abstain depending on persistability
                notes="state_value_gap",
            )
        )

    for i in range(12):
        cases.append(
            CapCase(
                f"ATTR_INCOMPLETE_{i:02d}",
                "attribute_incomplete",
                lambda i=i: _attr(
                    subject=_ent(f"carro{i}", "vehicle"),
                    stable_property_semantics=True,
                    attribute_expression="",
                ),
                "clarify",
                notes="attribute_dimension_gap",
            )
        )

    # --- Safe partial Event (low-value taxonomy) → SAFE_ABSTAIN ---
    for i in range(20):
        cases.append(
            CapCase(
                f"ABSTAIN_EVENT_PARTIAL_{i:02d}",
                "safe_partial_event",
                lambda i=i: _event(
                    subject=_ent(f"item{i}"),
                    action_expression=f"fiz{i}",
                    event_expression=f"fiz algo {i}",
                    # no resolvable canonical type expected
                ),
                "safe_abstain",
                notes="do_not_clarify_for_taxonomy",
            )
        )

    # --- Executable measurements with entity ---
    for i in range(20):
        cases.append(
            CapCase(
                f"AUTO_MEAS_{i:02d}",
                "auto",
                lambda i=i: _meas(
                    subject=_ent(f"sensorX{i}"),
                    measurement_expression=f"{20+i}C",
                    measurable_dimension_key="temperature",
                    measurement_numeric_value=str(20 + i),
                    measurement_unit="C",
                ),
                "auto_execute",
            )
        )

    # --- Relation complete ---
    for i in range(10):
        cases.append(
            CapCase(
                f"AUTO_REL_{i:02d}",
                "auto",
                lambda i=i: _relation(
                    subject=_ent(f"Alice{i}", "person"),
                    object=_ent(f"Acme{i}", "organization"),
                    relation_expression="trabalha em",
                ),
                "auto_execute",
            )
        )

    # --- Known good fixtures ---
    cases.append(CapCase("AUTO_FRIDGE", "auto", pr1_fridge_broken, "auto_execute"))
    cases.append(CapCase("AUTO_EMPLOY", "auto", pr3_employment, "auto_execute"))
    cases.append(CapCase("AUTO_DOOR", "auto", pr5_door_open, "auto_execute"))

    # --- Multiple missing slots: still one clarification (entity preferred) ---
    for i in range(8):
        cases.append(
            CapCase(
                f"MULTI_GAP_{i:02d}",
                "multiple_missing_slots",
                lambda i=i: _meas(
                    raw_input=f"multi {i}",
                    measurement_expression="x",
                    # missing entity AND dimension AND value
                ),
                "clarify",
                expect_clarification_slot="measured_entity",
                notes="one_high_value_question_only",
            )
        )

    # --- Undetectable omission: Measurement-only when Event was expected is
    #     not detectable from structured state alone → AUTO or whatever
    #     the proposal actually contains (no phantom Event clarify). ---
    for i in range(10):
        cases.append(
            CapCase(
                f"UNDETECT_MEAS_ONLY_{i:02d}",
                "undetectable_omission",
                lambda i=i: _meas(
                    subject=_ent(f"probe{i}"),
                    measurement_expression=f"{i}",
                    measurable_dimension_key="temperature",
                    measurement_numeric_value=str(i),
                ),
                "auto_execute",
                notes="engine_cannot_clarify_about_omitted_event",
            )
        )

    # --- Ambiguous entity surface (still clarify for missing entity, not invent) ---
    for i in range(8):
        cases.append(
            CapCase(
                f"AMBIG_ENTITY_GAP_{i:02d}",
                "ambiguous_entity",
                lambda i=i: _meas(
                    raw_input=f"marcou {i}",
                    measurement_expression=f"{50+i}",
                    measurable_dimension_key="temperature",
                    measurement_numeric_value=str(50 + i),
                ),
                "clarify",
                expect_clarification_slot="measured_entity",
            )
        )

    return cases


I1212_CORPUS = build_i1212_corpus()
