"""ADR 0092 — engine-anchored discourse writes, pending intent, identity/role."""

from __future__ import annotations

from pathlib import Path

import pytest

from pke.application.ask_results import AskStatus
from pke.application.discourse import apply_ingest_to_discourse
from pke.application.results import IngestResult, IngestStatus, MaterializationResult
from pke.application.session import SessionContext
from pke.domain.ontology import ConceptRef
from pke.domain.value_objects import EventStatus
from pke.interpretation.discourse import DiscourseState
from pke.interpretation.models import (
    EntityMention,
    IngestIntent,
    IngestIR,
    IrEvent,
    IrTime,
    MentionReferenceKind,
    QueryIR,
    QuerySpec,
)
from pke.interpretation.semantic.models import (
    SemanticClaim,
    SemanticClaimKind,
    SemanticEntityMention,
    SemanticProposal,
    SemanticTime,
)
from pke.interpretation.semantic.pipeline import proposal_to_canonical_ir
from pke.persist import open_sqlite_uow
from tests.discourse.test_cross_turn_reference_resolution import (
    _actor,
    _attr_texts,
    _continue_attr,
    _focus_ids,
    _harness,
    _ir_from_proposal,
    _named,
    _possessive_attr,
    _register_write,
    _session,
)

OPAQUE_HOUSE = "OPAQUE-DISCOURSE-HOUSE-001"
OPAQUE_NOTEBOOK = "OPAQUE-DISCOURSE-NOTEBOOK-001"


def _owned_named(raw: str, name: str, class_hint: str, *, kind: str = "thing") -> SemanticProposal:
    obj = _named(name, class_hint=class_hint, kind=kind)
    actor = _actor()
    return SemanticProposal(
        raw_input=raw,
        utterance_kind="assert",
        primitive_hint="relation",
        subject=actor,
        object=obj,
        relation_expression="owns",
        link_semantics=True,
        classification_semantics=True,
        discourse_decision="new_topic",
        temporal=SemanticTime(occurrence_aspect="ongoing"),
        claims=[
            SemanticClaim(kind=SemanticClaimKind.ENTITY, subject=obj),
            SemanticClaim(
                kind=SemanticClaimKind.CLASSIFICATION, subject=obj, class_hint=class_hint
            ),
            SemanticClaim(
                kind=SemanticClaimKind.RELATION, predicate="owns", subject=actor, object=obj
            ),
            SemanticClaim(
                kind=SemanticClaimKind.INTRINSIC_PROPERTY,
                subject=obj,
                dimension="name",
                value_text=name,
            ),
        ],
        confidence=1.0,
    )


def _continue_write(dimension: str, value: str):
    def build(ctx) -> IngestIR:
        focus = ctx.discourse.active_focus if ctx.discourse is not None else None
        ids = list(focus.entity_ids) if focus is not None else []
        if not ids:
            return IngestIR(
                intent=IngestIntent.NONE,
                raw_input="",
                discourse_decision="ambiguous",
            )
        subject = SemanticEntityMention(
            text="discourse-focus",
            kind_hint="thing",
            reference_kind="contextual",
            known_entity_id=ids[0],
            confidence=1.0,
        )
        proposal = SemanticProposal(
            raw_input="",
            utterance_kind="assert",
            primitive_hint="attribute",
            subject=subject,
            stable_property_semantics=True,
            discourse_decision="continue",
            temporal=SemanticTime(occurrence_aspect="ongoing"),
            claims=[
                SemanticClaim(
                    kind=SemanticClaimKind.ATTRIBUTE,
                    subject=subject,
                    predicate=dimension,
                    dimension=dimension,
                    value_text=value,
                )
            ],
            confidence=1.0,
        )
        outcome = proposal_to_canonical_ir(proposal)
        assert outcome.ir is not None, (outcome.failure_stage, outcome.execution_reasons)
        return outcome.ir

    return build


