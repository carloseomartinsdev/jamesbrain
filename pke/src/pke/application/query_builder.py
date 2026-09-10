"""QueryIR + resoluções → ResolvedQuerySpec. Fora do QueryEngine."""

from __future__ import annotations

import datetime as dt

from pke.application.ask_results import AskClarification
from pke.application.session import SessionContext
from pke.domain.ontology import ConceptKind, ConceptRef
from pke.domain.value_objects import UserContext
from pke.interpretation.models import QueryIR, QuerySpec
from pke.ontology.errors import ConceptKindError, ConceptNotFoundError, OntologyError
from pke.ontology.registry import OntologyRegistry
from pke.query.spec import (
    AggregateKind,
    AttributeQueryMode,
    AttributeValueFilter,
    EntityAssociation,
    FactVersionPolicy,
    HierarchyMode,
    MeasurementQueryMode,
    MeasurementValueFilter,
    RelationScope,
    RelationQueryKind,
    ResolvedQuerySpec,
    SortKey,
    TimeRange,
)
from pke.domain.attributes import AttributeValueKind
from pke.resolution.context import ResolutionContext, ResolutionPurpose
from pke.resolution.entities import EntityResolver, ResolutionStatus
from pke.resolution.errors import InsufficientTemporalContextError, TemporalError
from pke.resolution.lookup import EntityLookup
from pke.resolution.query_temporal import QueryTemporalContext, QueryTemporalResolver
from pke.resolution.self_ref import is_self_entity_mention


class QueryBuildError(Exception):
    def __init__(self, code: str, message: str, *, clarification: AskClarification | None = None):
        self.code = code
        self.message = message
        self.clarification = clarification
        super().__init__(message)


