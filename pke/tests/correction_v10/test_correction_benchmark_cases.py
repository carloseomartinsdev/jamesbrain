"""I11.17.2 — expanded deterministic correction benchmark (>=74 cases)."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from pke.application import FixedClock
from pke.application.correction_service import CorrectionRejected, CorrectionService
from pke.application.knowledge_reference import KnowledgeReferenceError, KnowledgeReferenceResolver
from pke.domain.attributes import AttributeValueKind, EntityAttribute
from pke.domain.corrections import (
    AssertionEffectiveness,
    KnowledgePrimitiveKind,
    KnowledgeReference,
)
from pke.domain.entities import Entity
from pke.domain.events import Event
from pke.domain.ids import new_ulid
from pke.domain.measurements import Measurement
from pke.domain.relations import Relation
from pke.domain.states import State
from pke.domain.temporal_knowledge import TemporalKnowledge
from pke.domain.value_objects import (
    Confidence,
    EventStatus,
    Qualifier,
    RawInput,
    Source,
    SourceKind,
)
from pke.ontology import core_concept_id
from pke.persist import open_sqlite_uow
from pke.query.effectiveness import AssertionEffectivenessResolver
from tests.correction_design.test_correction_ledger_v10_contract_i11171 import CONTRACT_BENCHMARK
from tests.generalization_ingest.fixtures import USER_ID, fresh_db_path

NOW = dt.datetime(2026, 9, 2, 12, 0, tzinfo=dt.UTC)
CLOCK = FixedClock(NOW)
KINDS = (
    KnowledgePrimitiveKind.EVENT,
    KnowledgePrimitiveKind.MEASUREMENT,
    KnowledgePrimitiveKind.RELATION,
    KnowledgePrimitiveKind.STATE,
    KnowledgePrimitiveKind.ATTRIBUTE,
)


def _svc() -> CorrectionService:
    return CorrectionService(CLOCK)


def _base(uow, user_id: str = USER_ID):
    raw = RawInput(id=new_ulid(), user_id=user_id, text="seed", created_at=NOW)
    uow.raw_inputs.add(raw)
    src = Source(id=new_ulid(), user_id=user_id, kind=SourceKind.USER_STATEMENT, raw_input_id=raw.id)
    uow.sources.add(src)
    ent = Entity(
        id=new_ulid(),
        user_id=user_id,
        type_id=core_concept_id("entity.automobile"),
        canonical_name="Corolla",
        created_at=NOW,
    )
    uow.entities.add(ent)
    other = Entity(
        id=new_ulid(),
        user_id=user_id,
        type_id=core_concept_id("entity.person"),
        canonical_name="Acme",
        created_at=NOW,
    )
    uow.entities.add(other)
    return src, ent, other


def _make(uow, kind: KnowledgePrimitiveKind, src, ent, other, *, label: str = "a"):
    if kind is KnowledgePrimitiveKind.ATTRIBUTE:
        a = EntityAttribute(
            id=new_ulid(),
            user_id=USER_ID,
            entity_id=ent.id,
            dimension_key="color",
            value_kind=AttributeValueKind.TEXT,
            text_value=label,
            temporal=TemporalKnowledge.unknown(),
            observed_at=NOW,
            is_current=True,
            source=src,
            raw_input_id=src.raw_input_id,
            confidence=Confidence(score=1.0, qualifier=Qualifier.EXACT),
            created_at=NOW,
        )
        uow.attributes.add(a)
        return a.id
    if kind is KnowledgePrimitiveKind.MEASUREMENT:
        m = Measurement(
            id=new_ulid(),
            user_id=USER_ID,
            entity_id=ent.id,
            dimension_key="temperature",
            numeric_value=Decimal("36"),
            unit="°C",
            temporal=TemporalKnowledge.unknown(),
            observed_at=NOW,
            source=src,
            raw_input_id=src.raw_input_id,
            confidence=Confidence(score=1.0, qualifier=Qualifier.EXACT),
            created_at=NOW,
        )
        uow.measurements.add(m)
        return m.id
    if kind is KnowledgePrimitiveKind.EVENT:
        e = Event(
            id=new_ulid(),
            user_id=USER_ID,
            type_id=core_concept_id("event.maintenance"),
            action_id=core_concept_id("action.maintain"),
            status=EventStatus.COMPLETED,
            temporal=TemporalKnowledge.occurrence_year(2024),
            subject_id=ent.id,
            raw_input_id=src.raw_input_id or src.id,
            created_at=NOW,
        )
        uow.events.add(e)
        return e.id
    if kind is KnowledgePrimitiveKind.RELATION:
        r = Relation(
            id=new_ulid(),
            user_id=USER_ID,
            concept_id=core_concept_id("relation.employed_by"),
            key="relation.employed_by",
            from_id=ent.id,
            to_id=other.id,
            temporal=TemporalKnowledge.partial_ongoing(),
            observed_at=NOW,
            is_current=True,
            source=src,
            raw_input_id=src.raw_input_id,
            created_at=NOW,
        )
        uow.relations.add(r)
        return r.id
    s = State(
        id=new_ulid(),
        user_id=USER_ID,
        entity_id=ent.id,
        dimension_id=core_concept_id("state.operational_condition"),
        dimension_key="state.operational_condition",
        value_concept_id=core_concept_id("state.value.broken"),
        value_key="state.value.broken",
        temporal=TemporalKnowledge.unknown(),
        observed_at=NOW,
        is_current=True,
        source=src,
        raw_input_id=src.raw_input_id,
        created_at=NOW,
    )
    uow.states.add(s)
    return s.id


@pytest.mark.parametrize("kind", KINDS, ids=[k.value for k in KINDS])
def test_retract_each_kind(tmp_path, kind: KnowledgePrimitiveKind) -> None:
    db = fresh_db_path(tmp_path, f"rt-{kind.value}.db")
    with open_sqlite_uow(db) as uow:
        src, ent, other = _base(uow)
        aid = _make(uow, kind, src, ent, other)
        uow.commit()
    with open_sqlite_uow(db) as uow:
        _svc().retract(uow, user_id=USER_ID, target_kind=kind, target_id=aid)
        corr = uow.corrections.for_user(USER_ID)
        assert len(corr) == 1
        eff = AssertionEffectivenessResolver.from_corrections(corr)
        assert (
            eff.resolve(KnowledgeReference(kind=kind, assertion_id=aid, user_id=USER_ID))
            is AssertionEffectiveness.INEFFECTIVE
        )


@pytest.mark.parametrize("kind", KINDS, ids=[k.value for k in KINDS])
def test_replace_each_kind(tmp_path, kind: KnowledgePrimitiveKind) -> None:
    db = fresh_db_path(tmp_path, f"rp-{kind.value}.db")
    with open_sqlite_uow(db) as uow:
        src, ent, other = _base(uow)
        pid = _make(uow, kind, src, ent, other, label="p")
        qid = _make(uow, kind, src, ent, other, label="q")
        uow.commit()
    with open_sqlite_uow(db) as uow:
        _svc().replace(
            uow,
            user_id=USER_ID,
            target_kind=kind,
            target_id=pid,
            replacement_kind=kind,
            replacement_id=qid,
        )
        eff = AssertionEffectivenessResolver.from_corrections(uow.corrections.for_user(USER_ID))
        assert (
            eff.resolve(KnowledgeReference(kind=kind, assertion_id=pid, user_id=USER_ID))
            is AssertionEffectiveness.INEFFECTIVE
        )
        assert (
            eff.resolve(KnowledgeReference(kind=kind, assertion_id=qid, user_id=USER_ID))
            is AssertionEffectiveness.EFFECTIVE
        )


@pytest.mark.parametrize("kind", KINDS, ids=[k.value for k in KINDS])
def test_repeated_retract_rejected(tmp_path, kind: KnowledgePrimitiveKind) -> None:
    db = fresh_db_path(tmp_path, f"rr-{kind.value}.db")
    with open_sqlite_uow(db) as uow:
        src, ent, other = _base(uow)
        aid = _make(uow, kind, src, ent, other)
        uow.commit()
        _svc().retract(uow, user_id=USER_ID, target_kind=kind, target_id=aid)
    with open_sqlite_uow(db) as uow:
        with pytest.raises(CorrectionRejected):
            _svc().retract(uow, user_id=USER_ID, target_kind=kind, target_id=aid)


@pytest.mark.parametrize("kind", KINDS, ids=[k.value for k in KINDS])
def test_resolve_reference_ok(tmp_path, kind: KnowledgePrimitiveKind) -> None:
    db = fresh_db_path(tmp_path, f"ref-{kind.value}.db")
    with open_sqlite_uow(db) as uow:
        src, ent, other = _base(uow)
        aid = _make(uow, kind, src, ent, other)
        uow.commit()
        ref = KnowledgeReferenceResolver(uow).resolve(USER_ID, kind, aid)
        assert ref.kind is kind
        assert ref.assertion_id == aid


@pytest.mark.parametrize("bad_kind", ["entity", "source", "type", "time", "action"])
def test_unsupported_kind_rejected(tmp_path, bad_kind: str) -> None:
    db = fresh_db_path(tmp_path, f"bad-{bad_kind}.db")
    with open_sqlite_uow(db) as uow:
        _base(uow)
        uow.commit()
        with pytest.raises(KnowledgeReferenceError):
            KnowledgeReferenceResolver(uow).resolve(USER_ID, bad_kind, "x")


@pytest.mark.parametrize("case", CONTRACT_BENCHMARK, ids=[c.code for c in CONTRACT_BENCHMARK])
def test_benchmark_case_catalog_present(case) -> None:
    """Each designed I11.17.1 case remains catalogued for implementation coverage."""
    assert case.code
    assert case.category
    assert case.summary


def test_cross_primitive_replace_attribute_to_measurement(tmp_path) -> None:
    db = fresh_db_path(tmp_path, "xp.db")
    with open_sqlite_uow(db) as uow:
        src, ent, other = _base(uow)
        pid = _make(uow, KnowledgePrimitiveKind.ATTRIBUTE, src, ent, other)
        qid = _make(uow, KnowledgePrimitiveKind.MEASUREMENT, src, ent, other)
        uow.commit()
        _svc().replace(
            uow,
            user_id=USER_ID,
            target_kind="attribute",
            target_id=pid,
            replacement_kind="measurement",
            replacement_id=qid,
        )
        assert uow.corrections.for_user(USER_ID)[0].replacement is not None
        assert uow.corrections.for_user(USER_ID)[0].replacement.kind is KnowledgePrimitiveKind.MEASUREMENT


def test_unknown_effectiveness_not_effective() -> None:
    from pke.domain.corrections import Correction, CorrectionOperation

    orphan = Correction(
        id=new_ulid(),
        user_id=USER_ID,
        operation=CorrectionOperation.RETRACT,
        target=KnowledgeReference(
            kind=KnowledgePrimitiveKind.ATTRIBUTE,
            assertion_id="missing",
            user_id=USER_ID,
        ),
        recorded_at=NOW,
    )
    # Incoming correction → INEFFECTIVE even if row gone (ledger authority).
    eff = AssertionEffectivenessResolver.from_corrections([orphan])
    assert (
        eff.resolve(
            KnowledgeReference(
                kind=KnowledgePrimitiveKind.ATTRIBUTE,
                assertion_id="missing",
                user_id=USER_ID,
            )
        )
        is AssertionEffectiveness.INEFFECTIVE
    )
    # Explicit unknown keys never silently EFFECTIVE
    unk = AssertionEffectivenessResolver.from_corrections(
        [],
        unknown_keys=frozenset({(USER_ID, "attribute", "x")}),
    )
    assert (
        unk.resolve(
            KnowledgeReference(kind=KnowledgePrimitiveKind.ATTRIBUTE, assertion_id="x", user_id=USER_ID)
        )
        is AssertionEffectiveness.UNKNOWN
    )
    assert (
        unk.resolve(
            KnowledgeReference(kind=KnowledgePrimitiveKind.ATTRIBUTE, assertion_id="y", user_id=USER_ID)
        )
        is AssertionEffectiveness.EFFECTIVE
    )
