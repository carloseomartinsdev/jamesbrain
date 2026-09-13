"""ADR 0092 — person role vs identity naming (single persistable person)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pke.application.clock import FixedClock
from pke.application.ingest import IngestService
from pke.application.results import IngestStatus
from pke.application.session import SessionContext
from pke.domain.value_objects import UserContext
from pke.interpretation import FakeInterpreter
from pke.interpretation.semantic.identity_naming import (
    persistable_identity_keys,
    slot_identity_keys,
)
from pke.interpretation.semantic.models import (
    SemanticClaim,
    SemanticClaimKind,
    SemanticEntityMention,
    SemanticProposal,
    SemanticTime,
)
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
from pke.interpretation.semantic.self_repair import apply_e1_self_repairs, last_applied_repairs
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.persist import open_sqlite_uow
from pke.resolution.context import PersonalContext
from tests.generalization_ingest.fixtures import fresh_db_path
from tests.integration.test_ingest import NOW

OPAQUE = "OPAQUE-IDENTITY-ROLE-001"


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _user(uid: str = "u-identity") -> UserContext:
    return UserContext(user_id=uid, timezone="America/Fortaleza", now=NOW)


def _session(uid: str = "u-identity") -> SessionContext:
    return SessionContext(personal=PersonalContext(user_id=uid))


def _self() -> SemanticEntityMention:
    return SemanticEntityMention(
        text="self", kind_hint="person", reference_kind="contextual", confidence=1.0
    )


def _named(text: str, *, kind: str = "person", class_hint: str | None = "person"):
    return SemanticEntityMention(
        text=text,
        kind_hint=kind,  # type: ignore[arg-type]
        class_hint=class_hint,
        reference_kind="named",
        confidence=1.0,
    )


def _possessed(text: str, *, kind: str = "person", class_hint: str | None = None):
    return SemanticEntityMention(
        text=text,
        kind_hint=kind,  # type: ignore[arg-type]
        class_hint=class_hint,
        reference_kind="possessive",
        confidence=1.0,
    )


def _accountant_named_relation(raw: str) -> SemanticProposal:
    role = _possessed("contador", class_hint="accountant")
    person = _named("Angelo")
    return SemanticProposal(
        raw_input=raw,
        utterance_kind="assert",
        primitive_hint="relation",
        subject=role,
        object=person,
        relation_expression="named",
        link_semantics=True,
        classification_semantics=True,
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        claims=[
            SemanticClaim(kind=SemanticClaimKind.ENTITY, subject=role),
            SemanticClaim(
                kind=SemanticClaimKind.CLASSIFICATION, subject=role, class_hint="accountant"
            ),
            SemanticClaim(
                kind=SemanticClaimKind.RELATION,
                predicate="named",
                subject=role,
                object=person,
            ),
            SemanticClaim(kind=SemanticClaimKind.ENTITY, subject=person),
        ],
        confidence=1.0,
    )


def _accountant_name_attribute(raw: str) -> SemanticProposal:
    role = _possessed("contador", class_hint="accountant")
    return SemanticProposal(
        raw_input=raw,
        utterance_kind="assert",
        primitive_hint="attribute",
        subject=role,
        stable_property_semantics=True,
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        claims=[
            SemanticClaim(kind=SemanticClaimKind.ENTITY, subject=role),
            SemanticClaim(
                kind=SemanticClaimKind.INTRINSIC_PROPERTY,
                subject=role,
                dimension="name",
                value_text="Angelo",
            ),
        ],
        confidence=1.0,
    )


def _ingest(proposal: SemanticProposal, db: Path, user: UserContext, *, opaque: bool = False):
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is not None, (outcome.failure_stage, outcome.execution_reasons)
    ir = outcome.ir
    raw = OPAQUE if opaque else proposal.raw_input
    if opaque:
        ir = ir.model_copy(update={"raw_input": OPAQUE})
    ontology = OntologyRegistry.with_core_seeds()
    svc = IngestService(
        FakeInterpreter({raw: ir}),  # type: ignore[arg-type]
        ontology,
        lambda: open_sqlite_uow(db),
        FixedClock(NOW),
    )
    return svc.ingest(raw, user, _session(user.user_id)), outcome


def _assert_single_accountant(db: Path, user: UserContext) -> None:
    with open_sqlite_uow(db) as uow:
        people = [
            e
            for e in uow.entities.all_for_user(user.user_id)
            if e.canonical_name == "Angelo"
        ]
        names = {e.canonical_name for e in uow.entities.all_for_user(user.user_id)}
        assert people, names
        assert "contador" not in names
        assert "accountant" not in names
        binding = uow.principal_bindings.get(user.user_id)
        assert binding is not None
        rels = [
            r
            for r in uow.relations.for_entity(user.user_id, binding.entity_id)
            if r.is_current
        ]
        keys = {r.key for r in rels}
        assert not any(k.endswith(".named") or k == "relation.named" for k in keys)
        assert any("accountant" in k for k in keys)
        targets = {r.to_id for r in rels if "accountant" in r.key}
        assert people[0].id in targets
        professions = [
            a.text_value
            for a in uow.attributes.for_entity(user.user_id, people[0].id)
            if a.is_current and a.dimension_key == "profession"
        ]
        assert professions == ["accountant"]
        uow.commit()


@pytest.mark.parametrize(
    "raw",
    [
        "meu contador se chama Angelo",
        "Angelo é meu contador",
        "o nome do meu contador é Angelo",
    ],
)
def test_identity_role_single_entity(tmp_path: Path, raw: str) -> None:
    db = fresh_db_path(tmp_path, "id-angelo")
    user = _user("u-angelo")
    proposal = _accountant_named_relation(raw)
    result, outcome = _ingest(proposal, db, user)
    assert result.status is IngestStatus.COMMITTED, result.issues
    assert outcome.ir is not None
    assert outcome.ir.relation is not None
    assert "named" not in outcome.ir.relation.type.key
    assert "accountant" in outcome.ir.relation.type.key
    mentioned = {e.text.casefold() for e in outcome.ir.entities_mentioned}
    assert "angelo" in mentioned
    assert "contador" not in mentioned
    _assert_single_accountant(db, user)


def test_identity_role_from_name_attribute(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "id-name-attr")
    user = _user("u-name-attr")
    result, _ = _ingest(_accountant_name_attribute("o nome do meu contador é Angelo"), db, user)
    assert result.status is IngestStatus.COMMITTED, result.issues
    _assert_single_accountant(db, user)


def test_final_claims_match_final_proposal() -> None:
    proposal = _accountant_named_relation("meu contador se chama Angelo")
    folded = apply_e1_self_repairs(proposal)
    assert "identity_naming_fold" in last_applied_repairs()
    assert persistable_identity_keys(folded) == slot_identity_keys(folded)
    assert persistable_identity_keys(folded) == frozenset({"angelo"})
    assert folded.object is not None
    assert folded.object.text == "Angelo"
    assert folded.relation_expression == "accountant"
    assert any(
        c.kind is SemanticClaimKind.ATTRIBUTE
        and (c.dimension or "") == "profession"
        and (c.value_text or "") == "accountant"
        for c in folded.claims
    )
    assert not any(
        (c.predicate or "").lower() in {"named", "called"} for c in folded.claims
    )


def test_correct_role_relation_does_not_need_named_fold(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "id-correct")
    user = _user("u-correct")
    angelo = _named("Angelo")
    proposal = SemanticProposal(
        raw_input="Angelo is my accountant",
        utterance_kind="assert",
        primitive_hint="relation",
        subject=_self(),
        object=angelo,
        relation_expression="accountant",
        link_semantics=True,
        classification_semantics=True,
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        claims=[
            SemanticClaim(kind=SemanticClaimKind.ENTITY, subject=angelo),
            SemanticClaim(
                kind=SemanticClaimKind.CLASSIFICATION, subject=angelo, class_hint="person"
            ),
            SemanticClaim(
                kind=SemanticClaimKind.RELATION,
                predicate="accountant",
                subject=_self(),
                object=angelo,
            ),
            SemanticClaim(
                kind=SemanticClaimKind.INTRINSIC_PROPERTY,
                subject=angelo,
                dimension="name",
                value_text="Angelo",
            ),
        ],
        confidence=1.0,
    )
    repaired = apply_e1_self_repairs(proposal)
    assert persistable_identity_keys(repaired) == frozenset({"angelo"})
    result, _ = _ingest(proposal, db, user)
    assert result.status is IngestStatus.COMMITTED, result.issues
    _assert_single_accountant(db, user)


def test_luna_named_relation_thing_path_still_owns(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "id-luna-fold")
    user = _user("u-luna-fold")
    cat = _possessed("gata", kind="thing", class_hint="cat")
    luna = SemanticEntityMention(
        text="Luna", kind_hint="thing", class_hint="cat", reference_kind="named", confidence=1.0
    )
    proposal = SemanticProposal(
        raw_input="minha gata se chama Luna",
        utterance_kind="assert",
        primitive_hint="relation",
        subject=cat,
        object=luna,
        relation_expression="named",
        link_semantics=True,
        classification_semantics=True,
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        claims=[
            SemanticClaim(kind=SemanticClaimKind.ENTITY, subject=cat),
            SemanticClaim(
                kind=SemanticClaimKind.RELATION, predicate="named", subject=cat, object=luna
            ),
        ],
        confidence=1.0,
    )
    result, outcome = _ingest(proposal, db, user)
    assert result.status is IngestStatus.COMMITTED, result.issues
    assert outcome.ir is not None
    assert outcome.ir.relation is not None
    assert outcome.ir.relation.type.key == "relation.owns"
    with open_sqlite_uow(db) as uow:
        names = {e.canonical_name for e in uow.entities.all_for_user(user.user_id)}
        assert "Luna" in names
        assert "gata" not in names
        uow.commit()