def _named_query(name: str, class_hint: str, expression: str, *, kind: str = "thing"):
    def build(ctx) -> QueryIR:
        del ctx
        proposal = SemanticProposal(
            raw_input="",
            utterance_kind="query",
            primitive_hint="attribute",
            subject=_named(name, class_hint=class_hint, kind=kind),
            attribute_expression=expression,
            stable_property_semantics=True,
            discourse_decision="new_topic",
            temporal=SemanticTime(),
            confidence=1.0,
        )
        return _ir_from_proposal(proposal)

    return build


def _subject_only_named(name: str):
    def build(ctx) -> QueryIR:
        del ctx
        return QueryIR(
            raw_input="",
            discourse_decision="continue",
            query=QuerySpec(
                intent="attribute",
                entities=[
                    EntityMention(text=name, reference_kind=MentionReferenceKind.NAMED)
                ],
                entity_association="subject",
            ),
        )

    return build


def _incompatible_attr(dimension: str):
    def build(ctx) -> QueryIR:
        del ctx
        return QueryIR(
            raw_input="",
            discourse_decision="ambiguous",
            query=QuerySpec(intent="attribute", attribute_dimension_key=dimension),
        )

    return build


def _entity_names(db: Path, user_id: str) -> set[str]:
    with open_sqlite_uow(db) as uow:
        names = {e.canonical_name for e in uow.entities.all_for_user(user_id) if e.canonical_name}
        uow.commit()
    return names


def _attrs_for(db: Path, user_id: str, entity_id: str) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    with open_sqlite_uow(db) as uow:
        for row in uow.attributes.for_entity(user_id, entity_id):
            if row.is_current:
                out[row.dimension_key] = row.text_value
        uow.commit()
    return out


def _attr(attrs: dict[str, str | None], dim: str) -> str | None:
    if dim in attrs:
        return attrs[dim]
    learned = f"attribute.learned.{dim}"
    if learned in attrs:
        return attrs[learned]
    suffix = f".{dim}"
    for key, value in attrs.items():
        if key.endswith(suffix):
            return value
    return None


def test_write_updates_active_focus(tmp_path: Path) -> None:
    user, _, interpreter, ingest, _ = _harness(tmp_path, "w-focus")
    session = _session(user.user_id)
    _register_write(
        interpreter,
        _owned_named("eu tenho uma casa chamada Casa da Praia", "Casa da Praia", "house"),
    )
    written = ingest.ingest("eu tenho uma casa chamada Casa da Praia", user, session)
    assert written.status is IngestStatus.COMMITTED, written.issues
    ids = _focus_ids(session)
    assert len(ids) == 1
    assert ids[0] != user.user_id
    assert session.discourse.active_focus is not None
    assert session.discourse.active_focus.display_name == "Casa da Praia"
    assert session.discourse.last_update_reason in {
        "successful_write",
        "new_focus",
        "topic_switch",
    }


def test_pronoun_resolves_active_focus(tmp_path: Path) -> None:
    user, _, interpreter, ingest, _ = _harness(tmp_path, "w-pronoun")
    session = _session(user.user_id)
    _register_write(
        interpreter,
        _owned_named("eu tenho uma casa chamada Casa da Praia", "Casa da Praia", "house"),
    )
    interpreter.on("ela fica em Cumbuco", _continue_write("location", "Cumbuco"))
    interpreter.on("ela tem 3 quartos", _continue_write("bedrooms", "3"))
    first = ingest.ingest("eu tenho uma casa chamada Casa da Praia", user, session)
    assert first.status is IngestStatus.COMMITTED
    house_id = _focus_ids(session)[0]
    loc = ingest.ingest("ela fica em Cumbuco", user, session)
    rooms = ingest.ingest("ela tem 3 quartos", user, session)
    assert loc.status is IngestStatus.COMMITTED, loc.issues
    assert rooms.status is IngestStatus.COMMITTED, rooms.issues
    assert _focus_ids(session) == [house_id]
    attrs = _attrs_for(tmp_path / "w-pronoun.db", user.user_id, house_id)
    assert _attr(attrs, "location") == "Cumbuco"
    assert _attr(attrs, "bedrooms") == "3"


