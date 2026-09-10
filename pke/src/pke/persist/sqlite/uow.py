"""Unit of Work SQLite — atomicidade explícita."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from pke.persist.sqlite.engine import (
    create_sqlite_engine,
    init_database,
    session_factory,
    sqlite_url,
)
from pke.persist.sqlite.repositories import (
    SqlAttributeRepository,
    SqlCorrectionRepository,
    SqlEntityRepository,
    SqlEventRepository,
    SqlFactRepository,
    SqlMeasurementRepository,
    SqlPrincipalBindingRepository,
    SqlRawInputRepository,
    SqlRelationRepository,
    SqlSourceRepository,
    SqlStateRepository,
)
from pke.persist.versions import DEFAULT_SQLITE_PATH


class SqliteUnitOfWork:
    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory
        self.session: Session | None = None
        self.raw_inputs: SqlRawInputRepository
        self.entities: SqlEntityRepository
        self.events: SqlEventRepository
        self.facts: SqlFactRepository
        self.relations: SqlRelationRepository
        self.states: SqlStateRepository
        self.attributes: SqlAttributeRepository
        self.measurements: SqlMeasurementRepository
        self.corrections: SqlCorrectionRepository
        self.sources: SqlSourceRepository
        self.principal_bindings: SqlPrincipalBindingRepository

    def begin(self) -> SqliteUnitOfWork:
        return self.__enter__()

    def __enter__(self) -> SqliteUnitOfWork:
        self.session = self._factory()
        self.raw_inputs = SqlRawInputRepository(self.session)
        self.entities = SqlEntityRepository(self.session)
        self.events = SqlEventRepository(self.session)
        self.facts = SqlFactRepository(self.session)
        self.relations = SqlRelationRepository(self.session)
        self.states = SqlStateRepository(self.session)
        self.attributes = SqlAttributeRepository(self.session)
        self.measurements = SqlMeasurementRepository(self.session)
        self.corrections = SqlCorrectionRepository(self.session)
        self.sources = SqlSourceRepository(self.session)
        self.principal_bindings = SqlPrincipalBindingRepository(self.session)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        if self.session is None:
            return
        if exc_type is not None:
            self.rollback()
        self.session.close()
        self.session = None

    def commit(self) -> None:
        if self.session is None:
            raise RuntimeError("UnitOfWork sem sessão")
        self.session.commit()

    def rollback(self) -> None:
        if self.session is None:
            return
        self.session.rollback()


def open_sqlite_uow(path: str | Path = DEFAULT_SQLITE_PATH) -> SqliteUnitOfWork:
    engine = create_sqlite_engine(sqlite_url(path))
    init_database(engine)
    return SqliteUnitOfWork(session_factory(engine))


@contextmanager
def sqlite_uow(path: str | Path = DEFAULT_SQLITE_PATH) -> Iterator[SqliteUnitOfWork]:
    uow = open_sqlite_uow(path)
    with uow as started:
        yield started
