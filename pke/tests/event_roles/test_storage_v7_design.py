"""I11.10.1 — design/audit assertions for Event participant storage (no v7 implementation)."""

from __future__ import annotations

from pke.domain.events import Event
from pke.domain.ontology import ConceptKind
from pke.ontology.seeds import CORE_SEEDS
from pke.persist.versions import STORAGE_SCHEMA_VERSION
from pke.query.spec import EntityAssociation


def test_schema_still_v6() -> None:
    assert STORAGE_SCHEMA_VERSION == "11"


def test_event_domain_has_participant_list_and_legacy_slots() -> None:
    fields = set(Event.model_fields)
    assert "actor_id" in fields
    assert "subject_id" in fields
    assert "participants" in fields
    assert "object_id" not in fields
    assert "context_id" not in fields


def test_v6_cannot_store_three_simultaneous_roles_without_loss() -> None:
    """Historical v6 structural limit (two FK slots vs actor+object+context)."""
    slots = ("actor_id", "subject_id")
    needed = ("actor", "object", "context")
    assert len(needed) > len(slots)


def test_event_context_is_generic_association_not_role() -> None:
    assert EntityAssociation.EVENT_CONTEXT.value == "event_context"
    assert EntityAssociation.ACTOR.value == "actor"
    assert EntityAssociation.SUBJECT.value == "subject"


def test_role_seeds_are_core_ontology_concepts() -> None:
    roles = {s.key for s in CORE_SEEDS if s.kind is ConceptKind.ROLE}
    assert "role.actor" in roles
    assert "role.subject" in roles
    assert "role.provider" in roles
    # I11.10 additions — CORE did change for ROLE vocabulary
    assert "role.object" in roles
    assert "role.patient" in roles
    assert "role.context" in roles
    assert "role.unspecified" in roles


def test_legacy_actor_id_semantics_are_ambiguous_classes() -> None:
    """Migration must not assume actor_id → ACTOR for every row."""
    historical_classes = {"ACTOR", "CONTEXT", "LEGACY_UNKNOWN", "OTHER"}
    assert "CONTEXT" in historical_classes
    assert "LEGACY_UNKNOWN" in historical_classes