def test_ellipsis_resolves_active_focus(tmp_path: Path) -> None:
    user, _, interpreter, ingest, ask = _harness(tmp_path, "w-ellipsis")
    session = _session(user.user_id)
    _register_write(
        interpreter, _owned_named("seed house", "Casa da Praia", "house")
    )
    interpreter.on("e 2 banheiros", _continue_write("bathrooms", "2"))
    interpreter.on("e banheiros?", _continue_attr("bathrooms"))
    ingest.ingest("seed house", user, session)
    house_id = _focus_ids(session)[0]
    written = ingest.ingest("e 2 banheiros", user, session)
    assert written.status is IngestStatus.COMMITTED, written.issues
    assert _focus_ids(session) == [house_id]
    interpreter.on("quantos banheiros?", _continue_attr("bathrooms"))
    asked = ask.ask("quantos banheiros?", user, session)
    assert asked.status is AskStatus.ANSWERED, (asked.status, asked.issues)
    assert _attr_texts(asked) == ["2"]


def test_house_acceptance_conversation(tmp_path: Path) -> None:
    user, _, interpreter, ingest, ask = _harness(tmp_path, "w-house")
    session = _session(user.user_id)
    _register_write(
        interpreter,
        _owned_named("eu tenho uma casa chamada Casa da Praia", "Casa da Praia", "house"),
    )
    interpreter.on("ela fica em Cumbuco", _continue_write("location", "Cumbuco"))
    interpreter.on("ela tem 3 quartos", _continue_write("bedrooms", "3"))
    interpreter.on("e 2 banheiros", _continue_write("bathrooms", "2"))
    interpreter.on("quantos quartos?", _continue_attr("bedrooms"))
    interpreter.on("e banheiros?", _continue_attr("bathrooms"))
    interpreter.on("onde ela fica?", _continue_attr("location"))
    assert ingest.ingest("eu tenho uma casa chamada Casa da Praia", user, session).status is IngestStatus.COMMITTED
    house_id = _focus_ids(session)[0]
    for raw in ("ela fica em Cumbuco", "ela tem 3 quartos", "e 2 banheiros"):
        result = ingest.ingest(raw, user, session)
        assert result.status is IngestStatus.COMMITTED, (raw, result.issues)
        assert _focus_ids(session) == [house_id]
    assert _attr_texts(ask.ask("quantos quartos?", user, session)) == ["3"]
    assert _attr_texts(ask.ask("e banheiros?", user, session)) == ["2"]
    assert _attr_texts(ask.ask("onde ela fica?", user, session)) == ["Cumbuco"]
    assert _focus_ids(session) == [house_id]


def test_notebook_acceptance_and_value_not_entity(tmp_path: Path) -> None:
    user, _, interpreter, ingest, ask = _harness(tmp_path, "w-atlas")
    session = _session(user.user_id)
    _register_write(
        interpreter, _owned_named("eu tenho um notebook chamado Atlas", "Atlas", "notebook")
    )
    interpreter.on("o modelo dele é ThinkPad T14", _continue_write("model", "ThinkPad T14"))
    interpreter.on("ele tem 32 GB de memória", _continue_write("memory", "32 GB"))
    interpreter.on("qual o modelo?", _continue_attr("model"))
    interpreter.on("e a memória?", _continue_attr("memory"))
    assert ingest.ingest("eu tenho um notebook chamado Atlas", user, session).status is IngestStatus.COMMITTED
    atlas_id = _focus_ids(session)[0]
    assert ingest.ingest("o modelo dele é ThinkPad T14", user, session).status is IngestStatus.COMMITTED
    assert ingest.ingest("ele tem 32 GB de memória", user, session).status is IngestStatus.COMMITTED
    assert _focus_ids(session) == [atlas_id]
    assert _attr_texts(ask.ask("qual o modelo?", user, session)) == ["ThinkPad T14"]
    assert _attr_texts(ask.ask("e a memória?", user, session)) == ["32 GB"]
    names = _entity_names(tmp_path / "w-atlas.db", user.user_id)
    assert "Atlas" in names
    assert "ThinkPad T14" not in names
    assert "32 GB" not in names
    assert "modelo" not in names
    assert "memória" not in names


