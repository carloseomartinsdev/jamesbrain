"""Multi-primitive occurrence vs measurement — shared evidence predicates (I12.5).

Authority for assertion set remains ``collect_assertions`` in router.py.
These helpers only classify evidence already present on SemanticProposal.
They must not invent Event/Measurement from raw text alone.
"""

from __future__ import annotations

from pke.interpretation.semantic.models import SemanticProposal

# Instrument-like subject surface forms already present on the proposal (not lexicon invent).
_INSTRUMENT_SUBJECT_MARKERS = (
    "sensor",
    "termometro",
    "termômetro",
    "balanca",
    "balança",
    "medidor",
    "relogio",
    "relógio",
    "termopar",
)

# Measure-report verbs when the subject is the instrument (MP5 class).
_INSTRUMENT_REPORT_ACTIONS = (
    "mediu",
    "marcou",
    "mostrou",
    "indicou",
    "leu",
    "registrou",
)


def has_measurement_evidence(proposal: SemanticProposal) -> bool:
    """Explicit observation-of-quantity evidence — not Attribute/State by syntax."""
    if proposal.measurement_semantics:
        return True
    if proposal.primitive_hint == "measurement" and (
        proposal.measurement_expression
        or proposal.measurable_dimension_key
        or proposal.measurement_numeric_value
    ):
        return True
    return False


def is_instrument_reading_report(proposal: SemanticProposal) -> bool:
    """True when proposal structure is instrument→reading (MP5), not user act+reading.

    Uses only proposal fields (subject text, action_expression, flags). Does not
    reconstruct frames from raw utterance text.
    """
    if proposal.change_semantics:
        return False
    if proposal.lifecycle_cue in {"start", "end"}:
        return False
    if proposal.event_expression and proposal.change_semantics:
        return False

    subject_text = (proposal.subject.text if proposal.subject else "") or ""
    subject_l = subject_text.casefold()
    action = (proposal.action_expression or "").casefold().strip()

    instrument_subject = any(m in subject_l for m in _INSTRUMENT_SUBJECT_MARKERS)
    report_action = (not action) or action in _INSTRUMENT_REPORT_ACTIONS or action.startswith(
        "medi"
    )

    # Canonical MP5 shape: measurement hint/semantics, instrument subject, no change act.
    if (
        has_measurement_evidence(proposal)
        and instrument_subject
        and report_action
        and proposal.object is None
    ):
        return True

    # Measurement-only hint with instrument subject and no distinct event expression.
    if (
        proposal.primitive_hint == "measurement"
        and has_measurement_evidence(proposal)
        and instrument_subject
        and not proposal.event_expression
        and not proposal.change_semantics
    ):
        return True

    return False


def has_explicit_occurrence_evidence(proposal: SemanticProposal) -> bool:
    """True when the proposal itself already encodes an action/occurrence.

    Recovery of Event is allowed only when this is True (proposal preservation).
    Instrument reading reports are excluded so MP5 stays Measurement-only.
    """
    if is_instrument_reading_report(proposal):
        return False

    if proposal.change_semantics:
        return True
    if proposal.lifecycle_cue in {"start", "end"}:
        # Link-only lifecycle without occurrence expressions stays Relation (router).
        if (
            proposal.link_semantics
            and proposal.relation_expression
            and not proposal.action_expression
            and not proposal.event_expression
            and not proposal.change_semantics
        ):
            return False
        return True

    if proposal.temporal.occurrence_aspect == "happened" and (
        proposal.action_expression or proposal.event_expression
    ):
        return True

    # Residual: action/event expression already on the proposal (not inferred from raw text).
    if proposal.action_expression or proposal.event_expression:
        return True

    return False
