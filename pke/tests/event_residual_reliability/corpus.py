"""I12.17 Event residual reliability — focused deterministic corpus (>=120)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from pke.interpretation.semantic.models import (
    SemanticEntityMention,
    SemanticProposal,
    SemanticTime,
)
from tests.event_partial_semantics.corpus import (
    ANCHOR_CASES,
    mp1,
    mp2,
    mp3,
    mp4,
    mp5,
)
from tests.event_routing_hardening.corpus import ms18_i126
from tests.semantic_resolution.fixtures import sc4_replace_clutch
from tests.structured_proposal_reliability.corpus import (
    event_safe_partial,
    mp1_missing_subject,
    mp1_with_subject,
)

Expect = Literal[
    "partial_non_materialized",
    "resolved_materialized",
    "measurement_only",
    "event_only_partial",
    "no_event",
    "state_no_event",
    "relation_no_event",
]


@dataclass(frozen=True)
class ResidualCase:
    case_id: str
    family: str
    factory: Callable[[], SemanticProposal]
    expect: Expect
    notes: str = ""


def _ent(text: str, kind: str | None = None) -> SemanticEntityMention:
    return SemanticEntityMention(text=text, kind_hint=kind)


def _happened() -> SemanticTime:
    return SemanticTime(occurrence_aspect="happened")


def _ongoing() -> SemanticTime:
    return SemanticTime(occurrence_aspect="ongoing")


def build_corpus() -> list[ResidualCase]:
    cases: list[ResidualCase] = []

    # Mandatory anchors (repeated for residual density)
    anchors = [
        ("MP1", mp1, "partial_non_materialized"),
        ("MP2", mp2, "partial_non_materialized"),
        ("MP3", mp3, "partial_non_materialized"),
        ("MP4", mp4, "partial_non_materialized"),
        ("MP5", mp5, "measurement_only"),
        ("MS18", ms18_i126, "partial_non_materialized"),
        ("MP1_MISS_SUBJ", mp1_missing_subject, "partial_non_materialized"),
        ("MP1_WITH_SUBJ", mp1_with_subject, "partial_non_materialized"),
        ("EVT_SAFE_PARTIAL", event_safe_partial, "event_only_partial"),
        ("SC4", sc4_replace_clutch, "resolved_materialized"),
    ]
    for name, factory, expect in anchors:
        for j in range(3):
            cases.append(
                ResidualCase(f"{name}_R{j}", "anchor", factory, expect)  # type: ignore[arg-type]
            )

    # From I12.7.1 ANCHOR_CASES once more
    for ac in ANCHOR_CASES:
        cases.append(ResidualCase(f"A_{ac.case_id}", "anchor_import", ac.factory, ac.expect))  # type: ignore[arg-type]

    # Explicit simple Event (resolved maintenance)
    for i in range(15):
        cases.append(
            ResidualCase(
                f"SIMPLE_EVT_{i:02d}",
                "simple_event",
                lambda i=i: SemanticProposal(
                    raw_input=f"troquei a embreagem {i}",
                    subject=_ent("corolla", "vehicle"),
                    object=_ent("embreagem"),
                    action_expression="troquei a embreagem",
                    event_expression="troquei a embreagem",
                    change_semantics=True,
                    primitive_hint="event",
                    temporal=_happened(),
                ),
                "resolved_materialized",
            )
        )

    # Partial Event missing entity
    for i in range(12):
        cases.append(
            ResidualCase(
                f"PARTIAL_NOENT_{i:02d}",
                "partial_event",
                lambda i=i: SemanticProposal(
                    raw_input=f"olhei o tanque {i}",
                    action_expression="olhei",
                    event_expression="olhei o tanque",
                    change_semantics=True,
                    primitive_hint="event",
                    temporal=_happened(),
                ),
                "event_only_partial",
            )
        )

    # State → no Event
    for i in range(12):
        cases.append(
            ResidualCase(
                f"STATE_CTRL_{i:02d}",
                "state_control",
                lambda i=i: SemanticProposal(
                    raw_input=f"porta aberta {i}",
                    subject=_ent(f"porta-{i}"),
                    condition_semantics=True,
                    state_expression="aberta",
                    change_semantics=False,
                    primitive_hint="state",
                    temporal=_ongoing(),
                ),
                "state_no_event",
            )
        )

    # Relation → no Event
    for i in range(12):
        cases.append(
            ResidualCase(
                f"REL_CTRL_{i:02d}",
                "relation_control",
                lambda i=i: SemanticProposal(
                    raw_input=f"trabalha em {i}",
                    subject=_ent(f"Alice-{i}", "person"),
                    object=_ent(f"Acme-{i}", "organization"),
                    link_semantics=True,
                    relation_expression="trabalha em",
                    change_semantics=False,
                    primitive_hint="relation",
                    temporal=_ongoing(),
                ),
                "relation_no_event",
            )
        )

    # Measurement-only extras (MP5 class)
    for i in range(12):
        cases.append(
            ResidualCase(
                f"MEAS_ONLY_{i:02d}",
                "measurement_only",
                lambda i=i: SemanticProposal(
                    raw_input=f"temperatura 37.5 {i}",
                    subject=_ent(f"sensor-{i}"),
                    measurement_semantics=True,
                    measurable_dimension_key="temperature",
                    measurement_numeric_value="37.5",
                    measurement_unit="°C",
                    change_semantics=False,
                    primitive_hint="measurement",
                    temporal=_happened(),
                ),
                "measurement_only",
            )
        )

    # Correction boundary — no Event invent
    for i in range(8):
        cases.append(
            ResidualCase(
                f"CORR_CTRL_{i:02d}",
                "correction_control",
                lambda i=i: SemanticProposal(
                    raw_input=f"Corrigindo, li errado: era 36°C. #{i}",
                    utterance_kind="correct",
                    correction_semantics=True,
                    correction_operation="replace",
                    correction_target_kind="measurement",
                    measurement_expression="36°C",
                    measurable_dimension_key="temperature",
                    measurement_numeric_value="36",
                    measurement_unit="°C",
                    measurement_semantics=True,
                    change_semantics=False,
                    primitive_hint="measurement",
                    temporal=_happened(),
                ),
                "no_event",
                notes="Correction Guard path; must not invent Event",
            )
        )

    # Unresolved canonical Event category (expression outside CORE → safe partial)
    for i in range(8):
        cases.append(
            ResidualCase(
                f"EVT_UNRES_CANON_{i:02d}",
                "canonical_unresolved",
                lambda i=i: SemanticProposal(
                    raw_input=f"finalizei o onboarding #{i}",
                    subject=_ent(f"projeto-{i}"),
                    action_expression="finalizei o onboarding",
                    event_expression="finalizei o onboarding",
                    change_semantics=True,
                    primitive_hint="event",
                    temporal=_happened(),
                ),
                "event_only_partial",
                notes="Outside frozen CORE event types → safe partial, not fake canon",
            )
        )

    # Event vs Measurement: explicit Event + Measurement both present (sibling)
    for i in range(6):
        cases.append(
            ResidualCase(
                f"EVT_MEAS_SIB_{i:02d}",
                "event_measurement_sibling",
                lambda i=i: SemanticProposal(
                    raw_input=f"medi o motor e deu 90 #{i}",
                    subject=_ent(f"motor-{i}"),
                    action_expression="medi",
                    event_expression="medi o motor",
                    change_semantics=True,
                    measurement_semantics=True,
                    measurable_dimension_key="temperature",
                    measurement_numeric_value="90",
                    measurement_unit="°C",
                    primitive_hint="event",
                    temporal=_happened(),
                ),
                "partial_non_materialized",
                notes="Event category may be unresolved; Measurement may commit independently",
            )
        )

    return cases


I1217_EVENT_RESIDUAL_CORPUS = build_corpus()