def test_query_updates_active_focus(tmp_path: Path) -> None:
    user, _, interpreter, ingest, ask = _harness(tmp_path, "w-qfocus")
    session = _session(user.user_id)
    _register_write(interpreter, _owned_named("seed atlas", "Atlas", "notebook"))
    _register_write(interpreter, _owned_named("seed house", "Casa da Praia", "house"))
    ingest.ingest("seed atlas", user, session)
    ingest.ingest("seed house", user, session)
    interpreter.on("qual o modelo do Atlas?", _named_query("Atlas", "notebook", "model"))
    asked = ask.ask("qual o modelo do Atlas?", user, session)
    assert asked.status in {AskStatus.ANSWERED, AskStatus.NO_RESULTS}
    assert _focus_ids(session) == asked.resolved_entity_ids
    assert asked.resolved_entity_ids


def test_explicit_reference_overrides_focus(tmp_path: Path) -> None:
    user, _, interpreter, ingest, ask = _harness(tmp_path, "w-explicit")
    session = _session(user.user_id)
    _register_write(interpreter, _owned_named("seed house", "Casa da Praia", "house"))
    _register_write(interpreter, _owned_named("seed atlas", "Atlas", "notebook"))
    interpreter.on("ela tem 3 quartos", _continue_write("bedrooms", "3"))
    interpreter.on("quantos quartos tem a Casa da Praia?", _named_query("Casa da Praia", "house", "bedrooms"))
    ingest.ingest("seed house", user, session)
    ingest.ingest("ela tem 3 quartos", user, session)
    ingest.ingest("seed atlas", user, session)
    assert _focus_ids(session)
    atlas_id = _focus_ids(session)[0]
    asked = ask.ask("quantos quartos tem a Casa da Praia?", user, session)
    assert asked.status is AskStatus.ANSWERED, (asked.status, asked.issues)
    assert _attr_texts(asked) == ["3"]
    house_ids = asked.resolved_entity_ids
    assert house_ids
    assert atlas_id not in house_ids
    assert _focus_ids(session) == house_ids


def test_topic_switch_updates_focus(tmp_path: Path) -> None:
    user, _, interpreter, ingest, ask = _harness(tmp_path, "w-switch")
    session = _session(user.user_id)
    _register_write(interpreter, _owned_named("seed house", "Casa da Praia", "house"))
    _register_write(interpreter, _owned_named("seed atlas", "Atlas", "notebook"))
    interpreter.on("ela tem 3 quartos", _continue_write("bedrooms", "3"))
    interpreter.on("o modelo dele é ThinkPad T14", _continue_write("model", "ThinkPad T14"))
    interpreter.on("qual o modelo?", _continue_attr("model"))
    ingest.ingest("seed house", user, session)
    ingest.ingest("ela tem 3 quartos", user, session)
    house_id = _focus_ids(session)[0]
    ingest.ingest("seed atlas", user, session)
    atlas_id = _focus_ids(session)[0]
    assert atlas_id != house_id
    ingest.ingest("o modelo dele é ThinkPad T14", user, session)
    assert _attr_texts(ask.ask("qual o modelo?", user, session)) == ["ThinkPad T14"]
    assert _focus_ids(session) == [atlas_id]


