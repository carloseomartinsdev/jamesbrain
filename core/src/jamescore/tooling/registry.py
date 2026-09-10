"""Tool Registry — belongs to jamesCore. Tools themselves do not.

PKE is not registered here. Future specialized capabilities are not required to be Tools.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


SideEffect = Literal["NONE"]


@dataclass(frozen=True)
class ToolContract:
    tool_id: str
    capability: str
    input_contract: dict[str, Any]
    output_contract: dict[str, Any]
    availability: str
    permissions: tuple[str, ...]
    freshness_requirements: str | None
    side_effect: SideEffect
    endpoint: str | None


class ToolRegistry:
    """Discovers and dispatches Tools. Empty in J1.1 — no real Tools."""

    def __init__(self, contracts: list[ToolContract] | None = None) -> None:
        self._contracts = list(contracts or [])

    def list_contracts(self) -> list[ToolContract]:
        return list(self._contracts)

    def get(self, tool_id: str) -> ToolContract | None:
        for item in self._contracts:
            if item.tool_id == tool_id:
                return item
        return None

    def find_by_capability(self, capability: str) -> ToolContract | None:
        for item in self._contracts:
            if item.capability == capability:
                return item
        return None

    def registered_count(self) -> int:
        return len(self._contracts)

    def dispatch(self, tool_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("J1.1 Tool Registry is empty; no Tool may be dispatched.")
