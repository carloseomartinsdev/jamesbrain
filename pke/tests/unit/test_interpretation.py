from __future__ import annotations

from datetime import date, time

import pytest
from pydantic import ValidationError

from pke.domain import (
    ConceptRef,
    EventStatus,
    Qualifier,
    Recurrence,
    TimePrecision,
    UserContext,
)
from pke.interpretation import (
    CorrectionStrategy,
    EntityMention,
    FakeInterpreter,
    IngestIntent,
    IngestIR,
    InterpretationContext,
    InterpretationError,
    IrCorrection,
    IrEvent,
    IrFact,
    IrObligation,
    IrQueryTime,
    IrTime,
    MentionedEntity,
    QueryIR,
    QuerySpec,
    ScriptedInterpreter,
)


def _ctx() -> InterpretationContext:
    return InterpretationContext(user=UserContext(user_id="local"))


def _amount(value: str) -> IrFact:
    return IrFact(
        attribute=ConceptRef(key="attribute.amount"),
        value={"amount": value, "currency": "BRL"},
    )


def _maintenance_ir(raw: str) -> IngestIR:
    return IngestIR(
        intent=IngestIntent.RECORD_EVENT,
        raw_input=raw,
        domains=[
            ConceptRef(key="domain.vehicle"),
            ConceptRef(key="domain.finance"),
        ],
        entities_mentioned=[
            MentionedEntity(
                text="Corolla",
                type_hint=ConceptRef(key="entity.vehicle"),
                role=ConceptRef(key="role.subject"),
            ),
        ],
        event=IrEvent(
            type=ConceptRef(key="event.vehicle_maintenance"),
            action=ConceptRef(key="action.replace"),
            status=EventStatus.COMPLETED,
            time=IrTime(original_text="hoje", precision=TimePrecision.DAY),
            facts=[
                _amount("320"),
                IrFact(
                    attribute=ConceptRef(key="attribute.maintenance_type"),
                    value=ConceptRef(key="action.oil_change"),
                ),
            ],
        ),
        missing_hints=[ConceptRef(key="attribute.mileage")],
    )


def test_ingest_ir_uses_concept_refs_not_closed_type_enums() -> None:
    ir = _maintenance_ir("Troquei o óleo do Corolla hoje por 320 reais.")
    assert ir.event is not None
    assert ir.event.type.key == "event.vehicle_maintenance"
    assert ir.entities_mentioned[0].type_hint is not None
    assert ir.entities_mentioned[0].type_hint.key == "entity.vehicle"


def test_ingest_ir_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        IngestIR.model_validate(
            {
                "intent": "record_event",
                "raw_input": "x",
                "hallucinated_specialty": "dentist",
            }
        )


def test_query_ir_is_structured() -> None:
    ir = QueryIR(
        raw_input="Quanto gastei com o Corolla este mês?",
        query=QuerySpec(
            intent="aggregate",
            entities=[EntityMention(text="Corolla", type_hint=ConceptRef(key="entity.vehicle"))],
            entity_association="subject",
            event_types=[ConceptRef(key="event.vehicle_maintenance")],
            facts=[ConceptRef(key="attribute.amount")],
            aggregate="sum",
            version_policy="current",
            time=IrQueryTime(relative_period="this_month", original_text="este mês"),
        ),
    )
    assert ir.intent == "query"
    assert ir.query.aggregate == "sum"


def test_obligation_and_correction_shapes() -> None:
    obligation = IngestIR(
        intent=IngestIntent.RECORD_OBLIGATION,
        raw_input="A internet vence todo dia 10 e é 129,90.",
        obligation=IrObligation(
            type=ConceptRef(key="event.recurring_bill"),
            cadence=Recurrence(freq="monthly", by_monthday=10),
            due=IrTime(original_text="todo dia 10", precision=TimePrecision.RECURRING),
            facts=[_amount("129.90")],
        ),
    )
    correction = IngestIR(
        intent=IngestIntent.CORRECT,
        raw_input="Não, achei a nota. Foi 186,50.",
        correction=IrCorrection(
            strategy=CorrectionStrategy.LAST_EVENT,
            facts=[_amount("186.50").model_copy(update={"qualifier": Qualifier.EXACT})],
        ),
    )
    assert obligation.obligation is not None
    assert correction.correction is not None
    assert correction.correction.strategy is CorrectionStrategy.LAST_EVENT
    assert correction.correction.event_id is None


def test_explicit_correction_requires_concrete_id() -> None:
    with pytest.raises(ValidationError):
        IrCorrection(strategy=CorrectionStrategy.EXPLICIT, facts=[_amount("1")])
    resolved = IrCorrection(
        strategy=CorrectionStrategy.EXPLICIT,
        event_id="01J00000000000000000000000",
        facts=[_amount("186.50")],
    )
    assert resolved.event_id is not None


def test_appointment_ir_keeps_original_time_text() -> None:
    ir = IngestIR(
        intent=IngestIntent.RECORD_EVENT,
        raw_input="Tenho dentista quinta às 15h com a Dra. Ana.",
        domains=[
            ConceptRef(key="domain.health"),
            ConceptRef(key="domain.appointments"),
        ],
        entities_mentioned=[
            MentionedEntity(
                text="Dra. Ana",
                type_hint=ConceptRef(key="entity.person"),
                role=ConceptRef(key="role.provider"),
                confidence=0.8,
            ),
        ],
        event=IrEvent(
            type=ConceptRef(key="event.appointment"),
            action=ConceptRef(key="action.attend"),
            status=EventStatus.SCHEDULED,
            time=IrTime(
                original_text="quinta às 15h",
                interpretation="próxima quinta 15:00",
                date=date(2026, 9, 3),
                time_of_day=time(15, 0),
                precision=TimePrecision.MINUTE,
            ),
        ),
    )
    assert ir.event is not None
    assert ir.event.time.original_text == "quinta às 15h"
    assert all(f.attribute.key != "attribute.specialty" for f in ir.event.facts)


def test_fake_interpreter_returns_registered_ir() -> None:
    raw = "Troquei o óleo do Corolla hoje por 320 reais."
    fake = FakeInterpreter({raw: _maintenance_ir(raw)})
    got = fake.interpret(raw, _ctx())
    assert isinstance(got, IngestIR)
    assert got.event is not None
    assert got.event.type.key == "event.vehicle_maintenance"


def test_fake_interpreter_unknown_raw_raises() -> None:
    with pytest.raises(InterpretationError, match="nenhuma IR scriptada"):
        FakeInterpreter().interpret("texto sem script", _ctx())


def test_scripted_interpreter_consumes_queue_and_binds_raw() -> None:
    first = _maintenance_ir("placeholder")
    second = IngestIR(
        intent=IngestIntent.CORRECT,
        raw_input="placeholder",
        correction=IrCorrection(
            strategy=CorrectionStrategy.LAST_EVENT,
            facts=[_amount("186.50")],
        ),
    )
    scripted = ScriptedInterpreter([first, second])
    a = scripted.interpret("frase um", _ctx())
    b = scripted.interpret("frase dois", _ctx())
    assert a.raw_input == "frase um"
    assert b.raw_input == "frase dois"
    assert isinstance(b, IngestIR)
    assert b.intent is IngestIntent.CORRECT
    with pytest.raises(InterpretationError, match="esgotado"):
        scripted.interpret("extra", _ctx())