def test_topic_return_updates_focus(tmp_path: Path) -> None:
    user, _, interpreter, ingest, ask = _harness(tmp_path, "w-return")
    session = _session(user.user_id)
    _register_write(interpreter, _owned_named("seed house", "Casa da Praia", "house"))
    _register_write(interpreter, _owned_named("seed atlas", "Atlas", "notebook"))
    interpreter.on("ela tem 3 quartos", _continue_write("bedrooms", "3"))
    interpreter.on("o modelo dele é ThinkPad T14", _continue_write("model", "ThinkPad T14"))
    interpreter.on("quantos quartos tem a Casa da Praia?", _named_query("Casa da Praia", "house", "bedrooms"))
    interpreter.on("e onde ela fica?", _continue_attr("location"))
    interpreter.on("ela fica em Cumbuco", _continue_write("location", "Cumbuco"))
    ingest.ingest("seed house", user, session)
    ingest.ingest("ela fica em Cumbuco", user, session)
    ingest.ingest("ela tem 3 quartos", user, session)
    ingest.ingest("seed atlas", user, session)
    ingest.ingest("o modelo dele é ThinkPad T14", user, session)
    asked = ask.ask("quantos quartos tem a Casa da Praia?", user, session)
    assert _attr_texts(asked) == ["3"]
    house_id = asked.resolved_entity_ids[0]
    assert _focus_ids(session) == [house_id]
    assert _attr_texts(ask.ask("e onde ela fica?", user, session)) == ["Cumbuco"]


def test_mixed_domain_conversation(tmp_path: Path) -> None:
    user, _, interpreter, ingest, ask = _harness(tmp_path, "w-mixed")
    session = _session(user.user_id)
    _register_write(
        interpreter, _owned_named("eu tenho uma casa chamada Casa da Praia", "Casa da Praia", "house")
    )
    _register_write(
        interpreter, _owned_named("eu tenho um notebook chamado Atlas", "Atlas", "notebook")
    )
    interpreter.on("ela fica em Cumbuco", _continue_write("location", "Cumbuco"))
    interpreter.on("ela tem 3 quartos", _continue_write("bedrooms", "3"))
    interpreter.on("o modelo dele é ThinkPad T14", _continue_write("model", "ThinkPad T14"))
    interpreter.on("ele tem 32 GB de memória", _continue_write("memory", "32 GB"))
    interpreter.on("quantos quartos tem a Casa da Praia?", _named_query("Casa da Praia", "house", "bedrooms"))
    interpreter.on("e onde ela fica?", _continue_attr("location"))
    interpreter.on("qual o modelo do Atlas?", _named_query("Atlas", "notebook", "model"))
    interpreter.on("e a memória?", _continue_attr("memory"))
    ingest.ingest("eu tenho uma casa chamada Casa da Praia", user, session)
    ingest.ingest("ela fica em Cumbuco", user, session)
    ingest.ingest("ela tem 3 quartos", user, session)
    ingest.ingest("eu tenho um notebook chamado Atlas", user, session)
    ingest.ingest("o modelo dele é ThinkPad T14", user, session)
    ingest.ingest("ele tem 32 GB de memória", user, session)
    assert _attr_texts(ask.ask("quantos quartos tem a Casa da Praia?", user, session)) == ["3"]
    assert _attr_texts(ask.ask("e onde ela fica?", user, session)) == ["Cumbuco"]
    assert _attr_texts(ask.ask("qual o modelo do Atlas?", user, session)) == ["ThinkPad T14"]
    assert _attr_texts(ask.ask("e a memória?", user, session)) == ["32 GB"]


def test_incompatible_focus_does_not_force_resolution(tmp_path: Path) -> None:
    user, _, interpreter, ingest, ask = _harness(tmp_path, "w-incompat")
    session = _session(user.user_id)
    _register_write(interpreter, _owned_named("seed house", "Casa da Praia", "house"))
    interpreter.on("qual a bateria?", _incompatible_attr("battery"))
    ingest.ingest("seed house", user, session)
    result = ask.ask("qual a bateria?", user, session)
    assert result.status is AskStatus.NEEDS_CLARIFICATION
    assert result.query_result is None


