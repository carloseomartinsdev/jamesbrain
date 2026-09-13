"""QueryEngine — recupera conhecimento persistido. Não interpreta nem completa."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from pke.domain.events import Event
from pke.domain.facts import Fact
from pke.domain.ontology import ConceptKind
from pke.domain.value_objects import Money
from pke.domain.corrections import KnowledgePrimitiveKind
from pke.ontology.registry import OntologyRegistry
from pke.persist.snapshot import UserKnowledgeSnapshot
from pke.query.errors import MultiCurrencyAggregateError, QueryIsolationError, QuerySpecError
from pke.query.effectiveness import AssertionEffectivenessResolver, filter_effective
from pke.query.relation_resolver import RelationScope as ResolverRelationScope
from pke.query.relation_resolver import (
    resolve_held_during,
    resolve_historical_existence,
    resolve_relation_query,
    resolve_termination_date,
)
from pke.query.attribute_resolver import (
    AttributeResolutionStatus,
    resolve_attribute_query,
)
from pke.query.measurement_resolver import (
    MeasurementResolutionStatus,
    observable_value_groups,
    observation_instant,
    resolve_measurement_query,
)
from pke.query.results import (
    AggregateResult,
    AttributeValueItem,
    CurrentRelationItem,
    CurrentStateItem,
    MeasurementValueItem,
    QueryItem,
    QueryPlan,
    QueryResult,
    TemporalCompleteness,
    UnknownTemporalContributor,
)
from pke.query.spec import (
    AggregateKind,
    AttributeQueryMode,
    EntityAssociation,
    FactVersionPolicy,
    HierarchyMode,
    MeasurementQueryMode,
    RelationScope,
    RelationQueryKind,
    ResolvedQuerySpec,
    SortKey,
)
from pke.query.store import KnowledgeReadStore
from pke.query.state_resolver import resolve_current_by_dimension
from pke.temporal.membership import (
    TemporalMembership,
    derive_temporal_membership_role,
    range_membership,
    temporal_instant,
)
from pke.temporal.membership import sort_key as temporal_sort_key

MAX_ITEM_LIMIT = 200


class QueryEngine:
    def __init__(self, store: KnowledgeReadStore, ontology: OntologyRegistry) -> None:
        self._store = store
        self._ontology = ontology

    def _effectiveness(self, graph: UserKnowledgeSnapshot) -> AssertionEffectivenessResolver:
        return AssertionEffectivenessResolver.from_corrections(graph.corrections)

    def execute(self, spec: ResolvedQuerySpec) -> QueryResult:
        graph = self._store.load_user_graph(spec.user_id)
        if spec.attribute_query_mode is AttributeQueryMode.SNAPSHOT:
            return self._execute_attribute_snapshot(spec, graph)
        if spec.measurement_dimension_key:
            return self._execute_measurement(spec, graph)
        if spec.attribute_dimension_key:
            from pke.query.intrinsic import try_intrinsic_attribute_result

            intrinsic = try_intrinsic_attribute_result(spec, graph)
            if intrinsic is not None:
                return intrinsic
            return self._execute_attribute(spec, graph)
        if spec.relation_type_ids:
            return self._execute_relation(spec, graph)
        if spec.state_dimension_ids or spec.state_value_ids:
            return self._execute_state(spec, graph)
        expanded_types, expanded_actions = self._expand(spec)
        self._assert_visible_ids(spec, graph)
        eff = self._effectiveness(graph)
        events_eff, _ = filter_effective(
            graph.events,
            kind=KnowledgePrimitiveKind.EVENT,
            user_id=spec.user_id,
            resolver=eff,
        )
        base_events = [
            event
            for event in events_eff
            if self._base_event_matches(event, spec, graph, expanded_types, expanded_actions)
        ]
        temporal_unknown: list[Event] = []
        if spec.time_range is not None:
            matched_events: list[Event] = []
            for event in base_events:
                membership = range_membership(
                    event.temporal,
                    spec.time_range,
                    role=derive_temporal_membership_role("event", "temporal"),
                )
                if membership is TemporalMembership.MATCH:
                    matched_events.append(event)
                elif membership is TemporalMembership.UNKNOWN:
                    temporal_unknown.append(event)
            events = matched_events
        else:
            events = base_events
        facts_by_event = _facts_for_events(graph.facts, {event.id for event in base_events})
        current_ids = _current_fact_ids(graph.facts)
        selected_facts = self._select_facts(spec, events, facts_by_event, current_ids)
        plan = QueryPlan(
            sets=["events", "facts", "entities", "relations"],
            filters=self._filters(spec),
            expanded_event_type_ids=expanded_types,
            expanded_action_ids=expanded_actions,
            version_policy=spec.fact_version_policy,
            aggregation=spec.aggregate,
            ordering=spec.sort,
            hierarchy=spec.hierarchy,
        )
        if spec.aggregate is AggregateKind.NONE:
            items = self._items(spec, events, selected_facts, current_ids)
            items = self._sort_items(items, spec.sort)
            limited = items[: _item_limit(spec.limit)]
            completeness = (
                TemporalCompleteness.PARTIAL
                if temporal_unknown
                else TemporalCompleteness.COMPLETE
            )
            return QueryResult(
                items=limited,
                matched_count=len(items),
                applied_filters=plan.filters,
                plan=plan,
                provenance_fact_ids=[item.fact_id for item in limited if item.fact_id],
                temporal_completeness=completeness,
                temporal_membership_unknown=bool(temporal_unknown),
            )
        aggregate = self._aggregate(
            spec, events, selected_facts, temporal_unknown, facts_by_event
        )
        completeness = aggregate.temporal_completeness
        return QueryResult(
            items=[],
            aggregate=aggregate,
            matched_count=len(selected_facts) if spec.fact_concept_ids else len(events),
            applied_filters=plan.filters,
            plan=plan,
            provenance_fact_ids=list(aggregate.contributing_fact_ids),
            temporal_completeness=completeness,
            temporal_membership_unknown=bool(temporal_unknown),
        )

    def _execute_attribute(
        self, spec: ResolvedQuerySpec, graph: UserKnowledgeSnapshot
    ) -> QueryResult:
        self._assert_visible_ids(spec, graph)
        dimension = spec.attribute_dimension_key
        assert dimension is not None
        mode = spec.attribute_query_mode or AttributeQueryMode.VALUE_LOOKUP
        pool = list(graph.attributes)
        if spec.entity_ids:
            entity_set = set(spec.entity_ids)
            pool = [a for a in pool if a.entity_id in entity_set]
        pool = [a for a in pool if a.dimension_key == dimension]
        pool, _ = filter_effective(
            pool,
            kind=KnowledgePrimitiveKind.ATTRIBUTE,
            user_id=spec.user_id,
            resolver=self._effectiveness(graph),
        )
        resolved = resolve_attribute_query(
            pool,
            dimension_key=dimension,
            mode=mode,
            value_filter=spec.attribute_value_filter,
            time_range=spec.time_range,
            version_policy=spec.fact_version_policy,
            sort=spec.sort,
            limit=spec.limit,
        )
        values = [
            AttributeValueItem(
                value_kind=g.identity.value_kind.value,
                text_value=g.identity.text_value,
                numeric_value=g.identity.numeric_value,
                unit=g.identity.unit,
                year_value=g.identity.year_value,
                date_value=g.identity.date_value,
                concept_value_id=g.identity.concept_value_id,
                support_count=g.support_count,
                assertion_ids=[a.id for a in g.assertions],
            )
            for g in resolved.groups
        ]
        assertion_ids = [a.id for a in resolved.candidate_assertions]
        if not assertion_ids:
            for g in resolved.groups:
                assertion_ids.extend(a.id for a in g.assertions)
        matched = sum(v.support_count for v in values)
        if resolved.status is AttributeResolutionStatus.UNKNOWN:
            matched = 0
        completeness = TemporalCompleteness.COMPLETE
        if resolved.temporal_membership_unknown:
            completeness = TemporalCompleteness.PARTIAL
        if resolved.status is AttributeResolutionStatus.TEMPORALLY_UNKNOWN:
            completeness = TemporalCompleteness.INDETERMINATE
        plan = QueryPlan(
            sets=["attributes", "entities"],
            filters=self._filters(spec),
            expanded_event_type_ids=[],
            expanded_action_ids=[],
            version_policy=spec.fact_version_policy,
            aggregation=AggregateKind.NONE,
            ordering=spec.sort,
            hierarchy=spec.hierarchy,
        )
        return QueryResult(
            matched_count=matched,
            applied_filters=plan.filters,
            plan=plan,
            temporal_completeness=completeness,
            temporal_membership_unknown=resolved.temporal_membership_unknown,
            attribute_status=resolved.status.value,
            attribute_dimension_key=dimension,
            attribute_values=values,
            attribute_proposition_answer=resolved.proposition_answer,
            attribute_assertion_ids=assertion_ids,
            warnings=list(resolved.notes),
        )

    def _execute_attribute_snapshot(
        self, spec: ResolvedQuerySpec, graph: UserKnowledgeSnapshot
    ) -> QueryResult:
        """All current attributes of the resolved entity — no invented keys."""
        self._assert_visible_ids(spec, graph)
        pool = list(graph.attributes)
        if spec.entity_ids:
            entity_set = set(spec.entity_ids)
            pool = [a for a in pool if a.entity_id in entity_set]
        pool, _ = filter_effective(
            pool,
            kind=KnowledgePrimitiveKind.ATTRIBUTE,
            user_id=spec.user_id,
            resolver=self._effectiveness(graph),
        )
        values: list[AttributeValueItem] = []
        assertion_ids: list[str] = []
        dimensions = sorted({a.dimension_key for a in pool if a.dimension_key})
        for dimension in dimensions:
            dim_pool = [a for a in pool if a.dimension_key == dimension]
            if not dim_pool:
                continue
            resolved = resolve_attribute_query(
                dim_pool,
                dimension_key=dimension,
                mode=AttributeQueryMode.VALUE_LOOKUP,
                time_range=spec.time_range,
            )
            if resolved.status is AttributeResolutionStatus.UNKNOWN:
                continue
            for g in resolved.groups:
                values.append(
                    AttributeValueItem(
                        value_kind=g.identity.value_kind.value,
                        text_value=g.identity.text_value,
                        numeric_value=g.identity.numeric_value,
                        unit=g.identity.unit,
                        year_value=g.identity.year_value,
                        date_value=g.identity.date_value,
                        concept_value_id=g.identity.concept_value_id,
                        support_count=g.support_count,
                        assertion_ids=[a.id for a in g.assertions],
                        dimension_key=dimension,
                    )
                )
                assertion_ids.extend(a.id for a in g.assertions)
        matched = sum(v.support_count for v in values)
        plan = QueryPlan(
            sets=["attributes", "entities"],
            filters=self._filters(spec),
            expanded_event_type_ids=[],
            expanded_action_ids=[],
            version_policy=spec.fact_version_policy,
            aggregation=AggregateKind.NONE,
            ordering=spec.sort,
            hierarchy=spec.hierarchy,
        )
        status = (
            AttributeResolutionStatus.KNOWN_MULTIPLE.value
            if len(values) > 1
            else (
                AttributeResolutionStatus.KNOWN_SINGLE.value
                if values
                else AttributeResolutionStatus.UNKNOWN.value
            )
        )
        return QueryResult(
            matched_count=matched,
            applied_filters=plan.filters,
            plan=plan,
            attribute_status=status,
            attribute_dimension_key=None,
            attribute_values=values,
            attribute_assertion_ids=assertion_ids,
        )

    def _execute_measurement(
        self, spec: ResolvedQuerySpec, graph: UserKnowledgeSnapshot
    ) -> QueryResult:
        self._assert_visible_ids(spec, graph)
        dimension = spec.measurement_dimension_key
        assert dimension is not None
        mode = spec.measurement_query_mode or MeasurementQueryMode.LATEST_OBSERVATION
        pool = list(graph.measurements)
        if spec.entity_ids:
            entity_set = set(spec.entity_ids)
            pool = [m for m in pool if m.entity_id in entity_set]
        pool, _ = filter_effective(
            pool,
            kind=KnowledgePrimitiveKind.MEASUREMENT,
            user_id=spec.user_id,
            resolver=self._effectiveness(graph),
        )
        resolved = resolve_measurement_query(
            pool,
            dimension_key=dimension,
            mode=mode,
            value_filter=spec.measurement_value_filter,
            time_range=spec.time_range,
            context_entity_ids=spec.context_entity_ids or None,
        )
        values = [
            MeasurementValueItem(
                numeric_value=g.identity.numeric_value,
                unit=g.identity.unit,
                currency_code=g.identity.currency_code,
                support_count=g.support_count,
                measurement_ids=[m.id for m in g.observations],
                observed_at=(
                    observation_instant(g.observations[0]).isoformat()
                    if g.observations and observation_instant(g.observations[0])
                    else None
                ),
            )
            for g in observable_value_groups(resolved)
        ]
        mids = [m.id for m in resolved.candidate_observations]
        if not mids:
            for g in resolved.groups:
                mids.extend(m.id for m in g.observations)
        matched = sum(v.support_count for v in values)
        if resolved.status is MeasurementResolutionStatus.UNKNOWN:
            matched = 0
        completeness = TemporalCompleteness.COMPLETE
        if resolved.temporal_membership_unknown:
            completeness = TemporalCompleteness.PARTIAL
        if resolved.status is MeasurementResolutionStatus.TEMPORALLY_UNKNOWN:
            completeness = TemporalCompleteness.INDETERMINATE
        plan = QueryPlan(
            sets=["measurements", "entities"],
            filters=self._filters(spec),
            expanded_event_type_ids=[],
            expanded_action_ids=[],
            version_policy=spec.fact_version_policy,
            aggregation=AggregateKind.NONE,
            ordering=spec.sort,
            hierarchy=spec.hierarchy,
        )
        return QueryResult(
            matched_count=matched,
            applied_filters=plan.filters,
            plan=plan,
            temporal_completeness=completeness,
            temporal_membership_unknown=resolved.temporal_membership_unknown,
            measurement_status=resolved.status.value,
            measurement_dimension_key=dimension,
            measurement_query_mode=mode.value,
            measurement_values=values,
            measurement_proposition_answer=resolved.proposition_answer,
            measurement_ids=mids,
            measurement_unknown_temporal_count=len(resolved.unknown_temporal_contributors),
            warnings=list(resolved.notes),
        )

    def _execute_state(
        self, spec: ResolvedQuerySpec, graph: UserKnowledgeSnapshot
    ) -> QueryResult:
        for dimension_id in spec.state_dimension_ids:
            self._require_kind(dimension_id, ConceptKind.STATE_DIMENSION)
        for value_id in spec.state_value_ids:
            self._require_kind(value_id, ConceptKind.STATE_VALUE)
        self._assert_visible_ids(spec, graph)
        pool = list(graph.states)
        if spec.entity_ids:
            pool = [s for s in pool if s.entity_id in spec.entity_ids]
        if spec.state_dimension_ids:
            pool = [s for s in pool if s.dimension_id in spec.state_dimension_ids]
        if spec.state_value_ids:
            pool = [s for s in pool if s.value_concept_id in spec.state_value_ids]
        pool, _ = filter_effective(
            pool,
            kind=KnowledgePrimitiveKind.STATE,
            user_id=spec.user_id,
            resolver=self._effectiveness(graph),
        )
        entity_ids = spec.entity_ids or sorted({s.entity_id for s in pool})
        by_dimension = resolve_current_by_dimension(
            pool,
            entity_id=entity_ids[0] if len(entity_ids) == 1 else None,
        )
        if spec.state_dimension_ids:
            dim_keys = {
                self._ontology.get_by_id(did).key  # type: ignore[union-attr]
                for did in spec.state_dimension_ids
            }
            by_dimension = {k: v for k, v in by_dimension.items() if k in dim_keys}
        overall = TemporalCompleteness.COMPLETE
        indeterminate = 0
        current_items: list[CurrentStateItem] = []
        for dim_key, result in by_dimension.items():
            if result.completeness is TemporalCompleteness.INDETERMINATE:
                overall = TemporalCompleteness.INDETERMINATE
            elif (
                result.completeness is TemporalCompleteness.PARTIAL
                and overall is not TemporalCompleteness.INDETERMINATE
            ):
                overall = TemporalCompleteness.PARTIAL
            indeterminate += result.indeterminate_count
            if result.state is not None:
                current_items.append(
                    CurrentStateItem(
                        state_id=result.state.id,
                        dimension_key=dim_key,
                        value_key=result.state.value_key,
                        payload=result.state.payload,
                    )
                )
        matched = 0
        for item in current_items:
            concept = self._ontology.get_by_key(item.value_key)
            if concept is None:
                continue
            if spec.state_value_ids and concept.id not in spec.state_value_ids:
                continue
            matched += 1
        primary = current_items[0] if len(current_items) == 1 else None
        plan = QueryPlan(
            sets=["states", "entities"],
            filters=self._filters(spec),
            expanded_event_type_ids=[],
            expanded_action_ids=[],
            version_policy=spec.fact_version_policy,
            aggregation=AggregateKind.NONE,
            ordering=spec.sort,
            hierarchy=spec.hierarchy,
        )
        return QueryResult(
            matched_count=matched,
            applied_filters=plan.filters,
            plan=plan,
            temporal_completeness=overall,
            current_state_id=primary.state_id if primary else None,
            current_state_value=primary.value_key if primary else None,
            state_dimension_key=primary.dimension_key if primary else None,
            state_value_key=primary.value_key if primary else None,
            current_states=current_items,
            indeterminate_state_count=indeterminate,
        )

    def _execute_relation(
        self, spec: ResolvedQuerySpec, graph: UserKnowledgeSnapshot
    ) -> QueryResult:
        for concept_id in spec.relation_type_ids:
            self._require_kind(concept_id, ConceptKind.RELATION_TYPE)
        self._assert_visible_ids(spec, graph)
        relations, _ = filter_effective(
            graph.relations,
            kind=KnowledgePrimitiveKind.RELATION,
            user_id=spec.user_id,
            resolver=self._effectiveness(graph),
        )
        subject_id: str | None = None
        object_id: str | None = None
        if len(spec.entity_ids) >= 2:
            subject_id = spec.entity_ids[0]
            object_id = spec.entity_ids[1]
        elif spec.entity_association is EntityAssociation.RELATION_SUBJECT:
            subject_id = spec.entity_ids[0] if spec.entity_ids else None
        elif spec.entity_association is EntityAssociation.RELATION_OBJECT:
            object_id = spec.entity_ids[0] if spec.entity_ids else None
        elif spec.entity_association is EntityAssociation.SUBJECT and spec.entity_ids:
            subject_id = spec.entity_ids[0]
        elif len(spec.entity_ids) == 1:
            subject_id = spec.entity_ids[0]
        scope = ResolverRelationScope(spec.relation_scope.value)
        concept_ids = set(spec.relation_type_ids)
        boolean_check = subject_id is not None and object_id is not None
        kind = spec.relation_query_kind
        if kind is RelationQueryKind.HISTORICAL_EXISTENCE:
            answer = resolve_historical_existence(
                relations,
                subject_id=subject_id,
                object_id=object_id,
                concept_ids=concept_ids,
            )
        elif kind is RelationQueryKind.TERMINATION_DATE:
            answer = resolve_termination_date(
                relations,
                subject_id=subject_id,
                object_id=object_id,
                concept_ids=concept_ids,
            )
        elif kind is RelationQueryKind.HELD_DURING:
            if spec.time_range is None:
                raise QuerySpecError("held_during exige time_range")
            answer = resolve_held_during(
                relations,
                spec.time_range,
                subject_id=subject_id,
                object_id=object_id,
                concept_ids=concept_ids,
            )
        else:
            answer = resolve_relation_query(
                relations,
                subject_id=subject_id,
                object_id=object_id,
                concept_ids=concept_ids,
                scope=scope,
                boolean_check=boolean_check,
            )
        items = [
            CurrentRelationItem(
                relation_id=match.relation.id,
                relation_key=match.relation.key,
                subject_entity_id=match.relation.from_id,
                object_entity_id=match.relation.to_id,
                is_current=match.relation.is_current,
            )
            for match in answer.matches
        ]
        relation_answer = answer.answer
        if spec.object_entity_type_ids:
            type_ids = set(spec.object_entity_type_ids)
            items = [
                item
                for item in items
                if self._entity_has_type(item.object_entity_id, type_ids, graph)
            ]
            if (
                spec.relation_query_kind is RelationQueryKind.CURRENT_BOOLEAN
                or spec.relation_query_kind is None
            ):
                current = [item for item in items if item.is_current]
                relation_answer = "yes" if current else "no"
        plan = QueryPlan(
            sets=["relations", "entities"],
            filters=self._filters(spec),
            expanded_event_type_ids=[],
            expanded_action_ids=[],
            version_policy=spec.fact_version_policy,
            aggregation=AggregateKind.NONE,
            ordering=spec.sort,
            hierarchy=spec.hierarchy,
        )
        return QueryResult(
            matched_count=len(items),
            applied_filters=plan.filters,
            plan=plan,
            temporal_completeness=answer.completeness,
            current_relations=items,
            relation_answer=relation_answer,
            indeterminate_relation_count=answer.indeterminate_count,
        )

    def _entity_has_type(
        self,
        entity_id: str,
        type_ids: set[str],
        graph: UserKnowledgeSnapshot,
    ) -> bool:
        entity = graph.entities.get(entity_id)
        if entity is None:
            return False
        return entity.type_id in type_ids

    def _expand(self, spec: ResolvedQuerySpec) -> tuple[list[str], list[str]]:
        types = self._expand_ids(spec.event_type_ids, ConceptKind.EVENT_TYPE, spec.hierarchy)
        actions = self._expand_ids(spec.action_ids, ConceptKind.ACTION, spec.hierarchy)
        for concept_id in spec.fact_concept_ids:
            self._require_kind(concept_id, ConceptKind.ATTRIBUTE)
        for domain_id in spec.domain_ids:
            self._require_kind(domain_id, ConceptKind.DOMAIN)
        return types, actions

    def _expand_ids(
        self,
        ids: list[str],
        kind: ConceptKind,
        hierarchy: HierarchyMode,
    ) -> list[str]:
        expanded: list[str] = []
        for concept_id in ids:
            self._require_kind(concept_id, kind)
            if hierarchy is HierarchyMode.INCLUDE_DESCENDANTS:
                expanded.extend(self._ontology.descendant_ids(concept_id, include_self=True))
            else:
                expanded.append(concept_id)
        return list(dict.fromkeys(expanded))

    def _require_kind(self, concept_id: str, kind: ConceptKind) -> None:
        concept = self._ontology.get_by_id(concept_id)
        if concept is None:
            raise QuerySpecError(f"conceito inexistente: {concept_id}")
        if concept.kind is not kind:
            raise QuerySpecError(f"kind incompatível: {concept.key} é {concept.kind}")

    def _assert_visible_ids(self, spec: ResolvedQuerySpec, graph: UserKnowledgeSnapshot) -> None:
        if spec.entity_ids and spec.entity_association is None:
            relation_ok = spec.relation_type_ids and len(spec.entity_ids) >= 2
            event_ok = spec.action_ids and len(spec.entity_ids) >= 1
            if not relation_ok and not event_ok:
                raise QuerySpecError("entity_ids exige entity_association")
        for entity_id in spec.entity_ids:
            if entity_id not in graph.entities:
                raise QueryIsolationError(f"entidade não visível: {entity_id}")
        event_ids = {event.id for event in graph.events}
        for event_id in spec.event_ids:
            if event_id not in event_ids:
                raise QueryIsolationError(f"evento não visível: {event_id}")

    def _base_event_matches(
        self,
        event: Event,
        spec: ResolvedQuerySpec,
        graph: UserKnowledgeSnapshot,
        type_ids: list[str],
        action_ids: list[str],
    ) -> bool:
        if spec.event_ids and event.id not in spec.event_ids:
            return False
        if type_ids and event.type_id not in type_ids:
            return False
        if action_ids and (event.action_id is None or event.action_id not in action_ids):
            return False
        if spec.event_statuses and event.status.value not in spec.event_statuses:
            return False
        if spec.domain_ids and not set(spec.domain_ids).intersection(event.domain_ids):
            return False
        if spec.entity_ids and not self._entity_match(event, spec, graph):
            return False
        return True

    def _event_matches(
        self,
        event: Event,
        spec: ResolvedQuerySpec,
        graph: UserKnowledgeSnapshot,
        type_ids: list[str],
        action_ids: list[str],
    ) -> bool:
        if not self._base_event_matches(event, spec, graph, type_ids, action_ids):
            return False
        if spec.time_range is not None:
            # Preserve UNKNOWN contributors (do not require MATCH-only).
            membership = range_membership(
                event.temporal,
                spec.time_range,
                role=derive_temporal_membership_role("event", "temporal"),
            )
            return membership is not TemporalMembership.NO_MATCH
        return True

    def _entity_match(
        self,
        event: Event,
        spec: ResolvedQuerySpec,
        graph: UserKnowledgeSnapshot,
    ) -> bool:
        wanted = set(spec.entity_ids)
        association = spec.entity_association
        present = event.participant_entity_ids()
        if association is EntityAssociation.ACTOR:
            actors = event.participant_ids_for_role("role.actor")
            if actors:
                return bool(actors & wanted)
            return event.actor_id in wanted
        if association is EntityAssociation.SUBJECT:
            subjects = event.participant_ids_for_role(
                "role.object", "role.patient", "role.subject"
            )
            if subjects:
                return bool(subjects & wanted)
            return event.subject_id in wanted
        if association is EntityAssociation.EVENT_CONTEXT:
            return wanted.issubset(present)
        if association is EntityAssociation.RELATION_ENDPOINT:
            related = set()
            for relation in graph.relations:
                if relation.from_id in wanted:
                    related.add(relation.to_id)
                if relation.to_id in wanted:
                    related.add(relation.from_id)
            return bool(present & (wanted | related))
        return False

    def _select_facts(
        self,
        spec: ResolvedQuerySpec,
        events: list[Event],
        facts_by_event: dict[str, list[Fact]],
        current_ids: set[str],
    ) -> list[Fact]:
        if not spec.fact_concept_ids:
            return []
        selected: list[Fact] = []
        for event in events:
            for fact in facts_by_event.get(event.id, []):
                if fact.concept_id not in spec.fact_concept_ids:
                    continue
                current_only = spec.fact_version_policy is FactVersionPolicy.CURRENT
                if current_only and fact.id not in current_ids:
                    continue
                selected.append(fact)
        return selected

    def _items(
        self,
        spec: ResolvedQuerySpec,
        events: list[Event],
        facts: list[Fact],
        current_ids: set[str],
    ) -> list[QueryItem]:
        if spec.fact_concept_ids:
            by_event = {event.id: event for event in events}
            return [
                _fact_item(fact, by_event.get(fact.about_id), fact.id in current_ids)
                for fact in facts
            ]
        return [_event_item(event) for event in events]

    def _sort_items(self, items: list[QueryItem], sort: SortKey) -> list[QueryItem]:
        reverse = sort in {SortKey.EVENT_TIME_DESC, SortKey.CREATED_AT_DESC}
        use_created = sort in {SortKey.CREATED_AT_ASC, SortKey.CREATED_AT_DESC}
        key_name = "created_at" if use_created else "event_time"

        def key(item: QueryItem) -> tuple[str, str]:
            stamp = getattr(item, key_name) or ""
            return (stamp, item.event_id or item.fact_id or "")

        return sorted(items, key=key, reverse=reverse)

    def _aggregate(
        self,
        spec: ResolvedQuerySpec,
        events: list[Event],
        facts: list[Fact],
        temporal_unknown: list[Event],
        facts_by_event: dict[str, list[Fact]],
    ) -> AggregateResult:
        if spec.aggregate is AggregateKind.COUNT:
            if spec.fact_concept_ids:
                result = AggregateResult(
                    kind=AggregateKind.COUNT,
                    value=len(facts),
                    contributing_fact_ids=[fact.id for fact in facts],
                    contributing_event_ids=list(dict.fromkeys(fact.about_id for fact in facts)),
                )
            else:
                result = AggregateResult(
                    kind=AggregateKind.COUNT,
                    value=len(events),
                    contributing_event_ids=[event.id for event in events],
                )
            if temporal_unknown:
                result.temporal_completeness = TemporalCompleteness.PARTIAL
                result.indeterminate_event_count = len(temporal_unknown)
            return result
        if spec.aggregate is AggregateKind.SUM:
            return self._sum(spec, facts, temporal_unknown, facts_by_event)
        if spec.aggregate is AggregateKind.LATEST:
            pool = {event.id: event for event in events}
            for event in temporal_unknown:
                pool[event.id] = event
            return self._latest(list(pool.values()), facts, temporal_unknown)
        raise QuerySpecError(f"agregação não suportada: {spec.aggregate}")

    def _sum(
        self,
        spec: ResolvedQuerySpec,
        facts: list[Fact],
        temporal_unknown: list[Event],
        facts_by_event: dict[str, list[Fact]],
    ) -> AggregateResult:
        money: list[tuple[Fact, Money]] = []
        for fact in facts:
            if not isinstance(fact.value, Money):
                raise QuerySpecError("SUM exige Facts Money")
            money.append((fact, fact.value))
        currencies = {item.currency for _fact, item in money}
        if spec.currency:
            money = [(fact, item) for fact, item in money if item.currency == spec.currency]
            currencies = {spec.currency} if money else set()
        if len(currencies) > 1:
            raise MultiCurrencyAggregateError("SUM recusado para múltiplas currencies")
        total = sum((item.amount for _fact, item in money), Decimal("0"))
        currency = next(iter(currencies), spec.currency)
        unknown_contributors = self._unknown_contributors(
            temporal_unknown, facts_by_event, spec.fact_concept_ids
        )
        completeness = (
            TemporalCompleteness.PARTIAL if unknown_contributors else TemporalCompleteness.COMPLETE
        )
        return AggregateResult(
            kind=AggregateKind.SUM,
            value=total,
            currency=currency,
            contributing_fact_ids=[fact.id for fact, _item in money],
            contributing_event_ids=list(dict.fromkeys(fact.about_id for fact, _item in money)),
            temporal_completeness=completeness,
            unknown_temporal_contributors=unknown_contributors,
            indeterminate_event_count=len(temporal_unknown),
        )

    def _unknown_contributors(
        self,
        temporal_unknown: list[Event],
        facts_by_event: dict[str, list[Fact]],
        fact_concept_ids: list[str],
    ) -> list[UnknownTemporalContributor]:
        if not fact_concept_ids:
            return []
        contributors: list[UnknownTemporalContributor] = []
        for event in temporal_unknown:
            for fact in facts_by_event.get(event.id, []):
                if fact.concept_id not in fact_concept_ids:
                    continue
                value = fact.value.amount if isinstance(fact.value, Money) else fact.value
                currency = fact.value.currency if isinstance(fact.value, Money) else None
                contributors.append(
                    UnknownTemporalContributor(
                        event_id=event.id,
                        fact_id=fact.id,
                        value=value,
                        currency=currency,
                    )
                )
        return contributors

    def _latest(
        self,
        events: list[Event],
        facts: list[Fact],
        temporal_unknown: list[Event],
    ) -> AggregateResult:
        if not events:
            return AggregateResult(kind=AggregateKind.LATEST, value=None)
        ranked_known = sorted(
            [event for event in events if temporal_instant(event.temporal)],
            key=lambda event: (temporal_sort_key(event.temporal), event.id),
            reverse=True,
        )
        unknown_calendar = [event for event in events if temporal_instant(event.temporal) is None]
        chosen = ranked_known[0] if ranked_known else events[0]
        fact = next((item for item in facts if item.about_id == chosen.id), None)
        value: Decimal | int | None = None
        currency = None
        fact_ids = []
        if fact is not None:
            fact_ids = [fact.id]
            if isinstance(fact.value, Money):
                value = fact.value.amount
                currency = fact.value.currency
        latest_instant = temporal_instant(chosen.temporal)
        completeness = (
            TemporalCompleteness.PARTIAL
            if unknown_calendar or temporal_unknown
            else TemporalCompleteness.COMPLETE
        )
        return AggregateResult(
            kind=AggregateKind.LATEST,
            value=value,
            currency=currency,
            contributing_fact_ids=fact_ids,
            contributing_event_ids=[chosen.id],
            temporal_completeness=completeness,
            latest_known_event_id=ranked_known[0].id if ranked_known else None,
            latest_known_event_time=(
                temporal_instant(ranked_known[0].temporal).isoformat()
                if ranked_known and temporal_instant(ranked_known[0].temporal)
                else None
            ),
            indeterminate_event_count=len(temporal_unknown),
        )

    def _filters(self, spec: ResolvedQuerySpec) -> dict:
        return {
            "user_id": spec.user_id,
            "event_ids": spec.event_ids,
            "entity_ids": spec.entity_ids,
            "entity_association": (
                spec.entity_association.value if spec.entity_association else None
            ),
            "event_type_ids": spec.event_type_ids,
            "action_ids": spec.action_ids,
            "fact_concept_ids": spec.fact_concept_ids,
            "domain_ids": spec.domain_ids,
            "state_dimension_ids": spec.state_dimension_ids,
            "state_value_ids": spec.state_value_ids,
            "relation_type_ids": spec.relation_type_ids,
            "object_entity_type_ids": spec.object_entity_type_ids,
            "relation_scope": spec.relation_scope.value,
            "attribute_dimension_key": spec.attribute_dimension_key,
            "attribute_query_mode": (
                spec.attribute_query_mode.value if spec.attribute_query_mode else None
            ),
            "measurement_dimension_key": spec.measurement_dimension_key,
            "measurement_query_mode": (
                spec.measurement_query_mode.value if spec.measurement_query_mode else None
            ),
            "context_entity_ids": spec.context_entity_ids,
            "event_statuses": spec.event_statuses,
            "time_range": (
                {"start": spec.time_range.start.isoformat(), "end": spec.time_range.end.isoformat()}
                if spec.time_range
                else None
            ),
        }


def event_filter_instant(event: Event) -> dt.datetime | None:
    """Instante consultável. Recorrência sem âncora civil não entra no intervalo."""
    return temporal_instant(event.temporal)


def _event_sort_stamp(event: Event) -> str:
    rank, stamp = temporal_sort_key(event.temporal)
    if rank < 2:
        return stamp
    return ""


def _facts_for_events(facts: list[Fact], event_ids: set[str]) -> dict[str, list[Fact]]:
    grouped: dict[str, list[Fact]] = {event_id: [] for event_id in event_ids}
    for fact in facts:
        if fact.about_id in grouped:
            grouped[fact.about_id].append(fact)
    return grouped


def _current_fact_ids(facts: list[Fact]) -> set[str]:
    superseded = {fact.supersedes_id for fact in facts if fact.supersedes_id}
    return {fact.id for fact in facts if fact.id not in superseded}


def _item_limit(limit: int | None) -> int:
    if limit is None:
        return MAX_ITEM_LIMIT
    return max(0, min(limit, MAX_ITEM_LIMIT))


def _event_item(event: Event) -> QueryItem:
    instant = event_filter_instant(event)
    return QueryItem(
        event_id=event.id,
        entity_ids=sorted(event.participant_entity_ids()),
        event_time=instant.isoformat() if instant else None,
        created_at=event.created_at.isoformat() if event.created_at else None,
    )


def _fact_item(fact: Fact, event: Event | None, is_current: bool) -> QueryItem:
    currency = fact.value.currency if isinstance(fact.value, Money) else None
    value = fact.value.amount if isinstance(fact.value, Money) else fact.value
    instant = event_filter_instant(event) if event else None
    return QueryItem(
        event_id=fact.about_id if event else None,
        fact_id=fact.id,
        entity_ids=sorted(event.participant_entity_ids()) if event else [],
        value=value,
        currency=currency,
        event_time=instant.isoformat() if instant else None,
        created_at=fact.created_at.isoformat(),
        source_id=fact.source.id,
        supersedes_id=fact.supersedes_id,
        is_current=is_current,
    )


