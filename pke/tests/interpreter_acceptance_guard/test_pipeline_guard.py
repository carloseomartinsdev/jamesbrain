"""Pipeline-level Correction Acceptance Guard (I12.4)."""

from __future__ import annotations

from pke.interpretation.semantic.models import SemanticProposal
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir


def _correction_proposal(raw: str) -> SemanticProposal:
    return SemanticProposal(
        raw_input=raw,
        utterance_kind="correct",
        correction_semantics=True,
        correction_operation="replace",
    )


def test_pipeline_blocks_false_correction_before_ir() -> None:
    outcome = proposal_to_canonical_ir(_correction_proposal("João não trabalha mais na Acme."))
    assert outcome.ir is None
    assert outcome.failure_stage and outcome.failure_stage.startswith("ACCEPTANCE_GUARD:")


def test_pipeline_allows_supported_correction_flag_path() -> None:
    # May still fail later concept resolution; must not fail ACCEPTANCE_GUARD.
    outcome = proposal_to_canonical_ir(_correction_proposal("Corrigindo, foi em 2025."))
    assert not (outcome.failure_stage or "").startswith("ACCEPTANCE_GUARD")
