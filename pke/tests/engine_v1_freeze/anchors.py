"""I12-R Engine v1 freeze anchors F01–F50 (hand-audited)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from pke.interpretation.semantic.models import (
    SemanticEntityMention,
    SemanticProposal,
    SemanticTime,
)
from tests.multi_primitive_routing_hardening.corpus import mp1, mp2, mp3, mp4, mp5
from tests.semantic_resolution.fixtures import (
    pr3_employment,
    pr4_color,
    pr5_door_open,
    sc4_replace_clutch,
)
from tests.structured_proposal_reliability.corpus import (
    correction_unresolved_target,
    mp1_missing_subject,
)

ExpectedBoundary = Literal[
    "execute",
    "partial_execute",
    "clarify",
    "safe_abstain",
    "no_event",
    "measurement_only",
    "query_uncertain",
    "correction_guard",
    "provider_safe_fail",
]


@dataclass(frozen=True)
class FreezeAnchor:
    anchor_id: str
    family: str
    factory: Callable[[], SemanticProposal] | None
    expected_boundary: ExpectedBoundary
    safety_expectation: str
    notes: str = ""
    utterance: str = ""


def _ent(text: str, kind: str | None = None) -> SemanticEntityMention:
    return SemanticEntityMention(text=text, kind_hint=kind)


def _happened() -> SemanticTime:
    return SemanticTime(occurrence_aspect="happened")


def _ongoing() -> SemanticTime:
    return SemanticTime(occurrence_aspect="ongoing")


def build_freeze_anchors() -> list[FreezeAnchor]:
    """F01–F50 executable hand-audited freeze anchors."""
    a: list[FreezeAnchor] = []

    def add(
        fid: str,
        family: str,
        factory: Callable[[], SemanticProposal] | None,
        boundary: ExpectedBoundary,
        safety: str,
        notes: str = "",
        utterance: str = "",
    ) -> None:
        a.append(FreezeAnchor(fid, family, factory, boundary, safety, notes, utterance))

    # --- Core execute / partial ---
    add("F01", "execute", sc4_replace_clutch, "execute", "no false canon; Event materializes")
    add("F02", "execute", pr4_color, "execute", "Attribute executes; not State")
    add("F03", "execute", pr5_door_open, "execute", "State executes; not Event")
    add("F04", "execute", pr3_employment, "execute", "Relation executes; not Event")
    add("F05", "execute", mp5, "measurement_only", "MP5 Measurement only; no false Event")
    add("F06", "multi", mp1, "partial_execute", "Event partial + Measurement may commit")
    add("F07", "multi", mp2, "partial_execute", "Event+Measurement preserved")
    add("F08", "multi", mp3, "partial_execute", "Event+Measurement preserved")
    add("F09", "multi", mp4, "partial_execute", "Event+Measurement preserved")
    add(
        "F10",
        "clarify",
        mp1_missing_subject,
        "clarify",
        "missing entity → CLARIFY entity_reference; no invent",
    )

    # --- State / Relation / Event controls ---
    add(
        "F11",
        "state_control",
        lambda: SemanticProposal(
            raw_input="porta aberta",
            subject=_ent("porta"),
            condition_semantics=True,
            state_expression="aberta",
            change_semantics=False,
            primitive_hint="state",
            temporal=_ongoing(),
        ),
        "execute",
        "STATE_FALSE_CAUSAL_EVENT=0",
    )
    add(
        "F12",
        "relation_control",
        lambda: SemanticProposal(
            raw_input="Alice trabalha em Acme",
            subject=_ent("Alice", "person"),
            object=_ent("Acme", "organization"),
            link_semantics=True,
            relation_expression="trabalha em",
            change_semantics=False,
            primitive_hint="relation",
            temporal=_ongoing(),
        ),
        "execute",
        "RELATION_FALSE_START_EVENT=0",
    )
    add(
        "F13",
        "event_simple",
        lambda: SemanticProposal(
            raw_input="troquei a embreagem",
            subject=_ent("corolla", "vehicle"),
            object=_ent("embreagem"),
            action_expression="troquei a embreagem",
            event_expression="troquei a embreagem",
            change_semantics=True,
            primitive_hint="event",
            temporal=_happened(),
        ),
        "execute",
        "explicit Event preserved",
    )
    add(
        "F14",
        "event_partial",
        lambda: SemanticProposal(
            raw_input="olhei o tanque",
            action_expression="olhei",
            event_expression="olhei o tanque",
            change_semantics=True,
            primitive_hint="event",
            temporal=_happened(),
        ),
        "clarify",
        "partial Event not silently discarded",
    )
    add(
        "F15",
        "event_unresolved_canon",
        lambda: SemanticProposal(
            raw_input="finalizei o onboarding",
            subject=_ent("projeto"),
            action_expression="finalizei o onboarding",
            event_expression="finalizei o onboarding",
            change_semantics=True,
            primitive_hint="event",
            temporal=_happened(),
        ),
        "safe_abstain",
        "outside CORE → SAFE_ABSTAIN / safe partial; no fake canon",
    )

    # --- Canonical unresolved → abstain (not false clarify) ---
    add(
        "F16",
        "state_canon_unresolved",
        lambda: SemanticProposal(
            raw_input="dispositivo ligado",
            subject=_ent("dispositivo"),
            condition_semantics=True,
            state_expression="ligado",
            change_semantics=False,
            primitive_hint="state",
            temporal=_ongoing(),
        ),
        "safe_abstain",
        "state canonical unresolved → SAFE_ABSTAIN not false CLARIFY",
    )
    add(
        "F17",
        "relation_canon_unresolved",
        lambda: SemanticProposal(
            raw_input="Alice member of Acme",
            subject=_ent("Alice", "person"),
            object=_ent("Acme", "organization"),
            link_semantics=True,
            relation_expression="member of",
            change_semantics=False,
            primitive_hint="relation",
            temporal=_ongoing(),
        ),
        "safe_abstain",
        "relation type unresolved → SAFE_ABSTAIN not false endpoint CLARIFY",
    )

    # --- Correction ---
    add(
        "F18",
        "correction",
        correction_unresolved_target,
        "correction_guard",
        "Correction Guard; no false Event; ambiguous target safe",
    )
    add(
        "F19",
        "correction_control",
        lambda: SemanticProposal(
            raw_input="Corrigindo, era 36°C.",
            utterance_kind="correct",
            correction_semantics=True,
            correction_operation="replace",
            correction_target_kind="measurement",
            measurement_semantics=True,
            measurable_dimension_key="temperature",
            measurement_numeric_value="36",
            measurement_unit="°C",
            change_semantics=False,
            primitive_hint="measurement",
            temporal=_happened(),
        ),
        "correction_guard",
        "FALSE_EVENT_AS_CORRECTION=0",
    )

    # --- Measurement ---
    add(
        "F20",
        "measurement",
        lambda: SemanticProposal(
            raw_input="temperatura 37.5",
            subject=_ent("sensor"),
            measurement_semantics=True,
            measurable_dimension_key="temperature",
            measurement_numeric_value="37.5",
            measurement_unit="°C",
            change_semantics=False,
            primitive_hint="measurement",
            temporal=_happened(),
        ),
        "execute",
        "Measurement != Event/State/Attribute",
    )
    add(
        "F21",
        "measurement_no_entity",
        lambda: SemanticProposal(
            raw_input="deu 95",
            measurement_semantics=True,
            measurable_dimension_key="temperature",
            measurement_numeric_value="95",
            measurement_unit="°C",
            change_semantics=False,
            primitive_hint="measurement",
            temporal=_happened(),
        ),
        "clarify",
        "missing measured_entity → CLARIFY",
    )

    # --- Attribute ---
    add(
        "F22",
        "attribute",
        pr4_color,
        "execute",
        "Attribute != State; classification not Attribute",
    )

    # --- Clarification families ---
    add(
        "F23",
        "clarify_state_value",
        lambda: SemanticProposal(
            raw_input="porta ?",
            subject=_ent("porta"),
            condition_semantics=True,
            state_expression="",
            change_semantics=False,
            primitive_hint="state",
            temporal=_ongoing(),
        ),
        "clarify",
        "empty state_expression → CLARIFY state_value",
    )

    # --- Provider / retry documentation anchors (no factory) ---
    add(
        "F24",
        "provider",
        None,
        "provider_safe_fail",
        "invalid JSON after retry exhaustion → safe failure; no durable mutation",
        utterance="(provider malformed JSON)",
    )
    add(
        "F25",
        "provider",
        None,
        "provider_safe_fail",
        "timeout → retry ≤2 pre-commit; RETRY_DUPLICATE_COMMIT=0",
        utterance="(provider timeout)",
    )

    # --- Query temporal ---
    add(
        "F26",
        "query",
        None,
        "query_uncertain",
        "count=0 + temporal_membership_unknown ≠ automatic NO",
        utterance="já troquei isso?",
    )

    # --- Isolation ---
    add(
        "F27",
        "isolation",
        None,
        "safe_abstain",
        "WRONG_USER_MUTATION=0; CROSS_USER_KNOWLEDGE_LEAK=0",
        utterance="(cross-user write attempt)",
    )
    add(
        "F28",
        "isolation",
        None,
        "safe_abstain",
        "CROSS_CONVERSATION_RECOVERY=0",
        utterance="(cross-conversation clarification)",
    )

    # --- Undetectable omission ---
    add(
        "F29",
        "model_omission",
        None,
        "safe_abstain",
        "undetectable model omission → no invented semantics",
        utterance="(model omits Event signals)",
    )

    # --- More execute/partial density F30–F50 ---
    add("F30", "repeat_anchor", sc4_replace_clutch, "execute", "regression Event execute")
    add("F31", "repeat_anchor", pr4_color, "execute", "regression Attribute execute")
    add("F32", "repeat_anchor", pr5_door_open, "execute", "regression State execute")
    add("F33", "repeat_anchor", mp5, "measurement_only", "regression MP5")
    add("F34", "repeat_anchor", mp1, "partial_execute", "regression MP1 partial")

    add(
        "F35",
        "event_vs_state",
        lambda: SemanticProposal(
            raw_input="a porta está aberta",
            subject=_ent("porta"),
            condition_semantics=True,
            state_expression="aberta",
            change_semantics=False,
            action_expression=None,
            primitive_hint="state",
            temporal=_ongoing(),
        ),
        "execute",
        "observed State does not imply Event",
    )
    add(
        "F36",
        "event_vs_relation",
        lambda: SemanticProposal(
            raw_input="trabalha em",
            subject=_ent("Bob", "person"),
            object=_ent("Corp", "organization"),
            link_semantics=True,
            relation_expression="trabalha em",
            change_semantics=False,
            primitive_hint="relation",
            temporal=_ongoing(),
        ),
        "execute",
        "Relation assertion does not imply start Event",
    )
    add(
        "F37",
        "meas_vs_event",
        mp5,
        "measurement_only",
        "Measurement does not imply Event (MP5)",
    )
    add(
        "F38",
        "commit_independently",
        mp1,
        "partial_execute",
        "COMMIT_VALID_INDEPENDENTLY intact",
    )
    add(
        "F39",
        "raw_text",
        sc4_replace_clutch,
        "execute",
        "RAW_TEXT_REINTERPRETED_DOWNSTREAM=0",
    )
    add(
        "F40",
        "capability",
        mp1_missing_subject,
        "clarify",
        "CapabilityStrategy owns EXECUTE/CLARIFY/ABSTAIN",
    )

    # F41–F50: coverage of remaining families
    add(
        "F41",
        "temporal",
        lambda: SemanticProposal(
            raw_input="troquei ontem",
            subject=_ent("corolla", "vehicle"),
            object=_ent("óleo"),
            action_expression="troquei",
            event_expression="troquei o óleo",
            change_semantics=True,
            primitive_hint="event",
            temporal=SemanticTime(occurrence_aspect="happened"),
        ),
        "execute",
        "recorded_at != fact time; TIME-01",
    )
    add(
        "F42",
        "attr_multi_evidence",
        pr4_color,
        "execute",
        "same entity/dimension may have multiple evidence rows",
    )
    add(
        "F43",
        "state_dim_value",
        pr5_door_open,
        "execute",
        "State Dimension != State Value",
    )
    add(
        "F44",
        "relation_direction",
        pr3_employment,
        "execute",
        "subject/object direction preserved; no blind inverse",
    )
    add(
        "F45",
        "no_second_interpreter",
        None,
        "safe_abstain",
        "SECOND_INTERPRETER_COUNT=0",
        utterance="(authority audit)",
    )
    add(
        "F46",
        "execution_readiness",
        mp1_missing_subject,
        "clarify",
        "ExecutionReadiness remains readiness authority",
    )
    add(
        "F47",
        "clarification_recovery",
        mp1_missing_subject,
        "clarify",
        "ClarificationRecoveryService only recovery authority",
    )
    add(
        "F48",
        "unsupported_recovery",
        None,
        "safe_abstain",
        "correction_target/temporal/state_dimension/measurement_value = POST_V1 unsupported",
        utterance="(unsupported clarification family)",
    )
    add(
        "F49",
        "idempotency",
        None,
        "safe_abstain",
        "CLARIFICATION_DUPLICATE_COMMIT=0",
        utterance="(clarification replay)",
    )
    add(
        "F50",
        "product_boundary",
        None,
        "safe_abstain",
        "Product must not override EXECUTE/CLARIFY/ABSTAIN or expose internal IR",
        utterance="(product handoff)",
    )

    assert len(a) == 50, len(a)
    assert [x.anchor_id for x in a] == [f"F{i:02d}" for i in range(1, 51)]
    return a


FREEZE_ANCHORS = build_freeze_anchors()
