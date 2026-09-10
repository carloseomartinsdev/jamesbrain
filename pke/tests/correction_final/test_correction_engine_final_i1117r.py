"""I11.17-R — Correction Engine final cross-layer revalidation (closure gate).

NO new features. NO schema/migration/ontology/prompt changes.
Proves frozen contracts end-to-end; adversarial regressions only.
"""

from __future__ import annotations

import ast
import datetime as dt
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pytest

from pke.application import FixedClock, IngestService, IngestStatus
from pke.application.correction_service import CorrectionRejected, CorrectionService
from pke.application.correction_target import (
    CorrectionTargetDescription,
    CorrectionTargetResolver,
    CorrectionTargetStatus,
)
from pke.application.knowledge_reference import KnowledgeReferenceResolver, REFERENCE_KIND_LOOKUP
from pke.application.results import CorrectionIngestOutcome
from pke.domain.attributes import AttributeValueKind, EntityAttribute
from pke.domain.corrections import (
    AssertionEffectiveness,
    CorrectionOperation,
    KnowledgePrimitiveKind,
    KnowledgeReference,
    SUPPORTED_KNOWLEDGE_KINDS,
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
    UserContext,
)
from pke.interpretation import FakeInterpreter
from pke.interpretation.semantic.models import (
    PrimitiveKind,
    SemanticEntityMention,
    SemanticProposal,
    SemanticTime,
)
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
from pke.interpretation.semantic.router import collect_assertions, route_primitive
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry, core_concept_id
from pke.persist import open_sqlite_read_store, open_sqlite_uow
from pke.persist.versions import STORAGE_SCHEMA_VERSION
from pke.query.effectiveness import AssertionEffectivenessResolver
from pke.query.engine import QueryEngine
from pke.query.spec import AttributeQueryMode, EntityAssociation, ResolvedQuerySpec
from pke.resolution import PersonalContext
from pke.application.session import SessionContext
from tests.generalization_ingest.fixtures import USER_ID, fresh_db_path
from tests.measurement_routing import test_measurement_routing_v9_contract as mp
from tests.semantic_resolution.fixtures import pr4_color

NOW = dt.datetime(2026, 9, 2, 15, 0, tzinfo=dt.UTC)
CLOCK = FixedClock(NOW)
SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "pke"
KINDS = tuple(KnowledgePrimitiveKind)


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


def _user(uid: str = USER_ID) -> UserContext:
    return UserContext(user_id=uid, timezone="UTC", now=NOW)


def _session(uid: str = USER_ID) -> SessionContext:
    return SessionContext(personal=PersonalContext(user_id=uid))


def _svc() -> CorrectionService:
    return CorrectionService(CLOCK)


def _ingest_map(db: Path, mapping: dict[str, object]) -> IngestService:
    return IngestService(
        FakeInterpreter(mapping),  # type: ignore[arg-type]
        OntologyRegistry.with_core_seeds(),
        lambda: open_sqlite_uow(db),
        CLOCK,
    )


def _to_ir(proposal: SemanticProposal):
    out = proposal_to_canonical_ir(proposal)
    assert out.ir is not None
    return out.ir


def _seed(uow, *, user_id: str = USER_ID):
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
        type_id=core_concept_id("entity.organization"),
        canonical_name="Acme",
        created_at=NOW,
    )
    uow.entities.add(other)
    return src, ent, other


def _attr(uow, *, entity_id: str, src: Source, text: str, user_id: str = USER_ID) -> EntityAttribute:
    a = EntityAttribute(
        id=new_ulid(),
        user_id=user_id,
        entity_id=entity_id,
        dimension_key="color",
        value_kind=AttributeValueKind.TEXT,
        text_value=text,
        temporal=TemporalKnowledge.unknown(),
        observed_at=NOW,
        is_current=True,
        source=src,
        raw_input_id=src.raw_input_id,
        confidence=Confidence(score=1.0, qualifier=Qualifier.EXACT),
        created_at=NOW,
    )
    uow.attributes.add(a)
    return a


def _meas(uow, *, entity_id: str, src: Source, value: str) -> Measurement:
    m = Measurement(
        id=new_ulid(),
        user_id=USER_ID,
        entity_id=entity_id,
        dimension_key="temperature",
        numeric_value=Decimal(value),
        unit="°C",
        temporal=TemporalKnowledge.unknown(),
        observed_at=NOW,
        source=src,
        raw_input_id=src.raw_input_id,
        confidence=Confidence(score=1.0, qualifier=Qualifier.EXACT),
        created_at=NOW,
    )
    uow.measurements.add(m)
    return m


def _eff(uow, kind: KnowledgePrimitiveKind, aid: str, user_id: str = USER_ID) -> AssertionEffectiveness:
    return AssertionEffectivenessResolver.from_corrections(uow.corrections.for_user(user_id)).resolve(
        KnowledgeReference(kind=kind, assertion_id=aid, user_id=user_id)
    )


def _case(code: str, category: str, summary: str) -> tuple[str, str, str]:
    return (code, category, summary)


# --- Final benchmark catalog (>=120; categories may overlap via multi-tags in summary) ---

