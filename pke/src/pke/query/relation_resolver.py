"""Resolução de relations com currentness epistêmica e simetria."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from pke.domain.relation_lifecycle import (
    relation_calendar_endpoint,
    relation_calendar_start,
    termination_calendar_known,
)
from pke.domain.relations import Relation
from pke.ontology.relation_metadata import SYMMETRIC_RELATION_KEYS
from pke.query.results import TemporalCompleteness
from pke.query.spec import TimeRange
from pke.temporal.membership import (
    TemporalMembership,
    validity_interval_membership,
    sort_key as temporal_sort_key,
)


class RelationScope(StrEnum):
    CURRENT = "current"
    HISTORICAL = "historical"
    ANY = "any"


class RelationQueryKind(StrEnum):
    CURRENT_BOOLEAN = "current_boolean"
    HISTORICAL_EXISTENCE = "historical_existence"
    TERMINATION_DATE = "termination_date"
    HELD_DURING = "held_during"


@dataclass(frozen=True)
class RelationMatch:
    relation: Relation
    completeness: TemporalCompleteness = TemporalCompleteness.COMPLETE


@dataclass(frozen=True)
class RelationQueryAnswer:
    matches: list[RelationMatch]
    answer: Literal["yes", "no", "unknown"] | None = None
    completeness: TemporalCompleteness = TemporalCompleteness.COMPLETE
    indeterminate_count: int = 0


def _endpoint_match(relation: Relation, entity_id: str) -> bool:
    if relation.from_id == entity_id or relation.to_id == entity_id:
        return True
    if relation.key in SYMMETRIC_RELATION_KEYS:
        return relation.from_id == entity_id or relation.to_id == entity_id
    return False


def _matches_triple(
    relation: Relation,
    *,
    subject_id: str | None,
    object_id: str | None,
    concept_ids: set[str],
    scope: RelationScope,
) -> bool:
    if concept_ids and relation.concept_id not in concept_ids:
        return False
    if scope is RelationScope.CURRENT and not relation.is_current:
        return False
    if scope is RelationScope.HISTORICAL and relation.is_current:
        return False
    if subject_id is not None:
        if relation.from_id != subject_id:
            if relation.key in SYMMETRIC_RELATION_KEYS and relation.to_id == subject_id:
                pass
            else:
                return False
    if object_id is not None:
        if relation.to_id != object_id:
            if relation.key in SYMMETRIC_RELATION_KEYS and relation.from_id == object_id:
                pass
            else:
                return False
    return True


def filter_relations(
    relations: list[Relation],
    *,
    subject_id: str | None = None,
    object_id: str | None = None,
    concept_ids: set[str] | None = None,
    scope: RelationScope = RelationScope.CURRENT,
    endpoint_id: str | None = None,
) -> list[Relation]:
    ids = concept_ids or set()
    pool = relations
    if endpoint_id is not None:
        pool = [r for r in pool if _endpoint_match(r, endpoint_id)]
    return [
        r
        for r in pool
        if _matches_triple(
            r,
            subject_id=subject_id,
            object_id=object_id,
            concept_ids=ids,
            scope=scope,
        )
    ]


def resolve_relation_query(
    relations: list[Relation],
    *,
    subject_id: str | None = None,
    object_id: str | None = None,
    concept_ids: set[str] | None = None,
    scope: RelationScope = RelationScope.CURRENT,
    boolean_check: bool = False,
) -> RelationQueryAnswer:
    matches = filter_relations(
        relations,
        subject_id=subject_id,
        object_id=object_id,
        concept_ids=concept_ids,
        scope=scope,
    )
    if not boolean_check:
        ranked = _rank_matches(matches)
        return RelationQueryAnswer(matches=ranked)
    if not matches:
        if scope is RelationScope.CURRENT:
            historical = filter_relations(
                relations,
                subject_id=subject_id,
                object_id=object_id,
                concept_ids=concept_ids,
                scope=RelationScope.HISTORICAL,
            )
            if historical:
                return RelationQueryAnswer([], answer="no", completeness=TemporalCompleteness.COMPLETE)
        return RelationQueryAnswer([], answer="no", completeness=TemporalCompleteness.COMPLETE)
    ranked = _rank_matches(matches)
    current = [m for m in ranked if m.relation.is_current]
    if scope is RelationScope.CURRENT:
        if len(current) == 1:
            return RelationQueryAnswer(ranked, answer="yes")
        if len(current) > 1:
            return RelationQueryAnswer(
                ranked,
                answer="unknown",
                completeness=TemporalCompleteness.INDETERMINATE,
                indeterminate_count=len(current),
            )
    if ranked:
        return RelationQueryAnswer(ranked, answer="yes")
    return RelationQueryAnswer([], answer="no")


def _rank_matches(relations: list[Relation]) -> list[RelationMatch]:
    if not relations:
        return []
    ranked: list[tuple[tuple, Relation]] = []
    unknown: list[Relation] = []
    for relation in relations:
        rank = temporal_sort_key(relation.temporal)
        if rank[0] >= 2:
            unknown.append(relation)
        else:
            ranked.append((rank, relation))
    if not ranked:
        if len(unknown) == 1:
            return [RelationMatch(unknown[0], TemporalCompleteness.PARTIAL)]
        return [
            RelationMatch(r, TemporalCompleteness.INDETERMINATE) for r in unknown
        ]
    ranked.sort(key=lambda item: (item[0], item[1].id), reverse=True)
    result = [RelationMatch(ranked[0][1], TemporalCompleteness.COMPLETE)]
    if unknown:
        result.extend(RelationMatch(r, TemporalCompleteness.PARTIAL) for r in unknown)
    elif len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
        result[0] = RelationMatch(ranked[0][1], TemporalCompleteness.INDETERMINATE)
    return result


def resolve_historical_existence(
    relations: list[Relation],
    *,
    subject_id: str | None = None,
    object_id: str | None = None,
    concept_ids: set[str] | None = None,
) -> RelationQueryAnswer:
    matches = filter_relations(
        relations,
        subject_id=subject_id,
        object_id=object_id,
        concept_ids=concept_ids,
        scope=RelationScope.ANY,
    )
    if matches:
        return RelationQueryAnswer(_rank_matches(matches), answer="yes")
    return RelationQueryAnswer([], answer="no")


def resolve_termination_date(
    relations: list[Relation],
    *,
    subject_id: str | None = None,
    object_id: str | None = None,
    concept_ids: set[str] | None = None,
) -> RelationQueryAnswer:
    matches = filter_relations(
        relations,
        subject_id=subject_id,
        object_id=object_id,
        concept_ids=concept_ids,
        scope=RelationScope.ANY,
    )
    ended = [r for r in matches if r.termination_known or not r.is_current]
    if not ended:
        return RelationQueryAnswer([], answer="no")
    rel = ended[0]
    if termination_calendar_known(rel.termination_temporal):
        return RelationQueryAnswer(
            _rank_matches([rel]),
            answer="yes",
            completeness=TemporalCompleteness.COMPLETE,
        )
    if rel.termination_known:
        return RelationQueryAnswer(
            _rank_matches([rel]),
            answer="unknown",
            completeness=TemporalCompleteness.PARTIAL,
        )
    return RelationQueryAnswer([], answer="unknown", completeness=TemporalCompleteness.INDETERMINATE)


def relation_held_during(relation: Relation, time_range: TimeRange) -> TemporalMembership:
    """Validity-interval membership — not Event occurrence-window semantics.

    Delegates to shared ``validity_interval_membership`` (I11.16.3).
    Endpoints never come from recorded_at / created_at.
    """
    start = relation.valid_from or relation_calendar_start(relation.temporal)
    if relation.is_current:
        end = None
    else:
        end = relation.valid_to or relation_calendar_endpoint(relation.termination_temporal)
    return validity_interval_membership(
        start,
        end,
        time_range,
        open_ended=relation.is_current and end is None,
    )


def resolve_held_during(
    relations: list[Relation],
    time_range: TimeRange,
    *,
    subject_id: str | None = None,
    object_id: str | None = None,
    concept_ids: set[str] | None = None,
) -> RelationQueryAnswer:
    matches = filter_relations(
        relations,
        subject_id=subject_id,
        object_id=object_id,
        concept_ids=concept_ids,
        scope=RelationScope.ANY,
    )
    if not matches:
        return RelationQueryAnswer([], answer="no")
    rel = matches[0]
    membership = relation_held_during(rel, time_range)
    if membership is TemporalMembership.MATCH:
        return RelationQueryAnswer(_rank_matches([rel]), answer="yes")
    if membership is TemporalMembership.NO_MATCH:
        return RelationQueryAnswer(_rank_matches([rel]), answer="no")
    return RelationQueryAnswer(
        _rank_matches([rel]),
        answer="unknown",
        completeness=TemporalCompleteness.INDETERMINATE,
    )