def test_multiple_compatible_entities_requires_clarification(tmp_path: Path) -> None:
    user, _, interpreter, ingest, ask = _harness(tmp_path, "w-ambig")
    session = _session(user.user_id)
    _register_write(interpreter, _owned_named("seed atlas", "Atlas", "notebook"))
    _register_write(interpreter, _owned_named("seed vega", "Vega", "notebook"))
    interpreter.on("qual o modelo do meu notebook?", _possessive_attr("notebook", "notebook", "model"))
    ingest.ingest("seed atlas", user, session)
    ingest.ingest("seed vega", user, session)
    result = ask.ask("qual o modelo do meu notebook?", user, session)
    assert result.status is AskStatus.NEEDS_CLARIFICATION
    assert result.clarification is not None
    assert len(result.clarification.candidate_entity_ids) == 2
    assert session.discourse.pending_intent is not None
    assert session.discourse.pending_intent.attribute_dimension_key == "model"


def test_clarification_completes_pending_intent(tmp_path: Path) -> None:
    user, _, interpreter, ingest, ask = _harness(tmp_path, "w-pending")
    session = _session(user.user_id)
    _register_write(interpreter, _owned_named("seed atlas", "Atlas", "notebook"))
    _register_write(interpreter, _owned_named("seed vega", "Vega", "notebook"))
    interpreter.on(
        "qual o modelo do meu notebook?", _possessive_attr("notebook", "notebook", "model")
    )
    interpreter.on("do Atlas", _subject_only_named("Atlas"))
    ingest.ingest("seed atlas", user, session)
    interpreter.on("o modelo dele é ThinkPad T14", _continue_write("model", "ThinkPad T14"))
    ingest.ingest("o modelo dele é ThinkPad T14", user, session)
    ingest.ingest("seed vega", user, session)
    unclear = ask.ask("qual o modelo do meu notebook?", user, session)
    assert unclear.status is AskStatus.NEEDS_CLARIFICATION
    answered = ask.ask("do Atlas", user, session)
    assert answered.status is AskStatus.ANSWERED, (answered.status, answered.issues)
    assert _attr_texts(answered) == ["ThinkPad T14"]
    assert session.discourse.pending_intent is None


def test_discourse_isolation_by_conversation(tmp_path: Path) -> None:
    user, _, interpreter, ingest, _ = _harness(tmp_path, "w-iso")
    conversation_a = _session(user.user_id)
    _register_write(
        interpreter, _owned_named("eu tenho uma casa chamada Casa da Praia", "Casa da Praia", "house")
    )
    interpreter.on("ela tem 3 quartos", _continue_write("bedrooms", "3"))
    ingest.ingest("eu tenho uma casa chamada Casa da Praia", user, conversation_a)
    conversation_b = _session(user.user_id)
    result = ingest.ingest("ela tem 3 quartos", user, conversation_b)
    assert result.status is IngestStatus.NEEDS_CLARIFICATION
    assert conversation_b.discourse.active_focus is None


def test_discourse_raw_input_opaque_house(tmp_path: Path) -> None:
    user, _, interpreter, ingest, _ = _harness(tmp_path, "w-opaque-h")
    session = _session(user.user_id)
    _register_write(interpreter, _owned_named("seed house", "Casa da Praia", "house"))
    interpreter.on("ela tem 3 quartos", _continue_write("bedrooms", "3"))
    ingest.ingest("seed house", user, session)
    house_id = _focus_ids(session)[0]
    ctx = type("C", (), {"discourse": session.discourse})()
    ir = interpreter.interpret("ela tem 3 quartos", ctx)
    opaque = ir.model_copy(update={"raw_input": OPAQUE_HOUSE})
    interpreter.register(OPAQUE_HOUSE, opaque)
    written = ingest.ingest(OPAQUE_HOUSE, user, session)
    assert written.status is IngestStatus.COMMITTED, written.issues
    assert _attr(_attrs_for(tmp_path / "w-opaque-h.db", user.user_id, house_id), "bedrooms") == "3"


