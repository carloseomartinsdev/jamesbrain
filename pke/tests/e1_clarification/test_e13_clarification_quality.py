"""E1.3 — Clarification quality: CLARIFY vs UNSUPPORTED vs ABSTAIN."""

from __future__ import annotations

from pathlib import Path

import pytest

from pke.application.ask import AskService
from pke.application.ask_results import AskStatus
from pke.application.clock import FixedClock
from pke.application.ingest import IngestService
from pke.application.results import IngestStatus
from pke.application.session import SessionContext
from pke.domain.value_objects import UserContext
from pke.interpretation import FakeInterpreter
from pke.interpretation.models import EntityMention, MentionReferenceKind, QueryIR, QuerySpec
from pke.interpretation.semantic.capability_strategy import (
    CapabilityOutcome,
    decide_capability,
)
from pke.interpretation.semantic.execution_readiness import assess_execution_readiness
from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal, SemanticTime
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir, resolve_proposal
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.domain.ontology import ConceptRef
from pke.persist import open_sqlite_read_store, open_sqlite_uow
from pke.resolution.context import PersonalContext
from tests.generalization_ingest.fixtures import fresh_db_path
from tests.integration.test_ingest import NOW


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _decide(proposal: SemanticProposal):
    readiness = assess_execution_readiness(resolve_proposal(proposal))
    return decide_capability(readiness, proposal=proposal), readiness


def test_e13_c01_missing_vehicle_value_clarify() -> None:
    proposal = SemanticProposal(
        raw_input="Meu carro é...",
        utterance_kind="assert",
        primitive_hint="attribute",
        subject=SemanticEntityMention(
            text="carro", kind_hint="vehicle", reference_kind="contextual", confidence=1.0
        ),
        attribute_expression="",
        stable_property_semantics=True,
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        confidence=1.0,
    )
    decision, _ = _decide(proposal)
    assert decision.outcome is CapabilityOutcome.CLARIFY
    assert decision.user_unlockable is True
    assert decision.clarification is not None
    assert decision.clarification.missing_slot == "attribute_value"
    assert decision.clarification.question_key == "clarify.attribute.vehicle_value"
    assert "user_unlockable=true" in decision.diagnostic


def test_e13_c02_entity_ambiguity_ask_clarify(tmp_path: Path) -> None:
    """Ambiguous entity with known candidates → Ask NEEDS_CLARIFICATION + options path."""
    from pke.domain.entities import Entity
    from pke.domain.ids import new_ulid
    from pke.ontology.seeds import core_concept_id

    db = fresh_db_path(tmp_path, "e13-c02")
    user = UserContext(user_id="u-amb", timezone="America/Fortaleza", now=NOW)
    with open_sqlite_uow(db) as uow:
        a = Entity(
            id=new_ulid(),
            user_id=user.user_id,
            type_id=core_concept_id("entity.automobile"),
            canonical_name="Honda",
            created_at=NOW,
        )
        b = Entity(
            id=new_ulid(),
            user_id=user.user_id,
            type_id=core_concept_id("entity.automobile"),
            canonical_name="bicicleta",
            created_at=NOW,
        )
        uow.entities.add(a)
        uow.entities.add(b)
        uow.commit()

    mention = EntityMention(
        text="ele",
        type_hint=ConceptRef(key="entity.automobile"),
        reference_kind=MentionReferenceKind.CONTEXTUAL,
    )
    # Seed personal context with both recent entities to force ambiguity
    session = SessionContext(
        personal=PersonalContext(
            user_id=user.user_id,
            recent_entity_ids=[a.id, b.id],
            last_by_type_id={},
        )
    )
    query_ir = QueryIR(
        raw_input="Ele é vermelho.",
        query=QuerySpec(
            intent="attribute",
            entities=[mention],
            entity_association="subject",
            attribute_dimension_key="color",
            attribute_query_mode="value_lookup",
        ),
    )
    ask = AskService(
        FakeInterpreter({"Ele é vermelho.": query_ir}),
        OntologyRegistry.with_core_seeds(),
        open_sqlite_read_store(db),
        FixedClock(NOW),
    )
    result = ask.ask("Ele é vermelho.", user, session)
    assert result.status is AskStatus.NEEDS_CLARIFICATION
    assert result.clarification is not None
    assert result.clarification.candidate_entity_ids
    assert len(result.clarification.candidate_entity_ids) >= 2


def test_e13_c03_known_unsupported_dimension() -> None:
    proposal = SemanticProposal(
        raw_input="Meu signo é Áries.",
        utterance_kind="assert",
        primitive_hint="attribute",
        subject=SemanticEntityMention(
            text="eu", kind_hint="person", reference_kind="contextual", confidence=1.0
        ),
        attribute_expression="signo Áries",
        stable_property_semantics=True,
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        confidence=1.0,
    )
    decision, _ = _decide(proposal)
    assert decision.outcome is CapabilityOutcome.UNSUPPORTED
    assert decision.user_unlockable is False
    assert decision.clarification is None
    assert decision.primary_reason == "unsupported_attribute_dimension"
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is None or getattr(outcome.ir, "attribute", None) is None


