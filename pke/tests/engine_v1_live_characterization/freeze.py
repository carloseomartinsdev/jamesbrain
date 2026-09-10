"""Experimental freeze for I12.3 — locked before first live call."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from pke.interpretation.prompts import PROMPT_VERSION_V4
from pke.interpretation.retry import MAX_ATTEMPTS, RATE_LIMIT_POLICY, RetryPolicy
from pke.persist.versions import STORAGE_SCHEMA_VERSION


@dataclass(frozen=True)
class ExperimentalFreeze:
    experiment_id: str = "I12.3"
    date_utc: str = ""
    prompt_version: str = PROMPT_VERSION_V4
    semantic_proposal: str = "WireSemanticEnvelope / SemanticProposal (v3+ path)"
    wire_contract: str = "WIRE_SCHEMA_HINT + proposal wire"
    retry_max_attempts: int = MAX_ATTEMPTS
    retry_rate_limit_policy: str = RATE_LIMIT_POLICY
    schema_version: str = STORAGE_SCHEMA_VERSION
    core_concept_count: int = 67
    knowledge_core: str = "FROZEN"
    git_revision: str = "unavailable (pkeagent path not a git repo at measurement time)"
    corpus_source: str = "tests/engine_v1_baseline/corpus.py"
    runs_per_case_default: int = 3
    runs_per_mp_anchor: int = 5
    provider: str = "deepseek"
    model: str = "deepseek-chat"
    temperature: str = "provider default (unset by PKE)"
    top_p: str = "provider default (unset by PKE)"
    max_tokens: str = "provider default (unset by PKE)"
    structured_output_mode: str = "json_object"
    timeout_seconds: float = 30.0
    sdk_max_retries: int = 0
    http_client_retries: int = 0
    effective_max_provider_calls: int = 2
    note: str = (
        "Observational only. No prompt/retry/Core/ontology/query changes during experiment."
    )

    def with_now(self) -> ExperimentalFreeze:
        return ExperimentalFreeze(
            **{
                **asdict(self),
                "date_utc": datetime.now(timezone.utc).isoformat(),
            }
        )


def default_freeze() -> ExperimentalFreeze:
    policy = RetryPolicy()
    assert policy.max_attempts == 2
    return ExperimentalFreeze().with_now()
