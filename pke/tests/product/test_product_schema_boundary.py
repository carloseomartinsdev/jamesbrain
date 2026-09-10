from __future__ import annotations

from pke.ontology import OntologyRegistry
from pke.persist.sqlite.tables import Base
from pke.persist.versions import STORAGE_SCHEMA_VERSION
from pke.product.conversation.store import PRODUCT_SCHEMA_VERSION


def test_product_storage_is_isolated_from_core() -> None:
    assert STORAGE_SCHEMA_VERSION == "11"
    assert PRODUCT_SCHEMA_VERSION == "1.4"
    core_tables = set(Base.metadata.tables)
    # Product conversation/auth tables are not Knowledge ORM tables.
    # Knowledge may still have isolation key `users` (not Product account rows).
    assert "conversations" not in core_tables
    assert "messages" not in core_tables
    assert "clarifications" not in core_tables
    assert "idempotency" not in core_tables
    assert "sessions" not in core_tables
    assert "auth_events" not in core_tables
    assert "product_schema_meta" not in core_tables
    assert len(list(OntologyRegistry.with_core_seeds().concepts())) == 67