def test_discourse_raw_input_opaque_notebook(tmp_path: Path) -> None:
    user, _, interpreter, ingest, _ = _harness(tmp_path, "w-opaque-n")
    session = _session(user.user_id)
    _register_write(interpreter, _owned_named("seed atlas", "Atlas", "notebook"))
    interpreter.on("o modelo dele é ThinkPad T14", _continue_write("model", "ThinkPad T14"))
    ingest.ingest("seed atlas", user, session)
    atlas_id = _focus_ids(session)[0]
    ctx = type("C", (), {"discourse": session.discourse})()
    ir = interpreter.interpret("o modelo dele é ThinkPad T14", ctx)
    opaque = ir.model_copy(update={"raw_input": OPAQUE_NOTEBOOK})
    interpreter.register(OPAQUE_NOTEBOOK, opaque)
    written = ingest.ingest(OPAQUE_NOTEBOOK, user, session)
    assert written.status is IngestStatus.COMMITTED, written.issues
    assert _attr(_attrs_for(tmp_path / "w-opaque-n.db", user.user_id, atlas_id), "model") == "ThinkPad T14"


@pytest.mark.parametrize(
    ("create_raw", "follow_raw", "name"),
    [
        ("eu tenho uma casa chamada Casa da Praia", "ela tem 3 quartos", "Casa da Praia"),
        ("I own a house called Beach House", "it has 3 bedrooms", "Beach House"),
        ("tengo una casa llamada Casa de la Playa", "tiene 3 habitaciones", "Casa de la Playa"),
    ],
)
def test_pt_en_es_same_downstream_semantics(
    tmp_path: Path, create_raw: str, follow_raw: str, name: str
) -> None:
    slug = name.replace(" ", "-").lower()
    user, _, interpreter, ingest, ask = _harness(tmp_path, f"w-lang-{slug}")
    session = _session(user.user_id)
    _register_write(interpreter, _owned_named(create_raw, name, "house"))
    interpreter.on(follow_raw, _continue_write("bedrooms", "3"))
    interpreter.on("quantos quartos?", _continue_attr("bedrooms"))
    interpreter.on("how many bedrooms?", _continue_attr("bedrooms"))
    interpreter.on("cuantas habitaciones?", _continue_attr("bedrooms"))
    assert ingest.ingest(create_raw, user, session).status is IngestStatus.COMMITTED
    house_id = _focus_ids(session)[0]
    written = ingest.ingest(follow_raw, user, session)
    assert written.status is IngestStatus.COMMITTED, written.issues
    assert _focus_ids(session) == [house_id]
    asked = ask.ask("quantos quartos?", user, session)
    assert asked.status is AskStatus.ANSWERED
    assert _attr_texts(asked) == ["3"]


def test_secondary_participant_does_not_steal_focus() -> None:
    result = IngestResult(
        status=IngestStatus.COMMITTED,
        raw_text="bought",
        bound_entity_ids=["principal", "atlas", "store"],
        materialization=MaterializationResult(created_entity_ids=["atlas", "store"]),
    )
    ir = IngestIR(
        intent=IngestIntent.RECORD_EVENT,
        raw_input="bought",
        event=IrEvent(
            type=ConceptRef(key="event.purchase"),
            status=EventStatus.COMPLETED,
            time=IrTime(original_text=""),
            participants=[
                EntityMention(text="Atlas", known_entity_id="atlas"),
                EntityMention(text="TechStore", known_entity_id="store"),
            ],
        ),
    )
    state = apply_ingest_to_discourse(
        DiscourseState(),
        result,
        principal_id="principal",
        names={"atlas": "Atlas", "store": "TechStore"},
        ir=ir,
    )
    assert state.active_focus is not None
    assert state.active_focus.entity_ids == ["atlas"]


def test_attribute_value_not_promoted_to_entity(tmp_path: Path) -> None:
    test_notebook_acceptance_and_value_not_entity(tmp_path)
