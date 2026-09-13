"""ADR 0091 — conversation discourse context and cross-turn reference resolution."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from pke.application.ask import AskService
from pke.application.ask_results import AskResult, AskStatus
from pke.application.clock import FixedClock
from pke.application.discourse import apply_ask_to_discourse, binding_allowed
from pke.application.ingest import IngestService
from pke.application.results import IngestStatus
from pke.application.session import SessionContext
from pke.domain.value_objects import UserContext
from pke.interpretation.discourse import (
    MAX_IDLE_TURNS,
    DiscourseFocus,
    DiscourseState,
    allowed_entity_ids,
)
from pke.interpretation.interpreter import InterpretationError
from pke.interpretation.models import QueryIR, QuerySpec
from pke.interpretation.semantic.models import (
    SemanticClaim,
    SemanticClaimKind,
    SemanticEntityMention,
    SemanticProposal,
    SemanticTime,
)
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
from pke.interpretation.semantic.query_resolution import proposal_to_query_ir
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry
from pke.persist import open_sqlite_read_store, open_sqlite_uow
from pke.query.results import CurrentRelationItem, QueryPlan, QueryResult
from pke.query.spec import AggregateKind, FactVersionPolicy, HierarchyMode, SortKey
from pke.resolution.context import PersonalContext
from tests.generalization_ingest.fixtures import fresh_db_path
from tests.integration.test_ingest import NOW

OPAQUE = "OPAQUE-DISCOURSE-001"
SRC = Path(__file__).resolve().parents[2] / "src" / "pke"


@pytest.fixture(autouse=True)
def _catalog() -> None:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())


class DiscourseAwareInterpreter:
    """Test interpreter that may bind IDs from structured discourse — not from raw text."""

    def __init__(self) -> None:
        self._static: dict[str, object] = {}
        self._builders: dict[str, Callable] = {}

    def register(self, raw: str, ir: object) -> None:
        self._static[raw] = ir

    def on(self, raw: str, builder: Callable) -> None:
        self._builders[raw] = builder

    def interpret(self, raw: str, ctx):
        if raw in self._builders:
            ir = self._builders[raw](ctx)
            if hasattr(ir, "model_copy") and hasattr(ir, "raw_input"):
                return ir.model_copy(update={"raw_input": raw})
            return ir
        if raw in self._static:
            return self._static[raw]
        raise InterpretationError(f"nenhuma IR scriptada para: {raw!r}")


def _user(uid: str = "u-discourse") -> UserContext:
    return UserContext(user_id=uid, timezone="America/Fortaleza", now=NOW)


def _session(uid: str = "u-discourse") -> SessionContext:
    return SessionContext(personal=PersonalContext(user_id=uid))


def _actor() -> SemanticEntityMention:
    return SemanticEntityMention(
        text="self", kind_hint="person", reference_kind="contextual", confidence=1.0
    )


def _named(text: str, *, class_hint: str, kind: str = "thing") -> SemanticEntityMention:
    return SemanticEntityMention(
        text=text,
        kind_hint=kind,  # type: ignore[arg-type]
        class_hint=class_hint,
        reference_kind="named",
        confidence=1.0,
    )


def _possessed(text: str, *, class_hint: str, kind: str = "thing") -> SemanticEntityMention:
    return SemanticEntityMention(
        text=text,
        kind_hint=kind,  # type: ignore[arg-type]
        class_hint=class_hint,
        reference_kind="possessive",
        confidence=1.0,
    )


def _write_named(raw: str, name: str, class_hint: str) -> SemanticProposal:
    return SemanticProposal(
        raw_input=raw,
        utterance_kind="assert",
        primitive_hint="relation",
        subject=_actor(),
        object=_named(name, class_hint=class_hint),
        relation_expression="owns",
        link_semantics=True,
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        confidence=1.0,
    )


def _write_age(name: str, value: str, class_hint: str = "cat") -> SemanticProposal:
    subject = _named(name, class_hint=class_hint)
    return SemanticProposal(
        raw_input=f"{name} age {value}",
        utterance_kind="assert",
        primitive_hint="attribute",
        subject=subject,
        stable_property_semantics=True,
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        claims=[
            SemanticClaim(
                kind=SemanticClaimKind.ATTRIBUTE,
                subject=subject,
                predicate="age",
                value_text=value,
            )
        ],
        confidence=1.0,
    )


def _write_car(*, model: str = "City", color: str = "azul") -> SemanticProposal:
    owned = _possessed("carro", class_hint="automobile", kind="vehicle")
    return SemanticProposal(
        raw_input="meu carro é um City azul",
        utterance_kind="assert",
        primitive_hint="attribute",
        subject=_actor(),
        object=owned,
        relation_expression="owns",
        link_semantics=True,
        classification_semantics=True,
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        claims=[
            SemanticClaim(kind=SemanticClaimKind.CLASSIFICATION, subject=owned, class_hint="automobile"),
            SemanticClaim(kind=SemanticClaimKind.RELATION, predicate="owns", subject=_actor(), object=owned),
            SemanticClaim(
                kind=SemanticClaimKind.ATTRIBUTE,
                subject=owned,
                dimension="model",
                value_text=model,
            ),
            SemanticClaim(
                kind=SemanticClaimKind.ATTRIBUTE,
                subject=owned,
                dimension="color",
                value_text=color,
            ),
        ],
        confidence=1.0,
    )


def _class_owns(raw: str, class_hint: str, *, decision: str = "new_topic") -> SemanticProposal:
    return SemanticProposal(
        raw_input=raw,
        utterance_kind="query",
        primitive_hint="relation",
        subject=_actor(),
        object=SemanticEntityMention(
            text=class_hint,
            kind_hint="thing",
            reference_kind="class",
            class_hint=class_hint,
            confidence=1.0,
        ),
        relation_expression="owns",
        link_semantics=True,
        discourse_decision=decision,  # type: ignore[arg-type]
        temporal=SemanticTime(),
        confidence=1.0,
    )


def _ir_from_proposal(proposal: SemanticProposal) -> QueryIR:
    outcome = proposal_to_query_ir(proposal)
    assert outcome.query_ir is not None, (outcome.status, outcome.notes)
    return outcome.query_ir


def _continue_attr(expression: str):
    def build(ctx) -> QueryIR:
        focus = ctx.discourse.active_focus if ctx.discourse is not None else None
        ids = list(focus.entity_ids) if focus is not None else []
        if not ids:
            return QueryIR(
                raw_input="",
                discourse_decision="ambiguous",
                query=QuerySpec(intent="attribute"),
            )
        mentions = [
            SemanticEntityMention(
                text=f"discourse:{eid}",
                kind_hint="thing",
                reference_kind="contextual",
                known_entity_id=eid,
                confidence=1.0,
            )
            for eid in ids
        ]
        proposal = SemanticProposal(
            raw_input="",
            utterance_kind="query",
            primitive_hint="attribute",
            subject=mentions[0],
            entities_mentioned=mentions[1:],
            attribute_expression=expression,
            stable_property_semantics=True,
            discourse_decision="continue",
            temporal=SemanticTime(),
            confidence=1.0,
        )
        return _ir_from_proposal(proposal)

    return build


def _possessive_attr(noun: str, class_hint: str, expression: str, *, kind: str = "thing"):
    def build(ctx) -> QueryIR:
        del ctx
        proposal = SemanticProposal(
            raw_input="",
            utterance_kind="query",
            primitive_hint="attribute",
            subject=_possessed(noun, class_hint=class_hint, kind=kind),
            attribute_expression=expression,
            stable_property_semantics=True,
            discourse_decision="new_topic",
            temporal=SemanticTime(),
            confidence=1.0,
        )
        return _ir_from_proposal(proposal)

    return build


def _class_builder(class_hint: str, *, decision: str = "new_topic"):
    def build(ctx) -> QueryIR:
        del ctx
        return _ir_from_proposal(_class_owns("class-query", class_hint, decision=decision))

    return build


def _harness(tmp_path: Path, uid: str = "u-discourse"):
    db = fresh_db_path(tmp_path, f"{uid}.db")
    user = _user(uid)
    ontology = OntologyRegistry.with_core_seeds()
    ConceptCatalog.load(ontology)
    interpreter = DiscourseAwareInterpreter()
    ingest = IngestService(
        interpreter,  # type: ignore[arg-type]
        ontology,
        lambda: open_sqlite_uow(db),
        FixedClock(NOW),
    )
    ask = AskService(
        interpreter,  # type: ignore[arg-type]
        ontology,
        open_sqlite_read_store(db),
        FixedClock(NOW),
    )
    return user, ontology, interpreter, ingest, ask


def _register_write(interpreter: DiscourseAwareInterpreter, proposal: SemanticProposal) -> None:
    outcome = proposal_to_canonical_ir(proposal)
    assert outcome.ir is not None, (outcome.failure_stage, outcome.execution_reasons)
    interpreter.register(proposal.raw_input, outcome.ir)


def _attr_texts(result: AskResult) -> list[str]:
    assert result.query_result is not None
    return [item.text_value for item in result.query_result.attribute_values if item.text_value]


def _focus_ids(session: SessionContext) -> list[str]:
    if session.discourse.active_focus is None:
        return []
    return list(session.discourse.active_focus.entity_ids)


def test_legacy_session_json_without_discourse_still_loads() -> None:
    session = SessionContext.model_validate({"personal": {"user_id": "u-legacy"}})
    assert session.discourse.active_focus is None
    assert session.discourse.recent_referents == []
    assert session.discourse.pending_intent is None
    assert session.discourse.last_update_reason is None


def test_binding_allowed_legacy_when_discourse_empty() -> None:
    assert binding_allowed(DiscourseState(), "any-id") is True
    state = DiscourseState(active_focus=DiscourseFocus(entity_ids=["E1"]))
    assert binding_allowed(state, "E1") is True
    assert binding_allowed(state, "invented") is False


def test_d01_follow_up_attribute_from_query_focus(tmp_path: Path) -> None:
    user, _, interpreter, ingest, ask = _harness(tmp_path, "d01")
    seed = _session(user.user_id)
    _register_write(interpreter, _write_named("seed luna", "Luna", "cat"))
    written = ingest.ingest("seed luna", user, seed)
    assert written.status is IngestStatus.COMMITTED, written.issues

    session = _session(user.user_id)
    interpreter.on("eu tenho uma gata?", _class_builder("cat"))
    interpreter.on("qual o nome?", _continue_attr("name"))
    first = ask.ask("eu tenho uma gata?", user, session)
    assert first.status is AskStatus.ANSWERED
    assert first.query_result is not None
    assert first.query_result.relation_answer == "yes"
    assert _focus_ids(session)
    assert user.user_id not in _focus_ids(session)

    second = ask.ask("qual o nome?", user, session)
    assert second.status is AskStatus.ANSWERED, (second.status, second.issues)
    assert _attr_texts(second) == ["Luna"]
    assert _focus_ids(session) == second.resolved_entity_ids or set(_focus_ids(session)) <= set(
        allowed_entity_ids(session.discourse)
    )


def test_d02_second_follow_up_age(tmp_path: Path) -> None:
    user, _, interpreter, ingest, ask = _harness(tmp_path, "d02")
    seed = _session(user.user_id)
    _register_write(interpreter, _write_named("seed luna", "Luna", "cat"))
    _register_write(interpreter, _write_age("Luna", "3"))
    assert ingest.ingest("seed luna", user, seed).status is IngestStatus.COMMITTED
    assert ingest.ingest("Luna age 3", user, seed).status is IngestStatus.COMMITTED

    session = _session(user.user_id)
    interpreter.on("eu tenho uma gata?", _class_builder("cat"))
    interpreter.on("qual o nome?", _continue_attr("name"))
    interpreter.on("e a idade?", _continue_attr("age"))
    assert ask.ask("eu tenho uma gata?", user, session).status is AskStatus.ANSWERED
    named = ask.ask("qual o nome?", user, session)
    assert _attr_texts(named) == ["Luna"]
    aged = ask.ask("e a idade?", user, session)
    assert aged.status is AskStatus.ANSWERED, (aged.status, aged.issues)
    assert _attr_texts(aged) == ["3"]


def test_d03_topic_switch_to_car_model(tmp_path: Path) -> None:
    user, _, interpreter, ingest, ask = _harness(tmp_path, "d03")
    seed = _session(user.user_id)
    _register_write(interpreter, _write_named("seed luna", "Luna", "cat"))
    _register_write(interpreter, _write_car())
    assert ingest.ingest("seed luna", user, seed).status is IngestStatus.COMMITTED
    assert ingest.ingest("meu carro é um City azul", user, seed).status is IngestStatus.COMMITTED

    session = _session(user.user_id)
    interpreter.on("eu tenho uma gata?", _class_builder("cat"))
    interpreter.on("eu tenho um carro?", _class_builder("automobile"))
    interpreter.on("qual o modelo?", _continue_attr("model"))
    cat = ask.ask("eu tenho uma gata?", user, session)
    assert cat.query_result is not None and cat.query_result.relation_answer == "yes"
    cat_ids = _focus_ids(session)
    car = ask.ask("eu tenho um carro?", user, session)
    assert car.query_result is not None and car.query_result.relation_answer == "yes"
    car_ids = _focus_ids(session)
    assert car_ids
    assert set(car_ids).isdisjoint(set(cat_ids))
    model = ask.ask("qual o modelo?", user, session)
    assert model.status is AskStatus.ANSWERED, (model.status, model.issues)
    assert _attr_texts(model) == ["City"]


def test_d04_continue_new_topic_color(tmp_path: Path) -> None:
    user, _, interpreter, ingest, ask = _harness(tmp_path, "d04")
    seed = _session(user.user_id)
    _register_write(interpreter, _write_car())
    assert ingest.ingest("meu carro é um City azul", user, seed).status is IngestStatus.COMMITTED

    session = _session(user.user_id)
    interpreter.on("eu tenho um carro?", _class_builder("automobile"))
    interpreter.on("qual o modelo?", _continue_attr("model"))
    interpreter.on("e a cor?", _continue_attr("color"))
    assert ask.ask("eu tenho um carro?", user, session).status is AskStatus.ANSWERED
    assert _attr_texts(ask.ask("qual o modelo?", user, session)) == ["City"]
    color = ask.ask("e a cor?", user, session)
    assert color.status is AskStatus.ANSWERED, (color.status, color.issues)
    assert _attr_texts(color) == ["azul"]


def test_d05_explicit_topic_return_to_cat(tmp_path: Path) -> None:
    user, _, interpreter, ingest, ask = _harness(tmp_path, "d05")
    seed = _session(user.user_id)
    _register_write(interpreter, _write_named("seed luna", "Luna", "cat"))
    _register_write(interpreter, _write_car())
    assert ingest.ingest("seed luna", user, seed).status is IngestStatus.COMMITTED
    assert ingest.ingest("meu carro é um City azul", user, seed).status is IngestStatus.COMMITTED

    session = _session(user.user_id)
    interpreter.on("eu tenho uma gata?", _class_builder("cat"))
    interpreter.on("eu tenho um carro?", _class_builder("automobile"))
    interpreter.on("qual o nome da minha gata?", _possessive_attr("gata", "cat", "name"))
    ask.ask("eu tenho uma gata?", user, session)
    ask.ask("eu tenho um carro?", user, session)
    returned = ask.ask("qual o nome da minha gata?", user, session)
    assert returned.status is AskStatus.ANSWERED, (returned.status, returned.issues)
    assert _attr_texts(returned) == ["Luna"]


def test_d06_ambiguous_humans_request_clarification(tmp_path: Path) -> None:
    user, _, interpreter, _, ask = _harness(tmp_path, "d06")
    session = _session(user.user_id)

    def ambiguous(ctx) -> QueryIR:
        del ctx
        return QueryIR(
            raw_input="",
            discourse_decision="ambiguous",
            query=QuerySpec(intent="attribute", attribute_dimension_key="age"),
        )

    interpreter.on("qual a idade?", ambiguous)
    result = ask.ask("qual a idade?", user, session)
    assert result.status is AskStatus.NEEDS_CLARIFICATION
    assert result.clarification is not None
    assert result.clarification.clarification_key == "clarify.entity.which_one"
    assert result.query_result is None


def test_d07_set_reference_is_not_ambiguity(tmp_path: Path) -> None:
    user, _, interpreter, ingest, ask = _harness(tmp_path, "d07")
    seed = _session(user.user_id)
    _register_write(interpreter, _write_named("seed luna", "Luna", "cat"))
    _register_write(interpreter, _write_named("seed thor", "Thor", "cat"))
    assert ingest.ingest("seed luna", user, seed).status is IngestStatus.COMMITTED
    assert ingest.ingest("seed thor", user, seed).status is IngestStatus.COMMITTED

    session = _session(user.user_id)
    interpreter.on("eu tenho gatos?", _class_builder("cat"))
    interpreter.on("quais os nomes?", _continue_attr("name"))
    first = ask.ask("eu tenho gatos?", user, session)
    assert first.status is AskStatus.ANSWERED
    assert first.query_result is not None
    assert first.query_result.relation_answer == "yes"
    assert len(_focus_ids(session)) == 2
    names = ask.ask("quais os nomes?", user, session)
    assert names.status is AskStatus.ANSWERED, (names.status, names.issues)
    assert set(_attr_texts(names)) == {"Luna", "Thor"}


def test_d08_conversation_isolation(tmp_path: Path) -> None:
    user, _, interpreter, ingest, ask = _harness(tmp_path, "d08")
    seed = _session(user.user_id)
    _register_write(interpreter, _write_named("seed luna", "Luna", "cat"))
    assert ingest.ingest("seed luna", user, seed).status is IngestStatus.COMMITTED

    conversation_a = _session(user.user_id)
    interpreter.on("eu tenho uma gata?", _class_builder("cat"))
    interpreter.on("qual o nome?", _continue_attr("name"))
    ask.ask("eu tenho uma gata?", user, conversation_a)
    named = ask.ask("qual o nome?", user, conversation_a)
    assert _attr_texts(named) == ["Luna"]

    conversation_b = _session(user.user_id)
    isolated = ask.ask("qual o nome?", user, conversation_b)
    assert isolated.status is AskStatus.NEEDS_CLARIFICATION
    assert isolated.query_result is None
    assert conversation_b.discourse.active_focus is None


def test_d09_opaque_raw_input_after_discourse_binding(tmp_path: Path) -> None:
    user, _, interpreter, ingest, ask = _harness(tmp_path, "d09")
    seed = _session(user.user_id)
    _register_write(interpreter, _write_named("seed luna", "Luna", "cat"))
    assert ingest.ingest("seed luna", user, seed).status is IngestStatus.COMMITTED

    session = _session(user.user_id)
    interpreter.on("eu tenho uma gata?", _class_builder("cat"))
    interpreter.on(OPAQUE, _continue_attr("name"))
    ask.ask("eu tenho uma gata?", user, session)
    opaque = ask.ask(OPAQUE, user, session)
    assert opaque.status is AskStatus.ANSWERED, (opaque.status, opaque.issues)
    assert opaque.raw_text == OPAQUE
    assert _attr_texts(opaque) == ["Luna"]


@pytest.mark.parametrize(
    ("have_cat", "follow"),
    [
        ("eu tenho uma gata?", "qual o nome?"),
        ("Do I have a cat?", "What's the name?"),
        ("¿Tengo una gata?", "¿Cuál es el nombre?"),
    ],
)
def test_multilingual_same_discourse_binding(tmp_path: Path, have_cat: str, follow: str) -> None:
    uid = "u-" + have_cat[:8]
    user, _, interpreter, ingest, ask = _harness(tmp_path, uid)
    seed = _session(user.user_id)
    _register_write(interpreter, _write_named("seed luna", "Luna", "cat"))
    assert ingest.ingest("seed luna", user, seed).status is IngestStatus.COMMITTED

    session = _session(user.user_id)
    interpreter.on(have_cat, _class_builder("cat"))
    interpreter.on(follow, _continue_attr("name"))
    assert ask.ask(have_cat, user, session).status is AskStatus.ANSWERED
    named = ask.ask(follow, user, session)
    assert named.status is AskStatus.ANSWERED, (named.status, named.issues)
    assert _attr_texts(named) == ["Luna"]
    assert named.query_result is not None
    assert named.query_result.attribute_dimension_key == "name"


def test_explicit_current_turn_outranks_inherited_focus(tmp_path: Path) -> None:
    user, _, interpreter, ingest, ask = _harness(tmp_path, "d-explicit")
    seed = _session(user.user_id)
    _register_write(interpreter, _write_named("seed luna", "Luna", "cat"))
    _register_write(interpreter, _write_car())
    assert ingest.ingest("seed luna", user, seed).status is IngestStatus.COMMITTED
    assert ingest.ingest("meu carro é um City azul", user, seed).status is IngestStatus.COMMITTED

    session = _session(user.user_id)
    interpreter.on("eu tenho uma gata?", _class_builder("cat"))
    interpreter.on("qual o nome?", _continue_attr("name"))
    interpreter.on(
        "qual o modelo do meu carro?",
        _possessive_attr("carro", "automobile", "model", kind="vehicle"),
    )
    ask.ask("eu tenho uma gata?", user, session)
    assert _attr_texts(ask.ask("qual o nome?", user, session)) == ["Luna"]
    luna_ids = set(_focus_ids(session))
    model = ask.ask("qual o modelo do meu carro?", user, session)
    assert model.status is AskStatus.ANSWERED, (model.status, model.issues)
    assert _attr_texts(model) == ["City"]
    assert luna_ids.isdisjoint(set(model.resolved_entity_ids))


def test_invented_entity_id_is_invalid_binding(tmp_path: Path) -> None:
    user, _, interpreter, ingest, ask = _harness(tmp_path, "d-invalid")
    seed = _session(user.user_id)
    _register_write(interpreter, _write_named("seed luna", "Luna", "cat"))
    assert ingest.ingest("seed luna", user, seed).status is IngestStatus.COMMITTED

    session = _session(user.user_id)
    interpreter.on("eu tenho uma gata?", _class_builder("cat"))

    def invented(ctx) -> QueryIR:
        del ctx
        proposal = SemanticProposal(
            raw_input="",
            utterance_kind="query",
            primitive_hint="attribute",
            subject=SemanticEntityMention(
                text="fake",
                kind_hint="thing",
                reference_kind="contextual",
                known_entity_id="invented-entity-id",
                confidence=1.0,
            ),
            attribute_expression="name",
            stable_property_semantics=True,
            discourse_decision="continue",
            temporal=SemanticTime(),
            confidence=1.0,
        )
        return _ir_from_proposal(proposal)

    interpreter.on("qual o nome?", invented)
    ask.ask("eu tenho uma gata?", user, session)
    result = ask.ask("qual o nome?", user, session)
    assert result.status is AskStatus.REJECTED
    assert any(issue.code == "discourse.invalid_binding" for issue in result.issues)


def test_query_focus_does_not_require_ingest_in_same_conversation(tmp_path: Path) -> None:
    user, _, interpreter, ingest, ask = _harness(tmp_path, "d-query-focus")
    other = _session(user.user_id)
    _register_write(interpreter, _write_named("seed luna", "Luna", "cat"))
    assert ingest.ingest("seed luna", user, other).status is IngestStatus.COMMITTED
    assert other.discourse.active_focus is not None

    session = _session(user.user_id)
    assert session.discourse.active_focus is None
    interpreter.on("eu tenho uma gata?", _class_builder("cat"))
    interpreter.on("qual o nome?", _continue_attr("name"))
    ask.ask("eu tenho uma gata?", user, session)
    assert session.discourse.active_focus is not None
    assert _attr_texts(ask.ask("qual o nome?", user, session)) == ["Luna"]


def test_apply_ask_excludes_principal_and_replaces_focus() -> None:
    plan = QueryPlan(
        version_policy=FactVersionPolicy.CURRENT,
        aggregation=AggregateKind.NONE,
        ordering=SortKey.EVENT_TIME_DESC,
        hierarchy=HierarchyMode.EXACT,
    )
    first = AskResult(
        status=AskStatus.ANSWERED,
        raw_text="cats",
        query_result=QueryResult(
            matched_count=1,
            plan=plan,
            relation_answer="yes",
            current_relations=[
                CurrentRelationItem(
                    relation_id="r1",
                    relation_key="relation.owns",
                    subject_entity_id="principal",
                    object_entity_id="luna",
                )
            ],
        ),
        resolved_entity_ids=["principal"],
    )
    state = apply_ask_to_discourse(DiscourseState(), first, principal_id="principal")
    assert state.active_focus is not None
    assert state.active_focus.entity_ids == ["luna"]

    second = AskResult(
        status=AskStatus.ANSWERED,
        raw_text="car",
        query_result=QueryResult(
            matched_count=1,
            plan=plan,
            relation_answer="yes",
            current_relations=[
                CurrentRelationItem(
                    relation_id="r2",
                    relation_key="relation.owns",
                    subject_entity_id="principal",
                    object_entity_id="city-car",
                )
            ],
        ),
        resolved_entity_ids=["principal"],
    )
    nxt = apply_ask_to_discourse(state, second, principal_id="principal")
    assert nxt.active_focus is not None
    assert nxt.active_focus.entity_ids == ["city-car"]
    assert any(item.entity_id == "luna" for item in nxt.recent_referents)


def test_idle_turns_clear_stale_focus() -> None:
    plan = QueryPlan(
        version_policy=FactVersionPolicy.CURRENT,
        aggregation=AggregateKind.NONE,
        ordering=SortKey.EVENT_TIME_DESC,
        hierarchy=HierarchyMode.EXACT,
    )
    filled = AskResult(
        status=AskStatus.ANSWERED,
        raw_text="cats",
        query_result=QueryResult(
            matched_count=1,
            plan=plan,
            relation_answer="yes",
            current_relations=[
                CurrentRelationItem(
                    relation_id="r1",
                    relation_key="relation.owns",
                    subject_entity_id="principal",
                    object_entity_id="luna",
                )
            ],
        ),
    )
    state = apply_ask_to_discourse(DiscourseState(), filled, principal_id="principal")
    empty = AskResult(status=AskStatus.ANSWERED, raw_text="noop")
    for _ in range(MAX_IDLE_TURNS + 1):
        state = apply_ask_to_discourse(state, empty, principal_id="principal")
    assert state.active_focus is None


def test_no_linguistic_follow_up_heuristics_in_pke() -> None:
    banned = (
        "FOLLOW_UP_WORDS",
        'startswith("qual")',
        "startswith('qual')",
        'if "e a" in',
        "PT follow-up",
        "follow_up_repair",
    )
    hits: list[str] = []
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in banned:
            if token in text:
                hits.append(f"{path}:{token}")
    assert hits == []


def test_presenter_does_not_resolve_discourse() -> None:
    presenter = (SRC / "product" / "conversation" / "presenter.py").read_text(encoding="utf-8")
    assert "active_focus" not in presenter
    assert "recent_referents" not in presenter
    assert "allowed_entity_ids" not in presenter


def test_prompts_describe_discourse_without_phrase_catalog() -> None:
    from pke.interpretation import prompts_v4, prompts_v5

    for text in (prompts_v4.SYSTEM_PROMPT, prompts_v5.SYSTEM_PROMPT):
        folded = text.casefold()
        assert "structured conversation focus" in folded
        assert "allowed_entity_ids" in folded
        assert "discourse_decision=ambiguous" in folded
        assert "never invent" in folded
    assert "discourse_decision?" in prompts_v4.PROPOSAL_SHAPE
    assert "known_entity_id?" in prompts_v4.PROPOSAL_SHAPE
