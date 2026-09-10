"""Measurement dimension/value resolution — structured cues only, no number→Measurement inventiveness."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from pke.interpretation.semantic.aliases import normalize_expression
from pke.interpretation.semantic.models import SemanticProposal

# Units are not dimensions
_FORBIDDEN_DIMENSION_KEYS = frozenset(
    {"percent", "%", "kg", "liters", "l", "value", "reading", "r$", "$", "unit"}
)

# Controlled clarification-answer → measurement dimension map (exact match only).
# Not a free-text Interpreter — static vocabulary for Measurement.dimension recovery.
_MEASUREMENT_DIMENSION_ANSWER_ALIASES: dict[str, str] = {
    "temperatura": "temperature",
    "temperature": "temperature",
    "temp": "temperature",
    "peso": "weight",
    "weight": "weight",
    "saldo": "balance",
    "balance": "balance",
    "altura": "height",
    "height": "height",
    "volume": "volume",
    "pressao": "pressure",
    "pressão": "pressure",
    "pressure": "pressure",
    "distancia": "distance",
    "distância": "distance",
    "distance": "distance",
}


def resolve_measurement_dimension_key_from_answer(answer: str) -> str | None:
    """Map clarification answer text to a Measurement dimension key.

    Exact normalized match only. Does not scan the original utterance.
    """
    text = normalize_expression(answer or "")
    if not text:
        return None
    # Consume only the dimension head if user added extra content.
    head = text.split(",")[0].strip()
    head = head.split()[0] if head else ""
    # Prefer full-phrase match first, then single-token head.
    for candidate in (text, head):
        key = _MEASUREMENT_DIMENSION_ANSWER_ALIASES.get(candidate)
        if key and key.lower() not in _FORBIDDEN_DIMENSION_KEYS:
            return key
    # Multi-word exact keys (none today) — also try first two tokens.
    parts = text.split()
    if len(parts) >= 2:
        two = " ".join(parts[:2])
        key = _MEASUREMENT_DIMENSION_ANSWER_ALIASES.get(two)
        if key and key.lower() not in _FORBIDDEN_DIMENSION_KEYS:
            return key
    return None


@dataclass(frozen=True)
class ResolvedMeasurementValue:
    dimension_key: str
    numeric_value: Decimal
    unit: str | None = None
    currency_code: str | None = None


def resolve_measurement_value(proposal: SemanticProposal) -> ResolvedMeasurementValue | None:
    """Map Measurement proposals to dimension + Decimal value.

    Requires measurement_semantics (or equivalent structured evidence) and
    identifiable dimension + numeric value. Does not scan raw text for units
    to invent Measurement.
    """
    if not (
        proposal.measurement_semantics
        or proposal.primitive_hint == "measurement"
        or proposal.measurable_dimension_key
        or proposal.measurement_numeric_value
    ):
        return None

    dim = (proposal.measurable_dimension_key or "").strip()
    if not dim or dim.lower() in _FORBIDDEN_DIMENSION_KEYS:
        return None

    raw_num = proposal.measurement_numeric_value
    if raw_num is None:
        return None
    try:
        numeric = Decimal(str(raw_num).replace(",", "."))
    except (InvalidOperation, ValueError):
        return None

    unit = proposal.measurement_unit
    currency = proposal.measurement_currency_code
    if unit and currency:
        # Physical unit and currency must not coexist under frozen contract
        return None
    if currency:
        currency = currency.upper()
        unit = None

    return ResolvedMeasurementValue(
        dimension_key=dim,
        numeric_value=numeric,
        unit=unit,
        currency_code=currency,
    )
