"""Casos I11.4-R — State re-evaluation (medida; não altera expectativas históricas)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class StateCaseKind(StrEnum):
    SINGLE = "single"
    TRANSITION = "transition"
    INDEPENDENT_DIMS = "independent_dims"
    COLLAPSE_CONTRAST = "collapse_contrast"
    CURRENTNESS_INVARIANT = "currentness_invariant"


@dataclass(frozen=True)
class StateExpectation:
    dimension_key: str | None = None
    value_key: str | None = None
    max_events: int = 0
    provisional_s6: bool = False
    forbid_unpaid_for_overdue: bool = False
    forbid_causal_event: bool = True


@dataclass(frozen=True)
class StateBenchmarkCase:
    case_id: str
    kind: StateCaseKind
    texts: tuple[str, ...]
    expectation: StateExpectation
    live_runs: int = 3
    notes: str = ""
    entity_type_hint: str = "entity.home"
    entity_text: str = ""


# Deterministic FakeInterpreter fixtures map case_id → expected IR shape.
STATE_CASES: tuple[StateBenchmarkCase, ...] = (
    StateBenchmarkCase(
        "S1",
        StateCaseKind.SINGLE,
        ("A geladeira está quebrada.",),
        StateExpectation(
            dimension_key="state.operational_condition",
            value_key="state.value.broken",
        ),
        entity_type_hint="entity.appliance",
        entity_text="geladeira",
        notes="broken appliance → State, no causal Event",
    ),
    StateBenchmarkCase(
        "S2",
        StateCaseKind.SINGLE,
        ("O remédio acabou.",),
        StateExpectation(
            dimension_key="state.availability",
            value_key="state.value.depleted",
        ),
        entity_type_hint="entity.medication",
        entity_text="remédio",
        notes="depletion; no invented consume event",
    ),
    StateBenchmarkCase(
        "S3",
        StateCaseKind.SINGLE,
        ("A conta de luz está atrasada.",),
        StateExpectation(
            dimension_key="state.due_status",
            value_key="state.value.overdue",
            forbid_unpaid_for_overdue=True,
        ),
        entity_text="conta de luz",
        notes="overdue ≠ unpaid",
    ),
    StateBenchmarkCase(
        "S4",
        StateCaseKind.SINGLE,
        ("A porta está aberta.",),
        StateExpectation(
            dimension_key="state.openness",
            value_key="state.value.open",
        ),
        entity_text="porta",
        notes="openness; no invented open event",
    ),
    StateBenchmarkCase(
        "S5",
        StateCaseKind.SINGLE,
        ("Minha CNH está vencida.",),
        StateExpectation(
            dimension_key="state.validity",
            value_key="state.value.expired",
        ),
        entity_type_hint="entity.document",
        entity_text="CNH",
        notes="expired; no invented expiry date",
    ),
    StateBenchmarkCase(
        "S6",
        StateCaseKind.SINGLE,
        ("O Corolla está com 84.500 km.",),
        StateExpectation(
            dimension_key="state.observed_quantity",
            value_key="state.value.quantity_observation",
            provisional_s6=True,
        ),
        entity_type_hint="entity.automobile",
        entity_text="Corolla",
        notes="PROVISIONAL_MEASUREMENT_REPRESENTATION",
    ),
    StateBenchmarkCase(
        "ST_TRANSITION",
        StateCaseKind.TRANSITION,
        ("A geladeira está quebrada.", "Agora ela está funcionando."),
        StateExpectation(
            dimension_key="state.operational_condition",
            value_key="state.value.working",
        ),
        entity_type_hint="entity.appliance",
        entity_text="geladeira",
        notes="broken→working same dimension; history preserved",
    ),
    StateBenchmarkCase(
        "ST_INDEPENDENT",
        StateCaseKind.INDEPENDENT_DIMS,
        ("A geladeira está funcionando.", "A porta da geladeira está aberta."),
        StateExpectation(),
        entity_type_hint="entity.appliance",
        entity_text="geladeira",
        notes="operational_condition + openness both current",
    ),
    StateBenchmarkCase(
        "SHOP_002",
        StateCaseKind.SINGLE,
        ("Acabou detergente.",),
        StateExpectation(
            dimension_key="state.availability",
            value_key="state.value.depleted",
        ),
        entity_text="detergente",
        notes="DEV case formerly ArchitecturalGap.STATE",
    ),
)

# Collapse / primitive boundary contrasts (live + classify; deterministic when FakeIR given).
COLLAPSE_CASES: tuple[StateBenchmarkCase, ...] = (
    StateBenchmarkCase(
        "COLLAPSE_STATE_OPEN",
        StateCaseKind.COLLAPSE_CONTRAST,
        ("A porta está aberta.",),
        StateExpectation(dimension_key="state.openness", value_key="state.value.open"),
        entity_text="porta",
        notes="expect State",
    ),
    StateBenchmarkCase(
        "COLLAPSE_EVENT_OPENED",
        StateCaseKind.COLLAPSE_CONTRAST,
        ("A porta abriu.",),
        StateExpectation(max_events=99),  # Event preferred; State alone = collapse risk
        entity_text="porta",
        notes="expect Event/Action — not State-only",
    ),
    StateBenchmarkCase(
        "COLLAPSE_STATE_BROKEN",
        StateCaseKind.COLLAPSE_CONTRAST,
        ("A geladeira está quebrada.",),
        StateExpectation(
            dimension_key="state.operational_condition",
            value_key="state.value.broken",
        ),
        entity_type_hint="entity.appliance",
        entity_text="geladeira",
        notes="expect State",
    ),
    StateBenchmarkCase(
        "COLLAPSE_EVENT_BROKE",
        StateCaseKind.COLLAPSE_CONTRAST,
        ("A geladeira quebrou ontem.",),
        StateExpectation(max_events=99),
        entity_type_hint="entity.appliance",
        entity_text="geladeira",
        notes="expect Event/change — not current-State-only",
    ),
    StateBenchmarkCase(
        "COLLAPSE_RELATION",
        StateCaseKind.COLLAPSE_CONTRAST,
        ("João trabalha na Acme.",),
        StateExpectation(max_events=99),
        notes="Relation gap — must not absorb as State",
    ),
    StateBenchmarkCase(
        "COLLAPSE_ATTRIBUTE_COLOR",
        StateCaseKind.COLLAPSE_CONTRAST,
        ("O Corolla é prata.",),
        StateExpectation(max_events=99),
        entity_type_hint="entity.automobile",
        entity_text="Corolla",
        notes="Attribute — must not become State",
    ),
)

LIVE_STATE_IDS = frozenset(
    {"S1", "S2", "S3", "S4", "S5", "S6", "SHOP_002", "ST_TRANSITION"}
)
