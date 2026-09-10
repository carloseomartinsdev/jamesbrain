"""Alembic stub — NON-AUTHORITATIVE. Canonical: pke.persist.migrations.runner."""

revision = "003_storage_v4_state_dimension_value"
down_revision = "002_storage_v3_state_primitive"

_MSG = (
    "Alembic is not the PKE schema authority. "
    "Use pke.persist.migrations.runner.upgrade_to_current "
    "(see alembic/README.md and ADR 0027)."
)


def upgrade() -> None:
    raise RuntimeError(_MSG)


def downgrade() -> None:
    raise RuntimeError(_MSG)
