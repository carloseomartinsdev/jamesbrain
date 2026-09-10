"""I12.6 — thresholds frozen BEFORE any live candidate call.

Do not edit after Stage A results are known (spec §55).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from pke.interpretation.prompts import PROMPT_VERSION_V4
from pke.interpretation.retry import MAX_ATTEMPTS, RATE_LIMIT_POLICY
from pke.persist.versions import STORAGE_SCHEMA_VERSION


@dataclass(frozen=True)
class I126Thresholds:
    """Acceptance thresholds locked a priori for Stage A."""

    post_engine_s4: int = 0
    post_engine_unsafe_variance_max: float = 0.01  # <= 1%
    post_engine_systematic_s3_family_allowed: bool = False
    critical_correction_safety: float = 1.0  # 100%
    mp_anchors_post_engine_safety: float = 1.0
    explicit_assertion_preservation: float = 1.0
    intent_stable_correctness_min: float = 0.97
    primitive_stable_correctness_min: float = 0.95
    temporal_evidence_preservation_min: float = 0.97
    # Preferential: material STABLE_CORRECT lift vs baseline (absolute rate points)
    preferred_stable_correct_delta_min: float = 0.10


@dataclass(frozen=True)
class I126Freeze:
    experiment_id: str = "I12.6"
    date_utc: str = ""
    stage: str = "A"
    prompt_version: str = PROMPT_VERSION_V4
    semantic_proposal: str = "unchanged"
    wire: str = "unchanged"
    correction_guard: str = "unchanged"
    multi_primitive_preservation: str = "unchanged"
    retry_max_attempts: int = MAX_ATTEMPTS
    retry_rate_limit_policy: str = RATE_LIMIT_POLICY
    schema_version: str = STORAGE_SCHEMA_VERSION
    core_concept_count: int = 67
    knowledge_core: str = "FROZEN"
    holdout: str = "untouched"
    runs_per_case: int = 3
    runs_per_mp_anchor: int = 5
    corpus_target_min: int = 80
    corpus_target_max: int = 120
    sdk_max_retries: int = 0
    http_client_retries: int = 0
    effective_max_provider_calls: int = 2
    temperature_policy: str = "provider default (unset by PKE) — identical for all candidates"
    top_p_policy: str = "provider default (unset by PKE)"
    max_tokens_policy: str = "provider default (unset by PKE)"
    structured_output_mode: str = "json_object"
    note: str = (
        "Only model/provider varies. No prompt/guard/router/Core changes during experiment. "
        "No silent production switch."
    )

    def with_now(self) -> I126Freeze:
        return I126Freeze(
            **{**asdict(self), "date_utc": datetime.now(timezone.utc).isoformat()}
        )


def frozen_thresholds() -> I126Thresholds:
    return I126Thresholds()


def default_freeze() -> I126Freeze:
    assert MAX_ATTEMPTS == 2
    return I126Freeze().with_now()