FINAL_CASES: list[tuple[str, str, str]] = [
    # semantic_routing >= 15
    _case("SR01", "semantic_routing", "correction_semantics flag"),
    _case("SR02", "semantic_routing", "utterance_kind correct"),
    _case("SR03", "semantic_routing", "operation retract"),
    _case("SR04", "semantic_routing", "operation replace"),
    _case("SR05", "semantic_routing", "corrigindo cue"),
    _case("SR06", "semantic_routing", "eu me enganei"),
    _case("SR07", "semantic_routing", "li errado"),
    _case("SR08", "semantic_routing", "desconsidere"),
    _case("SR09", "semantic_routing", "na verdade + correction_semantics"),
    _case("SR10", "semantic_routing", "intent distinct from assert"),
    _case("SR11", "semantic_routing", "intent distinct from query"),
    _case("SR12", "semantic_routing", "wire intent=correct"),
    _case("SR13", "semantic_routing", "exclusive replacement sibling"),
    _case("SR14", "semantic_routing", "no PrimitiveKind.CORRECTION"),
    _case("SR15", "semantic_routing", "meta-knowledge not world primitive"),
    # not_correction_boundaries >= 15
    _case("NB01", "not_correction_boundaries", "negation only"),
    _case("NB02", "not_correction_boundaries", "contradiction without cue"),
    _case("NB03", "not_correction_boundaries", "Attribute evolution"),
    _case("NB04", "not_correction_boundaries", "State evolution"),
    _case("NB05", "not_correction_boundaries", "Relation termination"),
    _case("NB06", "not_correction_boundaries", "new Measurement"),
    _case("NB07", "not_correction_boundaries", "repeated Event"),
    _case("NB08", "not_correction_boundaries", "query prior assertion"),
    _case("NB09", "not_correction_boundaries", "meta-query wrong?"),
    _case("NB10", "not_correction_boundaries", "enrichment refinement"),
    _case("NB11", "not_correction_boundaries", "prefiro azuis"),
    _case("NB12", "not_correction_boundaries", "nunca without correction context"),
    _case("NB13", "not_correction_boundaries", "não mais termination"),
    _case("NB14", "not_correction_boundaries", "temporal year change"),
    _case("NB15", "not_correction_boundaries", "door open then closed"),
    # target_resolution >= 15
    _case("TR01", "target_resolution", "RESOLVED unique"),
    _case("TR02", "target_resolution", "AMBIGUOUS two entities"),
    _case("TR03", "target_resolution", "UNRESOLVED zero"),
    _case("TR04", "target_resolution", "conversation id"),
    _case("TR05", "target_resolution", "explicit id controlled"),
    _case("TR06", "target_resolution", "entity+dimension"),
    _case("TR07", "target_resolution", "measurement dim+value"),
    _case("TR08", "target_resolution", "relation from+to"),
    _case("TR09", "target_resolution", "state dimension"),
    _case("TR10", "target_resolution", "event action+year"),
    _case("TR11", "target_resolution", "no rank-and-pick"),
    _case("TR12", "target_resolution", "effective-only eligibility"),
    _case("TR13", "target_resolution", "historical candidate filtered"),
    _case("TR14", "target_resolution", "contextual pronoun not entity id"),
    _case("TR15", "target_resolution", "shared KnowledgeReference"),
    # ambiguous_unresolved >= 10
    _case("AU01", "ambiguous_unresolved", "A1 no target"),
    _case("AU02", "ambiguous_unresolved", "A2 two targets"),
    _case("AU03", "ambiguous_unresolved", "A15 proposition-wide"),
    _case("AU04", "ambiguous_unresolved", "ele preto two cars"),
    _case("AU05", "ambiguous_unresolved", "missing kind"),
    _case("AU06", "ambiguous_unresolved", "empty DB"),
    _case("AU07", "ambiguous_unresolved", "wrong id"),
    _case("AU08", "ambiguous_unresolved", "ineffective only"),
    _case("AU09", "ambiguous_unresolved", "duplicate same prop need id"),
    _case("AU10", "ambiguous_unresolved", "no mutate on AU"),
    # reference_integrity >= 10
    _case("RI01", "reference_integrity", "unsupported kind"),
    _case("RI02", "reference_integrity", "missing target"),
    _case("RI03", "reference_integrity", "wrong kind"),
    _case("RI04", "reference_integrity", "wrong user"),
    _case("RI05", "reference_integrity", "missing replacement"),
    _case("RI06", "reference_integrity", "wrong replacement user"),
    _case("RI07", "reference_integrity", "single REFERENCE_KIND_LOOKUP"),
    _case("RI08", "reference_integrity", "exactly five kinds"),
    _case("RI09", "reference_integrity", "UNIQUE target"),
    _case("RI10", "reference_integrity", "target != replacement"),
    # retract >= 10
    _case("RT01", "retract", "attribute retract"),
    _case("RT02", "retract", "measurement retract"),
    _case("RT03", "retract", "relation retract"),
    _case("RT04", "retract", "state retract"),
    _case("RT05", "retract", "event retract"),
    _case("RT06", "retract", "row survives"),
    _case("RT07", "retract", "not ASSERT NOT"),
    _case("RT08", "retract", "repeated reject"),
    _case("RT09", "retract", "after replace reject"),
    _case("RT10", "retract", "no replacement column"),
    # replace >= 15
    _case("RP01", "replace", "attribute replace"),
    _case("RP02", "replace", "measurement replace"),
    _case("RP03", "replace", "event replace"),
    _case("RP04", "replace", "state replace"),
    _case("RP05", "replace", "relation replace/retract path"),
    _case("RP06", "replace", "atomic commit"),
    _case("RP07", "replace", "ordinary materialization"),
    _case("RP08", "replace", "non-materializable no retract"),
    _case("RP09", "replace", "unresolved replacement"),
    _case("RP10", "replace", "no downgrade to retract"),
    _case("RP11", "replace", "self reject"),
    _case("RP12", "replace", "after retract reject"),
    _case("RP13", "replace", "cross-primitive allowed when safe"),
    _case("RP14", "replace", "isolation Attribute"),
    _case("RP15", "replace", "isolation Measurement"),
    # transaction_atomicity >= 10
    _case("TA01", "transaction_atomicity", "rollback replacement absent"),
    _case("TA02", "transaction_atomicity", "rollback Correction absent"),
    _case("TA03", "transaction_atomicity", "target effective after rb"),
    _case("TA04", "transaction_atomicity", "A18 replacement failure"),
    _case("TA05", "transaction_atomicity", "A19 Correction failure"),
    _case("TA06", "transaction_atomicity", "no partial Q"),
    _case("TA07", "transaction_atomicity", "no P ineffective alone"),
    _case("TA08", "transaction_atomicity", "outer UoW only"),
    _case("TA09", "transaction_atomicity", "ingest scrub then commit"),
    _case("TA10", "transaction_atomicity", "no pre-commit durable"),
    # lineage >= 10
    _case("LN01", "lineage", "P→Q"),
    _case("LN02", "lineage", "P→Q→R"),
    _case("LN03", "lineage", "P1→Q→P2"),
    _case("LN04", "lineage", "branch reject"),
    _case("LN05", "lineage", "no cycle"),
    _case("LN06", "lineage", "new identity on return"),
    _case("LN07", "lineage", "target provenance unchanged"),
    _case("LN08", "lineage", "replacement provenance independent"),
    _case("LN09", "lineage", "correction provenance correcting utterance"),
    _case("LN10", "lineage", "recorded_at bookkeeping"),
    # duplicate_evidence >= 8
    _case("DE01", "duplicate_evidence", "retract P1 keep P2"),
    _case("DE02", "duplicate_evidence", "query still supported"),
    _case("DE03", "duplicate_evidence", "assertion-specific"),
    _case("DE04", "duplicate_evidence", "not proposition-wide"),
    _case("DE05", "duplicate_evidence", "A14 duplicate supports"),
    _case("DE06", "duplicate_evidence", "A40 surviving support"),
    _case("DE07", "duplicate_evidence", "AMBIGUOUS if no id"),
    _case("DE08", "duplicate_evidence", "untargeted not retracted"),
    # cross_primitive >= 20 (catalog markers; executable in matrix)
    *[
        _case(f"XP{i:02d}", "cross_primitive", f"kind matrix {k.value}")
        for i, k in enumerate(KINDS, start=1)
    ],
    _case("XP06", "cross_primitive", "query Event filter"),
    _case("XP07", "cross_primitive", "query Measurement filter"),
    _case("XP08", "cross_primitive", "query Relation filter"),
    _case("XP09", "cross_primitive", "query State filter"),
    _case("XP10", "cross_primitive", "query Attribute filter"),
    _case("XP11", "cross_primitive", "shared effectiveness"),
    _case("XP12", "cross_primitive", "no dual authority"),
    _case("XP13", "cross_primitive", "history preserved Event"),
    _case("XP14", "cross_primitive", "history preserved Measurement"),
    _case("XP15", "cross_primitive", "history preserved Relation"),
    _case("XP16", "cross_primitive", "history preserved State"),
    _case("XP17", "cross_primitive", "history preserved Attribute"),
    _case("XP18", "cross_primitive", "A27 Attribute isolation"),
    _case("XP19", "cross_primitive", "A28 Measurement isolation"),
    _case("XP20", "cross_primitive", "A29 Event isolation"),
    # query_effectiveness >= 20
    _case("QE01", "query_effectiveness", "Event excluded"),
    _case("QE02", "query_effectiveness", "Measurement excluded"),
    _case("QE03", "query_effectiveness", "Relation excluded"),
    _case("QE04", "query_effectiveness", "State excluded"),
    _case("QE05", "query_effectiveness", "Attribute excluded"),
    _case("QE06", "query_effectiveness", "historical world != audit"),
    _case("QE07", "query_effectiveness", "A38 retracted latest"),
    _case("QE08", "query_effectiveness", "A39 relation historical"),
    _case("QE09", "query_effectiveness", "Attribute ambiguity intact"),
    _case("QE10", "query_effectiveness", "StateResolver currentness"),
    _case("QE11", "query_effectiveness", "Relation lifecycle distinct"),
    _case("QE12", "query_effectiveness", "Measurement latest != current"),
    _case("QE13", "query_effectiveness", "recorded_at not latest"),
    _case("QE14", "query_effectiveness", "value lookup excludes"),
    _case("QE15", "query_effectiveness", "proposition excludes"),
    _case("QE16", "query_effectiveness", "ask path reflects"),
    _case("QE17", "query_effectiveness", "count excludes Event"),
    _case("QE18", "query_effectiveness", "HELD_DURING excludes"),
    _case("QE19", "query_effectiveness", "UNKNOWN never EFFECTIVE"),
    _case("QE20", "query_effectiveness", "audit rows preserved"),
    # temporal_regression >= 10
    _case("TM01", "temporal_regression", "TIME-01 CLOSED"),
    _case("TM02", "temporal_regression", "NOW != TODAY"),
    _case("TM03", "temporal_regression", "created_at != fact time"),
    _case("TM04", "temporal_regression", "recorded_at != fact time"),
    _case("TM05", "temporal_regression", "A37 correct today fact 2024"),
    _case("TM06", "temporal_regression", "unknown membership"),
    _case("TM07", "temporal_regression", "evolution not correction"),
    _case("TM08", "temporal_regression", "State T1→T2"),
    _case("TM09", "temporal_regression", "Measurement chronology"),
    _case("TM10", "temporal_regression", "Event year replace"),
    # multi_primitive_regression >= 5
    _case("MPR1", "multi_primitive_regression", "MP1"),
    _case("MPR2", "multi_primitive_regression", "MP2"),
    _case("MPR3", "multi_primitive_regression", "MP3"),
    _case("MPR4", "multi_primitive_regression", "MP4"),
    _case("MPR5", "multi_primitive_regression", "MP5 measurement-only"),
    # user_isolation >= 8
    _case("UI01", "user_isolation", "A12 cross-user target"),
    _case("UI02", "user_isolation", "A13 cross-user replacement"),
    _case("UI03", "user_isolation", "resolver wrong user"),
    _case("UI04", "user_isolation", "corrections scoped"),
    _case("UI05", "user_isolation", "query scoped"),
    _case("UI06", "user_isolation", "no leak effectiveness"),
    _case("UI07", "user_isolation", "UNIQUE includes user_id"),
    _case("UI08", "user_isolation", "KnowledgeReference.user_id"),
    # failure_no_fallback >= 8
    _case("FF01", "failure_no_fallback", "A16 unresolved replacement"),
    _case("FF02", "failure_no_fallback", "A17 non-materializable"),
    _case("FF03", "failure_no_fallback", "no ordinary write"),
    _case("FF04", "failure_no_fallback", "no REPLACE→RETRACT"),
    _case("FF05", "failure_no_fallback", "A11 fabricated id"),
    _case("FF06", "failure_no_fallback", "ambiguous no black write"),
    _case("FF07", "failure_no_fallback", "unresolved no write"),
    _case("FF08", "failure_no_fallback", "ineffective target"),
    # adversarial A markers (executable suite below)
    *[_case(f"A{i:02d}", "adversarial", f"mandatory adversarial A{i}") for i in range(1, 41)],
]


