"""I12.15 State interpretation hardening — deterministic corpus (>=220)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from pke.interpretation.semantic.models import (
    SemanticEntityMention,
    SemanticProposal,
    SemanticTime,
)

ExpectedOutcome = Literal[
    "auto_execute",
    "clarify",
    "unsupported",
    "safe_abstain",
    "partial_execute",
]


@dataclass(frozen=True)
class StateCase:
    case_id: str
    family: str
    proposal_factory: Callable[[], SemanticProposal]
    expected_outcome: ExpectedOutcome
    expected_primitive: str | None = "state"
    notes: str = ""


def _ent(text: str, kind: str = "thing") -> SemanticEntityMention:
    return SemanticEntityMention(text=text, kind_hint=kind)


def _ongoing() -> SemanticTime:
    return SemanticTime(occurrence_aspect="ongoing")


def _happened() -> SemanticTime:
    return SemanticTime(occurrence_aspect="happened")


def state_prop(
    *,
    raw: str,
    entity: str,
    expr: str | None,
    condition: bool = True,
) -> SemanticProposal:
    return SemanticProposal(
        raw_input=raw,
        subject=_ent(entity),
        condition_semantics=condition,
        state_expression=expr,
        primitive_hint="state",
        temporal=_ongoing(),
    )


def build_corpus() -> list[StateCase]:
    cases: list[StateCase] = []

    # --- CORE-covered values → auto_execute ---
    core_ok = [
        ("quebrado", "broken"),
        ("quebrada", "broken"),
        ("broken", "broken"),
        ("funcionando", "working"),
        ("working", "working"),
        ("aberto", "open"),
        ("aberta", "open"),
        ("open", "open"),
        ("fechado", "closed"),
        ("fechada", "closed"),
        ("closed", "closed"),
        ("atrasado", "overdue"),
        ("atrasada", "overdue"),
        ("overdue", "overdue"),
        ("esgotado", "depleted"),
        ("depleted", "depleted"),
        ("acabou", "depleted"),
        ("não pago", "unpaid"),
        ("unpaid", "unpaid"),
        ("válido", "valid"),
        ("valid", "valid"),
        ("vencido", "expired"),
        ("expired", "expired"),
    ]
    for i, (expr, _canon) in enumerate(core_ok):
        for j in range(2):
            cases.append(
                StateCase(
                    f"CORE_OK_{i:02d}_{j}",
                    "core_value",
                    lambda expr=expr, i=i, j=j: state_prop(
                        raw=f"estado {expr} {i}-{j}",
                        entity=f"alvo-{i}-{j}",
                        expr=expr,
                    ),
                    "auto_execute",
                )
            )

    # --- Present expression outside CORE → unsupported (E1.3; not false clarify) ---
    unknown = [
        "ligado",
        "on",
        "off",
        "desligado",
        "paid",
        "paga",
        "ativo",
        "active",
        "inativo",
        "inactive",
        "indisponível",
        "unavailable",
        "cheio",
        "full",
        "connected",
        "disconnected",
        "sujo",
        "limpo",
        "molhado",
        "seco",
        "ocupado",
        "livre",
        "enabled",
        "disabled",
        "carregado",
        "blorp",
    ]
    for i, expr in enumerate(unknown):
        for j in range(2):
            cases.append(
                StateCase(
                    f"CANON_GAP_{i:02d}_{j}",
                    "canonical_gap",
                    lambda expr=expr, i=i, j=j: state_prop(
                        raw=f"gap {expr} {i}-{j}",
                        entity=f"gap-{i}-{j}",
                        expr=expr,
                    ),
                    "unsupported",
                    notes="expression present; CORE has no matching value",
                )
            )

    # --- Truly missing value → clarify state_value ---
    for i in range(30):
        cases.append(
            StateCase(
                f"MISSING_VAL_{i:02d}",
                "missing_value",
                lambda i=i: state_prop(
                    raw=f"condicao sem valor {i}",
                    entity=f"porta-{i}",
                    expr=None,
                ),
                "clarify",
            )
        )

    # --- Missing entity with CORE value ---
    for i in range(15):
        cases.append(
            StateCase(
                f"MISSING_ENT_{i:02d}",
                "missing_entity",
                lambda i=i: SemanticProposal(
                    raw_input=f"esta quebrado {i}",
                    subject=None,
                    condition_semantics=True,
                    state_expression="quebrado",
                    primitive_hint="state",
                    temporal=_ongoing(),
                ),
                "auto_execute",
                notes="persistability currently does not require subject for State",
            )
        )

    # --- No condition_semantics → should not invent State routing preference ---
    for i in range(15):
        cases.append(
            StateCase(
                f"NO_COND_{i:02d}",
                "boundary",
                lambda i=i: SemanticProposal(
                    raw_input=f"sem condicao {i}",
                    subject=_ent(f"x-{i}"),
                    condition_semantics=False,
                    state_expression="quebrado",
                    temporal=_ongoing(),
                ),
                "unsupported",
                expected_primitive=None,
                notes="alias requires condition_semantics — known non-materializable (E1.3)",
            )
        )

    # --- Attribute controls (must not become State) ---
    for i in range(15):
        cases.append(
            StateCase(
                f"ATTR_CTRL_{i:02d}",
                "attribute_control",
                lambda i=i: SemanticProposal(
                    raw_input=f"carro vermelho {i}",
                    subject=_ent("carro", "vehicle"),
                    attribute_expression="vermelho",
                    stable_property_semantics=True,
                    condition_semantics=False,
                    primitive_hint="attribute",
                    temporal=_happened(),
                ),
                "auto_execute",
                expected_primitive="attribute",
            )
        )

    # --- Relation controls ---
    for i in range(12):
        cases.append(
            StateCase(
                f"REL_CTRL_{i:02d}",
                "relation_control",
                lambda i=i: SemanticProposal(
                    raw_input=f"trabalha em acme {i}",
                    subject=_ent("João", "person"),
                    object=_ent("Acme", "organization"),
                    link_semantics=True,
                    relation_expression="trabalha em",
                    condition_semantics=False,
                    primitive_hint="relation",
                    temporal=_happened(),
                ),
                "auto_execute",
                expected_primitive="relation",
            )
        )

    # --- Event controls (no false State / causal) ---
    for i in range(12):
        cases.append(
            StateCase(
                f"EVT_CTRL_{i:02d}",
                "event_control",
                lambda i=i: SemanticProposal(
                    raw_input=f"troquei a embreagem {i}",
                    subject=_ent("corolla", "vehicle"),
                    change_semantics=True,
                    action_expression="troquei a embreagem",
                    event_expression="troquei a embreagem",
                    condition_semantics=False,
                    primitive_hint="event",
                    temporal=_happened(),
                ),
                "auto_execute",
                expected_primitive="event",
            )
        )

    # --- Measurement controls ---
    for i in range(12):
        cases.append(
            StateCase(
                f"MEAS_CTRL_{i:02d}",
                "measurement_control",
                lambda i=i: SemanticProposal(
                    raw_input=f"medicao {i}",
                    subject=_ent(f"sensor-{i}"),
                    measurement_semantics=True,
                    measurable_dimension_key="temperature",
                    measurement_numeric_value="37.5",
                    measurement_unit="°C",
                    condition_semantics=False,
                    primitive_hint="measurement",
                    temporal=_happened(),
                ),
                "auto_execute",
                expected_primitive="measurement",
            )
        )

    # --- State vs empty tank Measurement contrast (State empty) ---
    for i in range(12):
        cases.append(
            StateCase(
                f"EMPTY_STATE_{i:02d}",
                "state_vs_measurement",
                lambda i=i: state_prop(
                    raw=f"tanque vazio {i}",
                    entity="tanque",
                    expr="esgotado",
                ),
                "auto_execute",
                notes="depleted is CORE; empty lexical may not be",
            )
        )

    return cases


I1215_STATE_CORPUS = build_corpus()
