"""Application — orquestra ingestão. Não interpreta linguagem nem persiste sozinha."""

from pke.application.ask import AskService
from pke.application.ask_results import AskClarification, AskResult, AskStatus
from pke.application.builder import KnowledgeCandidateBuilder
from pke.application.clock import Clock, FixedClock
from pke.application.correction_service import CorrectionRejected, CorrectionService
from pke.application.errors import MaterializationDenied
from pke.application.ingest import IngestService
from pke.application.knowledge_reference import (
    KnowledgeReferenceError,
    KnowledgeReferenceResolver,
)
from pke.application.materializer import ApprovedKnowledge, KnowledgeMaterializer
from pke.application.query_builder import QueryBuildError, ResolvedQueryBuilder
from pke.application.results import IngestResult, IngestStatus, MaterializationResult
from pke.application.session import SessionContext

__all__ = [
    "ApprovedKnowledge",
    "AskClarification",
    "AskResult",
    "AskService",
    "AskStatus",
    "Clock",
    "CorrectionRejected",
    "CorrectionService",
    "FixedClock",
    "IngestResult",
    "IngestService",
    "IngestStatus",
    "KnowledgeCandidateBuilder",
    "KnowledgeMaterializer",
    "KnowledgeReferenceError",
    "KnowledgeReferenceResolver",
    "MaterializationDenied",
    "MaterializationResult",
    "QueryBuildError",
    "ResolvedQueryBuilder",
    "SessionContext",
]
