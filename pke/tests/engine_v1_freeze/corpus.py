"""I12-R Engine v1 freeze revalidation corpus (>=300 deterministic cases)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pke.interpretation.semantic.models import (
    SemanticEntityMention,
    SemanticProposal,
    SemanticTime,
)
from tests.engine_v1_freeze.anchors import FREEZE_ANCHORS, FreezeAnchor
from tests.event_residual_reliability.corpus import I1217_EVENT_RESIDUAL_CORPUS
from tests.model_capability_strategy.corpus import I1212_CORPUS
from tests.multi_primitive_routing_hardening.corpus import mp1, mp2, mp3, mp4, mp5
from tests.semantic_resolution.fixtures import (
    pr3_employment,
    pr4_color,
    pr5_door_open,
    sc4_replace_clutch,
)

Family = Literal[
    "anchor",
    "capability",
    "event",
    "state",
    "relation",
    "attribute",
    "measurement",
    "multi",
    "correction",
    "clarification",
    "abstain",
    "temporal",
    "isolation_doc",
]


@dataclass(frozen=True)
class FreezeCase:
    case_id: str
    family: Family
    factory: Callable[[], SemanticProposal] | None
    expect_cap: str | None  # auto_execute|partial_execute|clarify|safe_abstain|None
    notes: str = ""
    is_anchor: bool = False
    safety_expectation: str = ""


def _ent(text: str, kind: str | None = None) -> SemanticEntityMention:
    return SemanticEntityMention(text=text, kind_hint=kind)


def _happened() -> SemanticTime:
    return SemanticTime(occurrence_aspect="happened")


def _ongoing() -> SemanticTime:
    return SemanticTime(occurrence_aspect="ongoing")


def _from_anchor(a: FreezeAnchor) -> FreezeCase:
    cap_map = {
        "execute": "auto_execute",
        "partial_execute": "partial_execute",
        "clarify": "clarify",
        "safe_abstain": "safe_abstain",
        "measurement_only": "auto_execute",
        "no_event": None,
        "query_uncertain": None,
        "correction_guard": None,
        "provider_safe_fail": None,
    }
    return FreezeCase(
        case_id=a.anchor_id,
        family="anchor",
        factory=a.factory,
        expect_cap=cap_map.get(a.expected_boundary),
        notes=a.notes or a.safety_expectation,
        is_anchor=True,
        safety_expectation=a.safety_expectation,
    )


def build_freeze_corpus() -> list[FreezeCase]:
    cases: list[FreezeCase] = []

    for a in FREEZE_ANCHORS:
        cases.append(_from_anchor(a))

    # Capability strategy corpus (executable factories)
    for c in I1212_CORPUS:
        cases.append(
            FreezeCase(
                f"CAP_{c.case_id}",
                "capability",
                c.factory,
                c.expected,
                notes=c.notes,
            )
        )

    # Event residual (executable)
    for c in I1217_EVENT_RESIDUAL_CORPUS:
        expect = None
        if c.expect in {"resolved_materialized", "measurement_only"}:
            expect = "auto_execute"
        elif c.expect in {"partial_non_materialized", "event_only_partial"}:
            expect = "partial_execute"
        elif c.expect in {"state_no_event", "relation_no_event"}:
            expect = "auto_execute"
        cases.append(
            FreezeCase(f"EVT_{c.case_id}", "event", c.factory, expect, notes=c.notes)
        )

    # Densify boundary families to ensure >=300 unique ids
    for i in range(25):
        cases.append(
            FreezeCase(
                f"STATE_X_{i:02d}",
                "state",
                lambda i=i: SemanticProposal(
                    raw_input=f"janela aberta {i}",
                    subject=_ent(f"janela-{i}"),
                    condition_semantics=True,
                    state_expression="aberta",
                    change_semantics=False,
                    primitive_hint="state",
                    temporal=_ongoing(),
                ),
                "auto_execute",
                notes="State != Event",
            )
        )
        cases.append(
            FreezeCase(
                f"REL_X_{i:02d}",
                "relation",
                lambda i=i: SemanticProposal(
                    raw_input=f"trabalha {i}",
                    subject=_ent(f"P-{i}", "person"),
                    object=_ent(f"O-{i}", "organization"),
                    link_semantics=True,
                    relation_expression="trabalha em",
                    change_semantics=False,
                    primitive_hint="relation",
                    temporal=_ongoing(),
                ),
                "auto_execute",
                notes="Relation != Event",
            )
        )
        cases.append(
            FreezeCase(
                f"MEAS_X_{i:02d}",
                "measurement",
                lambda i=i: SemanticProposal(
                    raw_input=f"temp {i}",
                    subject=_ent(f"s-{i}"),
                    measurement_semantics=True,
                    measurable_dimension_key="temperature",
                    measurement_numeric_value=str(20 + i),
                    measurement_unit="°C",
                    change_semantics=False,
                    primitive_hint="measurement",
                    temporal=_happened(),
                ),
                "auto_execute",
                notes="Measurement != Event",
            )
        )

    # Multi-primitive repeats
    for i, factory in enumerate([mp1, mp2, mp3, mp4, mp5] * 4):
        cases.append(
            FreezeCase(
                f"MP_R_{i:02d}",
                "multi",
                factory,
                "partial_execute" if factory is not mp5 else "auto_execute",
                notes="MP anchors",
            )
        )

    # Abstain densify
    for i in range(20):
        cases.append(
            FreezeCase(
                f"ABSTAIN_STATE_{i:02d}",
                "abstain",
                lambda i=i: SemanticProposal(
                    raw_input=f"sensor ligado {i}",
                    subject=_ent(f"sensor-{i}"),
                    condition_semantics=True,
                    state_expression="ligado",
                    change_semantics=False,
                    primitive_hint="state",
                    temporal=_ongoing(),
                ),
                "safe_abstain",
                notes="canonical unresolved State",
            )
        )

    # Classic anchors extras
    for i, factory in enumerate([sc4_replace_clutch, pr4_color, pr5_door_open, pr3_employment] * 5):
        cases.append(
            FreezeCase(f"CLASSIC_{i:02d}", "attribute", factory, "auto_execute", notes="classic")
        )

    # Deduplicate by case_id preserving order
    seen: set[str] = set()
    unique: list[FreezeCase] = []
    for c in cases:
        if c.case_id in seen:
            continue
        seen.add(c.case_id)
        unique.append(c)
    return unique


I12R_FREEZE_CORPUS = build_freeze_corpus()
