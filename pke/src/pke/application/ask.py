"""AskService — orquestra consulta. Não soma e não escreve conhecimento."""

from __future__ import annotations

import datetime as dt

from pke.application.ask_results import AskClarification, AskResult, AskStatus
from pke.application.clock import Clock
from pke.application.query_builder import QueryBuildError, ResolvedQueryBuilder
from pke.application.session import SessionContext
from pke.domain.value_objects import UserContext
from pke.interpretation.interpreter import InterpretationContext, InterpretationError, Interpreter
from pke.interpretation.models import IngestIR, QueryIR
from pke.ontology.registry import OntologyRegistry
from pke.query.engine import QueryEngine
from pke.query.errors import MultiCurrencyAggregateError, QueryError, QueryIsolationError
from pke.query.results import QueryResult, TemporalCompleteness
from pke.query.spec import AggregateKind, AttributeQueryMode, ResolvedQuerySpec
from pke.query.store import KnowledgeReadStore
from pke.reasoning.issues import Issue, Severity
from pke.resolution.errors import ForeignEntityError
from pke.resolution.lookup import InMemoryEntityLookup


class AskService:
    def __init__(
        self,
        interpreter: Interpreter,
        ontology: OntologyRegistry,
        store: KnowledgeReadStore,
        clock: Clock,
        *,
        builder: ResolvedQueryBuilder | None = None,
        engine: QueryEngine | None = None,
    ) -> None:
        self._interpreter = interpreter
        self._ontology = ontology
        self._store = store
        self._clock = clock
        self._builder = builder or ResolvedQueryBuilder(ontology)
        self._engine = engine or QueryEngine(store, ontology)

    def ask(self, raw: str, user: UserContext, session: SessionContext) -> AskResult:
        if session.user_id != user.user_id:
            raise ValueError("SessionContext isolado por usuário")
        now = self._instant(user)
        try:
            interpreted = self._interpreter.interpret(
                raw,
                InterpretationContext(
                    user=user,
                    recent_event_ids=session.recent_event_ids,
                    recent_utterances=list(session.recent_utterances),
                ),
            )
        except InterpretationError as exc:
            return AskResult(
                status=AskStatus.REJECTED,
                raw_text=raw,
                issues=[_issue("interpretation.failed", str(exc))],
            )
        if isinstance(interpreted, IngestIR):
            return AskResult(status=AskStatus.UNSUPPORTED, raw_text=raw)
        if not isinstance(interpreted, QueryIR):
            return AskResult(status=AskStatus.UNSUPPORTED, raw_text=raw)
        from pke.interpretation.semantic.learned_relation import bind_learned_relation_types

        bind_learned_relation_types(self._ontology, interpreted)
        graph = self._store.load_user_graph(user.user_id)
        lookup = InMemoryEntityLookup()
        for entity in graph.entities.values():
            lookup.add(entity)
        owned_vehicle_ids: list[str] = []
        if graph.principal_entity_id is not None:
            from pke.application.ownership import owned_vehicle_entity_ids

            owned_vehicle_ids = owned_vehicle_entity_ids(
                principal_entity_id=graph.principal_entity_id,
                relations=list(graph.relations),
                entities=graph.entities,
                ontology=self._ontology,
            )
        try:
            spec = self._builder.build(
                interpreted,
                user,
                session,
                lookup,
                now=now,
                principal_entity_id=graph.principal_entity_id,
                owned_vehicle_entity_ids=owned_vehicle_ids,
            )
        except ForeignEntityError as exc:
            return AskResult(
                status=AskStatus.REJECTED,
                raw_text=raw,
                issues=[_issue("entity.foreign", str(exc))],
            )
        except QueryBuildError as exc:
            return self._from_build_error(raw, exc)
        try:
            query_result = self._engine.execute(spec)
        except QueryIsolationError as exc:
            return AskResult(
                status=AskStatus.REJECTED,
                raw_text=raw,
                issues=[_issue("query.isolation", str(exc))],
                resolved_spec=spec,
            )
        except MultiCurrencyAggregateError as exc:
            return AskResult(
                status=AskStatus.REJECTED,
                raw_text=raw,
                issues=[_issue("query.multi_currency", str(exc))],
                resolved_spec=spec,
            )
        except QueryError as exc:
            return AskResult(
                status=AskStatus.REJECTED,
                raw_text=raw,
                issues=[_issue("query.failed", str(exc))],
                resolved_spec=spec,
            )
        return self._from_query(raw, spec, query_result, graph=graph)

    def _instant(self, user: UserContext) -> dt.datetime:
        instant = user.now if user.now is not None else self._clock.now()
        if instant.tzinfo is None:
            raise ValueError("instante operacional exige timezone")
        return instant

    def _hydrate(self, user_id: str) -> InMemoryEntityLookup:
        graph = self._store.load_user_graph(user_id)
        lookup = InMemoryEntityLookup()
        for entity in graph.entities.values():
            lookup.add(entity)
        return lookup

    def _from_build_error(self, raw: str, exc: QueryBuildError) -> AskResult:
        if exc.code == "entity.ambiguous" and exc.clarification is not None:
            return AskResult(
                status=AskStatus.NEEDS_CLARIFICATION,
                raw_text=raw,
                issues=[_issue(exc.code, exc.message)],
                clarification=exc.clarification,
            )
        if exc.code == "time.insufficient":
            return AskResult(
                status=AskStatus.NEEDS_CLARIFICATION,
                raw_text=raw,
                issues=[_issue(exc.code, exc.message)],
                clarification=exc.clarification
                or AskClarification(
                    clarification_key="clarify.time.range",
                    reason="temporal_range_missing",
                    blocking=True,
                ),
            )
        if exc.code == "entity.unresolved":
            return AskResult(
                status=AskStatus.NO_RESULTS,
                raw_text=raw,
                issues=[_issue(exc.code, exc.message)],
            )
        return AskResult(
            status=AskStatus.REJECTED,
            raw_text=raw,
            issues=[_issue(exc.code, exc.message)],
            clarification=exc.clarification,
        )

    def _from_query(
        self,
        raw: str,
        spec: ResolvedQuerySpec,
        query_result: QueryResult,
        *,
        graph=None,
    ) -> AskResult:
        if (
            graph is not None
            and spec.attribute_dimension_key == "brand"
            and _is_vehicle_identity_query(raw)
            and query_result.attribute_status == "known_single"
            and spec.entity_ids
        ):
            query_result = _compose_vehicle_identity(query_result, graph, spec.entity_ids[0])
        if (
            graph is not None
            and query_result.current_relations
            and query_result.relation_answer is None
        ):
            query_result = _label_relation_objects(query_result, graph)
        empty = _is_empty(spec, query_result)
        return AskResult(
            status=AskStatus.NO_RESULTS if empty else AskStatus.ANSWERED,
            raw_text=raw,
            query_result=query_result,
            resolved_spec=spec,
            resolved_entity_ids=list(spec.entity_ids),
        )


