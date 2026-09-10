# ADR 0027 — Canonical Migration Architecture (I11.10.2 / MIGRATION-01)

## Status

Accepted — MIGRATION-01 **CLOSED**

## Context

I11.10.1 justified schema v7 (`event_participants`) but required:

```text
MIGRATION-01 = MUST_RESOLVE_BEFORE_V7
```

v6→v7 will be the first upgrade with schema evolution + semantic data backfill + dual-read. Dual migration authorities are unacceptable.

## Problem

Before I11.10.2:

- **De-facto authority:** Python scripts under `pke.persist.migrations` called from `init_database()`
- **Parallel artifacts:** `alembic/versions/*` stubs (empty/`pass` upgrades), no `alembic.ini` in repo root used for production
- Fresh DB: `Base.metadata.create_all` (latest ORM) + stamp `schema_meta` to current + call each migrate (no-ops)
- Existing DB: same migrate chain, each step early-returns if already past its `from_version`
- No single registry, no unsupported-future guard, conceptual dual authority risk

## HOW_DOES_SCHEMA_EVOLUTION_ACTUALLY_WORK_TODAY? (post I11.10.2)

```text
open_sqlite_uow / open_sqlite_read_store
  → create_sqlite_engine
  → init_database(engine)
       1. Base.metadata.create_all          # latest ORM shape
       2. install SQLite triggers
       3. ensure_schema_meta_row            # stamp STORAGE_SCHEMA_VERSION if empty
       4. upgrade_to_current(engine)        # canonical runner
            read schema_meta.storage_schema_version
            while version < CURRENT:
              run MIGRATIONS[version]
            if version > CURRENT: UnsupportedSchemaVersion
```

```text
HOW_DOES_PKE_UPGRADE_STORAGE_SCHEMA?
→ pke.persist.migrations.runner.upgrade_to_current

WHAT_IS_THE_SINGLE_MIGRATION_AUTHORITY?
→ Python migration runner (explicit MIGRATIONS registry)
```

## Alternatives

| Approach | Schema | Data migration | SQLite | Testability | Ops simplicity | Long-term |
|---|---:|---:|---:|---:|---:|---:|
| **A Python runner canonical** | 5 | 5 | 5 | 5 | 5 | 5 |
| B Alembic canonical | 5 | 4 | 3 | 4 | 3 | 4 |
| C hybrid | 3 | 3 | 3 | 2 | 1 | 1 |
| D recreate from models | 4 | 1 | 4 | 3 | 4 | 1 |

Chosen **A**: already production path; supports deterministic semantic backfill; SQLite-friendly; no second tool.

## Decision

```text
SINGLE_SCHEMA_MIGRATION_AUTHORITY = YES
PYTHON_MIGRATION_RUNNER = CANONICAL
ALEMBIC_STATUS = REMOVED_FROM_AUTHORITY
MIGRATION_DIRECTION = FORWARD_ONLY
DETERMINISTIC_MIGRATION = YES
```

Alembic stubs remain as documentation history; `upgrade()`/`downgrade()` raise `RuntimeError`. See `alembic/README.md`.

## Version source

```text
WHAT_IS_THE_CANONICAL_SCHEMA_VERSION_SOURCE?
schema_meta.storage_schema_version

Application target constant:
pke.persist.versions.STORAGE_SCHEMA_VERSION
(= runner.CURRENT_SCHEMA_VERSION)
```

No `PRAGMA user_version`. No Alembic revision as authority.

## Fresh database

```text
DOES_FRESH_DATABASE_CREATION_USE_MIGRATIONS?
PARTIALLY
```

Fresh path creates **latest** ORM schema via `create_all`, stamps current version, then runs runner (no-op). Historical migrations are not replayed for greenfield DBs.

Invariant:

```text
fresh database schema == fully migrated historical database schema
(structurally — table/column names)
```

Protected by equivalence tests (M6).

## Existing database

Ordered upgrades via registry `1→2→…→6`. No silent skipping. Multi-hop verified (`4→5→6`).

## Transactions / failure

Each existing step uses `engine.begin()` (one transaction per step). On failure, version must not advance; runner wraps unexpected errors as `MigrationFailed` and verifies version unchanged.

Future / unknown version `> CURRENT` → `UnsupportedSchemaVersion` (no auto-downgrade).

Missing `schema_meta` → `InvalidSchemaState`.

## Idempotency

Runner does not re-apply completed steps (version gate). Individual scripts may still early-return if re-invoked directly.

## Rollback

```text
FORWARD_ONLY
```

Knowledge store downgrades risk semantic loss; restore from backup instead.

## Operational backup

Not implemented. Future production ops: backup SQLite file before upgrade.

## Startup

`init_database` still auto-upgrades on open (dev + current app path). Authority remains the Python runner — not a second path. Production ops may later gate auto-migrate; not required to close MIGRATION-01.

## Ontology seeds

Schema migration ≠ CORE seed sync. Seeds load in-memory via `OntologyRegistry`; `core_schema_version` stored in `schema_meta` for bookkeeping only.

## Provider independence

Migration package must not import LLM/provider layers. Enforced by AST test.

## Testing

M1 fresh→v6 · M2 v5→v6 · M3 v6 no-op · M4 v7 fail · M5 fail keeps version · M6 equivalence · multi-hop · data preservation · Alembic stub raise · provider independence.

## v7 readiness

```text
IS_MIGRATION_INFRASTRUCTURE_READY_FOR_V7?
YES
```

Add `MigrationStep(6, 7, migrate_v6_to_v7, "v6_to_v7")` when implementing I11.10.x storage — not in this increment.

## MIGRATION-01

```text
CLOSED
```

Exactly one executable authority; Alembic cannot succeed as a competing upgrade path.

## Non-scope confirmed

Schema remains **v6**. No `event_participants`. No v7 migration.
