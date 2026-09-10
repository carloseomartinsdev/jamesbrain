"""I12.10 structured proposal reliability corpus (>=180 deterministic cases)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from pke.interpretation.semantic.execution_readiness import ProposalExecutionOutcome
from pke.interpretation.semantic.models import (
    SemanticEntityMention,
    SemanticProposal,
    SemanticTime,
)
from tests.multi_primitive_routing_hardening.corpus import mp1, mp2, mp3, mp4, mp5
from tests.semantic_resolution.fixtures import (
    pr1_fridge_broken,
    pr3_employment,
    pr4_color,
    pr5_door_open,
    sc4_replace_clutch,
)

ExpectedOutcome = Literal[
    "valid_executable",
    "valid_partially_executable",
    "valid_execution_incomplete",
    "invalid",
]


@dataclass(frozen=True)
class SPRCase:
    case_id: str
    family: str
    factory: Callable[[], SemanticProposal]
    expected: ExpectedOutcome
    expect_clarification: bool = False
    expect_zero_materializable: bool = False
    expect_partial_commit: bool = False
    notes: str = ""


def _happened() -> SemanticTime:
    return SemanticTime(occurrence_aspect="happened")


def _ongoing() -> SemanticTime:
    return SemanticTime(occurrence_aspect="ongoing")


def _ent(text: str, kind: str = "thing") -> SemanticEntityMention:
    return SemanticEntityMention(text=text, kind_hint=kind)  # type: ignore[arg-type]


def mp1_missing_subject() -> SemanticProposal:
    """I12.9 forensic shape: E+M present, subject/object absent."""
    return SemanticProposal(
        raw_input="medi a temperatura e deu 95°C",
        action_expression="medi",
        event_expression="medi a temperatura",
        change_semantics=True,
        measurement_expression="95°C",
        measurable_dimension_key="temperature",
        measurement_numeric_value="95",
        measurement_unit="°C",
        measurement_semantics=True,
        primitive_hint="event",
        temporal=_happened(),
    )


def mp1_with_subject() -> SemanticProposal:
    return SemanticProposal(
        raw_input="medi a temperatura e deu 95°C",
        subject=_ent("temperatura"),
        action_expression="medi",
        event_expression="medi a temperatura",
        change_semantics=True,
        measurement_expression="95°C",
        measurable_dimension_key="temperature",
        measurement_numeric_value="95",
        measurement_unit="°C",
        measurement_semantics=True,
        primitive_hint="event",
        temporal=_happened(),
    )


def meas_no_entity() -> SemanticProposal:
    return SemanticProposal(
        raw_input="deu 95°C",
        measurement_expression="95°C",
        measurable_dimension_key="temperature",
        measurement_numeric_value="95",
        measurement_unit="°C",
        measurement_semantics=True,
        primitive_hint="measurement",
        temporal=_happened(),
    )


def meas_no_dimension() -> SemanticProposal:
    return SemanticProposal(
        raw_input="o tanque 20",
        subject=_ent("tanque"),
        measurement_expression="20",
        measurement_numeric_value="20",
        measurement_semantics=True,
        primitive_hint="measurement",
        temporal=_happened(),
    )


def relation_missing_object() -> SemanticProposal:
    return SemanticProposal(
        raw_input="João trabalha",
        subject=_ent("João", "person"),
        relation_expression="trabalha",
        link_semantics=True,
        primitive_hint="relation",
        temporal=_ongoing(),
    )


def relation_missing_subject() -> SemanticProposal:
    return SemanticProposal(
        raw_input="trabalha na Acme",
        object=_ent("Acme", "organization"),
        relation_expression="trabalha na",
        link_semantics=True,
        primitive_hint="relation",
        temporal=_ongoing(),
    )


def attr_missing_dimension() -> SemanticProposal:
    return SemanticProposal(
        raw_input="o corolla é",
        subject=_ent("Corolla", "vehicle"),
        stable_property_semantics=True,
        primitive_hint="attribute",
        temporal=_ongoing(),
    )


def state_complete() -> SemanticProposal:
    return pr5_door_open()


def event_safe_partial() -> SemanticProposal:
    return SemanticProposal(
        raw_input="olhei o tanque",
        subject=_ent("tanque"),
        action_expression="olhei",
        event_expression="olhei o tanque",
        change_semantics=True,
        primitive_hint="event",
        temporal=_happened(),
    )


def query_boundary() -> SemanticProposal:
    return SemanticProposal(
        raw_input="já troquei isso?",
        utterance_kind="query",
        action_expression="troquei",
        change_semantics=True,
        primitive_hint="event",
        temporal=_happened(),
    )


def correction_unresolved_target() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Corrigindo, li errado: era 36°C.",
        utterance_kind="correct",
        correction_semantics=True,
        correction_operation="replace",
        correction_target_kind="measurement",
        measurement_expression="36°C",
        measurable_dimension_key="temperature",
        measurement_numeric_value="36",
        measurement_unit="°C",
        measurement_semantics=True,
        primitive_hint="measurement",
        temporal=_happened(),
    )


def _clone_mp1_missing(i: int) -> Callable[[], SemanticProposal]:
    def factory() -> SemanticProposal:
        p = mp1_missing_subject()
        return p.model_copy(update={"raw_input": f"{p.raw_input} #{i}"})

    return factory


def _clone_meas_entity(name: str) -> Callable[[], SemanticProposal]:
    def factory() -> SemanticProposal:
        return SemanticProposal(
            raw_input=f"medi {name}",
            action_expression="medi",
            event_expression=f"medi {name}",
            change_semantics=True,
            measurement_expression="10",
            measurable_dimension_key="mass",
            measurement_numeric_value="10",
            measurement_unit="kg",
            measurement_semantics=True,
            primitive_hint="event",
            temporal=_happened(),
        )

    return factory


def _executable_state(name: str) -> Callable[[], SemanticProposal]:
    def factory() -> SemanticProposal:
        return SemanticProposal(
            raw_input=f"a {name} está quebrada",
            subject=_ent(name, "appliance"),
            state_expression="broken",
            condition_semantics=True,
            primitive_hint="state",
            temporal=_ongoing(),
        )

    return factory


def _executable_relation(person: str, org: str) -> Callable[[], SemanticProposal]:
    def factory() -> SemanticProposal:
        return SemanticProposal(
            raw_input=f"{person} trabalha na {org}",
            subject=_ent(person, "person"),
            object=_ent(org, "organization"),
            relation_expression="trabalha na",
            link_semantics=True,
            primitive_hint="relation",
            temporal=_ongoing(),
        )

    return factory


def _executable_measurement(entity: str) -> Callable[[], SemanticProposal]:
    def factory() -> SemanticProposal:
        return SemanticProposal(
            raw_input=f"{entity} mediu 38°C",
            subject=_ent(entity),
            measurement_expression="38°C",
            measurable_dimension_key="temperature",
            measurement_numeric_value="38",
            measurement_unit="°C",
            measurement_semantics=True,
            primitive_hint="measurement",
            temporal=_happened(),
        )

    return factory


def _partial_em(entity: str) -> Callable[[], SemanticProposal]:
    def factory() -> SemanticProposal:
        return SemanticProposal(
            raw_input=f"olhei {entity} 20 L",
            subject=_ent(entity),
            action_expression="olhei",
            event_expression=f"olhei {entity}",
            change_semantics=True,
            measurement_expression="20 L",
            measurable_dimension_key="volume",
            measurement_numeric_value="20",
            measurement_unit="L",
            measurement_semantics=True,
            primitive_hint="event",
            temporal=_happened(),
        )

    return factory


def _rel_missing_obj(person: str) -> Callable[[], SemanticProposal]:
    def factory() -> SemanticProposal:
        return SemanticProposal(
            raw_input=f"{person} trabalha",
            subject=_ent(person, "person"),
            relation_expression="trabalha",
            link_semantics=True,
            primitive_hint="relation",
            temporal=_ongoing(),
        )

    return factory


def build_corpus() -> list[SPRCase]:
    cases: list[SPRCase] = [
        SPRCase("MP1_FIXTURE", "anchor", mp1, "valid_partially_executable", expect_partial_commit=True),
        SPRCase("MP2", "anchor", mp2, "valid_partially_executable", expect_partial_commit=True),
        SPRCase("MP3", "anchor", mp3, "valid_partially_executable", expect_partial_commit=True),
        SPRCase("MP4", "anchor", mp4, "valid_partially_executable", expect_partial_commit=True),
        SPRCase("MP5", "anchor", mp5, "valid_executable"),
        SPRCase(
            "MP1_MISSING_SUBJECT",
            "zero_materializable",
            mp1_missing_subject,
            "valid_execution_incomplete",
            expect_clarification=True,
            expect_zero_materializable=True,
        ),
        SPRCase(
            "MP1_WITH_SUBJECT",
            "partial_commit",
            mp1_with_subject,
            "valid_partially_executable",
            expect_partial_commit=True,
        ),
        SPRCase("MEAS_NO_ENTITY", "incomplete", meas_no_entity, "valid_execution_incomplete", True, True),
        SPRCase("MEAS_NO_DIM", "incomplete", meas_no_dimension, "valid_execution_incomplete", True, True),
        SPRCase("REL_NO_OBJ", "incomplete", relation_missing_object, "valid_execution_incomplete", True, True),
        SPRCase("REL_NO_SUBJ", "incomplete", relation_missing_subject, "valid_execution_incomplete", True, True),
        SPRCase("ATTR_NO_DIM", "incomplete", attr_missing_dimension, "valid_execution_incomplete", True, True),
        SPRCase("STATE_OK", "executable", state_complete, "valid_executable"),
        SPRCase("REL_OK", "executable", pr3_employment, "valid_executable"),
        SPRCase("ATTR_OK", "executable", pr4_color, "valid_executable"),
        SPRCase("STATE_FRIDGE", "executable", pr1_fridge_broken, "valid_executable"),
        SPRCase("EVT_REPLACE", "executable", sc4_replace_clutch, "valid_executable"),
        SPRCase("EVT_SAFE_PARTIAL", "safe_partial", event_safe_partial, "valid_execution_incomplete", False, True),
        SPRCase("QUERY", "query", query_boundary, "valid_execution_incomplete", False, True),
        SPRCase("CORR_UNRESOLVED", "correction", correction_unresolved_target, "valid_execution_incomplete", True, False),
    ]

    appliances = [
        "geladeira", "porta", "impressora", "tv", "fogao", "microondas",
        "ar", "lampada", "torneira", "janela", "caixa", "tanque",
        "bateria", "sensor", "termometro", "balanca",
    ]
    for name in appliances:
        cases.append(SPRCase(f"ST_{name}", "executable_state", _executable_state(name), "valid_executable"))

    people = ["Joao", "Maria", "Ana", "Carlos", "Pedro", "Lucia", "Paulo", "Rita"]
    orgs = ["Acme", "Globex", "Initech", "Umbrella"]
    n = 0
    for person in people:
        for org in orgs:
            n += 1
            cases.append(
                SPRCase(f"REL_{person}_{org}", "executable_relation", _executable_relation(person, org), "valid_executable")
            )
            cases.append(
                SPRCase(f"RELMISS_{person}_{org}", "incomplete_relation", _rel_missing_obj(person + org), "valid_execution_incomplete", True, True)
            )

    entities = ["tanque", "caixa", "saldo", "motor", "pneu", "oleo", "filtro", "bomba", "reservatorio", "bateria"]
    for ent in entities:
        cases.append(SPRCase(f"MEAS_{ent}", "executable_meas", _executable_measurement(ent), "valid_executable"))
        cases.append(SPRCase(f"PEM_{ent}", "partial_em", _partial_em(ent), "valid_partially_executable", expect_partial_commit=True))
        cases.append(SPRCase(f"Z_{ent}", "zero_em", _clone_meas_entity(ent), "valid_execution_incomplete", True, True))

    for i in range(1, 21):
        cases.append(
            SPRCase(
                f"MP1_HIST_{i}",
                "mp1_replay",
                _clone_mp1_missing(i),
                "valid_execution_incomplete",
                True,
                True,
            )
        )

    extras = [
        "radio", "modem", "roteador", "camera", "drone", "tablet", "notebook",
        "monitor", "teclado", "mouse", "hd", "ssd", "fonte", "cooler",
        "ventilador", "umidificador", "aspirador", "liquidificador", "batedeira",
        "cafeteira", "torradeira", "freezer", "adega", "chuveiro", "boia",
        "valvula", "mangueira", "filtroar", "catalisador", "embreagem",
        "alternador", "radiador", "amortecedor",
    ]
    for name in extras:
        cases.append(SPRCase(f"STX_{name}", "executable_state", _executable_state(name), "valid_executable"))
        cases.append(SPRCase(f"ZX_{name}", "zero_em", _clone_meas_entity(name), "valid_execution_incomplete", True, True))

    return cases


def load_i129_mp1_proposals() -> list[SemanticProposal]:
    path = Path(__file__).resolve().parents[2] / "docs" / "reports" / "i129_artifacts" / "checkpoint.jsonl"
    out: list[SemanticProposal] = []
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if not str(row.get("utterance", "")).casefold().startswith("medi a temperatura e deu 95"):
            continue
        dump = row.get("proposal_dump")
        if not dump:
            continue
        try:
            out.append(SemanticProposal.model_validate(dump))
        except Exception:
            continue
    return out


CORPUS = build_corpus()
