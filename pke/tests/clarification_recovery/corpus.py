"""I12.13 clarification recovery fixtures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from pke.application.pending_operation import PendingSemanticOperation
from pke.interpretation.semantic.models import (
    SemanticEntityMention,
    SemanticProposal,
    SemanticTime,
)
from tests.structured_proposal_reliability.corpus import mp1_missing_subject, mp1_with_subject


Expected = Literal[
    "resolved_committed",
    "remains_unresolved",
    "unsupported_slot",
    "rejected",
    "idempotent_replay",
]


@dataclass(frozen=True)
class RecoveryCase:
    case_id: str
    family: str
    pending_factory: Callable[[], PendingSemanticOperation]
    answer: str
    expected: Expected
    notes: str = ""


def _happened() -> SemanticTime:
    return SemanticTime(occurrence_aspect="happened")


def _ent(text: str) -> SemanticEntityMention:
    return SemanticEntityMention(text=text, kind_hint="thing")


def pending_from_proposal(
    proposal: SemanticProposal,
    *,
    slot: str = "measured_entity",
    kind: str = "entity_reference",
    primitive: str = "measurement",
    reason: str = "missing_entity",
) -> PendingSemanticOperation:
    return PendingSemanticOperation(
        originating_raw=proposal.raw_input,
        proposal_dump=proposal.model_dump(),
        missing_slot=slot,
        expected_answer_kind=kind,  # type: ignore[arg-type]
        primitive=primitive,
        reason=reason,
        question_key="clarify.entity.which_one",
    )


def mp1_pending() -> PendingSemanticOperation:
    return pending_from_proposal(mp1_missing_subject())


def relation_missing_object() -> SemanticProposal:
    return SemanticProposal(
        raw_input="trabalha em",
        subject=_ent("Alice"),
        link_semantics=True,
        relation_expression="trabalha em",
        primitive_hint="relation",
        temporal=_happened(),
    )


def relation_missing_subject() -> SemanticProposal:
    return SemanticProposal(
        raw_input="trabalha em Acme",
        object=_ent("Acme"),
        link_semantics=True,
        relation_expression="trabalha em",
        primitive_hint="relation",
        temporal=_happened(),
    )


def build_i1213_corpus() -> list[RecoveryCase]:
    cases: list[RecoveryCase] = []

    # MP1 anchors
    cases.append(
        RecoveryCase(
            "MP1_VALID",
            "mp1",
            mp1_pending,
            "O tanque do Corolla.",
            "resolved_committed",
        )
    )
    cases.append(
        RecoveryCase(
            "MP1_TEMPERATURA",
            "mp1",
            mp1_pending,
            "temperatura",
            "resolved_committed",
        )
    )
    cases.append(
        RecoveryCase(
            "MP1_IRRELEVANT_TEMPORAL",
            "mp1_irrelevant",
            mp1_pending,
            "foi ontem",
            "remains_unresolved",
        )
    )
    cases.append(
        RecoveryCase(
            "MP1_EMPTY",
            "mp1_irrelevant",
            mp1_pending,
            "   ",
            "remains_unresolved",
        )
    )
    cases.append(
        RecoveryCase(
            "MP1_EXTRA_CONTENT",
            "mp1",
            mp1_pending,
            "o Corolla, ontem",
            "resolved_committed",
            notes="only entity head consumed",
        )
    )

    for i in range(80):
        cases.append(
            RecoveryCase(
                f"MEAS_ENT_{i:02d}",
                "measurement_entity",
                lambda i=i: pending_from_proposal(
                    SemanticProposal(
                        raw_input=f"leu {i}",
                        measurement_expression=f"{i}",
                        measurable_dimension_key="temperature",
                        measurement_numeric_value=str(10 + i),
                        measurement_unit="C",
                        measurement_semantics=True,
                        primitive_hint="measurement",
                        temporal=_happened(),
                    )
                ),
                f"sensor {i}",
                "resolved_committed",
            )
        )

    for i in range(40):
        cases.append(
            RecoveryCase(
                f"REL_OBJ_{i:02d}",
                "relation_object",
                lambda i=i: pending_from_proposal(
                    relation_missing_object(),
                    slot="relation_object",
                    primitive="relation",
                    reason="missing_relation_object",
                ),
                f"Empresa {i}",
                "remains_unresolved",
                notes="entity filled but relation identity still incomplete",
            )
        )

    for i in range(40):
        cases.append(
            RecoveryCase(
                f"REL_SUBJ_{i:02d}",
                "relation_subject",
                lambda i=i: pending_from_proposal(
                    relation_missing_subject(),
                    slot="relation_subject",
                    primitive="relation",
                    reason="missing_relation_subject",
                ),
                f"Pessoa {i}",
                "remains_unresolved",
                notes="entity filled but relation identity still incomplete",
            )
        )

    for i in range(20):
        cases.append(
            RecoveryCase(
                f"IRRELEVANT_{i:02d}",
                "irrelevant",
                mp1_pending,
                ["foi ontem", "hoje", "amanhã", "agora"][i % 4],
                "remains_unresolved",
            )
        )

    for i in range(15):
        # state_dimension remains unsupported in Engine v1 (I12.14).
        cases.append(
            RecoveryCase(
                f"UNSUPPORTED_DIM_{i:02d}",
                "unsupported",
                lambda i=i: pending_from_proposal(
                    mp1_missing_subject(),
                    slot="state_dimension",
                    kind="dimension",
                    reason="missing_state_dimension",
                ),
                "operacional",
                "unsupported_slot",
            )
        )

    for i in range(10):
        cases.append(
            RecoveryCase(
                f"UNSUPPORTED_CORR_{i:02d}",
                "unsupported",
                lambda: pending_from_proposal(
                    mp1_missing_subject(),
                    slot="correction_target",
                    kind="correction_target",
                    reason="ambiguous_correction_target",
                ),
                "o último",
                "unsupported_slot",
            )
        )

    # Controls: already complete proposal shouldn't be "clarified" via wrong path —
    # recovery still fills measured_entity if pending claims that slot (idempotent surface).
    cases.append(
        RecoveryCase(
            "CONTROL_WITH_SUBJECT",
            "control",
            lambda: pending_from_proposal(mp1_with_subject()),
            "temperatura",
            "resolved_committed",
            notes="slot overwrite of target only",
        )
    )

    for i in range(30):
        cases.append(
            RecoveryCase(
                f"STATE_ENT_{i:02d}",
                "state_entity",
                lambda i=i: pending_from_proposal(
                    SemanticProposal(
                        raw_input=f"porta {i}",
                        condition_semantics=True,
                        state_expression="aberta",
                        primitive_hint="state",
                        temporal=SemanticTime(occurrence_aspect="ongoing"),
                    ),
                    slot="state_entity",
                    primitive="state",
                    reason="missing_entity",
                ),
                f"porta {i}",
                "remains_unresolved",
                notes="MVP may not materialize state from entity fill alone",
            )
        )

    return cases


I1213_CORPUS = build_i1213_corpus()
