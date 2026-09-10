"""Dispatch normalized provider payload to v3 semantic or v2 canonical routes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

from pke.interpretation.semantic.proposal_normalizer import (
    NormalizationCategory,
    NormalizationResult,
    normalize_raw_provider_output,
)


class ProviderRoute(StrEnum):
    SEMANTIC_V3 = "semantic_v3"
    V2_CANONICAL = "v2_canonical"
    INVALID = "invalid"


@dataclass
class ProviderDispatchResult:
    route: ProviderRoute
    payload: dict[str, Any] | None = None
    normalization: NormalizationResult | None = None
    failure_stage: Literal[
        "PROVIDER_EMPTY",
        "RAW_OUTPUT_FORMAT",
        "NORMALIZATION",
        "PROPOSAL_TRANSPORT",
    ] | None = None
    failure_category: NormalizationCategory | None = None
    v2_compat_fallback: bool = False
    notes: list[str] = field(default_factory=list)


def dispatch_provider_payload(content: str) -> ProviderDispatchResult:
    """Classify provider output — provider-independent."""
    norm = normalize_raw_provider_output(content)
    if not norm.ok or norm.success is None:
        failure = norm.failure
        stage = "PROVIDER_EMPTY"
        if failure and failure.category not in {
            NormalizationCategory.EMPTY_RESPONSE,
        }:
            stage = "RAW_OUTPUT_FORMAT" if failure.category in {
                NormalizationCategory.NON_JSON_TEXT,
                NormalizationCategory.MALFORMED_JSON,
                NormalizationCategory.MULTIPLE_JSON_OBJECTS,
            } else "NORMALIZATION"
        return ProviderDispatchResult(
            route=ProviderRoute.INVALID,
            normalization=norm,
            failure_stage=stage,
            failure_category=failure.category if failure else None,
            notes=[failure.message] if failure else ["normalization failed"],
        )

    payload = norm.success.payload
    ir_kind = payload.get("ir_kind")

    if ir_kind in {"ingest", "query"}:
        return ProviderDispatchResult(
            route=ProviderRoute.V2_CANONICAL,
            payload=payload,
            normalization=norm,
            v2_compat_fallback=True,
            notes=list(norm.success.notes),
        )

    if ir_kind in {"semantic_proposal", "semantic_query"}:
        return ProviderDispatchResult(
            route=ProviderRoute.SEMANTIC_V3,
            payload=payload,
            normalization=norm,
            notes=list(norm.success.notes),
        )

    return ProviderDispatchResult(
        route=ProviderRoute.INVALID,
        normalization=norm,
        failure_stage="PROPOSAL_TRANSPORT",
        failure_category=NormalizationCategory.WRONG_IR_KIND,
        notes=[f"unsupported ir_kind after normalization: {ir_kind}"],
    )
