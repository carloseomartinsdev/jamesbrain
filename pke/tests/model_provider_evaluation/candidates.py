"""I12.6 candidate registry — evaluation only; no production default switch."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

from pke.llm.config import DeepSeekConfig
from pke.llm.deepseek import DeepSeekProvider
from pke.llm.provider import LlmProvider

CandidateStatusHint = Literal[
    "EXECUTABLE",
    "NOT_EXECUTED_NO_CREDENTIAL",
    "NOT_EXECUTED_UNAVAILABLE",
]


@dataclass(frozen=True)
class CandidateSpec:
    candidate_id: str
    provider: str
    model: str
    role: Literal["baseline", "alt_same_provider", "alt_other_provider"]
    api_key_env: str
    base_url: str | None = None
    notes: str = ""

    def credential_present(self) -> bool:
        return bool(os.environ.get(self.api_key_env, "").strip())

    def availability(self) -> CandidateStatusHint:
        if not self.credential_present():
            return "NOT_EXECUTED_NO_CREDENTIAL"
        return "EXECUTABLE"


def all_candidates() -> list[CandidateSpec]:
    return [
        CandidateSpec(
            candidate_id="baseline_deepseek_chat",
            provider="deepseek",
            model="deepseek-chat",
            role="baseline",
            api_key_env="DEEPSEEK_API_KEY",
            base_url="https://api.deepseek.com",
            notes="Current Engine v1 baseline",
        ),
        CandidateSpec(
            candidate_id="deepseek_reasoner",
            provider="deepseek",
            model="deepseek-reasoner",
            role="alt_same_provider",
            api_key_env="DEEPSEEK_API_KEY",
            base_url="https://api.deepseek.com",
            notes="Same provider / different model — isolates MODEL_EFFECT",
        ),
        CandidateSpec(
            candidate_id="openai_gpt4o_mini",
            provider="openai",
            model="gpt-4o-mini",
            role="alt_other_provider",
            api_key_env="OPENAI_API_KEY",
            base_url="https://api.openai.com/v1",
            notes="Requires OPENAI_API_KEY — OpenAI-compatible adapter",
        ),
        CandidateSpec(
            candidate_id="openai_gpt4o",
            provider="openai",
            model="gpt-4o",
            role="alt_other_provider",
            api_key_env="OPENAI_API_KEY",
            base_url="https://api.openai.com/v1",
            notes="Requires OPENAI_API_KEY",
        ),
    ]


def build_provider(spec: CandidateSpec) -> LlmProvider:
    """Build LlmProvider for evaluation. Does not mutate production defaults."""
    if not spec.credential_present():
        raise RuntimeError(f"{spec.candidate_id}: missing {spec.api_key_env}")

    if spec.provider == "deepseek":
        cfg = DeepSeekConfig.from_env(model=spec.model, max_retries=0)
        return DeepSeekProvider(cfg)

    if spec.provider == "openai":
        # Experimental evaluation adapter — OpenAI-compatible chat completions.
        from pke.llm.openai_compatible import OpenAICompatibleConfig, OpenAICompatibleProvider

        cfg = OpenAICompatibleConfig.from_env(
            api_key_env=spec.api_key_env,
            model=spec.model,
            base_url=spec.base_url or "https://api.openai.com/v1",
            provider_name="openai",
            max_retries=0,
        )
        return OpenAICompatibleProvider(cfg)

    raise RuntimeError(f"unsupported provider {spec.provider}")
