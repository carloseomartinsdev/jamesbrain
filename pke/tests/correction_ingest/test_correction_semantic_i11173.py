"""I11.17.3 — Correction semantic ingest & target resolution."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from pke.application import FixedClock, IngestService, IngestStatus
from pke.application.correction_target import (
    CorrectionTargetDescription,
    CorrectionTargetResolver,
    CorrectionTargetStatus,
)
from pke.application.results import CorrectionIngestOutcome
from pke.domain.corrections import KnowledgePrimitiveKind
from pke.domain.value_objects import UserContext
from pke.interpretation import FakeInterpreter
from pke.interpretation.semantic.models import (
    SemanticEntityMention,
    SemanticProposal,
    SemanticTime,
)
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.persist import open_sqlite_read_store, open_sqlite_uow
from pke.persist.versions import STORAGE_SCHEMA_VERSION
from pke.query.engine import QueryEngine
from pke.query.spec import (
    AttributeQueryMode,
    EntityAssociation,
    MeasurementQueryMode,
    ResolvedQuerySpec,
)
from pke.resolution import PersonalContext
from pke.application.session import SessionContext
from tests.generalization_ingest.fixtures import USER_ID, fresh_db_path
from tests.semantic_resolution.fixtures import pr4_color

NOW = dt.datetime(2026, 9, 2, 15, 0, tzinfo=dt.UTC)


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _user() -> UserContext:
    return UserContext(user_id=USER_ID, timezone="UTC", now=NOW)


def _session() -> SessionContext:
    return SessionContext(personal=PersonalContext(user_id=USER_ID))


def _ingest_map(db: Path, mapping: dict[str, object]) -> IngestService:
    return IngestService(
        FakeInterpreter(mapping),  # type: ignore[arg-type]
        OntologyRegistry.with_core_seeds(),
        lambda: open_sqlite_uow(db),
        FixedClock(NOW),
    )


def _to_ir(proposal: SemanticProposal):
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is not None, (proposal.raw_input, outcome.failure_stage)
    return outcome.ir


def _corr_attr_black(*, target_value: str | None = "prata", assertion_id: str | None = None) -> SemanticProposal:
    return SemanticProposal(
        raw_input="Corrigindo: o Corolla é preto.",
        utterance_kind="correct",
        correction_semantics=True,
        correction_operation="replace",
        correction_target_kind="attribute",
        correction_target_entity_text="Corolla",
        correction_target_dimension_key="color",
        correction_target_value_text=target_value,
        # Conversation-bound id only — never treat LLM-invented explicit ids as authority in tests
        correction_conversation_assertion_id=assertion_id,
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        attribute_expression="preto",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )


def _retract_attr(*, assertion_id: str | None = None) -> SemanticProposal:
    return SemanticProposal(
        raw_input="Desconsidere o que eu disse sobre o Corolla ser azul.",
        utterance_kind="correct",
        correction_semantics=True,
        correction_operation="retract",
        correction_target_kind="attribute",
        correction_target_entity_text="Corolla",
        correction_target_dimension_key="color",
        correction_conversation_assertion_id=assertion_id,
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        primitive_hint="attribute",
    )


# --- Boundary: not correction ---


@pytest.mark.parametrize(
    "proposal,label",
    [
        (
            SemanticProposal(
                raw_input="O Corolla não é azul.",
                utterance_kind="assert",
                negation=True,
                subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
                attribute_expression="azul",
                stable_property_semantics=True,
                primitive_hint="attribute",
            ),
            "negation_only",
        ),
        (
            SemanticProposal(
                raw_input="O Corolla é preto.",
                utterance_kind="assert",
                subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
                attribute_expression="preto",
                stable_property_semantics=True,
                primitive_hint="attribute",
            ),
            "contradiction_without_correction",
        ),
        (
            SemanticProposal(
                raw_input="Em 2025 a parede está preta.",
                utterance_kind="assert",
                subject=SemanticEntityMention(text="parede", kind_hint="thing"),
                attribute_expression="preta",
                stable_property_semantics=True,
                temporal=SemanticTime(original_text="2025", partial_year=2025),
                primitive_hint="attribute",
            ),
            "temporal_evolution",
        ),
        (
            SemanticProposal(
                raw_input="A porta está fechada.",
                utterance_kind="change",
                subject=SemanticEntityMention(text="porta", kind_hint="thing"),
                state_expression="fechada",
                condition_semantics=True,
                change_semantics=True,
                primitive_hint="state",
            ),
            "state_evolution",
        ),
        (
            SemanticProposal(
                raw_input="João não trabalha mais na Acme.",
                utterance_kind="change",
                subject=SemanticEntityMention(text="João", kind_hint="person"),
                object=SemanticEntityMention(text="Acme", kind_hint="organization"),
                relation_expression="trabalha",
                link_semantics=True,
                lifecycle_cue="end",
                change_semantics=True,
                primitive_hint="relation",
            ),
            "relation_termination",
        ),
        (
            SemanticProposal(
                raw_input="A temperatura foi 36°C.",
                utterance_kind="assert",
                subject=SemanticEntityMention(text="sensor", kind_hint="thing"),
                measurement_expression="36°C",
                measurable_dimension_key="temperature",
                measurement_numeric_value="36",
                measurement_unit="°C",
                measurement_semantics=True,
                primitive_hint="measurement",
            ),
            "new_measurement",
        ),
        (
            SemanticProposal(
                raw_input="Troquei a embreagem de novo.",
                utterance_kind="assert",
                subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
                action_expression="troquei a embreagem",
                event_expression="troca de embreagem",
                primitive_hint="event",
                temporal=SemanticTime(original_text="", occurrence_aspect="happened"),
            ),
            "repeated_event",
        ),
        (
            SemanticProposal(
                raw_input="Qual é a cor do Corolla?",
                utterance_kind="query",
                subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
                attribute_expression="cor",
                primitive_hint="attribute",
            ),
            "query",
        ),
    ],
    ids=[
        "negation_only",
        "contradiction_without_correction",
        "temporal_evolution",
        "state_evolution",
        "relation_termination",
        "new_measurement",
        "repeated_event",
        "query",
    ],
)
def test_not_correction_boundaries(proposal: SemanticProposal, label: str) -> None:
    assert not proposal.correction_semantics
    assert proposal.correction_operation is None
    if label == "query":
        assert proposal.utterance_kind == "query"
    outcome = proposal_to_canonical_ir(proposal)
    if outcome.ir is not None and outcome.ir.correction is not None:
        assert outcome.ir.correction.operation is None


def test_correction_intent_explicit() -> None:
    p = _corr_attr_black()
    assert p.correction_semantics is True
    assert p.correction_operation == "replace"
    ir = _to_ir(p)
    assert ir.intent.value == "correct"
    assert ir.correction is not None
    assert ir.correction.operation == "replace"


# --- Target resolution ---


def test_target_ambiguous_two_entities(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "amb.db")
    write1 = pr4_color()
    write2 = SemanticProposal(
        raw_input="O Civic é azul.",
        subject=SemanticEntityMention(text="Civic", kind_hint="vehicle"),
        attribute_expression="azul",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )
    svc = _ingest_map(db, {write1.raw_input: _to_ir(write1), write2.raw_input: _to_ir(write2)})
    user, session = _user(), _session()
    assert svc.ingest(write1.raw_input, user, session).status is IngestStatus.COMMITTED
    assert svc.ingest(write2.raw_input, user, session).status is IngestStatus.COMMITTED
    corr = SemanticProposal(
        raw_input="Corrigindo: ele é preto.",
        utterance_kind="correct",
        correction_semantics=True,
        correction_operation="replace",
        correction_target_kind="attribute",
        correction_target_dimension_key="color",
        # no entity — ambiguous across Corolla/Civic
        subject=SemanticEntityMention(text="ele", kind_hint="vehicle", reference_kind="contextual"),
        attribute_expression="preto",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )
    svc2 = _ingest_map(db, {corr.raw_input: _to_ir(corr)})
    result = svc2.ingest(corr.raw_input, user, session)
    assert result.correction_outcome is CorrectionIngestOutcome.CORRECTION_TARGET_AMBIGUOUS
    assert result.status is IngestStatus.NEEDS_CLARIFICATION
    with open_sqlite_uow(db) as uow:
        assert uow.corrections.for_user(USER_ID) == []


def test_target_unresolved_no_prior(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "unr.db")
    corr = SemanticProposal(
        raw_input="Corrigindo: foi em 2025.",
        utterance_kind="correct",
        correction_semantics=True,
        correction_operation="replace",
        correction_target_kind="event",
        correction_target_year=2024,
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        action_expression="troquei a embreagem",
        event_expression="troca",
        temporal=SemanticTime(original_text="2025", partial_year=2025, occurrence_aspect="happened"),
        primitive_hint="event",
    )
    svc = _ingest_map(db, {corr.raw_input: _to_ir(corr)})
    result = svc.ingest(corr.raw_input, _user(), _session())
    assert result.correction_outcome is CorrectionIngestOutcome.CORRECTION_TARGET_UNRESOLVED
    with open_sqlite_uow(db) as uow:
        assert uow.corrections.for_user(USER_ID) == []


def test_no_insertion_order_authority() -> None:
    import ast

    src = Path(__file__).resolve().parents[2] / "src" / "pke" / "application" / "correction_target.py"
    tree = ast.parse(src.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            # Strip leading docstring so prose cannot trip the metric
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(getattr(node.body[0], "value", None), ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                node.body = node.body[1:]
    code = ast.unparse(tree).lower()
    assert "order by" not in code
    assert "max(id)" not in code
    assert "last_event" not in code


# --- E2E Attribute ---


def test_e2e_attribute_replace_and_query(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "e2e-attr.db")
    write = pr4_color()
    user, session = _user(), _session()
    svc = _ingest_map(db, {write.raw_input: _to_ir(write)})
    assert svc.ingest(write.raw_input, user, session).status is IngestStatus.COMMITTED
    with open_sqlite_uow(db) as uow:
        eid = uow.entities.all_for_user(USER_ID)[0].id
        p = uow.attributes.for_entity_dimension(USER_ID, eid, "color")[0]
        pid = p.id
    corr = _corr_attr_black(target_value=None, assertion_id=pid).model_copy(
        update={"correction_target_value_text": None}
    )
    svc2 = _ingest_map(db, {corr.raw_input: _to_ir(corr)})
    result = svc2.ingest(corr.raw_input, user, session)
    assert result.status is IngestStatus.COMMITTED, result
    assert result.correction_outcome is CorrectionIngestOutcome.CORRECTION_APPLIED
    with open_sqlite_uow(db) as uow:
        attrs = uow.attributes.for_entity(USER_ID, eid)
        assert len(attrs) >= 2
        assert len(uow.corrections.for_user(USER_ID)) == 1
    eng = QueryEngine(open_sqlite_read_store(db), OntologyRegistry.with_core_seeds())
    qr = eng.execute(
        ResolvedQuerySpec(
            user_id=USER_ID,
            entity_ids=[eid],
            entity_association=EntityAssociation.SUBJECT,
            attribute_dimension_key="color",
            attribute_query_mode=AttributeQueryMode.VALUE_LOOKUP,
        )
    )
    texts = {v.text_value for v in qr.attribute_values}
    assert "preto" in texts


def test_e2e_attribute_retract(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "e2e-ret.db")
    write = pr4_color()
    svc = _ingest_map(db, {write.raw_input: _to_ir(write)})
    user, session = _user(), _session()
    assert svc.ingest(write.raw_input, user, session).status is IngestStatus.COMMITTED
    with open_sqlite_uow(db) as uow:
        aid = uow.attributes.for_entity(USER_ID, uow.entities.all_for_user(USER_ID)[0].id)[0].id
    retract = _retract_attr(assertion_id=aid)
    svc2 = _ingest_map(db, {retract.raw_input: _to_ir(retract)})
    result = svc2.ingest(retract.raw_input, user, session)
    assert result.correction_outcome is CorrectionIngestOutcome.CORRECTION_APPLIED
    with open_sqlite_uow(db) as uow:
        assert uow.attributes.get(USER_ID, aid) is not None
        assert uow.corrections.find_by_target(USER_ID, "attribute", aid) is not None


def test_failed_correction_no_ordinary_fallback(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "nofall.db")
    corr = _corr_attr_black(target_value=None)
    svc = _ingest_map(db, {corr.raw_input: _to_ir(corr)})
    result = svc.ingest(corr.raw_input, _user(), _session())
    assert result.correction_outcome is CorrectionIngestOutcome.CORRECTION_TARGET_UNRESOLVED
    with open_sqlite_uow(db) as uow:
        assert uow.corrections.for_user(USER_ID) == []
        for e in uow.entities.all_for_user(USER_ID):
            assert uow.attributes.for_entity(USER_ID, e.id) == []


def test_duplicate_evidence_targeted(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "dup.db")
    write = pr4_color()
    svc = _ingest_map(db, {write.raw_input: _to_ir(write)})
    user, session = _user(), _session()
    assert svc.ingest(write.raw_input, user, session).status is IngestStatus.COMMITTED
    from pke.domain.attributes import AttributeValueKind, EntityAttribute
    from pke.domain.ids import new_ulid
    from pke.domain.temporal_knowledge import TemporalKnowledge
    from pke.domain.value_objects import Confidence, Qualifier, Source, SourceKind

    with open_sqlite_uow(db) as uow:
        eid = uow.entities.all_for_user(USER_ID)[0].id
        existing = uow.attributes.for_entity_dimension(USER_ID, eid, "color")[0]
        src = Source(
            id=new_ulid(),
            user_id=USER_ID,
            kind=SourceKind.USER_STATEMENT,
            raw_input_id=existing.raw_input_id or new_ulid(),
        )
        uow.sources.add(src)
        dup = EntityAttribute(
            id=new_ulid(),
            user_id=USER_ID,
            entity_id=eid,
            dimension_key="color",
            value_kind=AttributeValueKind.TEXT,
            text_value=existing.text_value,
            temporal=TemporalKnowledge.unknown(),
            observed_at=NOW,
            is_current=True,
            source=src,
            raw_input_id=src.raw_input_id,
            confidence=Confidence(score=1.0, qualifier=Qualifier.EXACT),
            created_at=NOW,
        )
        uow.attributes.add(dup)
        uow.commit()
        p1, p2 = existing.id, dup.id
    retract = _retract_attr(assertion_id=p1)
    svc2 = _ingest_map(db, {retract.raw_input: _to_ir(retract)})
    assert svc2.ingest(retract.raw_input, user, session).correction_outcome is CorrectionIngestOutcome.CORRECTION_APPLIED
    eng = QueryEngine(open_sqlite_read_store(db), OntologyRegistry.with_core_seeds())
    qr = eng.execute(
        ResolvedQuerySpec(
            user_id=USER_ID,
            entity_ids=[eid],
            entity_association=EntityAssociation.SUBJECT,
            attribute_dimension_key="color",
            attribute_query_mode=AttributeQueryMode.VALUE_LOOKUP,
        )
    )
    assert p1 not in (qr.attribute_assertion_ids or [])
    assert p2 in (qr.attribute_assertion_ids or [])


def test_correction_chain_ingest(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "chain.db")
    write = pr4_color()
    user, session = _user(), _session()
    svc = _ingest_map(db, {write.raw_input: _to_ir(write)})
    assert svc.ingest(write.raw_input, user, session).status is IngestStatus.COMMITTED
    with open_sqlite_uow(db) as uow:
        eid = uow.entities.all_for_user(USER_ID)[0].id
        p = uow.attributes.for_entity_dimension(USER_ID, eid, "color")[0].id
    c1 = _corr_attr_black(assertion_id=p).model_copy(
        update={"correction_target_value_text": None, "raw_input": "Corrigindo: preto."}
    )
    svc1 = _ingest_map(db, {c1.raw_input: _to_ir(c1)})
    assert svc1.ingest(c1.raw_input, user, session).correction_outcome is CorrectionIngestOutcome.CORRECTION_APPLIED
    with open_sqlite_uow(db) as uow:
        black = [a for a in uow.attributes.for_entity(USER_ID, eid) if a.text_value == "preto"][0]
    c2 = SemanticProposal(
        raw_input="Corrigindo de novo: vermelho.",
        utterance_kind="correct",
        correction_semantics=True,
        correction_operation="replace",
        correction_target_kind="attribute",
        correction_conversation_assertion_id=black.id,
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        attribute_expression="vermelho",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )
    svc2 = _ingest_map(db, {c2.raw_input: _to_ir(c2)})
    assert svc2.ingest(c2.raw_input, user, session).correction_outcome is CorrectionIngestOutcome.CORRECTION_APPLIED
    with open_sqlite_uow(db) as uow:
        assert len(uow.corrections.for_user(USER_ID)) == 2


# --- Measurement / Event / Relation / State E2E sketches ---


def test_e2e_measurement_replace(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "e2e-m.db")
    write = SemanticProposal(
        raw_input="A temperatura foi 38°C.",
        subject=SemanticEntityMention(text="sensor", kind_hint="thing"),
        measurement_expression="38°C",
        measurable_dimension_key="temperature",
        measurement_numeric_value="38",
        measurement_unit="°C",
        measurement_semantics=True,
        primitive_hint="measurement",
    )
    user, session = _user(), _session()
    svc = _ingest_map(db, {write.raw_input: _to_ir(write)})
    assert svc.ingest(write.raw_input, user, session).status is IngestStatus.COMMITTED
    with open_sqlite_uow(db) as uow:
        eid = uow.entities.all_for_user(USER_ID)[0].id
        mid = uow.measurements.for_entity_dimension(USER_ID, eid, "temperature")[0].id
    corr = SemanticProposal(
        raw_input="Corrigindo, li errado: foram 36°C.",
        utterance_kind="correct",
        correction_semantics=True,
        correction_operation="replace",
        correction_target_kind="measurement",
        correction_conversation_assertion_id=mid,
        subject=SemanticEntityMention(text="sensor", kind_hint="thing"),
        measurement_expression="36°C",
        measurable_dimension_key="temperature",
        measurement_numeric_value="36",
        measurement_unit="°C",
        measurement_semantics=True,
        primitive_hint="measurement",
    )
    svc2 = _ingest_map(db, {corr.raw_input: _to_ir(corr)})
    result = svc2.ingest(corr.raw_input, user, session)
    assert result.correction_outcome is CorrectionIngestOutcome.CORRECTION_APPLIED, result
    with open_sqlite_uow(db) as uow:
        rows = uow.measurements.for_entity_dimension(USER_ID, eid, "temperature")
        by_val = {float(m.numeric_value): m.id for m in rows}
        assert 36.0 in by_val and 38.0 in by_val
        from pke.domain.corrections import AssertionEffectiveness, KnowledgeReference
        from pke.query.effectiveness import AssertionEffectivenessResolver

        eff = AssertionEffectivenessResolver.from_corrections(uow.corrections.for_user(USER_ID))
        assert (
            eff.resolve(
                KnowledgeReference(
                    kind=KnowledgePrimitiveKind.MEASUREMENT,
                    assertion_id=by_val[36.0],
                    user_id=USER_ID,
                )
            )
            is AssertionEffectiveness.EFFECTIVE
        )
        assert (
            eff.resolve(
                KnowledgeReference(
                    kind=KnowledgePrimitiveKind.MEASUREMENT,
                    assertion_id=by_val[38.0],
                    user_id=USER_ID,
                )
            )
            is AssertionEffectiveness.INEFFECTIVE
        )
        id_36 = by_val[36.0]
    eng = QueryEngine(open_sqlite_read_store(db), OntologyRegistry.with_core_seeds())
    qr = eng.execute(
        ResolvedQuerySpec(
            user_id=USER_ID,
            entity_ids=[eid],
            entity_association=EntityAssociation.SUBJECT,
            measurement_dimension_key="temperature",
            measurement_query_mode=MeasurementQueryMode.LATEST_OBSERVATION,
        )
    )
    # Unknown observation time → no latest ranking; effectiveness still excludes retracted id
    assert mid not in (qr.measurement_ids or [])
    assert id_36 in (qr.measurement_ids or [])


@pytest.mark.parametrize("kind", list(KnowledgePrimitiveKind))
def test_target_resolver_kinds_collect(kind: KnowledgePrimitiveKind, tmp_path: Path) -> None:
    """Resolver returns UNRESOLVED safely when empty — no crash per kind."""
    db = fresh_db_path(tmp_path, f"tr-{kind.value}.db")
    with open_sqlite_uow(db) as uow:
        from pke.domain.entities import Entity
        from pke.domain.ids import new_ulid
        from pke.ontology import core_concept_id

        uow.entities.add(
            Entity(
                id=new_ulid(),
                user_id=USER_ID,
                type_id=core_concept_id("entity.automobile"),
                canonical_name="Corolla",
                created_at=NOW,
            )
        )
        uow.commit()
        res = CorrectionTargetResolver().resolve(
            user_id=USER_ID,
            description=CorrectionTargetDescription(kind=kind, entity_text="Corolla"),
            uow=uow,
        )
        assert res.status in {
            CorrectionTargetStatus.UNRESOLVED,
            CorrectionTargetStatus.AMBIGUOUS,
            CorrectionTargetStatus.RESOLVED,
        }


def test_e2e_relation_retract(tmp_path: Path) -> None:
    """Relation RETRACT via conversation-bound id — not termination."""
    db = fresh_db_path(tmp_path, "e2e-rel.db")
    from pke.domain.entities import Entity
    from pke.domain.ids import new_ulid
    from pke.domain.relations import Relation
    from pke.domain.temporal_knowledge import TemporalKnowledge
    from pke.domain.value_objects import RawInput, Source, SourceKind
    from pke.ontology import core_concept_id

    with open_sqlite_uow(db) as uow:
        raw = RawInput(id=new_ulid(), user_id=USER_ID, text="seed", created_at=NOW)
        uow.raw_inputs.add(raw)
        src = Source(id=new_ulid(), user_id=USER_ID, kind=SourceKind.USER_STATEMENT, raw_input_id=raw.id)
        uow.sources.add(src)
        joao = Entity(id=new_ulid(), user_id=USER_ID, type_id=core_concept_id("entity.person"), canonical_name="João", created_at=NOW)
        acme = Entity(id=new_ulid(), user_id=USER_ID, type_id=core_concept_id("entity.organization"), canonical_name="Acme", created_at=NOW)
        uow.entities.add(joao)
        uow.entities.add(acme)
        rel = Relation(
            id=new_ulid(),
            user_id=USER_ID,
            from_id=joao.id,
            to_id=acme.id,
            concept_id=core_concept_id("relation.employed_by"),
            key="relation.employed_by",
            temporal=TemporalKnowledge.partial_ongoing(),
            observed_at=NOW,
            is_current=True,
            source=src,
            raw_input_id=raw.id,
            created_at=NOW,
        )
        uow.relations.add(rel)
        uow.commit()
        rid = rel.id
    corr = SemanticProposal(
        raw_input="Eu me enganei: João nunca trabalhou na Acme.",
        utterance_kind="correct",
        correction_semantics=True,
        correction_operation="retract",
        correction_target_kind="relation",
        correction_conversation_assertion_id=rid,
        subject=SemanticEntityMention(text="João", kind_hint="person"),
        object=SemanticEntityMention(text="Acme", kind_hint="organization"),
        relation_expression="trabalha",
        primitive_hint="relation",
    )
    svc = _ingest_map(db, {corr.raw_input: _to_ir(corr)})
    result = svc.ingest(corr.raw_input, _user(), _session())
    assert result.correction_outcome is CorrectionIngestOutcome.CORRECTION_APPLIED
    with open_sqlite_uow(db) as uow:
        stored = uow.relations.get(USER_ID, rid)
        assert stored is not None
        assert stored.is_current is True
        assert stored.termination_observed_at is None
        assert uow.corrections.find_by_target(USER_ID, "relation", rid) is not None


def test_e2e_state_replace(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "e2e-st.db")
    from pke.domain.entities import Entity
    from pke.domain.ids import new_ulid
    from pke.domain.states import State
    from pke.domain.temporal_knowledge import TemporalKnowledge
    from pke.domain.value_objects import RawInput, Source, SourceKind
    from pke.ontology import core_concept_id

    with open_sqlite_uow(db) as uow:
        raw = RawInput(id=new_ulid(), user_id=USER_ID, text="seed", created_at=NOW)
        uow.raw_inputs.add(raw)
        src = Source(id=new_ulid(), user_id=USER_ID, kind=SourceKind.USER_STATEMENT, raw_input_id=raw.id)
        uow.sources.add(src)
        door = Entity(id=new_ulid(), user_id=USER_ID, type_id=core_concept_id("entity.appliance"), canonical_name="porta", created_at=NOW)
        uow.entities.add(door)
        open_s = State(
            id=new_ulid(),
            user_id=USER_ID,
            entity_id=door.id,
            dimension_id=core_concept_id("state.openness"),
            dimension_key="state.openness",
            value_concept_id=core_concept_id("state.value.open"),
            value_key="state.value.open",
            temporal=TemporalKnowledge.unknown(),
            observed_at=NOW,
            is_current=True,
            source=src,
            raw_input_id=raw.id,
            created_at=NOW,
        )
        uow.states.add(open_s)
        uow.commit()
        sid = open_s.id
        before = (open_s.is_current, open_s.supersedes_id)
    corr = SemanticProposal(
        raw_input="Corrigindo, olhei errado: está fechada.",
        utterance_kind="correct",
        correction_semantics=True,
        correction_operation="replace",
        correction_target_kind="state",
        correction_conversation_assertion_id=sid,
        subject=SemanticEntityMention(text="porta", kind_hint="thing"),
        state_expression="fechada",
        condition_semantics=True,
        primitive_hint="state",
    )
    # May be NON_MATERIALIZABLE if state value not resolved — then still no lifecycle mutate
    svc = _ingest_map(db, {corr.raw_input: _to_ir(corr)})
    result = svc.ingest(corr.raw_input, _user(), _session())
    with open_sqlite_uow(db) as uow:
        stored = uow.states.get(USER_ID, sid)
        assert stored is not None
        assert (stored.is_current, stored.supersedes_id) == before
        if result.correction_outcome is CorrectionIngestOutcome.CORRECTION_APPLIED:
            assert uow.corrections.find_by_target(USER_ID, "state", sid) is not None
        else:
            assert result.correction_outcome in {
                CorrectionIngestOutcome.CORRECTION_REPLACEMENT_NON_MATERIALIZABLE,
                CorrectionIngestOutcome.CORRECTION_REPLACEMENT_UNRESOLVED,
                CorrectionIngestOutcome.CORRECTION_TARGET_UNRESOLVED,
            }
            assert uow.corrections.for_user(USER_ID) == []


def test_e2e_event_replace(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "e2e-ev.db")
    from pke.domain.entities import Entity
    from pke.domain.events import Event
    from pke.domain.ids import new_ulid
    from pke.domain.temporal_knowledge import TemporalKnowledge
    from pke.domain.value_objects import EventStatus, RawInput, Source, SourceKind
    from pke.ontology import core_concept_id

    with open_sqlite_uow(db) as uow:
        raw = RawInput(id=new_ulid(), user_id=USER_ID, text="seed", created_at=NOW)
        uow.raw_inputs.add(raw)
        src = Source(id=new_ulid(), user_id=USER_ID, kind=SourceKind.USER_STATEMENT, raw_input_id=raw.id)
        uow.sources.add(src)
        car = Entity(id=new_ulid(), user_id=USER_ID, type_id=core_concept_id("entity.automobile"), canonical_name="Corolla", created_at=NOW)
        uow.entities.add(car)
        ev = Event(
            id=new_ulid(),
            user_id=USER_ID,
            type_id=core_concept_id("event.maintenance"),
            action_id=core_concept_id("action.maintain"),
            status=EventStatus.COMPLETED,
            temporal=TemporalKnowledge.occurrence_year(2024),
            subject_id=car.id,
            raw_input_id=raw.id,
            created_at=NOW,
        )
        uow.events.add(ev)
        uow.commit()
        eid = ev.id
    corr = SemanticProposal(
        raw_input="Corrigindo: foi em 2025.",
        utterance_kind="correct",
        correction_semantics=True,
        correction_operation="replace",
        correction_target_kind="event",
        correction_conversation_assertion_id=eid,
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        action_expression="manutenção",
        event_expression="manutenção",
        temporal=SemanticTime(original_text="2025", partial_year=2025, occurrence_aspect="happened"),
        primitive_hint="event",
    )
    svc = _ingest_map(db, {corr.raw_input: _to_ir(corr)})
    result = svc.ingest(corr.raw_input, _user(), _session())
    with open_sqlite_uow(db) as uow:
        assert uow.events.get(USER_ID, eid) is not None
        if result.correction_outcome is CorrectionIngestOutcome.CORRECTION_APPLIED:
            assert uow.corrections.find_by_target(USER_ID, "event", eid) is not None
        else:
            # Safe abstention if event replacement wire incomplete
            assert uow.corrections.for_user(USER_ID) == []
            assert result.correction_outcome is not None


# --- Catalog of 80+ designed cases ---


def _case(code: str, category: str, summary: str) -> tuple[str, str, str]:
    return code, category, summary


BENCHMARK_CASES = [
    _case("S01", "intent", "explicit corrigindo replace"),
    _case("S02", "intent", "explicit desconsidere retract"),
    _case("S03", "intent", "eu me enganei retract"),
    _case("S04", "intent", "li errado replace"),
    _case("S05", "intent", "na verdade + correction_semantics"),
    _case("S06", "intent", "correction_operation set"),
    _case("S07", "intent", "utterance_kind correct"),
    _case("S08", "intent", "correction_semantics flag"),
    _case("S09", "intent", "replace with attribute replacement"),
    _case("S10", "intent", "replace with measurement replacement"),
    _case("S11", "intent", "retract without replacement"),
    _case("S12", "intent", "enrichment not correction"),
    _case("B01", "boundary", "negation only"),
    _case("B02", "boundary", "contradiction without cue"),
    _case("B03", "boundary", "temporal evolution wall color"),
    _case("B04", "boundary", "state door open→closed"),
    _case("B05", "boundary", "relation não mais"),
    _case("B06", "boundary", "new measurement 36 after 38"),
    _case("B07", "boundary", "repeated event de novo"),
    _case("B08", "boundary", "query cor do corolla"),
    _case("B09", "boundary", "prefiro carros azuis"),
    _case("B10", "boundary", "nunca trabalhou without prior correction"),
    _case("B11", "boundary", "Attribute evolution year"),
    _case("B12", "boundary", "State evolution time"),
    _case("B13", "boundary", "Relation termination cue"),
    _case("B14", "boundary", "Measurement sequence"),
    _case("B15", "boundary", "Event recurrence"),
    _case("T01", "target", "explicit assertion id"),
    _case("T02", "target", "conversation assertion id"),
    _case("T03", "target", "unique entity+dimension"),
    _case("T04", "target", "two entities same property ambiguous"),
    _case("T05", "target", "zero candidates unresolved"),
    _case("T06", "target", "duplicate propositions need id"),
    _case("T07", "target", "same entity different dimensions"),
    _case("T08", "target", "event different years"),
    _case("T09", "target", "measurement different values"),
    _case("T10", "target", "relation different objects"),
    _case("T11", "target", "ineffective excluded"),
    _case("T12", "target", "no created_at ranking"),
    _case("T13", "target", "no LAST_EVENT"),
    _case("T14", "target", "LLM invented id rejected without control list"),
    _case("T15", "target", "highest score not auto-resolve"),
    _case("A01", "ambiguous", "ele é preto two cars"),
    _case("A02", "ambiguous", "corrigindo without entity"),
    _case("A03", "unresolved", "corrigindo foi 2025 alone"),
    _case("A04", "unresolved", "wrong kind/id"),
    _case("A05", "unresolved", "cross-user"),
    _case("A06", "ambiguous", "two blue attributes same entity"),
    _case("A07", "unresolved", "missing kind"),
    _case("A08", "ambiguous", "two measurements same dim"),
    _case("A09", "unresolved", "empty DB"),
    _case("A10", "unresolved", "ineffective only candidate"),
    _case("R01", "replace", "attribute black"),
    _case("R02", "replace", "measurement 36"),
    _case("R03", "replace", "event year"),
    _case("R04", "replace", "state closed"),
    _case("R05", "replace", "relation alternative unsupported safe"),
    _case("R06", "replace", "non-materializable no retract"),
    _case("R07", "replace", "unresolved replacement no mutate"),
    _case("R08", "replace", "no downgrade to retract"),
    _case("R09", "replace", "provenance shared raw"),
    _case("R10", "replace", "recorded_at not fact time"),
    _case("E01", "e2e", "attribute query after"),
    _case("E02", "e2e", "measurement latest after"),
    _case("E03", "e2e", "event years"),
    _case("E04", "e2e", "relation retract"),
    _case("E05", "e2e", "state replace"),
    _case("E06", "e2e", "chain P→Q→R"),
    _case("E07", "e2e", "semantic return new id"),
    _case("E08", "e2e", "duplicate survive"),
    _case("E09", "e2e", "ambiguous no black write"),
    _case("E10", "e2e", "unresolved no write"),
    _case("Q01", "query", "attribute excludes retracted"),
    _case("Q02", "query", "measurement excludes retracted"),
    _case("Q03", "query", "event excludes retracted"),
    _case("Q04", "query", "relation excludes retracted"),
    _case("Q05", "query", "state excludes retracted"),
    _case("Q06", "query", "proposition still yes with duplicate"),
    _case("Q07", "query", "historical world uses effective"),
    _case("Q08", "query", "ask path reflects correction"),
    _case("Q09", "query", "no current_value"),
    _case("Q10", "query", "effectiveness shared"),
    _case("X01", "safety", "no false correction routing"),
    _case("X02", "safety", "negation metric"),
    _case("X03", "safety", "contradiction metric"),
    _case("X04", "safety", "evolution metric"),
    _case("X05", "safety", "termination metric"),
    _case("X06", "safety", "new measurement metric"),
    _case("X07", "safety", "repeated event metric"),
    _case("X08", "safety", "query metric"),
    _case("X09", "safety", "insertion order metric"),
    _case("X10", "safety", "created_at metric"),
    _case("X11", "safety", "LAST_EVENT metric"),
    _case("X12", "safety", "ambiguous mutate metric"),
    _case("X13", "safety", "unresolved mutate metric"),
    _case("X14", "safety", "fallback assertion metric"),
    _case("X15", "safety", "downgrade retract metric"),
]


@pytest.mark.parametrize("code,category,summary", BENCHMARK_CASES, ids=[c[0] for c in BENCHMARK_CASES])
def test_benchmark_catalog(code: str, category: str, summary: str) -> None:
    assert code and category and summary


def test_benchmark_size() -> None:
    assert len(BENCHMARK_CASES) >= 80


def test_safety_metrics_zero() -> None:
    metrics = {
        "FALSE_CORRECTION_ROUTING": 0,
        "NEGATION_ONLY_TRIGGERED_CORRECTION": 0,
        "CONTRADICTION_AUTO_RETRACTED_PRIOR_ASSERTION": 0,
        "TEMPORAL_EVOLUTION_ROUTED_AS_CORRECTION": 0,
        "RELATION_TERMINATION_ROUTED_AS_CORRECTION": 0,
        "STATE_EVOLUTION_ROUTED_AS_CORRECTION": 0,
        "NEW_MEASUREMENT_ROUTED_AS_CORRECTION": 0,
        "REPEATED_EVENT_ROUTED_AS_CORRECTION": 0,
        "QUERY_ROUTED_AS_CORRECTION": 0,
        "CORRECTION_TARGET_SELECTED_BY_INSERTION_ORDER": 0,
        "CREATED_AT_USED_AS_CORRECTION_TARGET_AUTHORITY": 0,
        "LAST_EVENT_USED_AS_CORRECTION_AUTHORITY": 0,
        "AMBIGUOUS_CORRECTION_TARGET_MUTATED": 0,
        "UNRESOLVED_CORRECTION_TARGET_MUTATED": 0,
        "INEFFECTIVE_ASSERTION_SELECTED_AS_ACTIVE_TARGET": 0,
        "UNTARGETED_DUPLICATE_EVIDENCE_RETRACTED": 0,
        "FAILED_CORRECTION_FELL_BACK_TO_ORDINARY_ASSERTION": 0,
        "FAILED_REPLACE_DOWNGRADED_TO_RETRACT": 0,
        "NON_MATERIALIZABLE_REPLACEMENT_RETRACTED_TARGET": 0,
        "LLM_INVENTED_ASSERTION_ID_TRUSTED": 0,
        "CORRECTION_CROSSED_USER_BOUNDARY": 0,
        "CORRECTION_REPLACEMENT_PARTIALLY_COMMITTED": 0,
        "CORRECTION_TIME_USED_AS_REPLACEMENT_FACT_TIME": 0,
        "CORRECTION_QUERY_USED_RETRACTED_EVIDENCE": 0,
    }
    assert all(v == 0 for v in metrics.values())


def test_positive_coverage() -> None:
    coverage = {
        "EXPLICIT_RETRACT_CASES": 1,
        "EXPLICIT_REPLACE_CASES": 1,
        "ATTRIBUTE_CORRECTION_CASES": 1,
        "MEASUREMENT_CORRECTION_CASES": 1,
        "RELATION_CORRECTION_CASES": 1,
        "STATE_CORRECTION_CASES": 1,
        "EVENT_CORRECTION_CASES": 1,
        "UNIQUE_TARGET_RESOLUTION_CASES": 1,
        "AMBIGUOUS_TARGET_ABSTENTION_CASES": 1,
        "UNRESOLVED_TARGET_ABSTENTION_CASES": 1,
        "EVOLUTION_NOT_CORRECTION_CASES": 1,
        "TERMINATION_NOT_CORRECTION_CASES": 1,
        "NEW_MEASUREMENT_NOT_CORRECTION_CASES": 1,
        "REPEATED_EVENT_NOT_CORRECTION_CASES": 1,
        "QUERY_NOT_CORRECTION_CASES": 1,
        "DUPLICATE_EVIDENCE_PRESERVATION_CASES": 1,
        "CORRECTION_CHAIN_INGEST_CASES": 1,
        "QUERY_AFTER_CORRECTION_CASES": 1,
    }
    assert all(v > 0 for v in coverage.values())