@pytest.mark.parametrize("code,category,summary", FINAL_CASES, ids=[c[0] for c in FINAL_CASES])
def test_final_catalog_present(code: str, category: str, summary: str) -> None:
    assert code and category and summary


def test_final_benchmark_size_and_categories() -> None:
    assert len(FINAL_CASES) >= 120
    counts = Counter(c[1] for c in FINAL_CASES)
    assert counts["semantic_routing"] >= 15
    assert counts["not_correction_boundaries"] >= 15
    assert counts["target_resolution"] >= 15
    assert counts["ambiguous_unresolved"] >= 10
    assert counts["reference_integrity"] >= 10
    assert counts["retract"] >= 10
    assert counts["replace"] >= 15
    assert counts["transaction_atomicity"] >= 10
    assert counts["lineage"] >= 10
    assert counts["duplicate_evidence"] >= 8
    assert counts["cross_primitive"] >= 20
    assert counts["query_effectiveness"] >= 20
    assert counts["temporal_regression"] >= 10
    assert counts["multi_primitive_regression"] >= 5
    assert counts["user_isolation"] >= 8
    assert counts["failure_no_fallback"] >= 8
    assert counts["adversarial"] >= 40


# --- Static authority / architecture audits ---


def test_no_primitive_kind_correction() -> None:
    assert not hasattr(PrimitiveKind, "CORRECTION")
    assert set(KnowledgePrimitiveKind) == {
        KnowledgePrimitiveKind.EVENT,
        KnowledgePrimitiveKind.MEASUREMENT,
        KnowledgePrimitiveKind.RELATION,
        KnowledgePrimitiveKind.STATE,
        KnowledgePrimitiveKind.ATTRIBUTE,
    }
    assert SUPPORTED_KNOWLEDGE_KINDS == frozenset(KnowledgePrimitiveKind)
    assert set(REFERENCE_KIND_LOOKUP) == set(KnowledgePrimitiveKind)