class ResolvedQueryBuilder:
    def __init__(
        self,
        ontology: OntologyRegistry,
        *,
        temporal: QueryTemporalResolver | None = None,
    ) -> None:
        self._ontology = ontology
        self._temporal = temporal or QueryTemporalResolver()

    def build(
        self,
        ir: QueryIR,
        user: UserContext,
        session: SessionContext,
        lookup: EntityLookup,
        *,
        now: dt.datetime,
        principal_entity_id: str | None = None,
        owned_vehicle_entity_ids: list[str] | None = None,
    ) -> ResolvedQuerySpec:
        spec = ir.query
        entity_ids = self._entities(
            spec,
            user,
            session,
            lookup,
            principal_entity_id=principal_entity_id,
            owned_vehicle_entity_ids=owned_vehicle_entity_ids or [],
        )
        time_range = self._time(spec, user, now)
        attribute_filter = None
        if spec.attribute_value_kind:
            attribute_filter = AttributeValueFilter(
                value_kind=AttributeValueKind(spec.attribute_value_kind),
                text_value=spec.attribute_text_value,
                numeric_value=spec.attribute_numeric_value,
                unit=spec.attribute_unit,
                year_value=spec.attribute_year_value,
                concept_value_id=spec.attribute_concept_value_id,
            )
        measurement_filter = None
        if spec.measurement_numeric_value is not None:
            measurement_filter = MeasurementValueFilter(
                numeric_value=spec.measurement_numeric_value,
                unit=spec.measurement_unit,
                currency_code=spec.measurement_currency_code,
            )
        return ResolvedQuerySpec(
            user_id=user.user_id,
            entity_ids=entity_ids,
            entity_association=_association(spec.entity_association) if entity_ids else None,
            event_type_ids=self._concepts(spec.event_types, ConceptKind.EVENT_TYPE),
            action_ids=self._concepts(spec.actions, ConceptKind.ACTION),
            fact_concept_ids=self._concepts(spec.facts, ConceptKind.ATTRIBUTE),
            domain_ids=self._concepts(spec.domains, ConceptKind.DOMAIN),
            state_dimension_ids=self._concepts(spec.state_dimensions, ConceptKind.STATE_DIMENSION),
            state_value_ids=self._concepts(spec.state_values, ConceptKind.STATE_VALUE),
            relation_type_ids=self._concepts(spec.relation_types, ConceptKind.RELATION_TYPE),
            relation_scope=RelationScope(spec.relation_scope),
            relation_query_kind=(
                RelationQueryKind(spec.relation_query_kind)
                if spec.relation_query_kind
                else None
            ),
            attribute_dimension_key=spec.attribute_dimension_key,
            attribute_query_mode=(
                AttributeQueryMode(spec.attribute_query_mode)
                if spec.attribute_query_mode
                else None
            ),
            attribute_value_filter=attribute_filter,
            measurement_dimension_key=spec.measurement_dimension_key,
            measurement_query_mode=(
                MeasurementQueryMode(spec.measurement_query_mode)
                if spec.measurement_query_mode
                else None
            ),
            measurement_value_filter=measurement_filter,
            time_range=time_range,
            fact_version_policy=FactVersionPolicy(spec.version_policy),
            hierarchy=HierarchyMode(spec.hierarchy),
            aggregate=AggregateKind(spec.aggregate),
            currency=spec.currency,
            sort=SortKey(spec.sort),
            limit=spec.limit,
        )

    def _entities(
        self,
        spec: QuerySpec,
        user: UserContext,
        session: SessionContext,
        lookup: EntityLookup,
        *,
        principal_entity_id: str | None = None,
        owned_vehicle_entity_ids: list[str] | None = None,
    ) -> list[str]:
        if not spec.entities:
            return []
        resolver = EntityResolver(lookup, self._ontology)
        if principal_entity_id is None and any(is_self_entity_mention(m) for m in spec.entities):
            # Query does not create bindings; ingest path is the lazy bootstrap authority.
            principal_entity_id = None
        context = ResolutionContext(
            user_id=user.user_id,
            personal=session.personal,
            purpose=ResolutionPurpose.QUERY,
            principal_entity_id=principal_entity_id,
            owned_vehicle_entity_ids=list(owned_vehicle_entity_ids or []),
        )
        ids: list[str] = []
        for mention in spec.entities:
            resolution = resolver.resolve(mention, context)
            if resolution.status is ResolutionStatus.AMBIGUOUS:
                raise QueryBuildError(
                    "entity.ambiguous",
                    "menção ambígua",
                    clarification=AskClarification(
                        clarification_key="clarify.entity.which_one",
                        reason="ambiguous_entity",
                        blocking=True,
                        candidate_entity_ids=[c.entity_id for c in resolution.candidates],
                    ),
                )
            if resolution.status is ResolutionStatus.CREATE_CANDIDATE:
                raise QueryBuildError("entity.create_forbidden", "consulta não cria entidade")
            if resolution.status is not ResolutionStatus.RESOLVED or not resolution.entity_id:
                raise QueryBuildError("entity.unresolved", "entidade não encontrada")
            ids.append(resolution.entity_id)
        if spec.entity_association is None:
            raise QueryBuildError("entity.association_required", "entity_ids exige association")
        return ids

    def _time(self, spec: QuerySpec, user: UserContext, now) -> TimeRange | None:
        if spec.time is None:
            return None
        try:
            absolute = self._temporal.resolve(
                spec.time,
                QueryTemporalContext(user=user, reference_at=now),
            )
        except InsufficientTemporalContextError as exc:
            raise QueryBuildError(
                "time.insufficient",
                str(exc),
                clarification=AskClarification(
                    clarification_key="clarify.time.range",
                    reason="temporal_range_missing",
                    blocking=True,
                ),
            ) from exc
        except TemporalError as exc:
            raise QueryBuildError("time.invalid", str(exc)) from exc
        if absolute is None:
            return None
        return TimeRange(start=absolute.start, end=absolute.end)

    def _concepts(self, refs: list[ConceptRef], kind: ConceptKind) -> list[str]:
        ids: list[str] = []
        for ref in refs:
            try:
                if kind is ConceptKind.RELATION_TYPE:
                    from pke.interpretation.semantic.learned_relation import publish_relation_type
                    from pke.ontology.learned import ensure_if_learned

                    if ensure_if_learned(self._ontology, ref.key):
                        publish_relation_type(ref.key)
                resolved = self._ontology.resolve_ref(ref, expected_kind=kind)
            except ConceptNotFoundError as exc:
                raise QueryBuildError("ontology.unknown", str(exc)) from exc
            except ConceptKindError as exc:
                raise QueryBuildError("ontology.kind", str(exc)) from exc
            except OntologyError as exc:
                raise QueryBuildError("ontology.invalid", str(exc)) from exc
            assert resolved.concept_id is not None
            ids.append(resolved.concept_id)
        return ids


def _association(value: str | None) -> EntityAssociation | None:
    if value is None:
        return None
    return EntityAssociation(value)
