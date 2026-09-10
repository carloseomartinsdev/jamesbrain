"""E1.1 — Principal Binding / contextual self (no everyday Attribute expansion yet)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pke.application.clock import FixedClock
from pke.application.ingest import IngestService
from pke.application.ask import AskService
from pke.application.principal import PrincipalBindingService
from pke.application.results import IngestStatus
from pke.application.ask_results import AskStatus
from pke.domain.principal import PRINCIPAL_CANONICAL_NAME
from pke.interpretation import FakeInterpreter
from pke.interpretation.models import (
    EntityMention,
    IngestIR,
    IngestIntent,
    IrAttribute,
    IrTime,
    MentionReferenceKind,
    QueryIR,
    QuerySpec,
)
from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal, SemanticTime
from pke.interpretation.semantic.self_repair import apply_e1_self_repairs, repair_self_name_misparse
from pke.ontology import OntologyRegistry
from pke.ontology.seeds import core_concept_id
from pke.persist import open_sqlite_read_store, open_sqlite_uow
from pke.persist.versions import STORAGE_SCHEMA_VERSION
from pke.resolution.context import PersonalContext, ResolutionContext
from pke.resolution.entities import EntityResolver, EvidenceKind, ResolutionStatus
from pke.resolution.lookup import InMemoryEntityLookup
from pke.resolution.self_ref import is_self_lexeme
from pke.application.session import SessionContext
from pke.domain.ontology import ConceptRef
from pke.domain.value_objects import TimePrecision, UserContext
from tests.generalization_ingest.fixtures import fresh_db_path
from tests.integration.test_ingest import NOW


def _user(uid: str) -> UserContext:
    return UserContext(user_id=uid, timezone="America/Fortaleza", now=NOW)


def _session(uid: str) -> SessionContext:
    return SessionContext(personal=PersonalContext(user_id=uid))


def test_schema_is_v11() -> None:
    assert STORAGE_SCHEMA_VERSION == "11"


def test_ensure_principal_idempotent(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "e11-idem")
    user = _user("u-e11")
    svc = PrincipalBindingService()
    with open_sqlite_uow(db) as uow:
        a = svc.ensure_principal_entity(uow, user.user_id, now=NOW)
        b = svc.ensure_principal_entity(uow, user.user_id, now=NOW)
        c = svc.ensure_principal_entity(uow, user.user_id, now=NOW)
        assert a == b == c
        assert a != user.user_id
        entity = uow.entities.get(user.user_id, a)
        assert entity is not None
        assert entity.canonical_name == PRINCIPAL_CANONICAL_NAME
        assert entity.type_id == core_concept_id("entity.person")
        uow.commit()
    with open_sqlite_uow(db) as uow:
        again = svc.ensure_principal_entity(uow, user.user_id, now=NOW)
        assert again == a
        uow.commit()


def test_login_does_not_create_binding(tmp_path: Path) -> None:
    """Product auth is out of scope; Knowledge stays empty until self resolve."""
    db = fresh_db_path(tmp_path, "e11-login")
    user = _user("u-login")
    with open_sqlite_uow(db) as uow:
        assert uow.principal_bindings.get(user.user_id) is None
        assert uow.entities.all_for_user(user.user_id) == []
        uow.commit()


def test_self_name_repair_misparse() -> None:
    proposal = SemanticProposal(
        raw_input="Meu nome é Carlos.",
        utterance_kind="assert",
        primitive_hint="attribute",
        subject=SemanticEntityMention(
            text="Carlos", kind_hint="person", reference_kind="named", confidence=1.0
        ),
        attribute_expression="name is Carlos",
        stable_property_semantics=True,
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        confidence=1.0,
    )
    repaired = repair_self_name_misparse(proposal)
    assert repaired.subject is not None
    assert repaired.subject.reference_kind == "contextual"
    assert repaired.subject.text == "eu"
    assert "Carlos" in (repaired.attribute_expression or "")


def test_self_name_repair_does_not_consume_named_event() -> None:
    proposal = SemanticProposal(
        raw_input="Eu vi Carlos ontem.",
        utterance_kind="assert",
        primitive_hint="event",
        subject=SemanticEntityMention(
            text="Carlos", kind_hint="person", reference_kind="named", confidence=1.0
        ),
        event_expression="viu Carlos",
        change_semantics=True,
        temporal=SemanticTime(original_text="ontem", relative_day="yesterday"),
        confidence=1.0,
    )
    repaired = apply_e1_self_repairs(proposal)
    assert repaired.subject is not None
    assert repaired.subject.reference_kind == "named"
    assert repaired.subject.text == "Carlos"


def test_friend_name_not_repaired_to_self() -> None:
    proposal = SemanticProposal(
        raw_input="O nome do meu amigo é João.",
        utterance_kind="assert",
        primitive_hint="attribute",
        subject=SemanticEntityMention(
            text="amigo", kind_hint="person", reference_kind="named", confidence=1.0
        ),
        attribute_expression="name is João",
        stable_property_semantics=True,
        temporal=SemanticTime(),
        confidence=1.0,
    )
    repaired = repair_self_name_misparse(proposal)
    assert repaired.subject is not None
    assert repaired.subject.reference_kind == "named"


def test_resolver_self_via_principal_binding(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "e11-res")
    user = _user("u-res")
    svc = PrincipalBindingService()
    with open_sqlite_uow(db) as uow:
        pid = svc.ensure_principal_entity(uow, user.user_id, now=NOW)
        entity = uow.entities.get(user.user_id, pid)
        assert entity is not None
        lookup = InMemoryEntityLookup()
        lookup.add(entity)
        resolver = EntityResolver(lookup, OntologyRegistry.with_core_seeds())
        mention = EntityMention(
            text="eu",
            type_hint=ConceptRef(key="entity.person"),
            reference_kind=MentionReferenceKind.CONTEXTUAL,
        )
        result = resolver.resolve(
            mention,
            ResolutionContext(
                user_id=user.user_id,
                personal=PersonalContext(user_id=user.user_id),
                principal_entity_id=pid,
            ),
        )
        assert result.status is ResolutionStatus.RESOLVED
        assert result.entity_id == pid
        assert EvidenceKind.PRINCIPAL_BINDING in result.evidence
        uow.commit()


@pytest.mark.parametrize(
    "token,expected",
    [
        ("eu", True),
        ("me", True),
        ("mim", True),
        ("comigo", True),
        ("meu", True),
        ("minha", True),
        ("para mim", True),
        ("meu carro", False),
        ("Carlos", False),
    ],
)
def test_self_lexeme_table(token: str, expected: bool) -> None:
    assert is_self_lexeme(token) is expected


def test_self_height_write_and_query(tmp_path: Path) -> None:
    """E1.1.5: self write/query using already-materializable height (name is E1.2)."""
    db = fresh_db_path(tmp_path, "e11-height")
    user = _user("u-height")
    self_mention = EntityMention(
        text="eu",
        type_hint=ConceptRef(key="entity.person"),
        reference_kind=MentionReferenceKind.CONTEXTUAL,
    )
    write_ir = IngestIR(
        raw_input="Minha altura é 1,80 m.",
        intent=IngestIntent.RECORD_ATTRIBUTE,
        attribute=IrAttribute(
            subject=self_mention,
            dimension_key="height",
            value_kind="number",
            numeric_value="1.80",
            unit="m",
            is_current=True,
            time=IrTime(original_text="", precision=TimePrecision.PARTIAL),
        ),
    )
    query_ir = QueryIR(
        raw_input="Qual é a minha altura?",
        query=QuerySpec(
            intent="attribute",
            entities=[self_mention],
            entity_association="subject",
            attribute_dimension_key="height",
            attribute_query_mode="value_lookup",
        ),
    )
    ontology = OntologyRegistry.with_core_seeds()
    ingest = IngestService(
        FakeInterpreter({"Minha altura é 1,80 m.": write_ir}),
        ontology,
        lambda: open_sqlite_uow(db),
        FixedClock(NOW),
    )
    session = _session(user.user_id)
    result = ingest.ingest("Minha altura é 1,80 m.", user, session)
    assert result.status is IngestStatus.COMMITTED, result.issues

    with open_sqlite_uow(db) as uow:
        binding = uow.principal_bindings.get(user.user_id)
        assert binding is not None
        attrs = uow.attributes.for_entity_dimension(user.user_id, binding.entity_id, "height")
        assert len(attrs) >= 1
        uow.commit()

    ask = AskService(
        FakeInterpreter({"Qual é a minha altura?": query_ir}),
        ontology,
        open_sqlite_read_store(db),
        FixedClock(NOW),
    )
    answered = ask.ask("Qual é a minha altura?", user, _session(user.user_id))
    assert answered.status is AskStatus.ANSWERED
    assert answered.query_result is not None