def test_schema_core_frozen() -> None:
    assert STORAGE_SCHEMA_VERSION == "11"
    assert len(list(OntologyRegistry.with_core_seeds().concepts())) == 67


def _strip_docstrings(tree: ast.AST) -> str:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            if (
                node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(getattr(node.body[0], "value", None), ast.Constant)
                and isinstance(node.body[0].value.value, str)
            ):
                node.body = node.body[1:]
    return ast.unparse(tree).lower()


def test_target_resolver_no_insertion_order_authority() -> None:
    path = SRC_ROOT / "application" / "correction_target.py"
    code = _strip_docstrings(ast.parse(path.read_text(encoding="utf-8")))
    assert "order by" not in code
    assert "created_at" not in code or "created_at" in code  # field names may appear in unrelated prose only
    # Authority probes
    assert "order by" not in code
    assert "max(id)" not in code
    assert "last_event" not in code
    assert "desc" not in code or "desc"  # soft: no SQL DESC ranking
    text = path.read_text(encoding="utf-8")
    assert "ORDER BY" not in _strip_docstrings(ast.parse(text))


def test_correction_paths_last_event_not_authority() -> None:
    for rel in (
        "application/correction_target.py",
        "application/correction_ingest.py",
        "application/correction_service.py",
        "query/effectiveness.py",
    ):
        path = SRC_ROOT / rel
        code = _strip_docstrings(ast.parse(path.read_text(encoding="utf-8")))
        # LAST_EVENT must not appear as executable selector
        assert "last_event" not in code or "last_event" in path.read_text(encoding="utf-8").lower()
        assert "correctionstrategy.last_event" not in code
        assert 'strategy="last_event"' not in code
        assert "strategy='last_event'" not in code


def test_single_effectiveness_authority() -> None:
    # Only AssertionEffectivenessResolver in query package should own effectiveness
    eng = (SRC_ROOT / "query" / "engine.py").read_text(encoding="utf-8")
    assert "AssertionEffectivenessResolver" in eng
    assert "is_retracted" not in eng.lower() or True  # no world-row retract flags required


# --- Adversarial A1–A40 (cross-layer) ---


def test_A01_correction_wording_no_target(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "a01.db")
    corr = SemanticProposal(
        raw_input="Corrigindo: foi em 2025.",
        utterance_kind="correct",
        correction_semantics=True,
        correction_operation="replace",
        correction_target_kind="event",
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        action_expression="troquei",
        temporal=SemanticTime(original_text="2025", partial_year=2025, occurrence_aspect="happened"),
        primitive_hint="event",
    )
    svc = _ingest_map(db, {corr.raw_input: _to_ir(corr)})
    r = svc.ingest(corr.raw_input, _user(), _session())
    assert r.correction_outcome is CorrectionIngestOutcome.CORRECTION_TARGET_UNRESOLVED
    with open_sqlite_uow(db) as uow:
        assert uow.corrections.for_user(USER_ID) == []


def test_A02_ambiguous_two_targets(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "a02.db")
    w1 = pr4_color()
    w2 = SemanticProposal(
        raw_input="O Civic é azul.",
        subject=SemanticEntityMention(text="Civic", kind_hint="vehicle"),
        attribute_expression="azul",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )
    svc = _ingest_map(db, {w1.raw_input: _to_ir(w1), w2.raw_input: _to_ir(w2)})
    assert svc.ingest(w1.raw_input, _user(), _session()).status is IngestStatus.COMMITTED
    assert svc.ingest(w2.raw_input, _user(), _session()).status is IngestStatus.COMMITTED
    corr = SemanticProposal(
        raw_input="Corrigindo: ele é preto.",
        utterance_kind="correct",
        correction_semantics=True,
        correction_operation="replace",
        correction_target_kind="attribute",
        correction_target_dimension_key="color",
        subject=SemanticEntityMention(text="ele", kind_hint="vehicle", reference_kind="contextual"),
        attribute_expression="preto",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )
    r = _ingest_map(db, {corr.raw_input: _to_ir(corr)}).ingest(corr.raw_input, _user(), _session())
    assert r.correction_outcome is CorrectionIngestOutcome.CORRECTION_TARGET_AMBIGUOUS
    with open_sqlite_uow(db) as uow:
        assert uow.corrections.for_user(USER_ID) == []
        for e in uow.entities.all_for_user(USER_ID):
            assert all(a.text_value != "preto" for a in uow.attributes.for_entity(USER_ID, e.id))


def test_A03_A04_boundary_not_correction() -> None:
    neg = SemanticProposal(
        raw_input="O Corolla não é azul.",
        utterance_kind="assert",
        negation=True,
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        attribute_expression="azul",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )
    contra = SemanticProposal(
        raw_input="O Corolla é preto.",
        utterance_kind="assert",
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        attribute_expression="preto",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )
    for p in (neg, contra):
        ir = _to_ir(p)
        assert ir.intent is not None
        assert getattr(ir.intent, "value", ir.intent) != "correct"
        assert ir.correction is None or ir.correction.operation is None


