"""Schemas de completude CORE — identidade por conceito, não if-type espalhado."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from pke.ontology.registry import OntologyRegistry
from pke.ontology.seeds import core_concept_id

CORE_COMPLETENESS_VERSION = "1"


class Importance(StrEnum):
    ESSENTIAL = "essential"
    USEFUL = "useful"
    OPTIONAL = "optional"


class SlotKind(StrEnum):
    ENTITY = "entity"
    TIME = "time"
    ACTION = "action"
    FACT = "fact"
    RECURRENCE = "recurrence"
    DUE = "due"
    EVENT_TYPE = "event_type"
    SUBJECT = "subject"
    CORRECTION_TARGET = "correction_target"
    CORRECTION_FACT = "correction_fact"


class Requirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slot: str
    concept_key: str
    importance: Importance
    check: SlotKind
    priority: int
    clarification_key: str | None = None
    ask_if_missing: bool = False


class CompletenessSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    applies_to_key: str
    parent_key: str | None = None
    requirements: list[Requirement] = Field(default_factory=list)
    version: str = CORE_COMPLETENESS_VERSION

    @property
    def applies_to_concept_id(self) -> str:
        if self.applies_to_key.startswith("intent."):
            return self.applies_to_key
        return core_concept_id(self.applies_to_key)


def _req(
    slot: str,
    concept_key: str,
    importance: Importance,
    check: SlotKind,
    priority: int,
    *,
    ask: bool = False,
) -> Requirement:
    prefix = {
        SlotKind.FACT: "clarify.attribute.",
        SlotKind.ENTITY: "clarify.entity.",
        SlotKind.ACTION: "clarify.action.",
        SlotKind.TIME: "clarify.time",
        SlotKind.RECURRENCE: "clarify.recurrence",
        SlotKind.DUE: "clarify.due",
        SlotKind.SUBJECT: "clarify.subject",
        SlotKind.EVENT_TYPE: "clarify.event_type",
        SlotKind.CORRECTION_TARGET: "clarify.correction.target",
        SlotKind.CORRECTION_FACT: "clarify.correction.fact",
    }[check]
    if check in {SlotKind.FACT, SlotKind.ENTITY, SlotKind.ACTION}:
        key = prefix + concept_key.split(".")[-1]
    else:
        key = prefix
    return Requirement(
        slot=slot,
        concept_key=concept_key,
        importance=importance,
        check=check,
        priority=priority,
        clarification_key=key,
        ask_if_missing=ask,
    )


CORE_SCHEMAS: tuple[CompletenessSchema, ...] = (
    CompletenessSchema(
        applies_to_key="event.maintenance",
        requirements=[
            _req("action", "action.maintain", Importance.USEFUL, SlotKind.ACTION, 20, ask=True),
            _req("time", "slot.event_time", Importance.ESSENTIAL, SlotKind.TIME, 30),
        ],
    ),
    CompletenessSchema(
        applies_to_key="event.vehicle_maintenance",
        parent_key="event.maintenance",
        requirements=[
            _req("vehicle", "entity.vehicle", Importance.ESSENTIAL, SlotKind.ENTITY, 10),
            _req(
                "mileage",
                "attribute.mileage",
                Importance.USEFUL,
                SlotKind.FACT,
                40,
                ask=True,
            ),
            _req("amount", "attribute.amount", Importance.USEFUL, SlotKind.FACT, 50),
            _req("provider", "entity.organization", Importance.USEFUL, SlotKind.ENTITY, 60),
            _req("notes", "slot.notes", Importance.OPTIONAL, SlotKind.FACT, 90),
            _req("parts", "slot.parts", Importance.OPTIONAL, SlotKind.FACT, 91),
            _req("invoice", "slot.invoice", Importance.OPTIONAL, SlotKind.FACT, 92),
            _req("warranty", "slot.warranty", Importance.OPTIONAL, SlotKind.FACT, 93),
        ],
    ),
    CompletenessSchema(
        applies_to_key="event.appointment",
        requirements=[
            _req("time", "slot.event_time", Importance.ESSENTIAL, SlotKind.TIME, 10),
            _req("subject", "entity.person", Importance.ESSENTIAL, SlotKind.SUBJECT, 20),
            _req("event_type", "event.appointment", Importance.ESSENTIAL, SlotKind.EVENT_TYPE, 30),
            _req("provider", "entity.person", Importance.USEFUL, SlotKind.ENTITY, 40),
            _req("location", "slot.location", Importance.USEFUL, SlotKind.ENTITY, 50),
            _req("notes", "slot.notes", Importance.OPTIONAL, SlotKind.FACT, 90),
        ],
    ),
    CompletenessSchema(
        applies_to_key="event.recurring_bill",
        parent_key="event.obligation",
        requirements=[
            _req(
                "event_type",
                "event.recurring_bill",
                Importance.ESSENTIAL,
                SlotKind.EVENT_TYPE,
                10,
            ),
            _req("recurrence", "slot.recurrence", Importance.ESSENTIAL, SlotKind.RECURRENCE, 20),
            _req("due", "slot.due", Importance.ESSENTIAL, SlotKind.DUE, 30),
            _req("amount", "attribute.amount", Importance.USEFUL, SlotKind.FACT, 40),
            _req("place", "slot.place", Importance.USEFUL, SlotKind.ENTITY, 50),
            _req("notes", "slot.notes", Importance.OPTIONAL, SlotKind.FACT, 90),
        ],
    ),
    CompletenessSchema(
        applies_to_key="intent.correct",
        requirements=[
            _req(
                "target",
                "slot.correction_target",
                Importance.ESSENTIAL,
                SlotKind.CORRECTION_TARGET,
                10,
            ),
            _req(
                "fact",
                "slot.correction_fact",
                Importance.ESSENTIAL,
                SlotKind.CORRECTION_FACT,
                20,
            ),
        ],
    ),
)


class CompletenessSchemaRegistry:
    def __init__(self, schemas: tuple[CompletenessSchema, ...] = CORE_SCHEMAS) -> None:
        self._by_key = {schema.applies_to_key: schema for schema in schemas}
        if len(self._by_key) != len(schemas):
            raise ValueError("schema CORE com applies_to_key duplicado")

    @classmethod
    def core(cls) -> CompletenessSchemaRegistry:
        return cls(CORE_SCHEMAS)

    @property
    def version(self) -> str:
        return CORE_COMPLETENESS_VERSION

    def get(self, key: str) -> CompletenessSchema | None:
        return self._by_key.get(key)

    def resolve_for(self, key: str, ontology: OntologyRegistry) -> CompletenessSchema | None:
        """Schema do conceito + ancestrais. Filho sobrescreve o mesmo slot."""
        chain: list[CompletenessSchema] = []
        current: str | None = key
        seen: set[str] = set()
        while current and current not in seen:
            seen.add(current)
            schema = self._by_key.get(current)
            if schema is not None:
                chain.append(schema)
            concept = ontology.get_by_key(current)
            if concept is None or concept.parent_id is None:
                parent_key = schema.parent_key if schema else None
                current = parent_key
                continue
            parent = ontology.get_by_id(concept.parent_id)
            current = parent.key if parent else (schema.parent_key if schema else None)
        if not chain:
            return None
        merged: dict[str, Requirement] = {}
        for schema in reversed(chain):
            for req in schema.requirements:
                merged[req.slot] = req
        head = chain[0]
        return CompletenessSchema(
            applies_to_key=head.applies_to_key,
            parent_key=head.parent_key,
            requirements=sorted(merged.values(), key=lambda r: r.priority),
            version=head.version,
        )
