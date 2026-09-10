"""Contracts the Orchestrator may know about a Tool — not Tool execution logic."""

from __future__ import annotations

TOOL_METADATA_FIELDS = (
    "tool_id",
    "capability",
    "input_contract",
    "output_contract",
    "availability",
    "permissions",
    "freshness_requirements",
    "side_effect",
    "endpoint",
    "execution_status",
)
