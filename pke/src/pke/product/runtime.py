"""Composição do produto. Não altera o Knowledge Core."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from pke.application.ask import AskService
from pke.application.clarification_recovery import ClarificationRecoveryService
from pke.application.clock import Clock
from pke.application.ingest import IngestService
from pke.interpretation.deepseek_interpreter import DeepSeekInterpreter
from pke.interpretation.interpreter import Interpreter
from pke.llm import DeepSeekConfig, DeepSeekProvider
from pke.llm.errors import LlmConfigurationError
from pke.ontology import OntologyRegistry
from pke.persist.sqlite.engine import create_sqlite_engine, init_database, session_factory, sqlite_url
from pke.persist.sqlite.read_store import SqliteKnowledgeReadStore
from pke.persist.sqlite.uow import SqliteUnitOfWork
from pke.persist.versions import DEFAULT_SQLITE_PATH
from pke.product.auth import AUTH_MODE_DEV, ProductAuthResolver, resolve_auth_mode
from pke.product.conversation.engine_gateway import EngineGateway, TurnCachedInterpreter
from pke.product.conversation.orchestrator import ConversationOrchestrator
from pke.product.conversation.recovery import ProductRecoveryService
from pke.product.conversation.store import ProductStore
from pke.product.identity import DEFAULT_SESSION_TTL_SECONDS, ProductAuthService

DEFAULT_PRODUCT_DB = "data/pke_product.db"


class SystemClock:
    def now(self):
        import datetime as dt

        return dt.datetime.now(dt.UTC)


@dataclass
class ProductRuntime:
    orchestrator: ConversationOrchestrator
    knowledge: SqliteKnowledgeReadStore
    knowledge_db: Path
    product_db: Path
    debug_ui: bool
    cors_origins: list[str]
    web_root: Path
    auth_resolver: ProductAuthResolver
    auth_service: ProductAuthService | None
    auth_mode: str
    ontology: OntologyRegistry

    @classmethod
    def build(
        cls,
        *,
        interpreter: Interpreter,
        knowledge_db: str | Path,
        product_db: str | Path,
        web_root: str | Path | None = None,
        debug_ui: bool = False,
        cors_origins: list[str] | None = None,
        timezone: str = "America/Fortaleza",
        clock: Clock | None = None,
        ontology: OntologyRegistry | None = None,
        auth_mode: str | None = None,
        session_ttl_seconds: int | None = None,
        idempotency_stale_seconds: int | None = None,
    ) -> ProductRuntime:
        knowledge_path = Path(knowledge_db)
        product_path = Path(product_db)
        ontology = ontology or OntologyRegistry.with_core_seeds()
        clock = clock or SystemClock()
        engine = create_sqlite_engine(sqlite_url(knowledge_path))
        init_database(engine)
        from pke.interpretation.transport.catalog import ConceptCatalog
        from pke.ontology.learned import (
            hydrate_learned_attribute_dimensions,
            hydrate_learned_entity_types,
            hydrate_learned_relation_types,
        )
        from pke.ontology.trained import apply_trained_catalog

        apply_trained_catalog(ontology)
        hydrate_learned_relation_types(ontology, engine)
        hydrate_learned_entity_types(ontology, engine)
        hydrate_learned_attribute_dimensions(ontology, engine)
        from pke.interpretation.semantic.learned_attribute import publish_learned_attribute_dimension
        from pke.ontology.learned import is_learned_attribute_key

        for concept in ontology.concepts():
            if is_learned_attribute_key(concept.key):
                label = concept.presentation.label if concept.presentation is not None else None
                publish_learned_attribute_dimension(concept.key, label=label)
        ConceptCatalog.load(ontology)
        factory = session_factory(engine)
        cached = TurnCachedInterpreter(interpreter)
        ingest = IngestService(
            cached,  # type: ignore[arg-type]
            ontology,
            lambda: SqliteUnitOfWork(factory),
            clock,
        )
        ask = AskService(cached, ontology, SqliteKnowledgeReadStore(factory), clock)  # type: ignore[arg-type]
        gateway = EngineGateway(cached, ingest, ask)
        store = ProductStore(product_path)
        knowledge = SqliteKnowledgeReadStore(factory)
        clarification_recovery = ClarificationRecoveryService(ingest)
        product_recovery = ProductRecoveryService(
            store,
            stale_after_seconds=idempotency_stale_seconds,
            clock=lambda: clock.now(),
        )
        orchestrator = ConversationOrchestrator(
            store,
            gateway,
            knowledge,
            timezone=timezone,
            debug_ui=debug_ui,
            clarification_recovery=clarification_recovery,
            product_recovery=product_recovery,
        )
        mode = resolve_auth_mode(auth_mode)
        ttl = session_ttl_seconds
        if ttl is None:
            raw_ttl = os.environ.get("PKE_SESSION_TTL_SECONDS", "").strip()
            ttl = int(raw_ttl) if raw_ttl else DEFAULT_SESSION_TTL_SECONDS
        auth_service: ProductAuthService | None = None
        if mode != AUTH_MODE_DEV:
            auth_service = ProductAuthService(store, session_ttl_seconds=ttl)
        auth_resolver = ProductAuthResolver(auth_service, mode=mode)
        root = Path(web_root) if web_root else _default_web_root()
        return cls(
            orchestrator=orchestrator,
            knowledge=knowledge,
            knowledge_db=knowledge_path,
            product_db=product_path,
            debug_ui=debug_ui,
            cors_origins=cors_origins or _default_cors(),
            web_root=root,
            auth_resolver=auth_resolver,
            auth_service=auth_service,
            auth_mode=mode,
            ontology=ontology,
        )

    @classmethod
    def from_env(cls, interpreter: Interpreter | None = None) -> ProductRuntime:
        knowledge = os.environ.get("PKE_KNOWLEDGE_DB", DEFAULT_SQLITE_PATH)
        product = os.environ.get("PKE_PRODUCT_DB", DEFAULT_PRODUCT_DB)
        debug = os.environ.get("PKE_DEBUG_UI", "").lower() in {"1", "true", "yes"}
        timezone = os.environ.get("PKE_USER_TIMEZONE", "America/Fortaleza")
        if interpreter is None:
            interpreter = _live_or_missing()
        return cls.build(
            interpreter=interpreter,
            knowledge_db=knowledge,
            product_db=product,
            debug_ui=debug,
            timezone=timezone,
        )


def _live_or_missing() -> Interpreter:
    try:
        cfg = DeepSeekConfig.from_env()
    except LlmConfigurationError:
        return _MissingProviderInterpreter()
    return DeepSeekInterpreter(DeepSeekProvider(cfg), OntologyRegistry.with_core_seeds())


class _MissingProviderInterpreter:
    def interpret(self, raw: str, ctx) -> object:
        from pke.interpretation.interpreter import InterpretationError
        from pke.llm.errors import LlmConfigurationError

        del raw, ctx
        raise InterpretationError("provider: DEEPSEEK_API_KEY ausente") from LlmConfigurationError(
            "DEEPSEEK_API_KEY ausente"
        )


def _default_web_root() -> Path:
    return Path(__file__).resolve().parents[3] / "web"


def _default_cors() -> list[str]:
    raw = os.environ.get("PKE_CORS_ORIGINS", "").strip()
    if raw:
        return [item.strip() for item in raw.split(",") if item.strip()]
    return [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
