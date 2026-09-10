"""I12.7 event routing hardening corpus — downstream preservation focus."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from pke.interpretation.semantic.models import (
    PrimitiveKind,
    SemanticEntityMention,
    SemanticProposal,
    SemanticTime,
)
from tests.multi_primitive_routing_hardening.corpus import (
    ANCHORS,
    MPCase,
    all_cases as mp_all_cases,
    mp1,
    mp2,
    mp3,
    mp4,
    mp5,
)


@dataclass(frozen=True)
class ERCase:
    case_id: str
    family: str
    factory: Callable[[], SemanticProposal]
    expect_event: bool
    expect_measurement: bool
    explicit_event_on_proposal: bool = True


def _happened() -> SemanticTime:
    return SemanticTime(occurrence_aspect="happened")


def ms18_i126() -> SemanticProposal:
    """Captured I12.6 MS18 proposal (baseline_deepseek_chat run 1)."""
    return SemanticProposal(
        raw_input="olhei o tanque e ele estava com 20 litros",
        utterance_kind="assert",
        subject=SemanticEntityMention(text="tanque", kind_hint="thing"),
        action_expression="olhei",
        event_expression="olhei o tanque",
        change_semantics=True,
        measurement_expression="20 litros",
        measurable_dimension_key="volume",
        measurement_numeric_value="20",
        measurement_unit="litros",
        measurement_semantics=True,
        primitive_hint="event",
        temporal=_happened(),
    )


I126_ARTIFACTS = Path(__file__).resolve().parents[2] / "docs" / "reports" / "i126_artifacts"


def load_i126_event_loss_proposals() -> list[ERCase]:
    """Derive regression set from I12.6 artifacts where RAW had Event (§37)."""
    path = I126_ARTIFACTS / "baseline_deepseek_chat.jsonl"
    if not path.exists():
        return []
    from pke.interpretation.semantic.multi_primitive_evidence import has_explicit_occurrence_evidence
    from pke.interpretation.transport.proposal_wire import WireSemanticProposal

    cases: list[ERCase] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        dump = row.get("proposal_dump")
        if not dump:
            continue
        case_id = row.get("case_id", "")
        if case_id in seen:
            continue
        try:
            proposal = WireSemanticProposal.model_validate(
                {"ir_kind": "semantic_proposal", "ir": dump}
            ).parsed_proposal()
        except Exception:
            continue
        if not has_explicit_occurrence_evidence(proposal):
            continue
        seen.add(case_id)
        cid = f"I126_{case_id}"
        cases.append(
            ERCase(
                case_id=cid,
                family="i126_captured",
                factory=lambda p=proposal: p.model_copy(deep=True),
                expect_event=True,
                expect_measurement=proposal.measurement_semantics,
                explicit_event_on_proposal=True,
            )
        )
    return cases


def _from_mp(case: MPCase) -> ERCase:
    expect_e = PrimitiveKind.EVENT in case.expected
    expect_m = PrimitiveKind.MEASUREMENT in case.expected
    explicit_e = case.explicit_on_proposal and expect_e
    return ERCase(
        case_id=case.case_id,
        family=case.family,
        factory=case.factory,
        expect_event=expect_e,
        expect_measurement=expect_m,
        explicit_event_on_proposal=explicit_e,
    )


def anchor_cases() -> list[ERCase]:
    anchors = [_from_mp(c) for c in ANCHORS]
    anchors.append(
        ERCase(
            case_id="MS18",
            family="anchor",
            factory=ms18_i126,
            expect_event=True,
            expect_measurement=True,
        )
    )
    return anchors


def all_cases() -> list[ERCase]:
    base = [_from_mp(c) for c in mp_all_cases()]
    extra = load_i126_event_loss_proposals()
    by_id = {c.case_id: c for c in base}
    for c in extra:
        if c.case_id not in by_id:
            by_id[c.case_id] = c
    return list(by_id.values())


def explicit_event_cases() -> list[ERCase]:
    return [c for c in all_cases() if c.explicit_event_on_proposal and c.expect_event]
