"""Resolução de current state por dimensão com ordenação temporal epistêmica."""

from __future__ import annotations

from dataclasses import dataclass

from pke.domain.states import State
from pke.query.results import TemporalCompleteness
from pke.temporal.membership import sort_key as temporal_sort_key


@dataclass(frozen=True)
class CurrentStateResult:
    state: State | None
    completeness: TemporalCompleteness
    indeterminate_count: int = 0


def resolve_current(
    states: list[State],
    *,
    dimension_key: str,
    only_current: bool = True,
) -> CurrentStateResult:
    pool = [s for s in states if s.dimension_key == dimension_key]
    if only_current:
        pool = [s for s in pool if s.is_current]
    if not pool:
        return CurrentStateResult(None, TemporalCompleteness.COMPLETE)
    ranked: list[tuple[tuple, State]] = []
    unknown: list[State] = []
    for state in pool:
        rank = temporal_sort_key(state.temporal)
        if rank[0] >= 2:
            unknown.append(state)
        else:
            ranked.append((rank, state))
    if not ranked:
        if len(unknown) == 1:
            return CurrentStateResult(unknown[0], TemporalCompleteness.PARTIAL, 0)
        return CurrentStateResult(None, TemporalCompleteness.INDETERMINATE, len(unknown))
    ranked.sort(key=lambda item: (item[0], item[1].id), reverse=True)
    chosen = ranked[0][1]
    if unknown:
        return CurrentStateResult(chosen, TemporalCompleteness.PARTIAL, len(unknown))
    if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
        return CurrentStateResult(chosen, TemporalCompleteness.INDETERMINATE, 1)
    return CurrentStateResult(chosen, TemporalCompleteness.COMPLETE)


def resolve_current_by_dimension(
    states: list[State],
    *,
    entity_id: str | None = None,
) -> dict[str, CurrentStateResult]:
    pool = states if entity_id is None else [s for s in states if s.entity_id == entity_id]
    dimensions = sorted({s.dimension_key for s in pool})
    return {dim: resolve_current(pool, dimension_key=dim) for dim in dimensions}
