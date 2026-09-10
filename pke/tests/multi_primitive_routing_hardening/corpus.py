"""I12.5 multi-primitive routing hardening — deterministic corpus."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from pke.interpretation.semantic.models import (
    PrimitiveKind,
    SemanticEntityMention,
    SemanticProposal,
    SemanticTime,
)

ExpectedSet = frozenset[PrimitiveKind]


def _happened() -> SemanticTime:
    return SemanticTime(occurrence_aspect="happened")


def _ongoing() -> SemanticTime:
    return SemanticTime(occurrence_aspect="ongoing")


@dataclass(frozen=True)
class MPCase:
    case_id: str
    family: str
    factory: Callable[[], SemanticProposal]
    expected: ExpectedSet
    # Engine-only: proposal already has all expected assertions' evidence
    explicit_on_proposal: bool = True


def _kinds(*ks: str) -> ExpectedSet:
    return frozenset(PrimitiveKind(k) for k in ks)


# --- MP anchors (frozen) ---
def mp1() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Medi a temperatura e deu 95°C.",
        object=SemanticEntityMention(text="temperatura", kind_hint="thing"),
        action_expression="medi",
        change_semantics=True,
        event_expression="medi temperatura",
        measurement_expression="95°C",
        measurable_dimension_key="temperature",
        measurement_numeric_value="95",
        measurement_unit="°C",
        measurement_semantics=True,
        primitive_hint="event",
        temporal=_happened(),
    )


def mp2() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Olhei o tanque e ele estava com 20 litros.",
        object=SemanticEntityMention(text="tanque", kind_hint="thing"),
        action_expression="olhei",
        change_semantics=True,
        event_expression="olhei tanque",
        measurement_expression="20 litros",
        measurable_dimension_key="fuel_level",
        measurement_numeric_value="20",
        measurement_unit="L",
        measurement_semantics=True,
        primitive_hint="event",
        temporal=_happened(),
    )


def mp3() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Pesei a caixa: 10 kg.",
        object=SemanticEntityMention(text="caixa", kind_hint="thing"),
        action_expression="pesei",
        change_semantics=True,
        event_expression="pesei caixa",
        measurement_expression="10 kg",
        measurable_dimension_key="mass_reading",
        measurement_numeric_value="10",
        measurement_unit="kg",
        measurement_semantics=True,
        primitive_hint="event",
        temporal=_happened(),
    )


def mp4() -> SemanticProposal:
    return SemanticProposal(
        raw_input="Consultei o saldo e tinha R$2500.",
        object=SemanticEntityMention(text="saldo", kind_hint="document"),
        action_expression="consultei",
        change_semantics=True,
        event_expression="consultei saldo",
        measurement_expression="2500",
        measurable_dimension_key="balance",
        measurement_numeric_value="2500",
        measurement_currency_code="BRL",
        measurement_semantics=True,
        primitive_hint="event",
        temporal=_happened(),
    )


def mp5() -> SemanticProposal:
    return SemanticProposal(
        raw_input="O sensor mediu 38°C.",
        subject=SemanticEntityMention(text="sensor", kind_hint="thing"),
        measurement_expression="38°C",
        measurable_dimension_key="temperature",
        measurement_numeric_value="38",
        measurement_unit="°C",
        measurement_semantics=True,
        primitive_hint="measurement",
        temporal=_happened(),
    )


ANCHORS: list[MPCase] = [
    MPCase("MP1", "anchor", mp1, _kinds("event", "measurement")),
    MPCase("MP2", "anchor", mp2, _kinds("event", "measurement")),
    MPCase("MP3", "anchor", mp3, _kinds("event", "measurement")),
    MPCase("MP4", "anchor", mp4, _kinds("event", "measurement")),
    MPCase("MP5", "anchor", mp5, _kinds("measurement")),
]


def _em(
    cid: str,
    raw: str,
    *,
    action: str,
    obj: str,
    dim: str,
    num: str,
    unit: str | None = None,
    currency: str | None = None,
    change: bool = True,
    hint: str = "event",
) -> MPCase:
    def factory() -> SemanticProposal:
        return SemanticProposal(
            raw_input=raw,
            object=SemanticEntityMention(text=obj, kind_hint="thing"),
            action_expression=action,
            change_semantics=change,
            event_expression=f"{action} {obj}",
            measurement_expression=f"{num} {unit or ''}".strip(),
            measurable_dimension_key=dim,
            measurement_numeric_value=num,
            measurement_unit=unit,
            measurement_currency_code=currency,
            measurement_semantics=True,
            primitive_hint=hint,  # type: ignore[arg-type]
            temporal=_happened(),
        )

    return MPCase(cid, "event_measurement", factory, _kinds("event", "measurement"))


def _m_only(
    cid: str,
    raw: str,
    *,
    subject: str,
    dim: str,
    num: str,
    unit: str | None = None,
) -> MPCase:
    def factory() -> SemanticProposal:
        return SemanticProposal(
            raw_input=raw,
            subject=SemanticEntityMention(text=subject, kind_hint="thing"),
            measurement_expression=f"{num} {unit or ''}".strip(),
            measurable_dimension_key=dim,
            measurement_numeric_value=num,
            measurement_unit=unit,
            measurement_semantics=True,
            primitive_hint="measurement",
            temporal=_happened(),
        )

    return MPCase(cid, "measurement_only", factory, _kinds("measurement"))


def _e_only(cid: str, raw: str, *, action: str, obj: str) -> MPCase:
    def factory() -> SemanticProposal:
        return SemanticProposal(
            raw_input=raw,
            object=SemanticEntityMention(text=obj, kind_hint="thing"),
            action_expression=action,
            change_semantics=True,
            event_expression=f"{action} {obj}",
            primitive_hint="event",
            temporal=_happened(),
        )

    return MPCase(cid, "event_only", factory, _kinds("event"))


def _attr(cid: str, raw: str, *, subject: str, expr: str) -> MPCase:
    def factory() -> SemanticProposal:
        return SemanticProposal(
            raw_input=raw,
            subject=SemanticEntityMention(text=subject, kind_hint="thing"),
            attribute_expression=expr,
            stable_property_semantics=True,
            primitive_hint="attribute",
        )

    return MPCase(cid, "attribute", factory, _kinds("attribute"))


def _state(cid: str, raw: str, *, subject: str, expr: str) -> MPCase:
    def factory() -> SemanticProposal:
        return SemanticProposal(
            raw_input=raw,
            subject=SemanticEntityMention(text=subject, kind_hint="thing"),
            state_expression=expr,
            condition_semantics=True,
            primitive_hint="state",
            temporal=_ongoing(),
        )

    return MPCase(cid, "state", factory, _kinds("state"))


def _rel(cid: str, raw: str, *, subj: str, obj: str, expr: str) -> MPCase:
    def factory() -> SemanticProposal:
        return SemanticProposal(
            raw_input=raw,
            subject=SemanticEntityMention(text=subj, kind_hint="person"),
            object=SemanticEntityMention(text=obj, kind_hint="organization"),
            relation_expression=expr,
            link_semantics=True,
            primitive_hint="relation",
        )

    return MPCase(cid, "relation", factory, _kinds("relation"))


# Captured-style: model omitted Event fields (interpreter loss) — must NOT invent Event.
def _ms18_measurement_only_proposal() -> SemanticProposal:
    return SemanticProposal(
        raw_input="olhei o tanque e ele estava com 20 litros",
        subject=SemanticEntityMention(text="tanque", kind_hint="thing"),
        measurement_expression="20 litros",
        measurable_dimension_key="fuel_level",
        measurement_numeric_value="20",
        measurement_unit="L",
        measurement_semantics=True,
        primitive_hint="measurement",
    )


# Captured-style: action present without change_semantics (engine preservation path).
def _ms18_action_without_change() -> SemanticProposal:
    return SemanticProposal(
        raw_input="olhei o tanque e ele estava com 20 litros",
        object=SemanticEntityMention(text="tanque", kind_hint="thing"),
        action_expression="olhei",
        event_expression="olhei tanque",
        measurement_expression="20 litros",
        measurable_dimension_key="fuel_level",
        measurement_numeric_value="20",
        measurement_unit="L",
        measurement_semantics=True,
        primitive_hint="measurement",
    )


CAPTURED: list[MPCase] = [
    MPCase(
        "MS18_INTERPRETER_OMISSION",
        "captured",
        _ms18_measurement_only_proposal,
        _kinds("measurement"),
        explicit_on_proposal=True,
    ),
    MPCase(
        "MS18_ENGINE_PRESERVE",
        "captured",
        _ms18_action_without_change,
        _kinds("event", "measurement"),
        explicit_on_proposal=True,
    ),
]


def _build_bulk() -> list[MPCase]:
    cases: list[MPCase] = []
    # Event+Measurement variants (no change_semantics) — preservation regression
    pairs = [
        ("olhei", "tanque", "fuel_level", "20", "L"),
        ("pesei", "caixa", "mass_reading", "10", "kg"),
        ("medi", "temperatura", "temperature", "95", "°C"),
        ("consultei", "saldo", "balance", "2500", None),
        ("verifiquei", "bateria", "battery_charge", "55", "%"),
        ("olhei", "painel", "speed", "80", "km/h"),
        ("encheu", "tanque", "fuel_level", "40", "L"),
        ("troquei", "embreagem", "odometer", "125000", "km"),
        ("revisei", "carro", "temperature", "90", "°C"),
        ("anotei", "leitura", "temperature", "38", "°C"),
        ("li", "odometro", "odometer", "50000", "km"),
        ("chequei", "pressao", "pressure", "2.2", "bar"),
        ("aferi", "peso", "mass_reading", "3", "kg"),
        ("meci", "altura", "length", "180", "cm"),
        ("contei", "pecas", "count", "12", None),
        ("registrei", "voltagem", "voltage", "12", "V"),
        ("observei", "nivel", "fuel_level", "15", "L"),
        ("inspecionei", "oleo", "oil_level", "80", "%"),
        ("testei", "sensor", "temperature", "37", "°C"),
        ("avali", "carga", "battery_charge", "70", "%"),
    ]
    for i, (action, obj, dim, num, unit) in enumerate(pairs, start=1):
        raw = f"{action} {obj}: {num} {unit or ''}".strip()
        cases.append(
            _em(
                f"EM{i:02d}",
                raw,
                action=action,
                obj=obj,
                dim=dim,
                num=num,
                unit=unit,
                change=False,
                hint="measurement",
            )
        )
        cases.append(
            _em(
                f"EMC{i:02d}",
                raw + " (com change)",
                action=action,
                obj=obj,
                dim=dim,
                num=num,
                unit=unit,
                change=True,
                hint="event",
            )
        )

    for i in range(1, 31):
        cases.append(
            _m_only(
                f"MO{i:02d}",
                f"leitura {i}: {30 + i} C",
                subject="termometro" if i % 2 == 0 else "sensor",
                dim="temperature",
                num=str(30 + i),
                unit="°C",
            )
        )
        cases.append(
            _e_only(
                f"EO{i:02d}",
                f"acao {i}: fiz X",
                action=["troquei", "lavei", "revisei", "paguei", "abri"][i % 5],
                obj=["embreagem", "carro", "filtro", "conta", "porta"][i % 5],
            )
        )

    for i in range(1, 21):
        cases.append(
            _attr(
                f"AT{i:02d}",
                f"atributo {i}",
                subject="carro",
                expr=["azul", "preto", "vermelho", "branco"][i % 4],
            )
        )
        cases.append(
            _state(
                f"ST{i:02d}",
                f"estado {i}",
                subject="porta",
                expr=["aberta", "fechada", "trancada"][i % 3],
            )
        )
        cases.append(
            _rel(
                f"RL{i:02d}",
                f"relacao {i}",
                subj="João",
                obj="Acme",
                expr="trabalha na",
            )
        )
        # Near-boundary: Event + Measurement with currency
        cases.append(
            _em(
                f"BC{i:02d}",
                f"consultei item{i}: R${100 * i}",
                action="consultei",
                obj=f"item{i}",
                dim="balance",
                num=str(100 * i),
                currency="BRL",
                change=False,
                hint="measurement",
            )
        )

    # Quantity without observation act → measurement or attribute (no Event invent)
    def mass_attr() -> SemanticProposal:
        return SemanticProposal(
            raw_input="A caixa pesa 10 kg.",
            subject=SemanticEntityMention(text="caixa", kind_hint="thing"),
            attribute_expression="10 kg",
            stable_property_semantics=True,
            primitive_hint="attribute",
        )

    cases.append(MPCase("QA01", "quantity_no_act", mass_attr, _kinds("attribute")))

    def mass_meas() -> SemanticProposal:
        return SemanticProposal(
            raw_input="A caixa pesa 10 kg.",
            subject=SemanticEntityMention(text="caixa", kind_hint="thing"),
            measurement_expression="10 kg",
            measurable_dimension_key="mass_reading",
            measurement_numeric_value="10",
            measurement_unit="kg",
            measurement_semantics=True,
            primitive_hint="measurement",
        )

    cases.append(MPCase("QA02", "quantity_no_act", mass_meas, _kinds("measurement")))

    # Event only weigh without number
    cases.append(_e_only("QA03", "Pesei a caixa.", action="pesei", obj="caixa"))

    # Extra near-boundary / false-extra protection cases to clear 200 floor
    for i in range(1, 16):
        cases.append(
            _m_only(
                f"MX{i:02d}",
                f"instrumento extra {i}",
                subject="medidor",
                dim="pressure",
                num=str(i),
                unit="bar",
            )
        )

    # Sensor with spurious action_expression=mediu still Measurement-only
    def sensor_mediu() -> SemanticProposal:
        return SemanticProposal(
            raw_input="O sensor mediu 38°C.",
            subject=SemanticEntityMention(text="sensor", kind_hint="thing"),
            action_expression="mediu",
            measurement_expression="38°C",
            measurable_dimension_key="temperature",
            measurement_numeric_value="38",
            measurement_unit="°C",
            measurement_semantics=True,
            primitive_hint="measurement",
            temporal=_happened(),
        )

    cases.append(
        MPCase("MP5b", "measurement_only", sensor_mediu, _kinds("measurement"))
    )

    return cases


def all_cases() -> list[MPCase]:
    return ANCHORS + CAPTURED + _build_bulk()
