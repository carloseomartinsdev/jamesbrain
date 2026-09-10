"""Frozen Measurement v9 storage contract (I11.15.1) — design authority, no migration."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Final

# --- Frozen decisions ---

MEASUREMENT_HAS_IS_CURRENT: Final = False
MEASUREMENT_AUTO_SUPERSEDES: Final = False
CREATED_AT_IS_OBSERVATION_TIME: Final = False
PERCENTAGE_AS_FRACTION: Final = False  # store 80 + unit="%", not 0.80
UNIT_AND_CURRENCY_COEXIST: Final = False
PRIMARY_ENTITY_REQUIRED_FOR_MATERIALIZATION: Final = True
CONTEXT_ENTITY_SUPPORTED: Final = True
DIMENSION_KEY_REQUIRED: Final = True
DIMENSION_CONCEPT_OPTIONAL: Final = True
LEGACY_STATE_OBSERVED_QUANTITY_POLICY: Final = "NO_BACKFILL"
PARTIAL_MATERIALIZATION_POLICY: Final = "COMMIT_VALID_INDEPENDENTLY"
# Event may commit while Measurement remains non-materialized until v9
CANONICAL_TABLE_NAME: Final = "measurements"
CANONICAL_DOMAIN_NAME: Final = "Measurement"
SCHEMA_V9_REQUIRED: Final = True
SCHEMA_V9_AUTHORIZED: Final = True


@dataclass(frozen=True)
class MeasurementV9Contract:
    """Conceptual row shape for future schema v9 — not implemented."""

    id: str
    user_id: str
    entity_id: str  # required for materialization
    context_entity_id: str | None
    dimension_key: str
    dimension_concept_id: str | None
    numeric_value: Decimal
    unit: str | None
    currency_code: str | None
    # temporal: TemporalKnowledge on domain object
    # observed_at: optional exact instant when known; never = created_at fallback
    source_id: str
    raw_input_id: str | None
    # confidence: interpretation confidence
    # created_at: bookkeeping only


FUTURE_INDEXES: Final = (
    "user_id",
    "entity_id",
    "(entity_id, dimension_key)",
    "dimension_key",
    "raw_input_id",
)

FUTURE_CHECKS: Final = (
    "dimension_key NOT NULL / non-empty",
    "numeric_value NOT NULL",
    "NOT (unit IS NOT NULL AND currency_code IS NOT NULL)",
    "no is_current column",
    "no supersedes_id on base Measurement",
)

FUTURE_UNIQUES: Final = ()  # 0..N history; no entity+dimension uniqueness
