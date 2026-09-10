"""I12.14 clarification coverage fixtures (>=300 cases)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from pke.application.pending_operation import PendingSemanticOperation
from pke.interpretation.semantic.models import (
    SemanticEntityMention,
    SemanticProposal,
    SemanticTime,
)

Expected = Literal[
    "resolved_committed",
    "remains_unresolved",
    "unsupported_slot",
    "rejected",
    "idempotent_replay",
    "invalid_answer",
    "already_resolved",
]


@dataclass(frozen=True)
class CoverageCase:
    case_id: str
    family: str
    pending_factory: Callable[[], PendingSemanticOperation]
    answer: str
    expected: Expected
    notes: str = ""


def _ent(text: str, kind: str = "thing") -> SemanticEntityMention:
    return SemanticEntityMention(text=text, kind_hint=kind)


def _ongoing() -> SemanticTime:
    return SemanticTime(occurrence_aspect="ongoing")


def _happened() -> SemanticTime:
    return SemanticTime(occurrence_aspect="happened")


def pending(
    proposal: SemanticProposal,
    *,
    slot: str,
    kind: str,
    primitive: str,
    reason: str,
) -> PendingSemanticOperation:
    return PendingSemanticOperation(
        originating_raw=proposal.raw_input,
        proposal_dump=proposal.model_dump(),
        missing_slot=slot,
        expected_answer_kind=kind,  # type: ignore[arg-type]
        primitive=primitive,
        reason=reason,
        question_key=f"clarify.{slot}",
    )


def meas_missing_dim(i: int = 0) -> SemanticProposal:
    return SemanticProposal(
        raw_input=f"medicao {i} deu 37.5",
        subject=_ent(f"sensor-{i}"),
        measurement_expression="37.5",
        measurement_numeric_value="37.5",
        measurement_unit="°C",
        measurement_semantics=True,
        primitive_hint="measurement",
        temporal=_happened(),
    )


def attr_missing_dim_color(i: int = 0) -> SemanticProposal:
    return SemanticProposal(
        raw_input=f"corolla {i} azul",
        subject=_ent("corolla", "vehicle"),
        attribute_expression="azul",
        stable_property_semantics=True,
        primitive_hint="attribute",
        temporal=_happened(),
    )


def attr_brand_gap(i: int = 0) -> SemanticProposal:
    """Unsupported Attribute surface — not in everyday registry (E1.2+).

    Formerly used ``toyota`` / brand, which became materializable in E1.2.
    """
    return SemanticProposal(
        raw_input=f"aura blorp {i}",
        subject=_ent("carro", "vehicle"),
        attribute_expression="aura blorp",
        stable_property_semantics=True,
        primitive_hint="attribute",
        temporal=_happened(),
    )


def state_missing_value(i: int = 0, *, expr: str | None = None) -> SemanticProposal:
    return SemanticProposal(
        raw_input=f"porta {i} estado",
        subject=_ent(f"porta-{i}"),
        condition_semantics=True,
        state_expression=expr,
        primitive_hint="state",
        temporal=_ongoing(),
    )


def state_no_condition(i: int = 0) -> SemanticProposal:
    return SemanticProposal(
        raw_input=f"sem condicao {i}",
        subject=_ent(f"x-{i}"),
        condition_semantics=False,
        primitive_hint="state",
        temporal=_ongoing(),
    )


def build_i1214_corpus() -> list[CoverageCase]:
    cases: list[CoverageCase] = []

    # --- Measurement dimension: valid ---
    for i in range(40):
        cases.append(
            CoverageCase(
                f"MEAS_DIM_OK_{i:03d}",
                "measurement_dimension",
                lambda i=i: pending(
                    meas_missing_dim(i),
                    slot="measurement_dimension",
                    kind="dimension",
                    primitive="measurement",
                    reason="missing_measurement_dimension",
                ),
                ["temperatura", "temperature", "temp", "Temperatura"][i % 4],
                "resolved_committed",
            )
        )

    # Extra info in answer — only dimension consumed; value must not be invented from "95"
    for i in range(15):
        cases.append(
            CoverageCase(
                f"MEAS_DIM_EXTRA_{i:03d}",
                "measurement_dimension",
                lambda i=i: pending(
                    meas_missing_dim(100 + i),
                    slot="measurement_dimension",
                    kind="dimension",
                    primitive="measurement",
                    reason="missing_measurement_dimension",
                ),
                "temperatura de 95 graus",
                "resolved_committed",
                notes="extra value ignored; existing numeric preserved",
            )
        )

    # Unknown / wrong family
    for i in range(20):
        cases.append(
            CoverageCase(
                f"MEAS_DIM_UNKNOWN_{i:03d}",
                "measurement_dimension",
                lambda i=i: pending(
                    meas_missing_dim(200 + i),
                    slot="measurement_dimension",
                    kind="dimension",
                    primitive="measurement",
                    reason="missing_measurement_dimension",
                ),
                ["blorpt", "xyzzy", "???"][i % 3],
                "remains_unresolved",
            )
        )

    for i in range(10):
        cases.append(
            CoverageCase(
                f"MEAS_DIM_WRONG_FAM_{i:03d}",
                "measurement_dimension",
                lambda i=i: pending(
                    meas_missing_dim(300 + i),
                    slot="measurement_dimension",
                    kind="dimension",
                    primitive="measurement",
                    reason="missing_measurement_dimension",
                ),
                "cor",
                "remains_unresolved",
                notes="attribute vocabulary does not resolve measurement dim",
            )
        )

    # Already present dimension
    for i in range(10):
        p = meas_missing_dim(400 + i).model_copy(update={"measurable_dimension_key": "temperature"})
        cases.append(
            CoverageCase(
                f"MEAS_DIM_ALREADY_{i:03d}",
                "measurement_dimension",
                lambda p=p: pending(
                    p,
                    slot="measurement_dimension",
                    kind="dimension",
                    primitive="measurement",
                    reason="missing_measurement_dimension",
                ),
                "temperatura",
                "already_resolved",
            )
        )

    # --- Attribute dimension ---
    # Bare color already resolves via attribute_resolution → already_resolved.
    for i in range(25):
        cases.append(
            CoverageCase(
                f"ATTR_DIM_ALREADY_{i:03d}",
                "attribute_dimension",
                lambda i=i: pending(
                    attr_missing_dim_color(i),
                    slot="attribute_dimension",
                    kind="dimension",
                    primitive="attribute",
                    reason="missing_attribute_dimension",
                ),
                ["cor", "color", "cores"][i % 3],
                "already_resolved",
            )
        )

    for i in range(15):
        cases.append(
            CoverageCase(
                f"ATTR_DIM_UNKNOWN_{i:03d}",
                "attribute_dimension",
                lambda i=i: pending(
                    attr_brand_gap(i),
                    slot="attribute_dimension",
                    kind="dimension",
                    primitive="attribute",
                    reason="missing_attribute_dimension",
                ),
                "signo",
                "remains_unresolved",
                notes="unsupported dimension alias — user cannot unlock via registry",
            )
        )

    for i in range(10):
        cases.append(
            CoverageCase(
                f"ATTR_DIM_WRONG_FAM_{i:03d}",
                "attribute_dimension",
                lambda i=i: pending(
                    attr_brand_gap(50 + i),
                    slot="attribute_dimension",
                    kind="dimension",
                    primitive="attribute",
                    reason="missing_attribute_dimension",
                ),
                "temperatura",
                "invalid_answer",
            )
        )

    for i in range(10):
        # Injecting a valid dimension into unsupported text remains incomplete (no typed value).
        cases.append(
            CoverageCase(
                f"ATTR_DIM_PARTIAL_{i:03d}",
                "attribute_dimension",
                lambda i=i: pending(
                    attr_brand_gap(80 + i),
                    slot="attribute_dimension",
                    kind="dimension",
                    primitive="attribute",
                    reason="missing_attribute_dimension",
                ),
                "cor, e peso 10",
                "remains_unresolved",
                notes="dimension may resolve; value still incomplete — no invent",
            )
        )

    # --- State value ---
    valid_answers = [
        "fechado",
        "fechada",
        "closed",
        "quebrado",
        "quebrada",
        "broken",
        "aberto",
        "aberta",
        "open",
        "funcionando",
        "working",
        "atrasado",
        "overdue",
        "esgotado",
        "depleted",
        "unpaid",
        "não pago",
        "válido",
        "valid",
        "vencido",
        "expired",
    ]
    for i in range(60):
        ans = valid_answers[i % len(valid_answers)]
        cases.append(
            CoverageCase(
                f"STATE_VAL_OK_{i:03d}",
                "state_value",
                lambda i=i: pending(
                    state_missing_value(i),
                    slot="state_value",
                    kind="value",
                    primitive="state",
                    reason="missing_state_value",
                ),
                ans,
                "resolved_committed",
            )
        )

    for i in range(25):
        cases.append(
            CoverageCase(
                f"STATE_VAL_UNKNOWN_{i:03d}",
                "state_value",
                lambda i=i: pending(
                    state_missing_value(200 + i),
                    slot="state_value",
                    kind="value",
                    primitive="state",
                    reason="missing_state_value",
                ),
                ["ligado", "pago", "ativo", "inativo", "blorp"][i % 5],
                "remains_unresolved",
            )
        )

    for i in range(15):
        cases.append(
            CoverageCase(
                f"STATE_VAL_NO_COND_{i:03d}",
                "state_value",
                lambda i=i: pending(
                    state_no_condition(i),
                    slot="state_value",
                    kind="value",
                    primitive="state",
                    reason="missing_state_value",
                ),
                "fechado",
                "remains_unresolved",
                notes="must not invent condition_semantics",
            )
        )

    for i in range(10):
        cases.append(
            CoverageCase(
                f"STATE_VAL_EXTRA_{i:03d}",
                "state_value",
                lambda i=i: pending(
                    state_missing_value(300 + i),
                    slot="state_value",
                    kind="value",
                    primitive="state",
                    reason="missing_state_value",
                ),
                "fechado, desde ontem",
                "resolved_committed",
            )
        )

    # --- Unsupported families ---
    for i in range(15):
        cases.append(
            CoverageCase(
                f"UNSUP_CORR_{i:03d}",
                "unsupported",
                lambda i=i: pending(
                    state_missing_value(400 + i),
                    slot="correction_target",
                    kind="correction_target",
                    primitive="correction",
                    reason="ambiguous_correction_target",
                ),
                "assertion-123",
                "unsupported_slot",
            )
        )

    for i in range(10):
        cases.append(
            CoverageCase(
                f"UNSUP_STATE_DIM_{i:03d}",
                "unsupported",
                lambda i=i: pending(
                    state_missing_value(500 + i, expr="quebrado"),
                    slot="state_dimension",
                    kind="dimension",
                    primitive="state",
                    reason="missing_state_dimension",
                ),
                "operacional",
                "unsupported_slot",
            )
        )

    for i in range(10):
        cases.append(
            CoverageCase(
                f"UNSUP_MEAS_VAL_{i:03d}",
                "unsupported",
                lambda i=i: pending(
                    meas_missing_dim(600 + i).model_copy(
                        update={"measurable_dimension_key": "temperature"}
                    ),
                    slot="measurement_value",
                    kind="value",
                    primitive="measurement",
                    reason="missing_measurement_value",
                ),
                "95",
                "unsupported_slot",
                notes="measurement_value not SAFE_FOR_ENGINE_V1 in I12.14",
            )
        )

    # --- Isolation / closed / replay controls ---
    for i in range(8):
        cases.append(
            CoverageCase(
                f"CTRL_IRRELEVANT_{i:03d}",
                "control",
                lambda i=i: pending(
                    meas_missing_dim(700 + i),
                    slot="measurement_dimension",
                    kind="dimension",
                    primitive="measurement",
                    reason="missing_measurement_dimension",
                ),
                "foi ontem",
                "remains_unresolved",
            )
        )

    return cases


I1214_CORPUS = build_i1214_corpus()
