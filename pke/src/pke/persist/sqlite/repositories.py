"""Repositórios SQLAlchemy. Sempre filtram por user_id."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pke.domain.attributes import EntityAttribute
from pke.domain.corrections import Correction, CorrectionOperation, KnowledgePrimitiveKind, KnowledgeReference
from pke.domain.entities import Entity
from pke.domain.events import Event
from pke.domain.facts import Fact
from pke.domain.ids import new_ulid
from pke.domain.measurements import Measurement
from pke.domain.principal import PrincipalBinding
from pke.domain.relations import Relation, RelationTerminationEvidence
from pke.domain.states import State
from pke.domain.value_objects import RawInput, Source
from pke.persist.errors import RawInputImmutableError, StorageIntegrityError
from pke.persist.sqlite.mappers import (
    correction_from_row,
    correction_to_row,
    entity_attribute_from_row,
    entity_attribute_to_row,
    entity_from_row,
    entity_to_row,
    event_from_row,
    event_to_row,
    fact_from_row,
    fact_to_row,
    measurement_from_row,
    measurement_to_row,
    raw_from_row,
    raw_to_row,
    relation_from_row,
    relation_to_row,
    source_from_row,
    source_to_row,
    state_from_row,
    state_to_row,
)
from pke.persist.sqlite.tables import (
    EntityAttributeRow,
    EntityRow,
    KnowledgeCorrectionRow,
    MeasurementRow,
    EventRow,
    FactRow,
    PrincipalBindingRow,
    RawInputRow,
    RelationRow,
    SourceRow,
    StateRow,
    UserRow,
)


def ensure_user(session: Session, user_id: str) -> None:
    with session.no_autoflush:
        exists = session.get(UserRow, user_id) is not None
    if not exists:
        session.add(UserRow(id=user_id, created_at=dt.datetime.now(dt.UTC)))
        session.flush()


def _integrity(exc: IntegrityError) -> StorageIntegrityError:
    return StorageIntegrityError(str(exc.orig) if exc.orig else str(exc))


class SqlRawInputRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, raw: RawInput) -> RawInput:
        existing = self._session.get(RawInputRow, raw.id)
        if existing is not None:
            raise RawInputImmutableError(f"raw_input já existe: {raw.id}")
        ensure_user(self._session, raw.user_id)
        self._session.add(raw_to_row(raw))
        self._session.flush()
        return raw

    def get(self, user_id: str, raw_id: str) -> RawInput | None:
        row = self._session.get(RawInputRow, raw_id)
        if row is None or row.user_id != user_id:
            return None
        return raw_from_row(row)


class SqlEntityRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, entity: Entity) -> Entity:
        ensure_user(self._session, entity.user_id)
        try:
            self._session.add(entity_to_row(entity))
            self._session.flush()
        except IntegrityError as exc:
            raise _integrity(exc) from exc
        return entity

    def get(self, user_id: str, entity_id: str) -> Entity | None:
        row = self._session.get(EntityRow, entity_id)
        if row is None or row.user_id != user_id:
            return None
        return entity_from_row(row)

    def all_for_user(self, user_id: str) -> list[Entity]:
        rows = self._session.scalars(
            select(EntityRow).where(EntityRow.user_id == user_id)
        ).all()
        return [entity_from_row(row) for row in rows]


class SqlSourceRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, source: Source) -> Source:
        ensure_user(self._session, source.user_id)
        if source.raw_input_id:
            raw = self._session.get(RawInputRow, source.raw_input_id)
            if raw is None or raw.user_id != source.user_id:
                raise StorageIntegrityError("source.raw_input inexistente ou cross-user")
        try:
            row = source_to_row(source)
            self._session.add(row)
            self._session.flush()
        except IntegrityError as exc:
            raise _integrity(exc) from exc
        return source_from_row(row)

    def get(self, user_id: str, source_id: str) -> Source | None:
        row = self._session.get(SourceRow, source_id)
        if row is None or row.user_id != user_id:
            return None
        return source_from_row(row)


class SqlEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, event: Event) -> Event:
        ensure_user(self._session, event.user_id)
        for participant in event.participants:
            self._require_entity(participant.entity_id, event.user_id, "event.participant")
        if event.actor_id:
            self._require_entity(event.actor_id, event.user_id, "event.actor")
        if event.subject_id:
            self._require_entity(event.subject_id, event.user_id, "event.subject")
        if self._session.get(RawInputRow, event.raw_input_id) is None:
            raise StorageIntegrityError("event.raw_input inexistente")
        try:
            self._session.add(event_to_row(event))
            self._session.flush()
        except IntegrityError as exc:
            raise _integrity(exc) from exc
        return self.get(event.user_id, event.id) or event

    def list_participants(self, user_id: str, event_id: str) -> list:
        from pke.domain.event_participants import EventParticipant

        event = self.get(user_id, event_id)
        if event is None:
            return []
        return list(event.participants)

    def _require_entity(self, entity_id: str, user_id: str, label: str) -> EntityRow:
        row = self._session.get(EntityRow, entity_id)
        if row is None or row.user_id != user_id:
            raise StorageIntegrityError(f"{label} inexistente ou cross-user")
        return row

    def get(self, user_id: str, event_id: str) -> Event | None:
        row = self._session.get(EventRow, event_id)
        if row is None or row.user_id != user_id:
            return None
        return event_from_row(row)


class SqlFactRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, fact: Fact) -> Fact:
        self._assert_about(fact)
        self._assert_supersession(fact)
        source = fact.source
        if source.user_id != fact.user_id:
            raise StorageIntegrityError("fact.source cross-user")
        if source.raw_input_id and self._session.get(RawInputRow, source.raw_input_id) is None:
            raise StorageIntegrityError("fact.source.raw_input inexistente")
        if source.id is not None:
            existing = self._session.get(SourceRow, source.id)
            if existing is not None and existing.user_id != fact.user_id:
                raise StorageIntegrityError("fact.source cross-user")
        if source.id is None or self._session.get(SourceRow, source.id) is None:
            ensure_user(self._session, source.user_id)
            sid = source.id or new_ulid()
            self._session.add(source_to_row(source.model_copy(update={"id": sid})))
            source = source.model_copy(update={"id": sid})
            self._session.flush()
        try:
            stored = fact.model_copy(update={"source": source})
            self._session.add(fact_to_row(stored, source.id or ""))
            self._session.flush()
        except IntegrityError as exc:
            raise _integrity(exc) from exc
        return self.get(fact.user_id, fact.id) or fact

    def save(self, fact: Fact) -> Fact:
        row = self._session.get(FactRow, fact.id)
        if row is None or row.user_id != fact.user_id:
            return self.add(fact)
        row.superseded_at = fact.superseded_at
        row.supersedes_id = fact.supersedes_id
        return fact

    def get(self, user_id: str, fact_id: str) -> Fact | None:
        row = self._session.get(FactRow, fact_id)
        if row is None or row.user_id != user_id:
            return None
        source_row = self._session.get(SourceRow, row.source_id)
        if source_row is None:
            return None
        return fact_from_row(row, source_from_row(source_row))

    def history(self, user_id: str, about_id: str, concept_id: str) -> list[Fact]:
        rows = self._session.scalars(
            select(FactRow)
            .where(
                FactRow.user_id == user_id,
                FactRow.about_id == about_id,
                FactRow.concept_id == concept_id,
            )
            .order_by(FactRow.created_at.asc(), FactRow.id.asc())
        ).all()
        result: list[Fact] = []
        for row in rows:
            source_row = self._session.get(SourceRow, row.source_id)
            if source_row is None:
                continue
            result.append(fact_from_row(row, source_from_row(source_row)))
        return result

    def _assert_about(self, fact: Fact) -> None:
        if fact.about_kind.value == "entity":
            row = self._session.get(EntityRow, fact.about_id)
            if row is None or row.user_id != fact.user_id:
                raise StorageIntegrityError("fact.about entity inexistente ou cross-user")
        elif fact.about_kind.value == "event":
            row = self._session.get(EventRow, fact.about_id)
            if row is None or row.user_id != fact.user_id:
                raise StorageIntegrityError("fact.about event inexistente ou cross-user")

    def _assert_supersession(self, fact: Fact) -> None:
        if not fact.supersedes_id:
            return
        if fact.supersedes_id == fact.id:
            raise StorageIntegrityError("fact não pode superseder a si mesmo")
        previous = self._session.get(FactRow, fact.supersedes_id)
        if previous is None:
            raise StorageIntegrityError("fact.supersedes inexistente")
        if previous.user_id != fact.user_id:
            raise StorageIntegrityError("fact.supersedes cross-user")
        if previous.about_kind != fact.about_kind.value or previous.about_id != fact.about_id:
            raise StorageIntegrityError("fact.supersedes about mismatch")
        if previous.concept_id != fact.concept_id:
            raise StorageIntegrityError("fact.supersedes concept mismatch")
        successor = self._session.scalars(
            select(FactRow).where(FactRow.supersedes_id == fact.supersedes_id)
        ).first()
        if successor is not None:
            raise StorageIntegrityError("fact já possui sucessor direto")


class SqlRelationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def _relation_from_row(self, row: RelationRow) -> Relation:
        source = None
        if row.source_id:
            source_row = self._session.get(SourceRow, row.source_id)
            if source_row is not None:
                source = source_from_row(source_row)
        term_source = None
        if row.termination_source_id:
            term_row = self._session.get(SourceRow, row.termination_source_id)
            if term_row is not None:
                term_source = source_from_row(term_row)
        return relation_from_row(row, source=source, termination_source=term_source)

    def add(self, relation: Relation) -> Relation:
        left = self._session.get(EntityRow, relation.from_id)
        right = self._session.get(EntityRow, relation.to_id)
        if left is None or right is None:
            raise StorageIntegrityError("relation endpoint inexistente")
        if left.user_id != relation.user_id or right.user_id != relation.user_id:
            raise StorageIntegrityError("relation cross-user")
        try:
            self._session.add(relation_to_row(relation))
            self._session.flush()
        except IntegrityError as exc:
            raise _integrity(exc) from exc
        return relation

    def get(self, user_id: str, relation_id: str) -> Relation | None:
        row = self._session.get(RelationRow, relation_id)
        if row is None or row.user_id != user_id:
            return None
        return self._relation_from_row(row)

    def find_instance(
        self,
        user_id: str,
        from_id: str,
        concept_id: str,
        to_id: str,
        *,
        current_only: bool = False,
    ) -> Relation | None:
        stmt = select(RelationRow).where(
            RelationRow.user_id == user_id,
            RelationRow.from_id == from_id,
            RelationRow.type_id == concept_id,
            RelationRow.to_id == to_id,
        )
        if current_only:
            stmt = stmt.where(RelationRow.is_current == True)  # noqa: E712
        row = self._session.scalars(stmt.order_by(RelationRow.observed_at.desc())).first()
        if row is None:
            return None
        return self._relation_from_row(row)

    def for_entity(self, user_id: str, entity_id: str) -> list[Relation]:
        rows = self._session.scalars(
            select(RelationRow)
            .where(
                RelationRow.user_id == user_id,
                (RelationRow.from_id == entity_id) | (RelationRow.to_id == entity_id),
            )
            .order_by(RelationRow.observed_at.asc())
        ).all()
        return [self._relation_from_row(r) for r in rows]

    def save(self, relation: Relation) -> Relation:
        self._session.merge(relation_to_row(relation))
        self._session.flush()
        return relation

    def terminate(self, relation: Relation, evidence: RelationTerminationEvidence) -> Relation:
        terminated = relation.apply_termination(evidence)
        return self.save(terminated)


class SqlStateRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, state: State) -> State:
        entity = self._session.get(EntityRow, state.entity_id)
        if entity is None or entity.user_id != state.user_id:
            raise StorageIntegrityError("state.entity inexistente ou cross-user")
        try:
            self._session.add(state_to_row(state))
            self._session.flush()
        except IntegrityError as exc:
            raise _integrity(exc) from exc
        return state

    def get(self, user_id: str, state_id: str) -> State | None:
        row = self._session.get(StateRow, state_id)
        if row is None or row.user_id != user_id:
            return None
        return state_from_row(row)

    def for_entity(self, user_id: str, entity_id: str) -> list[State]:
        rows = self._session.scalars(
            select(StateRow)
            .where(StateRow.user_id == user_id, StateRow.entity_id == entity_id)
            .order_by(StateRow.observed_at.asc())
        ).all()
        return [state_from_row(r) for r in rows]

    def save(self, state: State) -> State:
        self._session.merge(state_to_row(state))
        self._session.flush()
        return state


class SqlAttributeRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, attr: EntityAttribute) -> EntityAttribute:
        entity = self._session.get(EntityRow, attr.entity_id)
        if entity is None or entity.user_id != attr.user_id:
            raise StorageIntegrityError("attribute.entity inexistente ou cross-user")
        if attr.source is None or not attr.source.id:
            raise StorageIntegrityError("attribute.source obrigatório")
        if attr.source.user_id != attr.user_id:
            raise StorageIntegrityError("attribute.source cross-user")
        try:
            self._session.add(entity_attribute_to_row(attr))
            self._session.flush()
        except IntegrityError as exc:
            raise _integrity(exc) from exc
        return attr

    def _from_row(self, row: EntityAttributeRow) -> EntityAttribute:
        source = None
        if row.source_id:
            src_row = self._session.get(SourceRow, row.source_id)
            if src_row is not None:
                source = source_from_row(src_row)
        return entity_attribute_from_row(row, source)

    def get(self, user_id: str, attribute_id: str) -> EntityAttribute | None:
        row = self._session.get(EntityAttributeRow, attribute_id)
        if row is None or row.user_id != user_id:
            return None
        return self._from_row(row)

    def for_entity(self, user_id: str, entity_id: str) -> list[EntityAttribute]:
        rows = self._session.scalars(
            select(EntityAttributeRow)
            .where(
                EntityAttributeRow.user_id == user_id,
                EntityAttributeRow.entity_id == entity_id,
            )
            .order_by(EntityAttributeRow.created_at.asc())
        ).all()
        return [self._from_row(r) for r in rows]

    def for_entity_dimension(
        self, user_id: str, entity_id: str, dimension_key: str
    ) -> list[EntityAttribute]:
        rows = self._session.scalars(
            select(EntityAttributeRow)
            .where(
                EntityAttributeRow.user_id == user_id,
                EntityAttributeRow.entity_id == entity_id,
                EntityAttributeRow.dimension_key == dimension_key,
            )
            .order_by(EntityAttributeRow.created_at.asc())
        ).all()
        return [self._from_row(r) for r in rows]

    def list_by_entity_dimension(
        self, user_id: str, entity_id: str, dimension_key: str
    ) -> list[EntityAttribute]:
        """Retrieval-only alias — epistemic decisions live in AttributeResolver."""
        return self.for_entity_dimension(user_id, entity_id, dimension_key)

    def save(self, attr: EntityAttribute) -> EntityAttribute:
        if attr.source is None or not attr.source.id:
            raise StorageIntegrityError("attribute.source obrigatório")
        try:
            self._session.merge(entity_attribute_to_row(attr))
            self._session.flush()
        except IntegrityError as exc:
            raise _integrity(exc) from exc
        return attr


class SqlMeasurementRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, measurement: Measurement) -> Measurement:
        entity = self._session.get(EntityRow, measurement.entity_id)
        if entity is None or entity.user_id != measurement.user_id:
            raise StorageIntegrityError("measurement.entity inexistente ou cross-user")
        if measurement.context_entity_id is not None:
            ctx = self._session.get(EntityRow, measurement.context_entity_id)
            if ctx is None or ctx.user_id != measurement.user_id:
                raise StorageIntegrityError("measurement.context inexistente ou cross-user")
        if measurement.source is None or not measurement.source.id:
            raise StorageIntegrityError("measurement.source obrigatório")
        if measurement.source.user_id != measurement.user_id:
            raise StorageIntegrityError("measurement.source cross-user")
        try:
            self._session.add(measurement_to_row(measurement))
            self._session.flush()
        except IntegrityError as exc:
            raise _integrity(exc) from exc
        return measurement

    def get(self, user_id: str, measurement_id: str) -> Measurement | None:
        row = self._session.get(MeasurementRow, measurement_id)
        if row is None or row.user_id != user_id:
            return None
        source = None
        if row.source_id:
            src_row = self._session.get(SourceRow, row.source_id)
            if src_row is not None:
                source = source_from_row(src_row)
        return measurement_from_row(row, source)

    def for_user(self, user_id: str) -> list[Measurement]:
        rows = self._session.scalars(
            select(MeasurementRow)
            .where(MeasurementRow.user_id == user_id)
            .order_by(MeasurementRow.created_at.asc())
        ).all()
        return [measurement_from_row(r) for r in rows]

    def for_entity(self, user_id: str, entity_id: str) -> list[Measurement]:
        rows = self._session.scalars(
            select(MeasurementRow)
            .where(
                MeasurementRow.user_id == user_id,
                MeasurementRow.entity_id == entity_id,
            )
            .order_by(MeasurementRow.created_at.asc())
        ).all()
        return [measurement_from_row(r) for r in rows]

    def for_entity_dimension(
        self, user_id: str, entity_id: str, dimension_key: str
    ) -> list[Measurement]:
        rows = self._session.scalars(
            select(MeasurementRow)
            .where(
                MeasurementRow.user_id == user_id,
                MeasurementRow.entity_id == entity_id,
                MeasurementRow.dimension_key == dimension_key,
            )
            .order_by(MeasurementRow.created_at.asc())
        ).all()
        return [measurement_from_row(r) for r in rows]


class SqlCorrectionRepository:
    """Committed Correction ledger — persistence/retrieval only."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, correction: Correction) -> Correction:
        """Persist a domain Correction already validated by CorrectionService."""
        ensure_user(self._session, correction.user_id)
        if correction.raw_input_id is not None:
            raw = self._session.get(RawInputRow, correction.raw_input_id)
            if raw is None or raw.user_id != correction.user_id:
                raise StorageIntegrityError("correction.raw_input inexistente ou cross-user")
        if correction.source_id is not None:
            src = self._session.get(SourceRow, correction.source_id)
            if src is None or src.user_id != correction.user_id:
                raise StorageIntegrityError("correction.source inexistente ou cross-user")
        existing = self.find_by_target(
            correction.user_id, correction.target.kind, correction.target.assertion_id
        )
        if existing is not None:
            raise StorageIntegrityError("CORRECTION_BRANCH_CREATED")
        try:
            self._session.add(correction_to_row(correction))
            self._session.flush()
        except IntegrityError as exc:
            raise _integrity(exc) from exc
        return correction

    def get(self, user_id: str, correction_id: str) -> Correction | None:
        row = self._session.get(KnowledgeCorrectionRow, correction_id)
        if row is None or row.user_id != user_id:
            return None
        return correction_from_row(row)

    def find_by_target(
        self,
        user_id: str,
        kind: KnowledgePrimitiveKind | str,
        assertion_id: str,
    ) -> Correction | None:
        kind_v = kind.value if isinstance(kind, KnowledgePrimitiveKind) else str(kind)
        row = self._session.scalars(
            select(KnowledgeCorrectionRow).where(
                KnowledgeCorrectionRow.user_id == user_id,
                KnowledgeCorrectionRow.target_kind == kind_v,
                KnowledgeCorrectionRow.target_id == assertion_id,
            )
        ).first()
        return correction_from_row(row) if row is not None else None

    def find_by_targets(
        self,
        user_id: str,
        refs: list[tuple[KnowledgePrimitiveKind | str, str]],
    ) -> list[Correction]:
        if not refs:
            return []
        out: list[Correction] = []
        for kind, assertion_id in refs:
            found = self.find_by_target(user_id, kind, assertion_id)
            if found is not None:
                out.append(found)
        return out

    def find_by_replacement(
        self,
        user_id: str,
        kind: KnowledgePrimitiveKind | str,
        assertion_id: str,
    ) -> list[Correction]:
        kind_v = kind.value if isinstance(kind, KnowledgePrimitiveKind) else str(kind)
        rows = self._session.scalars(
            select(KnowledgeCorrectionRow).where(
                KnowledgeCorrectionRow.user_id == user_id,
                KnowledgeCorrectionRow.replacement_kind == kind_v,
                KnowledgeCorrectionRow.replacement_id == assertion_id,
            )
        ).all()
        return [correction_from_row(r) for r in rows]

    def for_user(self, user_id: str) -> list[Correction]:
        rows = self._session.scalars(
            select(KnowledgeCorrectionRow)
            .where(KnowledgeCorrectionRow.user_id == user_id)
            .order_by(KnowledgeCorrectionRow.recorded_at.asc())
        ).all()
        return [correction_from_row(r) for r in rows]


class SqlPrincipalBindingRepository:
    """Knowledge-owned PrincipalBinding rows (schema v11)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, user_id: str) -> PrincipalBinding | None:
        row = self._session.get(PrincipalBindingRow, user_id)
        if row is None:
            return None
        return PrincipalBinding(
            user_id=row.user_id,
            entity_id=row.entity_id,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def put(self, binding: PrincipalBinding) -> PrincipalBinding:
        ensure_user(self._session, binding.user_id)
        existing = self._session.get(PrincipalBindingRow, binding.user_id)
        if existing is not None:
            existing.entity_id = binding.entity_id
            existing.updated_at = binding.updated_at
            self._session.flush()
            return binding
        try:
            self._session.add(
                PrincipalBindingRow(
                    user_id=binding.user_id,
                    entity_id=binding.entity_id,
                    created_at=binding.created_at,
                    updated_at=binding.updated_at,
                )
            )
            self._session.flush()
        except IntegrityError as exc:
            raise _integrity(exc) from exc
        return binding
