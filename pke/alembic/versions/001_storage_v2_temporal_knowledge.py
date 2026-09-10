"""Alembic stub — NON-AUTHORITATIVE. Canonical: pke.persist.migrations.runner."""

revision = "001"
down_revision = None
branch_labels = None
depends_on = None

_MSG = (
    "Alembic is not the PKE schema authority. "
    "Use pke.persist.migrations.runner.upgrade_to_current "
    "(see alembic/README.md and ADR 0027)."
)


def upgrade() -> None:
    raise RuntimeError(_MSG)


def downgrade() -> None:
    raise RuntimeError(_MSG)
