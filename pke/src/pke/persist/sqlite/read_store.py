"""Leitura analítica. Não interpreta e não escreve."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pke.persist.snapshot import UserKnowledgeSnapshot
from pke.persist.sqlite.engine import (
    create_sqlite_engine,
    init_database,
    session_factory,
    sqlite_url,
)
from pke.persist.sqlite.mappers import (
    correction_from_row,
    entity_attribute_from_row,
    entity_from_row,
    event_from_row,
    fact_from_row,
    measurement_from_row,
    relation_from_row,
    source_from_row,
    state_from_row,
)
from pke.persist.sqlite.tables import (
    EntityAttributeRow,
    EntityRow,
    EventRow,
    FactRow,
    KnowledgeCorrectionRow,
    MeasurementRow,
    PrincipalBindingRow,
    RelationRow,
    SourceRow,
    StateRow,
)


class SqliteKnowledgeReadStore:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory

    def load_user_graph(self, user_id: str) -> UserKnowledgeSnapshot:
        session = self._factory()
        try:
            entities = {
                row.id: entity_from_row(row)
                for row in session.scalars(select(EntityRow).where(EntityRow.user_id == user_id))
            }
            events = [
                event_from_row(row)
                for row in session.scalars(select(EventRow).where(EventRow.user_id == user_id))
            ]
            facts = []
            for row in session.scalars(select(FactRow).where(FactRow.user_id == user_id)):
                source_row = session.get(SourceRow, row.source_id)
                if source_row is None or source_row.user_id != user_id:
                    continue
                facts.append(fact_from_row(row, source_from_row(source_row)))
            relations = []
            for row in session.scalars(
                select(RelationRow).where(RelationRow.user_id == user_id)
            ):
                source_row = session.get(SourceRow, row.source_id) if row.source_id else None
                source = source_from_row(source_row) if source_row is not None else None
                term_source_row = (
                    session.get(SourceRow, row.termination_source_id)
                    if row.termination_source_id
                    else None
                )
                term_source = (
                    source_from_row(term_source_row) if term_source_row is not None else None
                )
                relations.append(relation_from_row(row, source=source, termination_source=term_source))
            states = []
            for row in session.scalars(select(StateRow).where(StateRow.user_id == user_id)):
                source_row = session.get(SourceRow, row.source_id) if row.source_id else None
                source = source_from_row(source_row) if source_row is not None else None
                states.append(state_from_row(row, source=source))
            attributes = []
            for row in session.scalars(
                select(EntityAttributeRow).where(EntityAttributeRow.user_id == user_id)
            ):
                source_row = session.get(SourceRow, row.source_id) if row.source_id else None
                source = source_from_row(source_row) if source_row is not None else None
                attributes.append(entity_attribute_from_row(row, source=source))
            measurements = []
            for row in session.scalars(
                select(MeasurementRow).where(MeasurementRow.user_id == user_id)
            ):
                source_row = session.get(SourceRow, row.source_id) if row.source_id else None
                source = source_from_row(source_row) if source_row is not None else None
                measurements.append(measurement_from_row(row, source=source))
            corrections = [
                correction_from_row(row)
                for row in session.scalars(
                    select(KnowledgeCorrectionRow).where(
                        KnowledgeCorrectionRow.user_id == user_id
                    )
                )
            ]
            binding = session.get(PrincipalBindingRow, user_id)
            return UserKnowledgeSnapshot(
                user_id=user_id,
                entities=entities,
                events=events,
                facts=facts,
                relations=relations,
                states=states,
                attributes=attributes,
                measurements=measurements,
                corrections=corrections,
                principal_entity_id=binding.entity_id if binding is not None else None,
            )
        finally:
            session.close()


def open_sqlite_read_store(path: str | Path) -> SqliteKnowledgeReadStore:
    engine = create_sqlite_engine(sqlite_url(path))
    init_database(engine)
    return SqliteKnowledgeReadStore(session_factory(engine))
