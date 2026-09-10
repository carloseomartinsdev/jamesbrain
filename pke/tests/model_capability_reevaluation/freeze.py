"""I12.11 thresholds frozen BEFORE any live candidate call. Do not retune."""

from __future__ import annotations

from dataclasses import dataclass

from pke.interpretation.prompts import PROMPT_VERSION_V4
from pke.interpretation.retry import MAX_ATTEMPTS, RATE_LIMIT_POLICY
from pke.persist.versions import STORAGE_SCHEMA_VERSION


@dataclass(frozen=True)
class I1211Thresholds:
    useful_capture_delta_min: float = 0.10
    execution_ready_delta_min: float = 0.10
    mp1_useful_capture_material: float = 0.70
    post_s4: int = 0
    false_correction_accepted: int = 0
    partial_event_false_canonicalization: int = 0
    missing_information_invented: int = 0
    unsupported_primitive_addition: int = 0


@dataclass(frozen=True)
class I1211Freeze:
    experiment_id: str = "I12.11"
    prompt_version: str = PROMPT_VERSION_V4
    semantic_proposal: str = "unchanged"
    wire: str = "unchanged"
    retry_policy: str = "Interpreter RetryPolicy unchanged (I12.2)"
    retry_max_attempts: int = MAX_ATTEMPTS
    retry_rate_limit_policy: str = RATE_LIMIT_POLICY
    sdk_max_retries: int = 0
    temperature: str | None = None
    top_p: str | None = None
    max_tokens: str | None = None
    structured_output_mode: str = "json_object"
    schema_version: str = STORAGE_SCHEMA_VERSION
    core_concept_count: int = 67
    knowledge_core: str = "FROZEN"
    holdout: str = "untouched"
    runs_per_case: int = 3
    runs_per_mp_anchor: int = 5
    runs_per_mp1: int = 10
    i12_6: str = "CLOSED — not reused as ranking"
    note: str = (
        "Only model/provider varies. prompt v4 identical. "
        "No silent production switch. Thresholds frozen a priori."
    )


def frozen_thresholds() -> I1211Thresholds:
    return I1211Thresholds()


def default_freeze() -> I1211Freeze:
    assert MAX_ATTEMPTS == 2
    return I1211Freeze()
