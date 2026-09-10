"""Contrast tests — primitive collapse rate."""

from __future__ import annotations

from pke.interpretation.semantic.models import PrimitiveKind
from pke.interpretation.semantic.router import route_primitive
from tests.semantic_resolution.fixtures import (
    pr1_fridge_broken,
    pr2_fridge_broke,
    pr3_employment,
    pr4_color,
    pr5_door_open,
    pr6_door_opened,
)


def test_state_vs_event_contrast() -> None:
    assert route_primitive(pr1_fridge_broken())[0] is PrimitiveKind.STATE
    assert route_primitive(pr2_fridge_broke())[0] is PrimitiveKind.EVENT


def test_relation_vs_state_unemployment() -> None:
    from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal

    unemployed = SemanticProposal(
        raw_input="João está desempregado.",
        subject=SemanticEntityMention(text="João", kind_hint="person"),
        state_expression="desempregado",
        condition_semantics=True,
    )
    assert route_primitive(unemployed)[0] is PrimitiveKind.STATE
    assert route_primitive(pr3_employment())[0] is PrimitiveKind.RELATION


def test_relation_vs_attribute() -> None:
    assert route_primitive(pr3_employment())[0] is PrimitiveKind.RELATION
    assert route_primitive(pr4_color())[0] is PrimitiveKind.ATTRIBUTE


def test_no_collapse_across_pr_suite() -> None:
    cases = [pr1_fridge_broken(), pr2_fridge_broke(), pr3_employment(), pr4_color(), pr5_door_open(), pr6_door_opened()]
    primitives = {route_primitive(c)[0] for c in cases}
    assert len(primitives) == 4
