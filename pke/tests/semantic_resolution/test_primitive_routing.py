"""PR1–PR6 primitive routing."""

from __future__ import annotations

import pytest

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


@pytest.mark.parametrize(
    ("fixture", "expected"),
    [
        (pr1_fridge_broken, PrimitiveKind.STATE),
        (pr2_fridge_broke, PrimitiveKind.EVENT),
        (pr3_employment, PrimitiveKind.RELATION),
        (pr4_color, PrimitiveKind.ATTRIBUTE),
        (pr5_door_open, PrimitiveKind.STATE),
        (pr6_door_opened, PrimitiveKind.EVENT),
    ],
    ids=["PR1", "PR2", "PR3", "PR4", "PR5", "PR6"],
)
def test_primitive_routing(fixture, expected) -> None:
    proposal = fixture()
    primitive, _ = route_primitive(proposal)
    assert primitive is expected
