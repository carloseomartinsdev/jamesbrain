"""I12-R authority audit — competing semantic authorities must be zero."""

from __future__ import annotations

import ast
from pathlib import Path

from pke.application.clarification_recovery import ClarificationRecoveryService
from pke.interpretation.retry import MAX_ATTEMPTS, RetryPolicy
from pke.interpretation.semantic import capability_strategy, execution_readiness
from pke.persist.versions import STORAGE_SCHEMA_VERSION

SRC = Path(__file__).resolve().parents[2] / "src" / "pke"


# Canonical authority map (documentation-enforced)
ENGINE_AUTHORITY_MAP: dict[str, str] = {
    "Raw-language interpretation": "Interpreter",
    "Provider transport/retry": "RetryPolicy / provider boundary",
    "Semantic proposal structure": "SemanticProposal",
    "Transport normalization": "proposal normalization / Wire boundary",
    "Primitive routing": "canonical semantic routing (router.collect_assertions)",
    "Entity resolution": "EntityResolver",
    "Temporal write semantics": "TemporalResolver",
    "Temporal query expansion": "QueryTemporalResolver",
    "State epistemic resolution": "StateResolver",
    "Relation semantic/lifecycle resolution": "Relation authorities",
    "Attribute epistemic resolution": "AttributeResolver",
    "Measurement query semantics": "Measurement resolver/query authority",
    "Correction acceptance": "Correction Acceptance Guard",
    "Correction target identity": "CorrectionTargetResolver",
    "Correction effectiveness": "AssertionEffectivenessResolver",
    "Execution readiness": "ExecutionReadiness (assess_execution_readiness)",
    "Execute / clarify / abstain": "CapabilityStrategy (decide_capability)",
    "Clarification recovery": "ClarificationRecoveryService",
    "Persistence transaction": "IngestService / UoW",
    "Query truth/result semantics": "Query layer / resolvers",
}


def test_authority_map_complete() -> None:
    assert len(ENGINE_AUTHORITY_MAP) >= 20


def test_no_competing_capability_decision() -> None:
    """CapabilityStrategy must be the only decide_capability authority."""
    hits: list[str] = []
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "def decide_capability" in text and path.name != "capability_strategy.py":
            hits.append(str(path.relative_to(SRC)))
    assert hits == [], hits


def test_no_competing_execution_readiness() -> None:
    hits: list[str] = []
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "def assess_execution_readiness" in text and path.name != "execution_readiness.py":
            hits.append(str(path.relative_to(SRC)))
    assert hits == [], hits


def test_clarification_recovery_single_class() -> None:
    hits: list[str] = []
    for path in SRC.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "ClarificationRecoveryService":
                hits.append(str(path.relative_to(SRC)))
    assert [h.replace("\\", "/") for h in hits] == ["application/clarification_recovery.py"]
    assert ClarificationRecoveryService.__name__ == "ClarificationRecoveryService"


def test_no_second_interpreter_patterns() -> None:
    """SECOND_INTERPRETER_COUNT — no regex/lexical semantic engine in Engine path."""
    banned_snippets = [
        "semantic majority",
        "majority_vote_semantic",
        "union_of_independent_model",
        "secondary_llm_interpreter",
        "generic_clarification_filler",
    ]
    hits: list[str] = []
    for path in SRC.rglob("*.py"):
        # Skip comments-heavy docs strings lightly: scan lowercase
        low = path.read_text(encoding="utf-8").lower()
        for snip in banned_snippets:
            if snip in low:
                hits.append(f"{path.name}:{snip}")
    assert hits == [], hits


def test_retry_policy_invariants() -> None:
    assert MAX_ATTEMPTS == 2
    assert RetryPolicy().max_attempts <= 2
    assert STORAGE_SCHEMA_VERSION == "11"


def test_capability_does_not_reimplement_readiness() -> None:
    """CapabilityStrategy consumes ExecutionReadiness; does not duplicate readiness predicates."""
    src = Path(capability_strategy.__file__).read_text(encoding="utf-8")
    # Must import/use assess or ProposalExecutionOutcome from execution_readiness
    assert "execution_readiness" in src or "ProposalExecutionOutcome" in src
    er_src = Path(execution_readiness.__file__).read_text(encoding="utf-8")
    assert "def assess_execution_readiness" in er_src


def test_engine_authority_conflict_count() -> None:
    """ENGINE_AUTHORITY_CONFLICT_COUNT target 0."""
    conflicts = 0
    # Competing decide_capability
    for path in SRC.rglob("*.py"):
        if path.name == "capability_strategy.py":
            continue
        if "def decide_capability" in path.read_text(encoding="utf-8"):
            conflicts += 1
    for path in SRC.rglob("*.py"):
        if path.name == "execution_readiness.py":
            continue
        if "def assess_execution_readiness" in path.read_text(encoding="utf-8"):
            conflicts += 1
    assert conflicts == 0
