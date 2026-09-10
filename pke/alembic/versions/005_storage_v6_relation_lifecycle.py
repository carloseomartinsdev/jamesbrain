"""Alembic stub — NON-AUTHORITATIVE. Canonical: pke.persist.migrations.runner."""

revision = "005_storage_v6_relation_lifecycle"
down_revision = "004_storage_v5_relation_evolution"

_MSG = (
    "Alembic is not the PKE schema authority. "
    "Use pke.persist.migrations.runner.upgrade_to_current "
    "(see alembic/README.md and ADR 0027)."
)


def upgrade() -> None:
    raise RuntimeError(_MSG)


def downgrade() -> None:
    raise RuntimeError(_MSG)
