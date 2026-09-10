"""I12.11 scoring — evaluation only. Does not complete missing proposal slots."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pke.interpretation.models import IngestIR, IngestIntent, QueryIR
from pke.interpretation.semantic.execution_readiness import (
    PrimitiveExecutionStatus,
    ProposalExecutionOutcome,
)
from pke.interpretation.semantic.models import PrimitiveKind, SemanticProposal
from pke.interpretation.semantic.multi_primitive_evidence import has_explicit_occurrence_evidence
from pke.interpretation.semantic.router import collect_assertions
from tests.engine_v1_baseline.corpus import EngineCase


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").casefold())


def _mention_in_utterance(text: str | None, utterance: str) -> bool:
    if not text or not text.strip():
        return False
    t = _norm(text)
    u = _norm(utterance)
    if t in u:
        return True
    # Allow trivial articles stripped
    for prefix in ("o ", "a ", "os ", "as "):
        if t.startswith(prefix) and t[len(prefix) :] in u:
            return True
    return False


_PRONOUNS = frozenset({"eu", "ele", "ela", "eles", "elas", "isso", "isto", "aquilo", "alguém"})


def invented_required_information(case: EngineCase, proposal: SemanticProposal | None) -> list[str]:
    """Unsupported fillers — evaluation compares proposal slots to utterance surface."""
    if proposal is None:
        return []
    flags: list[str] = []
    for ent, label in (
        (proposal.subject, "invented_subject"),
        (proposal.object, "invented_object"),
    ):
        text = (ent.text if ent else None) or ""
        token = _norm(text)
        if not token or token in _PRONOUNS or len(token) < 3:
            continue
        if not _mention_in_utterance(text, case.utterance):
            flags.append(label)
    return flags


def expected_completeness_slots(case: EngineCase) -> list[str]:
    prim = case.expected_primitive
    slots: list[str] = []
    if prim in {"measurement", "multi"}:
        slots.extend(["measurement_entity", "measurement_dimension", "measurement_value"])
    if prim in {"event", "multi"}:
        slots.append("event_occurrence")
    if prim == "relation":
        slots.extend(["relation_subject", "relation_object"])
    if prim == "state":
        slots.append("state_subject")
    if prim == "attribute":
        slots.append("attribute_subject")
    return slots


def observed_slots(proposal: SemanticProposal | None) -> set[str]:
    if proposal is None:
        return set()
    found: set[str] = set()
    entity = proposal.subject or proposal.object or proposal.context
    if entity and (entity.text or "").strip():
        found.add("measurement_entity")
        found.add("state_subject")
        found.add("attribute_subject")
        found.add("relation_subject")
    if proposal.object and (proposal.object.text or "").strip():
        found.add("relation_object")
    if proposal.measurable_dimension_key:
        found.add("measurement_dimension")
    if proposal.measurement_numeric_value:
        found.add("measurement_value")
    if has_explicit_occurrence_evidence(proposal):
        found.add("event_occurrence")
    return found


@dataclass
class CompletenessScore:
    expected_slots: tuple[str, ...] = ()
    present_correct: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    invented: tuple[str, ...] = ()

    @property
    def precision(self) -> float | None:
        filled = len(self.present_correct) + len(self.invented)
        if not filled:
            return None
        return len(self.present_correct) / filled

    @property
    def recall(self) -> float | None:
        if not self.expected_slots:
            return None
        return len(self.present_correct) / len(self.expected_slots)


def score_completeness(case: EngineCase, proposal: SemanticProposal | None) -> CompletenessScore:
    expected = tuple(expected_completeness_slots(case))
    obs = observed_slots(proposal)
    invented = tuple(invented_required_information(case, proposal))
    present = []
    missing = []
    for slot in expected:
        if slot in obs:
            # entity slots must not be invented
            if slot.endswith("entity") or slot.endswith("subject") or slot.endswith("object"):
                if invented:
                    # still present structurally; precision penalizes invented separately
                    present.append(slot)
                else:
                    present.append(slot)
            else:
                present.append(slot)
        else:
            missing.append(slot)
    return CompletenessScore(
        expected_slots=expected,
        present_correct=tuple(present),
        missing=tuple(missing),
        invented=invented,
    )


def useful_capture(
    case: EngineCase,
    *,
    ir,
    outcome,
    error: str | None,
) -> bool:
    """Committed expected materializable knowledge. Abstention is not capture."""
    if error and error.startswith("acceptance_guard:"):
        return False
    if error and error.startswith("semantic_resolution:execution_incomplete"):
        return False
    if ir is None:
        return False
    if case.expected_safe_abstention or case.expected_primitive == "unknown":
        return False
    if case.expected_intent == "query":
        return isinstance(ir, QueryIR)
    if case.expected_intent == "correct":
        return isinstance(ir, IngestIR) and ir.intent is IngestIntent.CORRECT
    if isinstance(ir, QueryIR):
        return False
    if case.expected_primitive == "measurement":
        return ir.measurement is not None
    if case.expected_primitive == "multi":
        return ir.measurement is not None
    if case.expected_primitive == "event":
        return ir.event is not None
    if case.expected_primitive == "state":
        return ir.state is not None
    if case.expected_primitive == "relation":
        return ir.relation is not None
    if case.expected_primitive == "attribute":
        return ir.attribute is not None
    return False


def safe_handled(
    *,
    capture: bool,
    error: str | None,
    post_s4: bool,
    invented: bool,
    false_correction_accepted: bool,
) -> bool:
    if post_s4 or invented or false_correction_accepted:
        return False
    if capture:
        return True
    if error is None:
        return True
    if error.startswith("semantic_resolution:execution_incomplete"):
        return True
    if error.startswith("acceptance_guard:"):
        return True
    if error.startswith("proposal_semantics:"):
        return True
    return False


def execution_ready_flag(readiness) -> bool:
    return readiness.outcome in {
        ProposalExecutionOutcome.VALID_EXECUTABLE,
        ProposalExecutionOutcome.VALID_PARTIALLY_EXECUTABLE,
    }


def primitive_family_status(case: EngineCase, proposal: SemanticProposal | None, readiness) -> str:
    prim = case.expected_primitive
    if proposal is None:
        return "omitted"
    kinds = {f.primitive for f in collect_assertions(proposal)}
    mapping = {
        "event": PrimitiveKind.EVENT,
        "state": PrimitiveKind.STATE,
        "relation": PrimitiveKind.RELATION,
        "attribute": PrimitiveKind.ATTRIBUTE,
        "measurement": PrimitiveKind.MEASUREMENT,
        "multi": PrimitiveKind.EVENT,
    }
    kind = mapping.get(prim or "")
    if kind is None:
        return "n/a"
    if kind not in kinds and prim != "multi":
        if prim == "measurement" and PrimitiveKind.MEASUREMENT in kinds:
            pass
        else:
            return "omitted"
    if prim == "multi":
        has_e = PrimitiveKind.EVENT in kinds
        has_m = PrimitiveKind.MEASUREMENT in kinds
        if not has_e and not has_m:
            return "omitted"
    for item in readiness.primitives:
        if item.primitive == kind or (
            prim == "measurement" and item.primitive is PrimitiveKind.MEASUREMENT
        ):
            if item.status is PrimitiveExecutionStatus.READY:
                return "correct"
            if item.status is PrimitiveExecutionStatus.SAFE_PARTIAL_NON_MATERIALIZABLE:
                return "correct" if prim == "event" else "incomplete"
            if item.status is PrimitiveExecutionStatus.INCOMPLETE_REQUIRED_INFORMATION:
                return "incomplete"
            return "unsafe"
    if prim == "multi":
        statuses = {p.primitive: p.status for p in readiness.primitives}
        m = statuses.get(PrimitiveKind.MEASUREMENT)
        if m is PrimitiveExecutionStatus.READY:
            return "correct"
        if m is PrimitiveExecutionStatus.INCOMPLETE_REQUIRED_INFORMATION:
            return "incomplete"
    return "incomplete"