def _is_empty(spec: ResolvedQuerySpec, result: QueryResult) -> bool:
    if spec.attribute_query_mode is AttributeQueryMode.SNAPSHOT:
        if result.attribute_values:
            return False
        return result.matched_count == 0
    if spec.attribute_dimension_key:
        if result.attribute_proposition_answer is not None:
            return False
        if result.attribute_status in {
            "known_single",
            "known_multiple",
            "ambiguous",
            "temporally_unknown",
        }:
            return False
        return True
    if spec.measurement_dimension_key:
        if result.measurement_proposition_answer is not None:
            return False
        if result.measurement_status in {
            "known_single",
            "known_multiple",
            "ambiguous",
            "temporally_unknown",
        }:
            return False
        return True
    if spec.aggregate is AggregateKind.NONE:
        return result.matched_count == 0
    if result.aggregate is None:
        return True
    if spec.aggregate is AggregateKind.SUM:
        return not result.aggregate.contributing_fact_ids
    if spec.aggregate is AggregateKind.COUNT:
        if result.aggregate.value not in {0, None}:
            return False
        return (
            result.temporal_completeness is TemporalCompleteness.COMPLETE
            and not result.temporal_membership_unknown
            and result.aggregate.indeterminate_event_count == 0
        )
    if spec.aggregate is AggregateKind.LATEST:
        return not result.aggregate.contributing_event_ids
    return result.matched_count == 0


def _label_relation_objects(query_result: QueryResult, graph) -> QueryResult:
    labeled = []
    for item in query_result.current_relations:
        entity = graph.entities.get(item.object_entity_id)
        name = entity.canonical_name if entity is not None else None
        labeled.append(item.model_copy(update={"object_label": name}))
    return query_result.model_copy(update={"current_relations": labeled})


def _issue(code: str, message: str) -> Issue:
    return Issue(code=code, rule_id="ask", message=message, severity=Severity.ERROR)


def _is_vehicle_identity_query(raw: str) -> bool:
    import re
    import unicodedata

    from pke.interpretation.semantic.possessive_attribute_repair import dimension_in_text

    normalized = unicodedata.normalize("NFKD", raw or "")
    folded = "".join(ch for ch in normalized if not unicodedata.combining(ch)).casefold()
    if dimension_in_text(folded):
        return False
    return bool(re.search(r"\bqual\b.*\bmeu\s+carro\b", folded))


def _compose_vehicle_identity(query_result: QueryResult, graph, entity_id: str) -> QueryResult:
    """Present brand+model as a single identity label for 'qual é o meu carro?'."""
    from pke.query.attribute_resolver import (
        AttributeResolutionStatus,
        resolve_attribute_query,
    )
    from pke.query.results import AttributeValueItem
    from pke.query.spec import AttributeQueryMode

    if not query_result.attribute_values:
        return query_result
    brand = query_result.attribute_values[0].text_value
    if not brand:
        return query_result
    model_pool = [
        a
        for a in graph.attributes
        if a.entity_id == entity_id and a.dimension_key == "model"
    ]
    model_resolved = resolve_attribute_query(
        model_pool,
        dimension_key="model",
        mode=AttributeQueryMode.VALUE_LOOKUP,
    )
    if model_resolved.status is not AttributeResolutionStatus.KNOWN_SINGLE:
        return query_result
    if not model_resolved.groups or not model_resolved.groups[0].identity.text_value:
        return query_result
    model = model_resolved.groups[0].identity.text_value
    label = f"{brand} {model}".strip()
    composed = AttributeValueItem(
        value_kind="text",
        text_value=label,
        support_count=query_result.attribute_values[0].support_count,
        assertion_ids=list(query_result.attribute_values[0].assertion_ids),
    )
    return query_result.model_copy(update={"attribute_values": [composed]})