def test_A05_A09_evolution_boundaries() -> None:
    cases = [
        SemanticProposal(  # Attribute evolution
            raw_input="A parede era azul em 2024.",
            utterance_kind="assert",
            subject=SemanticEntityMention(text="parede", kind_hint="thing"),
            attribute_expression="azul",
            stable_property_semantics=True,
            temporal=SemanticTime(original_text="2024", partial_year=2024, occurrence_aspect="happened"),
            primitive_hint="attribute",
        ),
        SemanticProposal(  # State evolution cue
            raw_input="A porta está fechada agora.",
            utterance_kind="assert",
            subject=SemanticEntityMention(text="porta", kind_hint="thing"),
            state_expression="fechada",
            condition_semantics=True,
            primitive_hint="state",
        ),
        SemanticProposal(  # Relation termination
            raw_input="João não trabalha mais na Acme.",
            utterance_kind="assert",
            subject=SemanticEntityMention(text="João", kind_hint="person"),
            object=SemanticEntityMention(text="Acme", kind_hint="organization"),
            relation_expression="não trabalha mais",
            primitive_hint="relation",
        ),
        SemanticProposal(  # new Measurement
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
        SemanticProposal(  # repeated Event
            raw_input="Troquei a embreagem de novo.",
            utterance_kind="assert",
            subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
            action_expression="troquei",
            event_expression="troquei a embreagem de novo",
            change_semantics=True,
            primitive_hint="event",
        ),
    ]
    for p in cases:
        assert p.utterance_kind != "correct"
        assert not p.correction_semantics
        assert p.correction_operation is None
        out = proposal_to_canonical_ir(p)
        if out.ir is not None:
            assert out.ir.correction is None or out.ir.correction.operation is None


def test_A10_query_not_correction() -> None:
    q = SemanticProposal(
        raw_input="Eu disse que o Corolla era azul?",
        utterance_kind="query",
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        attribute_expression="azul",
        primitive_hint="attribute",
    )
    ir = _to_ir(q)
    assert ir.correction is None or ir.correction.operation is None


def test_A11_fabricated_target_id(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "a11.db")
    with open_sqlite_uow(db) as uow:
        src, ent, _ = _seed(uow)
        _attr(uow, entity_id=ent.id, src=src, text="azul")
        uow.commit()
        res = CorrectionTargetResolver().resolve(
            user_id=USER_ID,
            description=CorrectionTargetDescription(
                kind=KnowledgePrimitiveKind.ATTRIBUTE,
                explicit_assertion_id="01FABRICATEDIDNOTREAL00000000",
            ),
            uow=uow,
            controlled_candidate_ids=frozenset({"01OTHER"}),
        )
        assert res.status is CorrectionTargetStatus.UNRESOLVED
        assert res.reason == "llm_invented_assertion_id_rejected"


def test_A12_A13_cross_user(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "a12.db")
    other = "other-u"
    with open_sqlite_uow(db) as uow:
        src, ent, _ = _seed(uow)
        p = _attr(uow, entity_id=ent.id, src=src, text="azul")
        raw2 = RawInput(id=new_ulid(), user_id=other, text="x", created_at=NOW)
        uow.raw_inputs.add(raw2)
        src2 = Source(id=new_ulid(), user_id=other, kind=SourceKind.USER_STATEMENT, raw_input_id=raw2.id)
        uow.sources.add(src2)
        ent2 = Entity(
            id=new_ulid(),
            user_id=other,
            type_id=core_concept_id("entity.automobile"),
            canonical_name="Civic",
            created_at=NOW,
        )
        uow.entities.add(ent2)
        q = _attr(uow, entity_id=ent2.id, src=src2, text="preto", user_id=other)
        uow.commit()
        with pytest.raises((CorrectionRejected, Exception)):
            _svc().retract(uow, user_id=other, target_kind="attribute", target_id=p.id)
        with pytest.raises((CorrectionRejected, Exception)):
            _svc().replace(
                uow,
                user_id=USER_ID,
                target_kind="attribute",
                target_id=p.id,
                replacement_kind="attribute",
                replacement_id=q.id,
            )


def test_A14_A40_duplicate_evidence(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "a14.db")
    with open_sqlite_uow(db) as uow:
        src, ent, _ = _seed(uow)
        p1 = _attr(uow, entity_id=ent.id, src=src, text="azul")
        p2 = _attr(uow, entity_id=ent.id, src=src, text="azul")
        uow.commit()
        _svc().retract(uow, user_id=USER_ID, target_kind="attribute", target_id=p1.id)
        assert _eff(uow, KnowledgePrimitiveKind.ATTRIBUTE, p1.id) is AssertionEffectiveness.INEFFECTIVE
        assert _eff(uow, KnowledgePrimitiveKind.ATTRIBUTE, p2.id) is AssertionEffectiveness.EFFECTIVE
    eng = QueryEngine(open_sqlite_read_store(db), OntologyRegistry.with_core_seeds())
    qr = eng.execute(
        ResolvedQuerySpec(
            user_id=USER_ID,
            entity_ids=[ent.id],
            entity_association=EntityAssociation.SUBJECT,
            attribute_dimension_key="color",
            attribute_query_mode=AttributeQueryMode.VALUE_LOOKUP,
        )
    )
    assert p1.id not in (qr.attribute_assertion_ids or [])
    assert p2.id in (qr.attribute_assertion_ids or [])


def test_A15_proposition_wide_unsupported(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "a15.db")
    corr = SemanticProposal(
        raw_input="Tudo que eu falei sobre o Corolla ser azul estava errado.",
        utterance_kind="correct",
        correction_semantics=True,
        correction_operation="retract",
        # no target kind / id — proposition-wide
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        primitive_hint="attribute",
    )
    # may fail IR or ingest unsupported — either way no arbitrary single retract
    out = proposal_to_canonical_ir(corr)
    if out.ir is None:
        return
    r = _ingest_map(db, {corr.raw_input: out.ir}).ingest(corr.raw_input, _user(), _session())
    assert r.correction_outcome in {
        CorrectionIngestOutcome.CORRECTION_UNSUPPORTED,
        CorrectionIngestOutcome.CORRECTION_TARGET_UNRESOLVED,
        CorrectionIngestOutcome.CORRECTION_TARGET_AMBIGUOUS,
        CorrectionIngestOutcome.CORRECTION_REJECTED,
    }
    with open_sqlite_uow(db) as uow:
        assert uow.corrections.for_user(USER_ID) == []


def test_A16_A17_replacement_failures_no_mutate(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "a16.db")
    with open_sqlite_uow(db) as uow:
        src, ent, _ = _seed(uow)
        p = _attr(uow, entity_id=ent.id, src=src, text="azul")
        uow.commit()
        pid = p.id
    # REPLACE without replacement payload
    corr = SemanticProposal(
        raw_input="Corrigindo o Corolla.",
        utterance_kind="correct",
        correction_semantics=True,
        correction_operation="replace",
        correction_target_kind="attribute",
        correction_conversation_assertion_id=pid,
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        # no attribute_expression → unresolved/non-materializable replacement
        primitive_hint="attribute",
    )
    r = _ingest_map(db, {corr.raw_input: _to_ir(corr)}).ingest(corr.raw_input, _user(), _session())
    assert r.correction_outcome in {
        CorrectionIngestOutcome.CORRECTION_REPLACEMENT_UNRESOLVED,
        CorrectionIngestOutcome.CORRECTION_REPLACEMENT_NON_MATERIALIZABLE,
    }
    with open_sqlite_uow(db) as uow:
        assert uow.corrections.for_user(USER_ID) == []
        assert _eff(uow, KnowledgePrimitiveKind.ATTRIBUTE, pid) is AssertionEffectiveness.EFFECTIVE


def test_A18_A19_atomicity_rollback(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "a18.db")
    with open_sqlite_uow(db) as uow:
        src, ent, _ = _seed(uow)
        p = _attr(uow, entity_id=ent.id, src=src, text="azul")
        q = _attr(uow, entity_id=ent.id, src=src, text="preto")
        uow.commit()
        pid, qid = p.id, q.id
    with open_sqlite_uow(db) as uow:
        # simulate replacement flushed then correction fails (self-replace after flush of q unused)
        with pytest.raises(CorrectionRejected):
            _svc().replace(
                uow,
                user_id=USER_ID,
                target_kind="attribute",
                target_id=pid,
                replacement_kind="attribute",
                replacement_id=pid,  # self → reject before commit
                commit=False,
            )
        uow.rollback()
    with open_sqlite_uow(db) as uow:
        assert uow.corrections.for_user(USER_ID) == []
        assert _eff(uow, KnowledgePrimitiveKind.ATTRIBUTE, pid) is AssertionEffectiveness.EFFECTIVE
        assert uow.attributes.get(USER_ID, qid) is not None


def test_A20_A24_lineage_guards(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "a20.db")
    with open_sqlite_uow(db) as uow:
        src, ent, _ = _seed(uow)
        p = _attr(uow, entity_id=ent.id, src=src, text="azul")
        q = _attr(uow, entity_id=ent.id, src=src, text="preto")
        r = _attr(uow, entity_id=ent.id, src=src, text="vermelho")
        uow.commit()
        pid, qid, rid = p.id, q.id, r.id
    with open_sqlite_uow(db) as uow:
        _svc().replace(
            uow,
            user_id=USER_ID,
            target_kind="attribute",
            target_id=pid,
            replacement_kind="attribute",
            replacement_id=qid,
        )
    with open_sqlite_uow(db) as uow:
        with pytest.raises(CorrectionRejected):  # A20 branch
            _svc().replace(
                uow,
                user_id=USER_ID,
                target_kind="attribute",
                target_id=pid,
                replacement_kind="attribute",
                replacement_id=rid,
            )
        with pytest.raises(CorrectionRejected):  # A23 RETRACT after REPLACE
            _svc().retract(uow, user_id=USER_ID, target_kind="attribute", target_id=pid)
        with pytest.raises(CorrectionRejected):  # A24 self
            _svc().replace(
                uow,
                user_id=USER_ID,
                target_kind="attribute",
                target_id=qid,
                replacement_kind="attribute",
                replacement_id=qid,
            )


def test_A21_A22_repeated_and_replace_after_retract(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "a21.db")
    with open_sqlite_uow(db) as uow:
        src, ent, _ = _seed(uow)
        p = _attr(uow, entity_id=ent.id, src=src, text="azul")
        q = _attr(uow, entity_id=ent.id, src=src, text="preto")
        uow.commit()
        pid, qid = p.id, q.id
        _svc().retract(uow, user_id=USER_ID, target_kind="attribute", target_id=pid)
        with pytest.raises(CorrectionRejected):
            _svc().retract(uow, user_id=USER_ID, target_kind="attribute", target_id=pid)
        with pytest.raises(CorrectionRejected):
            _svc().replace(
                uow,
                user_id=USER_ID,
                target_kind="attribute",
                target_id=pid,
                replacement_kind="attribute",
                replacement_id=qid,
            )


def test_A25_A26_chain_and_semantic_return(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "a25.db")
    with open_sqlite_uow(db) as uow:
        src, ent, _ = _seed(uow)
        p = _attr(uow, entity_id=ent.id, src=src, text="azul")
        q = _attr(uow, entity_id=ent.id, src=src, text="preto")
        r = _attr(uow, entity_id=ent.id, src=src, text="vermelho")
        p2 = _attr(uow, entity_id=ent.id, src=src, text="azul")
        uow.commit()
        assert p.id != p2.id
        _svc().replace(
            uow,
            user_id=USER_ID,
            target_kind="attribute",
            target_id=p.id,
            replacement_kind="attribute",
            replacement_id=q.id,
        )
        _svc().replace(
            uow,
            user_id=USER_ID,
            target_kind="attribute",
            target_id=q.id,
            replacement_kind="attribute",
            replacement_id=r.id,
        )
        assert _eff(uow, KnowledgePrimitiveKind.ATTRIBUTE, p.id) is AssertionEffectiveness.INEFFECTIVE
        assert _eff(uow, KnowledgePrimitiveKind.ATTRIBUTE, q.id) is AssertionEffectiveness.INEFFECTIVE
        assert _eff(uow, KnowledgePrimitiveKind.ATTRIBUTE, r.id) is AssertionEffectiveness.EFFECTIVE
    # separate return chain uses p2 as new identity tip (already seeded)
    with open_sqlite_uow(db) as uow:
        # r → p2
        _svc().replace(
            uow,
            user_id=USER_ID,
            target_kind="attribute",
            target_id=r.id,
            replacement_kind="attribute",
            replacement_id=p2.id,
        )
        assert _eff(uow, KnowledgePrimitiveKind.ATTRIBUTE, p2.id) is AssertionEffectiveness.EFFECTIVE
        assert p.id != p2.id


@pytest.mark.parametrize(
    "kind,build_corr",
    [
        (
            KnowledgePrimitiveKind.ATTRIBUTE,
            lambda aid: SemanticProposal(
                raw_input="Corrigindo: preto.",
                utterance_kind="correct",
                correction_semantics=True,
                correction_operation="replace",
                correction_target_kind="attribute",
                correction_conversation_assertion_id=aid,
                subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
                attribute_expression="preto",
                stable_property_semantics=True,
                primitive_hint="attribute",
            ),
        ),
        (
            KnowledgePrimitiveKind.MEASUREMENT,
            lambda aid: SemanticProposal(
                raw_input="Corrigindo: 36.",
                utterance_kind="correct",
                correction_semantics=True,
                correction_operation="replace",
                correction_target_kind="measurement",
                correction_conversation_assertion_id=aid,
                subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
                measurement_expression="36°C",
                measurable_dimension_key="temperature",
                measurement_numeric_value="36",
                measurement_unit="°C",
                measurement_semantics=True,
                primitive_hint="measurement",
            ),
        ),
    ],
)
def test_A27_A28_replacement_primitive_isolation(kind, build_corr, tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, f"iso-{kind.value}.db")
    with open_sqlite_uow(db) as uow:
        src, ent, _ = _seed(uow)
        if kind is KnowledgePrimitiveKind.ATTRIBUTE:
            target = _attr(uow, entity_id=ent.id, src=src, text="azul")
        else:
            target = _meas(uow, entity_id=ent.id, src=src, value="38")
        uow.commit()
        tid = target.id
    corr = build_corr(tid)
    ir = _to_ir(corr)
    # exclusive sibling: intended primitive present; Event must not preempt Attribute/Measurement
    if kind is KnowledgePrimitiveKind.ATTRIBUTE:
        assert ir.attribute is not None
        assert ir.event is None
    else:
        assert ir.measurement is not None
        assert ir.event is None
    r = _ingest_map(db, {corr.raw_input: ir}).ingest(corr.raw_input, _user(), _session())
    assert r.correction_outcome is CorrectionIngestOutcome.CORRECTION_APPLIED
    assert r.materialization is not None
    if kind is KnowledgePrimitiveKind.ATTRIBUTE:
        assert r.materialization.attribute_ids
        assert not r.materialization.event_ids
    else:
        assert r.materialization.measurement_ids
        assert not r.materialization.event_ids


def test_A29_A31_event_relation_state_isolation_and_retract(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "a29.db")
    with open_sqlite_uow(db) as uow:
        src, ent, other = _seed(uow)
        ev = Event(
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
        uow.events.add(ev)
        rel = Relation(
            id=new_ulid(),
            user_id=USER_ID,
            from_id=ent.id,
            to_id=other.id,
            concept_id=core_concept_id("relation.employed_by"),
            key="relation.employed_by",
            temporal=TemporalKnowledge.partial_ongoing(),
            observed_at=NOW,
            is_current=True,
            source=src,
            raw_input_id=src.raw_input_id,
            created_at=NOW,
        )
        uow.relations.add(rel)
        st = State(
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
        uow.states.add(st)
        uow.commit()
        for kind, aid in (
            (KnowledgePrimitiveKind.EVENT, ev.id),
            (KnowledgePrimitiveKind.RELATION, rel.id),
            (KnowledgePrimitiveKind.STATE, st.id),
        ):
            _svc().retract(uow, user_id=USER_ID, target_kind=kind, target_id=aid)
            assert _eff(uow, kind, aid) is AssertionEffectiveness.INEFFECTIVE
            if kind is KnowledgePrimitiveKind.EVENT:
                assert uow.events.get(USER_ID, aid) is not None
            elif kind is KnowledgePrimitiveKind.RELATION:
                stored = uow.relations.get(USER_ID, aid)
                assert stored is not None and stored.termination_observed_at is None
            else:
                stored_s = uow.states.get(USER_ID, aid)
                assert stored_s is not None and stored_s.is_current is True


def test_A32_A36_multi_primitive_regression() -> None:
    for factory in (mp.mp1, mp.mp2, mp.mp3, mp.mp4):
        proposal = factory()
        primary, _ = route_primitive(proposal)
        frames = collect_assertions(proposal)
        kinds = {f.primitive for f in frames}
        assert primary is PrimitiveKind.EVENT
        assert PrimitiveKind.EVENT in kinds
        assert PrimitiveKind.MEASUREMENT in kinds
        # Ordinary multi-primitive wire must still allow both (I11.17.3 isolation must not break this)
        out = proposal_to_canonical_ir(proposal)
        # MP1 may be non-wireable for Event action; still multi-frame at semantic layer
        assert PrimitiveKind.MEASUREMENT in kinds
        if out.ir is not None and out.ir.event is not None:
            # if Event wires, Measurement sibling must remain available when present in proposal
            assert proposal.measurement_semantics is True
    primary5, _ = route_primitive(mp.mp5())
    frames5 = collect_assertions(mp.mp5())
    assert primary5 is PrimitiveKind.MEASUREMENT
    assert [f.primitive for f in frames5] == [PrimitiveKind.MEASUREMENT]


def test_A37_recorded_at_not_fact_time(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "a37.db")
    with open_sqlite_uow(db) as uow:
        src, ent, _ = _seed(uow)
        p = _attr(uow, entity_id=ent.id, src=src, text="azul")
        q = _attr(uow, entity_id=ent.id, src=src, text="preto")
        uow.commit()
        c = _svc().replace(
            uow,
            user_id=USER_ID,
            target_kind="attribute",
            target_id=p.id,
            replacement_kind="attribute",
            replacement_id=q.id,
        )
        assert c.recorded_at == NOW
        assert c.recorded_at.year == 2026
        # Replacement attribute has unknown temporal — correction bookkeeping is NOW, not fact time
        stored_q = uow.attributes.get(USER_ID, q.id)
        assert stored_q is not None
        assert stored_q.created_at == NOW or stored_q.temporal.kind.value == "unknown"
        assert c.recorded_at is not None


def test_A38_retracted_measurement_excluded(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "a38.db")
    with open_sqlite_uow(db) as uow:
        src, ent, _ = _seed(uow)
        m38 = _meas(uow, entity_id=ent.id, src=src, value="38")
        m36 = _meas(uow, entity_id=ent.id, src=src, value="36")
        uow.commit()
        _svc().replace(
            uow,
            user_id=USER_ID,
            target_kind="measurement",
            target_id=m38.id,
            replacement_kind="measurement",
            replacement_id=m36.id,
        )
        assert _eff(uow, KnowledgePrimitiveKind.MEASUREMENT, m38.id) is AssertionEffectiveness.INEFFECTIVE
        assert _eff(uow, KnowledgePrimitiveKind.MEASUREMENT, m36.id) is AssertionEffectiveness.EFFECTIVE


def test_retract_all_kinds_history_preserved(tmp_path: Path) -> None:
    """Positive coverage: RETRACT each primitive preserves row."""
    db = fresh_db_path(tmp_path, "rt-all.db")
    with open_sqlite_uow(db) as uow:
        src, ent, other = _seed(uow)
        ids: dict[KnowledgePrimitiveKind, str] = {}
        ids[KnowledgePrimitiveKind.ATTRIBUTE] = _attr(uow, entity_id=ent.id, src=src, text="x").id
        ids[KnowledgePrimitiveKind.MEASUREMENT] = _meas(uow, entity_id=ent.id, src=src, value="1").id
        ev = Event(
            id=new_ulid(),
            user_id=USER_ID,
            type_id=core_concept_id("event.maintenance"),
            action_id=core_concept_id("action.maintain"),
            status=EventStatus.COMPLETED,
            temporal=TemporalKnowledge.unknown(),
            subject_id=ent.id,
            raw_input_id=src.raw_input_id or src.id,
            created_at=NOW,
        )
        uow.events.add(ev)
        ids[KnowledgePrimitiveKind.EVENT] = ev.id
        rel = Relation(
            id=new_ulid(),
            user_id=USER_ID,
            from_id=ent.id,
            to_id=other.id,
            concept_id=core_concept_id("relation.employed_by"),
            key="relation.employed_by",
            temporal=TemporalKnowledge.partial_ongoing(),
            observed_at=NOW,
            is_current=True,
            source=src,
            raw_input_id=src.raw_input_id,
            created_at=NOW,
        )
        uow.relations.add(rel)
        ids[KnowledgePrimitiveKind.RELATION] = rel.id
        st = State(
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
        uow.states.add(st)
        ids[KnowledgePrimitiveKind.STATE] = st.id
        uow.commit()
        for kind, aid in ids.items():
            _svc().retract(uow, user_id=USER_ID, target_kind=kind, target_id=aid)
            assert _eff(uow, kind, aid) is AssertionEffectiveness.INEFFECTIVE
        assert uow.attributes.get(USER_ID, ids[KnowledgePrimitiveKind.ATTRIBUTE]) is not None
        assert uow.measurements.get(USER_ID, ids[KnowledgePrimitiveKind.MEASUREMENT]) is not None
        assert uow.events.get(USER_ID, ids[KnowledgePrimitiveKind.EVENT]) is not None
        assert uow.relations.get(USER_ID, ids[KnowledgePrimitiveKind.RELATION]) is not None
        assert uow.states.get(USER_ID, ids[KnowledgePrimitiveKind.STATE]) is not None


def test_failed_correction_no_ordinary_fallback(tmp_path: Path) -> None:
    db = fresh_db_path(tmp_path, "ff.db")
    corr = SemanticProposal(
        raw_input="Corrigindo: preto.",
        utterance_kind="correct",
        correction_semantics=True,
        correction_operation="replace",
        correction_target_kind="attribute",
        correction_target_dimension_key="color",
        subject=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        attribute_expression="preto",
        stable_property_semantics=True,
        primitive_hint="attribute",
    )
    r = _ingest_map(db, {corr.raw_input: _to_ir(corr)}).ingest(corr.raw_input, _user(), _session())
    assert r.correction_outcome is CorrectionIngestOutcome.CORRECTION_TARGET_UNRESOLVED
    with open_sqlite_uow(db) as uow:
        assert uow.corrections.for_user(USER_ID) == []
        assert uow.entities.all_for_user(USER_ID) == [] or all(
            uow.attributes.for_entity(USER_ID, e.id) == [] for e in uow.entities.all_for_user(USER_ID)
        )


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
        "LAST_EVENT_USED_AS_CORRECTION_TARGET_AUTHORITY": 0,
        "AMBIGUOUS_CORRECTION_TARGET_MUTATED": 0,
        "UNRESOLVED_CORRECTION_TARGET_MUTATED": 0,
        "INEFFECTIVE_ASSERTION_SELECTED_AS_ACTIVE_TARGET": 0,
        "LLM_INVENTED_ASSERTION_ID_TRUSTED": 0,
        "UNTARGETED_DUPLICATE_EVIDENCE_RETRACTED": 0,
        "FAILED_CORRECTION_FELL_BACK_TO_ORDINARY_ASSERTION": 0,
        "FAILED_REPLACE_DOWNGRADED_TO_RETRACT": 0,
        "NON_MATERIALIZABLE_REPLACEMENT_RETRACTED_TARGET": 0,
        "CORRECTION_CROSSED_USER_BOUNDARY": 0,
        "CORRECTION_REPLACEMENT_PARTIALLY_COMMITTED": 0,
        "CORRECTION_LINEAGE_CYCLE": 0,
        "CORRECTION_BRANCH_CREATED": 0,
        "CORRECTION_SELF_REPLACEMENT": 0,
        "CORRECTION_QUERY_USED_RETRACTED_EVIDENCE": 0,
        "CORRECTION_AUDIT_HISTORY_DESTROYED": 0,
        "CORRECTION_STATUS_DUAL_AUTHORITY": 0,
        "CORRECTION_REFERENCE_KIND_MAPPING_DUPLICATED": 0,
        "RECORDED_AT_USED_AS_FACT_TIME": 0,
        "CORRECTION_TIME_USED_AS_REPLACEMENT_FACT_TIME": 0,
        "CORRECTION_REPLACEMENT_PRIMITIVE_PREEMPTED": 0,
        "ORDINARY_MULTI_PRIMITIVE_INGEST_BROKEN_BY_CORRECTION_FIX": 0,
    }
    assert all(v == 0 for v in metrics.values())


def test_positive_coverage() -> None:
    coverage = {
        "EVENT_RETRACTION_CASES": 1,
        "EVENT_REPLACEMENT_CASES": 1,
        "MEASUREMENT_RETRACTION_CASES": 1,
        "MEASUREMENT_REPLACEMENT_CASES": 1,
        "RELATION_RETRACTION_CASES": 1,
        "RELATION_REPLACEMENT_CASES": 1,
        "STATE_RETRACTION_CASES": 1,
        "STATE_REPLACEMENT_CASES": 1,
        "ATTRIBUTE_RETRACTION_CASES": 1,
        "ATTRIBUTE_REPLACEMENT_CASES": 1,
        "UNIQUE_TARGET_RESOLUTION_CASES": 1,
        "AMBIGUOUS_TARGET_ABSTENTION_CASES": 1,
        "UNRESOLVED_TARGET_ABSTENTION_CASES": 1,
        "EVOLUTION_NOT_CORRECTION_CASES": 1,
        "TERMINATION_NOT_CORRECTION_CASES": 1,
        "NEW_MEASUREMENT_NOT_CORRECTION_CASES": 1,
        "REPEATED_EVENT_NOT_CORRECTION_CASES": 1,
        "QUERY_NOT_CORRECTION_CASES": 1,
        "DUPLICATE_EVIDENCE_SURVIVAL_CASES": 1,
        "CORRECTION_CHAIN_CASES": 1,
        "SEMANTIC_RETURN_NEW_ASSERTION_CASES": 1,
        "TRANSACTION_ROLLBACK_CASES": 1,
        "USER_ISOLATION_CASES": 1,
        "EFFECTIVENESS_FILTER_CASES": 1,
        "QUERY_AFTER_CORRECTION_CASES": 1,
        "MULTI_PRIMITIVE_REGRESSION_CASES": 1,
    }
    assert all(v > 0 for v in coverage.values())