def test_e13_c04_unsupported_primitive() -> None:
    proposal = SemanticProposal(
        raw_input="Classifique isso como tipo X.",
        utterance_kind="assert",
        primitive_hint="type",
        classification_semantics=True,
        subject=SemanticEntityMention(text="isso", kind_hint="thing", confidence=1.0),
        temporal=SemanticTime(),
        confidence=1.0,
    )
    decision, _ = _decide(proposal)
    assert decision.outcome in {
        CapabilityOutcome.UNSUPPORTED,
        CapabilityOutcome.SAFE_ABSTAIN,
    }
    assert decision.clarification is None
    assert decision.user_unlockable is False
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is None


def test_e13_c05_unsafe_abstain() -> None:
    proposal = SemanticProposal(
        raw_input="???",
        utterance_kind="assert",
        primitive_hint="attribute",
        stable_property_semantics=True,
        attribute_expression="###",
        temporal=SemanticTime(),
        confidence=0.1,
    )
    decision, _ = _decide(proposal)
    assert decision.outcome in {
        CapabilityOutcome.SAFE_ABSTAIN,
        CapabilityOutcome.UNSUPPORTED,
        CapabilityOutcome.INVALID,
    }
    assert decision.clarification is None


def test_e13_c06_valid_name_commits(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "e13-c06")
    user = UserContext(user_id="u-e13", timezone="America/Fortaleza", now=NOW)
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
    decision, _ = _decide(proposal)
    assert decision.outcome is CapabilityOutcome.AUTO_EXECUTE
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is not None
    svc = IngestService(
        FakeInterpreter({proposal.raw_input: outcome.ir}),  # type: ignore[arg-type]
        OntologyRegistry.with_core_seeds(),
        lambda: open_sqlite_uow(db),
        FixedClock(NOW),
    )
    result = svc.ingest(
        proposal.raw_input,
        user,
        SessionContext(personal=PersonalContext(user_id=user.user_id)),
    )
    assert result.status is IngestStatus.COMMITTED


def test_e13_c07_valid_vehicle_commits(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "e13-c07")
    user = UserContext(user_id="u-e13v", timezone="America/Fortaleza", now=NOW)
    proposal = SemanticProposal(
        raw_input="Meu carro é um Honda Civic.",
        utterance_kind="assert",
        primitive_hint="attribute",
        subject=SemanticEntityMention(
            text="carro", kind_hint="vehicle", reference_kind="contextual", confidence=1.0
        ),
        attribute_expression="Honda Civic",
        stable_property_semantics=True,
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        confidence=1.0,
    )
    decision, _ = _decide(proposal)
    assert decision.outcome is CapabilityOutcome.AUTO_EXECUTE
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is not None
    svc = IngestService(
        FakeInterpreter({proposal.raw_input: outcome.ir}),  # type: ignore[arg-type]
        OntologyRegistry.with_core_seeds(),
        lambda: open_sqlite_uow(db),
        FixedClock(NOW),
    )
    result = svc.ingest(
        proposal.raw_input,
        user,
        SessionContext(personal=PersonalContext(user_id=user.user_id)),
    )
    assert result.status is IngestStatus.COMMITTED


def test_e13_n01_missing_value_not_unsupported() -> None:
    proposal = SemanticProposal(
        raw_input="Meu carro é",
        utterance_kind="assert",
        primitive_hint="attribute",
        subject=SemanticEntityMention(
            text="carro", kind_hint="vehicle", reference_kind="contextual", confidence=1.0
        ),
        attribute_expression="",
        stable_property_semantics=True,
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        confidence=1.0,
    )
    decision, _ = _decide(proposal)
    assert decision.outcome is CapabilityOutcome.CLARIFY
    assert decision.outcome is not CapabilityOutcome.UNSUPPORTED


def test_e13_n02_unknown_unsafe_not_forced_clarify() -> None:
    proposal = SemanticProposal(
        raw_input="xyzzy plugh",
        utterance_kind="assert",
        primitive_hint="attribute",
        attribute_expression="xyzzy plugh",
        stable_property_semantics=True,
        temporal=SemanticTime(),
        confidence=1.0,
    )
    decision, _ = _decide(proposal)
    assert decision.outcome is not CapabilityOutcome.CLARIFY


def test_e13_n03_unsupported_no_ir() -> None:
    proposal = SemanticProposal(
        raw_input="Meu signo é Áries.",
        utterance_kind="assert",
        primitive_hint="attribute",
        subject=SemanticEntityMention(
            text="eu", kind_hint="person", reference_kind="contextual", confidence=1.0
        ),
        attribute_expression="signo Áries",
        stable_property_semantics=True,
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        confidence=1.0,
    )
    decision, _ = _decide(proposal)
    assert decision.outcome is CapabilityOutcome.UNSUPPORTED
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is None or getattr(outcome.ir, "attribute", None) is None
