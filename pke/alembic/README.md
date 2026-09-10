# Alembic — NON-AUTHORITATIVE

PKE storage schema evolution is owned exclusively by:

```text
pke.persist.migrations.runner.upgrade_to_current
```

Files in this directory are **historical reference stubs only**.

- Do **not** run `alembic upgrade`
- Do **not** treat empty/`pass` upgrades as migrations
- Calling `upgrade()` on these stubs raises `RuntimeError`

See ADR `docs/decisions/0027-canonical-migration-architecture.md`.

```text
ALEMBIC_STATUS = REMOVED_FROM_AUTHORITY
PYTHON_MIGRATION_RUNNER = CANONICAL
SINGLE_SCHEMA_MIGRATION_AUTHORITY = YES
```
