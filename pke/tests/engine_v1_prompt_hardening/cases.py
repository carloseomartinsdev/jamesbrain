"""I12.1 — Interpreter prompt hardening cases (Measurement / Correction / MP).

Deterministic contract tests. Live model success is separate and not closure authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pke.interpretation.semantic.models import (
    PrimitiveKind,
    SemanticEntityMention,
    SemanticProposal,
    SemanticTime,
)


@dataclass(frozen=True)
class HardenCase:
    id: str
    category: Literal["measurement", "correction", "multi_primitive", "regression"]
    summary: str
    proposal: SemanticProposal | None = None
    expected_primitive: PrimitiveKind | None = None
    expected_multi: bool | None = None
    expected_correction: bool | None = None
    expected_not_correction: bool = False


def _happened() -> SemanticTime:
    return SemanticTime(original_text="", occurrence_aspect="happened")


def _ongoing() -> SemanticTime:
    return SemanticTime(original_text="", occurrence_aspect="ongoing")


def build_hardening_cases() -> list[HardenCase]:
    cases: list[HardenCase] = []

    # --- Measurement >= 35 (catalog + fixtures where useful) ---
    meas_summaries = [
        "explicit observation 38C",
        "sensor measurement-only",
        "tank 20L observation",
        "balance currency",
        "percentage battery",
        "count boxes",
        "weight 10kg",
        "distance km",
        "speed",
        "pressure",
        "unitless count",
        "unknown time observation",
        "context entity tank on car",
        "primary entity sensor",
        "Attribute contrast color",
        "State contrast empty",
        "number+unit alone abstention watch",
        "odometer reading",
        "fuel level",
        "temperature partial text",
        "colloquial deu 38 graus",
        "saldo tinha 2500",
        "medi ontem 38",
        "balança indicou 72",
        "termômetro marcou 37",
        "volume 20 litros",
        "R$100",
        "80 por cento",
        "peso uns 10 quilos",
        "velocidade 60",
        "pressao 2 bar",
        "contagem 5",
        "measurement after check act",
        "currency BRL",
        "dimensionless inventory",
        "observation with subject",
        "observation with context",
    ]
    for i, s in enumerate(meas_summaries, 1):
        cases.append(HardenCase(f"MH{i:02d}", "measurement", s))

    # Fixture: Measurement-only (MP5-like)
    cases.append(
        HardenCase(
            "MH_FX_SENSOR",
            "measurement",
            "sensor 38 Measurement only",
            proposal=SemanticProposal(
                raw_input="O sensor mediu 38°C.",
                subject=SemanticEntityMention(text="sensor", kind_hint="thing"),
                measurement_expression="38°C",
                measurable_dimension_key="temperature",
                measurement_numeric_value="38",
                measurement_unit="°C",
                measurement_semantics=True,
                primitive_hint="measurement",
                temporal=_happened(),
            ),
            expected_primitive=PrimitiveKind.MEASUREMENT,
            expected_multi=False,
        )
    )
    # State not Measurement
    cases.append(
        HardenCase(
            "MH_FX_EMPTY",
            "measurement",
            "tank empty is State",
            proposal=SemanticProposal(
                raw_input="O tanque está vazio.",
                subject=SemanticEntityMention(text="tanque", kind_hint="thing"),
                state_expression="vazio",
                condition_semantics=True,
                primitive_hint="state",
                temporal=_ongoing(),
            ),
            expected_primitive=PrimitiveKind.STATE,
            expected_multi=False,
        )
    )
    # Attribute contrast
    cases.append(
        HardenCase(
            "MH_FX_COLOR",
            "measurement",
            "color is Attribute not Measurement",
            proposal=SemanticProposal(
                raw_input="O carro é preto.",
                subject=SemanticEntityMention(text="carro", kind_hint="vehicle"),
                attribute_expression="preto",
                stable_property_semantics=True,
                primitive_hint="attribute",
            ),
            expected_primitive=PrimitiveKind.ATTRIBUTE,
        )
    )

    # --- Correction >= 35 ---
    corr_summaries = [
        "RETRACT desconsidere",
        "REPLACE corrigindo preto",
        "REPLACE li errado 36",
        "REPLACE foi 2025",
        "RETRACT eu me enganei",
        "contradiction without cue",
        "negation only",
        "State evolution now closed",
        "Attribute evolution year",
        "Relation termination",
        "Measurement sequence now 36",
        "Event repetition de novo",
        "query said azul?",
        "ambiguous ele preto",
        "unresolved corrigindo 2025",
        "na verdade preference",
        "nunca without correction",
        "relation correction never worked",
        "state correction olhei errado",
        "attribute correction",
        "event year correction",
        "measurement correction",
        "proposition-wide unsupported",
        "conversational corrigindo o que disse",
        "retract vague isso",
        "replace with measurement payload",
        "replace with attribute payload",
        "no invented id",
        "termination not correction",
        "evolution not correction",
        "new measurement not correction",
        "repeated event not correction",
        "query not correction",
        "negation not correction",
        "contradiction not correction",
        "enrichment not correction",
        "meta-query wrong?",
    ]
    for i, s in enumerate(corr_summaries, 1):
        cases.append(HardenCase(f"CH{i:02d}", "correction", s))

    cases.append(
        HardenCase(
            "CH_FX_REPLACE",
            "correction",
            "explicit REPLACE measurement",
            proposal=SemanticProposal(
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
            ),
            expected_correction=True,
        )
    )
    cases.append(
        HardenCase(
            "CH_FX_TERM",
            "correction",
            "termination not correction",
            proposal=SemanticProposal(
                raw_input="João não trabalha mais na Acme.",
                utterance_kind="assert",
                subject=SemanticEntityMention(text="João", kind_hint="person"),
                object=SemanticEntityMention(text="Acme", kind_hint="organization"),
                relation_expression="não trabalha mais",
                link_semantics=True,
                lifecycle_cue="end",
                correction_semantics=False,
                primitive_hint="relation",
            ),
            expected_correction=False,
            expected_not_correction=True,
            expected_primitive=PrimitiveKind.RELATION,
        )
    )
    cases.append(
        HardenCase(
            "CH_FX_NEG",
            "correction",
            "negation only not correction",
            proposal=SemanticProposal(
                raw_input="O Corolla não é azul.",
                utterance_kind="assert",
                negation=True,
                subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
                attribute_expression="azul",
                stable_property_semantics=True,
                correction_semantics=False,
                primitive_hint="attribute",
            ),
            expected_not_correction=True,
        )
    )

    # --- Multi-primitive >= 25 ---
    mp_summaries = [
        "MP1 medi temperatura 95",
        "MP2 olhei tanque 20L",
        "MP3 pesei caixa 10kg",
        "MP4 consultei saldo 2500",
        "MP5 sensor only",
        "troquei embreagem + odometer",
        "revisei + temperatura",
        "paguei + saldo",
        "encheu tanque 40L",
        "verifiquei bateria 55%",
        "consultei app R$300",
        "olhei painel velocidade",
        "troquei oleo + km",
        "fiz medicao deu 37.5",
        "pesquei balanca 2kg",
        "medi aqui deu 38",
        "pesei a caixa deu 10kg",
        "olhei o tanque tava 20 litros",
        "consultei o saldo tinha 2500",
        "sensor marcou 38 only",
        "termometro mostrou 38 e anotei",
        "check + measurement currency",
        "weigh + mass",
        "look + volume colloquial",
        "measure + temp no punctuation",
        "instrument only no event",
        "event without measurement not multi",
    ]
    for i, s in enumerate(mp_summaries, 1):
        cases.append(HardenCase(f"PH{i:02d}", "multi_primitive", s))

    # --- Regression >= 25 ---
    reg_summaries = [
        "State geladeira quebrada",
        "Event geladeira quebrou",
        "Relation trabalha Acme",
        "Attribute cor preto",
        "TYPE é um carro",
        "Query cor do corolla",
        "Temporal ontem",
        "Temporal ano passado partial",
        "polysemy troquei ideia",
        "State porta aberta",
        "Event troquei embreagem",
        "Relation mora em",
        "Attribute marca toyota",
        "Query boolean event",
        "Query state",
        "Temporal hoje vs agora",
        "Event planned vou trocar",
        "State still open",
        "Relation historical",
        "Attribute area 200m2",
        "Query relation",
        "TYPE cachorro",
        "Event visit dentista",
        "State wifi connected",
        "Attribute model civic",
        "Query measurement latest",
        "Temporal recentemente vague",
    ]
    for i, s in enumerate(reg_summaries, 1):
        cases.append(HardenCase(f"RH{i:02d}", "regression", s))

    # Regression fixtures preserving v3 strengths
    cases.append(
        HardenCase(
            "RH_FX_STATE",
            "regression",
            "state broken",
            proposal=SemanticProposal(
                raw_input="A geladeira está quebrada.",
                subject=SemanticEntityMention(text="geladeira", kind_hint="appliance"),
                state_expression="quebrada",
                condition_semantics=True,
                primitive_hint="state",
                temporal=_ongoing(),
            ),
            expected_primitive=PrimitiveKind.STATE,
        )
    )
    cases.append(
        HardenCase(
            "RH_FX_EVENT",
            "regression",
            "event broke",
            proposal=SemanticProposal(
                raw_input="A geladeira quebrou.",
                subject=SemanticEntityMention(text="geladeira", kind_hint="appliance"),
                event_expression="quebrou",
                change_semantics=True,
                primitive_hint="event",
                temporal=_happened(),
            ),
            expected_primitive=PrimitiveKind.EVENT,
        )
    )

    return cases


HARDENING_CASES = build_hardening_cases()
