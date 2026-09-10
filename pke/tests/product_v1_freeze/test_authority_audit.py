"""Product v1 freeze — authority audit (no competing Product authorities)."""

from __future__ import annotations

import ast
from pathlib import Path

from pke.interpretation.prompts import PROMPT_VERSION_V4
from pke.interpretation.retry import MAX_ATTEMPTS, RetryPolicy
from pke.llm.config import DeepSeekConfig
from pke.ontology import OntologyRegistry
from pke.persist.versions import STORAGE_SCHEMA_VERSION
from pke.product.conversation.store import PRODUCT_SCHEMA_VERSION

SRC = Path(__file__).resolve().parents[2] / "src" / "pke"
WEB = Path(__file__).resolve().parents[2] / "web"
PRODUCT = SRC / "product"

FINAL_AUTHORITY_MAP: dict[str, str] = {
    "PRODUCT_API_AUTHORITY": "FastAPI /api/v1 routes + DTOs",
    "PRODUCT_IDENTITY_AUTHORITY": "ProductAuthService",
    "PRODUCT_SESSION_AUTHORITY": "ProductAuthService + sessions",
    "PRODUCT_RESOURCE_OWNERSHIP_AUTHORITY": "ConversationOrchestrator + scoped store",
    "CONVERSATION_LIFECYCLE_AUTHORITY": "ConversationOrchestrator",
    "MESSAGE_LIFECYCLE_AUTHORITY": "ConversationOrchestrator",
    "PENDING_CLARIFICATION_AUTHORITY": "ConversationOrchestrator",
    "PRODUCT_IDEMPOTENCY_AUTHORITY": "ProductStore + ProductRecoveryService",
    "PRODUCT_RECOVERY_AUTHORITY": "ProductRecoveryService",
    "PUBLIC_OUTCOME_RENDERING_AUTHORITY": "web/assets/js/renderers/index.js",
    "ENGINE_INVOCATION_AUTHORITY": "ConversationOrchestrator → EngineGateway",
    "INTERPRETER_AUTHORITY": "Interpreter",
    "EXECUTION_READINESS_AUTHORITY": "ExecutionReadiness",
    "CAPABILITY_STRATEGY_AUTHORITY": "CapabilityStrategy",
    "CLARIFICATION_RECOVERY_AUTHORITY": "ClarificationRecoveryService",
    "CORRECTION_ACCEPTANCE_AUTHORITY": "Correction Acceptance Guard",
    "CORRECTION_TARGET_AUTHORITY": "CorrectionTargetResolver",
    "ASSERTION_EFFECTIVENESS_AUTHORITY": "AssertionEffectivenessResolver",
    "ENTITY_RESOLUTION_AUTHORITY": "EntityResolver",
    "TEMPORAL_WRITE_AUTHORITY": "TemporalResolver",
    "TEMPORAL_QUERY_AUTHORITY": "QueryTemporalResolver",
    "STATE_EPISTEMIC_AUTHORITY": "StateResolver",
    "RELATION_EPISTEMIC_AUTHORITY": "Relation authorities",
    "ATTRIBUTE_EPISTEMIC_AUTHORITY": "AttributeResolver",
    "MEASUREMENT_QUERY_AUTHORITY": "Measurement query authority",
    "KNOWLEDGE_COMMIT_AUTHORITY": "IngestService / UoW",
}


def test_final_authority_map_complete() -> None:
    assert len(FINAL_AUTHORITY_MAP) >= 25


def test_single_conversation_orchestrator() -> None:
    hits = []
    for path in PRODUCT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "ConversationOrchestrator":
                hits.append(path.relative_to(SRC).as_posix())
    assert hits == ["product/conversation/orchestrator.py"]


def test_single_product_recovery_service() -> None:
    hits = []
    for path in PRODUCT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "ProductRecoveryService":
                hits.append(path.relative_to(SRC).as_posix())
    assert hits == ["product/conversation/recovery.py"]


def test_single_engine_gateway() -> None:
    hits = []
    for path in PRODUCT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "EngineGateway":
                hits.append(path.relative_to(SRC).as_posix())
    assert hits == ["product/conversation/engine_gateway.py"]


def test_no_competing_decide_capability_in_product() -> None:
    hits = []
    for path in PRODUCT.rglob("*.py"):
        if "def decide_capability" in path.read_text(encoding="utf-8"):
            hits.append(path.name)
    assert hits == []


def test_final_authority_conflict_count() -> None:
    conflicts = 0
    # Product must not redefine ClarificationRecoveryService
    for path in PRODUCT.rglob("*.py"):
        if "class ClarificationRecoveryService" in path.read_text(encoding="utf-8"):
            conflicts += 1
    assert conflicts == 0


def test_core_engine_freeze_versions() -> None:
    reg = OntologyRegistry.with_core_seeds()
    assert STORAGE_SCHEMA_VERSION == "11"
    assert PRODUCT_SCHEMA_VERSION == "1.4"
    assert len(list(reg.concepts())) == 67
    assert reg.core_frozen is True
    assert str(PROMPT_VERSION_V4).startswith("pke.interpret.v4")
    assert MAX_ATTEMPTS == 2
    assert RetryPolicy().max_attempts == 2
    assert DeepSeekConfig.model_fields["max_retries"].default == 0


def test_web_ir_isolation() -> None:
    banned = [
        "SemanticProposal",
        "QueryIR",
        "IngestIR",
        "ExecutionReadiness",
        "CapabilityStrategy",
        "PendingSemanticOperation",
        "KnowledgeCandidate",
    ]
    hits = []
    for path in WEB.rglob("*"):
        if path.suffix not in {".js", ".html", ".css"}:
            continue
        text = path.read_text(encoding="utf-8")
        for token in banned:
            if token in text:
                hits.append(f"{path.name}:{token}")
    assert hits == []


def test_public_dto_modules_avoid_engine_ir_imports() -> None:
    dto = (PRODUCT / "api" / "v1" / "dtos.py").read_text(encoding="utf-8")
    for token in ("SemanticProposal", "IngestIR", "QueryIR", "ResolutionResult"):
        assert token not in dto
