"""I12.7.1 partial Event semantics corpus."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from pke.interpretation.semantic.models import PrimitiveKind, SemanticProposal
from tests.event_routing_hardening.corpus import ms18_i126
from tests.multi_primitive_routing_hardening.corpus import (
    ANCHORS,
    CAPTURED,
    all_cases as mp_all_cases,
    mp1,
    mp2,
    mp3,
    mp4,
    mp5,
    _attr,
    _e_only,
    _em,
    _m_only,
    _rel,
    _state,
)
from tests.semantic_resolution.fixtures import sc4_replace_clutch

ExpectKind = Literal[
    "partial_non_materialized",
    "resolved_materialized",
    "measurement_only",
    "event_only_partial",
    "event_only_resolved",
    "no_event",
]


@dataclass(frozen=True)
class PartialEventCase:
    case_id: str
    family: str
    factory: Callable[[], SemanticProposal]
    expect: ExpectKind


def _resolved_event_measurement() -> SemanticProposal:
    base = sc4_replace_clutch()
    return base.model_copy(
        update={
            "measurement_semantics": True,
            "measurement_expression": "125000 km",
            "measurable_dimension_key": "odometer",
            "measurement_numeric_value": "125000",
            "measurement_unit": "km",
        }
    )


def _legitimate_intent_proposal() -> SemanticProposal:
    """Planned intent — resolver may set event.intent when type is on concepts."""
    from pke.interpretation.semantic.models import SemanticEntityMention, SemanticTime

    return SemanticProposal(
        raw_input="Pretendo trocar a embreagem na próxima semana.",
        object=SemanticEntityMention(text="embreagem", kind_hint="thing"),
        action_expression="pretendo trocar",
        event_expression="pretendo trocar a embreagem",
        change_semantics=True,
        primitive_hint="event",
        temporal=SemanticTime(occurrence_aspect="planned"),
    )


ANCHOR_CASES: list[PartialEventCase] = [
    PartialEventCase("MP1", "anchor", mp1, "partial_non_materialized"),
    PartialEventCase("MP2", "anchor", mp2, "partial_non_materialized"),
    PartialEventCase("MP3", "anchor", mp3, "partial_non_materialized"),
    PartialEventCase("MP4", "anchor", mp4, "partial_non_materialized"),
    PartialEventCase("MP5", "anchor", mp5, "measurement_only"),
    PartialEventCase("MS18", "anchor", ms18_i126, "partial_non_materialized"),
    PartialEventCase("RESOLVED_EM", "resolved", _resolved_event_measurement, "resolved_materialized"),
]


def _build_bulk() -> list[PartialEventCase]:
    cases: list[PartialEventCase] = []
    for mpc in mp_all_cases():
        if mpc.case_id in {a.case_id for a in ANCHORS} or mpc.case_id.startswith("MS18"):
            continue
        if PrimitiveKind.EVENT in mpc.expected and PrimitiveKind.MEASUREMENT in mpc.expected:
            cases.append(PartialEventCase(mpc.case_id, mpc.family, mpc.factory, "partial_non_materialized"))
        elif mpc.expected == frozenset({PrimitiveKind.MEASUREMENT}):
            cases.append(PartialEventCase(mpc.case_id, mpc.family, mpc.factory, "measurement_only"))
        elif mpc.expected == frozenset({PrimitiveKind.EVENT}):
            cases.append(PartialEventCase(mpc.case_id, mpc.family, mpc.factory, "event_only_partial"))

    for i in range(1, 16):
        cases.append(
            PartialEventCase(
                f"EOX{i:02d}",
                "event_only",
                _e_only(f"EOX{i:02d}", f"acao {i}", action="troquei", obj=f"peca{i}").factory,
                "event_only_partial",
            )
        )
        cases.append(
            PartialEventCase(
                f"MOX{i:02d}",
                "measurement_only",
                _m_only(f"MOX{i:02d}", f"leitura {i}", subject="sensor", dim="temperature", num=str(30 + i), unit="°C").factory,
                "measurement_only",
            )
        )
        cases.append(
            PartialEventCase(
                f"STX{i:02d}",
                "state",
                _state(f"STX{i:02d}", f"estado {i}", subject="porta", expr="aberta").factory,
                "no_event",
            )
        )
        cases.append(
            PartialEventCase(
                f"RLX{i:02d}",
                "relation",
                _rel(f"RLX{i:02d}", f"rel {i}", subj="Ana", obj="Acme", expr="trabalha na").factory,
                "no_event",
            )
        )
        cases.append(
            PartialEventCase(
                f"ATX{i:02d}",
                "attribute",
                _attr(f"ATX{i:02d}", f"attr {i}", subject="carro", expr="azul").factory,
                "no_event",
            )
        )

    cases.append(
        PartialEventCase("INTENT01", "legitimate_intent", _legitimate_intent_proposal, "event_only_partial")
    )
    return cases


def all_cases() -> list[PartialEventCase]:
    by_id = {c.case_id: c for c in ANCHOR_CASES + _build_bulk()}
    for c in CAPTURED:
        if c.case_id == "MS18_INTERPRETER_OMISSION":
            by_id[c.case_id] = PartialEventCase(c.case_id, "captured", c.factory, "measurement_only")
        elif c.case_id == "MS18_ENGINE_PRESERVE":
            by_id[c.case_id] = PartialEventCase(c.case_id, "captured", c.factory, "partial_non_materialized")
    return list(by_id.values())


def partial_event_cases() -> list[PartialEventCase]:
    return [c for c in all_cases() if c.expect == "partial_non_materialized"]
