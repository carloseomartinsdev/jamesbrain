from __future__ import annotations

import datetime as dt
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from pke.domain import (
    ConceptRef,
    Entity,
    EpistemicStatus,
    EventStatus,
    Qualifier,
    Recurrence,
    RelativeDay,
    TemporalKnowledge,
    TimePrecision,
    TimeValue,
)
from pke.interpretation import (
    CorrectionStrategy,
    EntityMention,
    IngestIntent,
    IngestIR,
    IrCorrection,
    IrEvent,
    IrFact,
    IrObligation,
    IrTime,
    MentionReferenceKind,
)
from pke.ontology import OntologyRegistry, core_concept_id
from pke.reasoning import (
    CompletenessSchemaRegistry,
    KnowledgeAssessor,
    KnowledgeCandidate,
    MentionBinding,
    Presence,
)
from pke.resolution import (
    EntityResolution,
    InMemoryEntityLookup,
    ResolutionStatus,
    normalize_lexical,
)

FORTALEZA = ZoneInfo("America/Fortaleza")
TODAY = TimeValue(
    original_text="hoje",
    date=dt.date(2026, 9, 1),
    precision=TimePrecision.DAY,
    timezone="America/Fortaleza",
    reference_at=dt.datetime(2026, 9, 1, 15, tzinfo=FORTALEZA),
    resolution_rule="relative.today",
)


def _amount(value: str, *, approx: bool = False, confidence: float = 1.0) -> IrFact:
    return IrFact(
        attribute=ConceptRef(key="attribute.amount"),
        value={"amount": value, "currency": "BRL"},
        qualifier=Qualifier.APPROXIMATELY if approx else Qualifier.EXACT,
        epistemic_status=EpistemicStatus.UNCERTAIN if approx else EpistemicStatus.EXPLICIT,
        confidence=confidence,
    )


def _mileage() -> IrFact:
    return IrFact(attribute=ConceptRef(key="attribute.mileage"), value=84230)


def _resolution(
    status: ResolutionStatus,
    *,
    text: str = "Corolla",
    entity_id: str | None = None,
    create_type: str | None = None,
) -> EntityResolution:
    return EntityResolution(
        status=status,
        original_text=text,
        entity_id=entity_id,
        create_type_id=create_type,
        create_canonical_name=text if status is ResolutionStatus.CREATE_CANDIDATE else None,
    )


def _binding(
    text: str,
    type_key: str,
    resolution: EntityResolution,
    *,
    contextual: bool = False,
) -> MentionBinding:
    return MentionBinding(
        mention=EntityMention(
            text=text,
            type_hint=ConceptRef(key=type_key),
            reference_kind=(
                MentionReferenceKind.CONTEXTUAL if contextual else MentionReferenceKind.NAMED
            ),
        ),
        resolution=resolution,
    )


def _maintenance_ir(*facts: IrFact) -> IngestIR:
    return IngestIR(
        intent=IngestIntent.RECORD_EVENT,
        raw_input="Troquei o óleo do Corolla hoje por 320 reais.",
        event=IrEvent(
            type=ConceptRef(key="event.vehicle_maintenance"),
            action=ConceptRef(key="action.oil_change"),
            status=EventStatus.COMPLETED,
            time=IrTime(original_text="hoje", relative_day=RelativeDay.TODAY),
            facts=list(facts),
        ),
    )


def _candidate(
    assessor_lookup: InMemoryEntityLookup,
    ir: IngestIR,
    *,
    user_id: str = "u1",
    time: TimeValue | None = TODAY,
    bindings: list[MentionBinding] | None = None,
    due: TimeValue | None = None,
) -> KnowledgeCandidate:
    del assessor_lookup
    return KnowledgeCandidate(
        user_id=user_id,
        ir=ir,
        resolved_temporal=TemporalKnowledge.from_calendar(time) if time else None,
        resolved_due=due,
        bindings=bindings or [],
    )


@pytest.fixture
def ontology() -> OntologyRegistry:
    return OntologyRegistry.with_core_seeds()


@pytest.fixture
def lookup() -> InMemoryEntityLookup:
    return InMemoryEntityLookup()


@pytest.fixture
def assessor(ontology: OntologyRegistry, lookup: InMemoryEntityLookup) -> KnowledgeAssessor:
    return KnowledgeAssessor(ontology, lookup)


def _car_resolved() -> MentionBinding:
    return _binding(
        "Corolla",
        "entity.automobile",
        _resolution(ResolutionStatus.RESOLVED, entity_id="ent:u1:corolla"),
    )


def test_valid_and_complete(assessor: KnowledgeAssessor, lookup: InMemoryEntityLookup) -> None:
    lookup.add(
        Entity(
            id="ent:u1:corolla",
            user_id="u1",
            type_id=core_concept_id("entity.automobile"),
            canonical_name="Corolla",
            created_at=datetime(2026, 9, 1, tzinfo=UTC),
        )
    )
    assessment = assessor.assess(
        _candidate(
            lookup,
            _maintenance_ir(_amount("320"), _mileage()),
            bindings=[
                _car_resolved(),
                _binding(
                    "Oficina do João",
                    "entity.organization",
                    _resolution(
                        ResolutionStatus.CREATE_CANDIDATE,
                        text="Oficina do João",
                        create_type=core_concept_id("entity.organization"),
                    ),
                ),
            ],
        )
    )
    assert assessment.validation.valid
    assert assessment.persistable
    assert assessment.completeness.essential_missing == []
    assert assessment.completeness.useful_missing == []
    assert assessment.clarification is None


def test_essential_missing_blocks(
    assessor: KnowledgeAssessor, lookup: InMemoryEntityLookup
) -> None:
    assessment = assessor.assess(
        _candidate(
            lookup,
            _maintenance_ir(_amount("320")),
            time=None,
            bindings=[
                _binding(
                    "Corolla",
                    "entity.automobile",
                    _resolution(
                        ResolutionStatus.CREATE_CANDIDATE,
                        create_type=core_concept_id("entity.automobile"),
                    ),
                )
            ],
        )
    )
    assert "time" in assessment.completeness.essential_missing
    assert assessment.persistable is False
    assert assessment.clarification is not None
    assert assessment.clarification.blocking is True


def test_useful_missing_does_not_block(
    assessor: KnowledgeAssessor, lookup: InMemoryEntityLookup
) -> None:
    assessment = assessor.assess(
        _candidate(
            lookup,
            _maintenance_ir(_amount("320")),
            bindings=[
                _binding(
                    "Corolla",
                    "entity.automobile",
                    _resolution(
                        ResolutionStatus.CREATE_CANDIDATE,
                        create_type=core_concept_id("entity.automobile"),
                    ),
                )
            ],
        )
    )
    assert assessment.validation.valid
    assert "mileage" in assessment.completeness.useful_missing
    assert assessment.persistable is True


def test_optional_missing_has_no_effect(
    assessor: KnowledgeAssessor, lookup: InMemoryEntityLookup
) -> None:
    assessment = assessor.assess(
        _candidate(
            lookup,
            _maintenance_ir(_amount("320"), _mileage()),
            bindings=[
                _binding(
                    "Corolla",
                    "entity.automobile",
                    _resolution(
                        ResolutionStatus.CREATE_CANDIDATE,
                        create_type=core_concept_id("entity.automobile"),
                    ),
                )
            ],
        )
    )
    notes = next(e for e in assessment.completeness.evaluations if e.slot == "notes")
    assert notes.status is Presence.MISSING
    assert assessment.clarification is None
    assert assessment.persistable


def test_at_most_one_clarification(
    assessor: KnowledgeAssessor, lookup: InMemoryEntityLookup
) -> None:
    assessment = assessor.assess(
        _candidate(lookup, _maintenance_ir(_amount("320")), time=None, bindings=[])
    )
    assert assessment.clarification is not None
    assert assessment.completeness.clarification is assessment.clarification


def test_essential_priority_over_useful(
    assessor: KnowledgeAssessor, lookup: InMemoryEntityLookup
) -> None:
    assessment = assessor.assess(
        _candidate(lookup, _maintenance_ir(), time=None, bindings=[])
    )
    assert assessment.clarification is not None
    assert assessment.clarification.reason == "essential_missing"
    assert assessment.clarification.question_key.startswith("clarify.")
    assert "mileage" not in assessment.clarification.question_key


def test_case_a_mileage_useful(assessor: KnowledgeAssessor, lookup: InMemoryEntityLookup) -> None:
    assessment = assessor.assess(
        _candidate(
            lookup,
            _maintenance_ir(_amount("320")),
            bindings=[
                _binding(
                    "Corolla",
                    "entity.automobile",
                    _resolution(
                        ResolutionStatus.CREATE_CANDIDATE,
                        create_type=core_concept_id("entity.automobile"),
                    ),
                )
            ],
        )
    )
    assert assessment.persistable
    assert assessment.clarification is not None
    assert assessment.clarification.question_key == "clarify.attribute.mileage"
    assert assessment.clarification.blocking is False


def test_appointment_without_location_valid(
    assessor: KnowledgeAssessor, lookup: InMemoryEntityLookup
) -> None:
    ir = IngestIR(
        intent=IngestIntent.RECORD_EVENT,
        raw_input="Tenho dentista quinta às 15h com a Dra. Ana.",
        event=IrEvent(
            type=ConceptRef(key="event.appointment"),
            action=ConceptRef(key="action.attend"),
            status=EventStatus.SCHEDULED,
            time=IrTime(original_text="quinta às 15h"),
            facts=[],
        ),
    )
    when = TimeValue(
        original_text="quinta às 15h",
        date=dt.date(2026, 9, 3),
        time_of_day=dt.time(15, 0),
        precision=TimePrecision.MINUTE,
        timezone="America/Fortaleza",
    )
    assessment = assessor.assess(
        _candidate(
            lookup,
            ir,
            time=when,
            bindings=[
                _binding(
                    "Dra. Ana",
                    "entity.person",
                    _resolution(
                        ResolutionStatus.CREATE_CANDIDATE,
                        text="Dra. Ana",
                        create_type=core_concept_id("entity.person"),
                    ),
                )
            ],
        )
    )
    assert assessment.validation.valid
    assert assessment.persistable
    assert "location" in assessment.completeness.useful_missing
    assert all(e.concept_key != "attribute.specialty" for e in assessment.completeness.evaluations)


def test_recurring_bill_without_home_valid(
    assessor: KnowledgeAssessor, lookup: InMemoryEntityLookup
) -> None:
    ir = IngestIR(
        intent=IngestIntent.RECORD_OBLIGATION,
        raw_input="A internet vence todo dia 10 e é 129,90.",
        obligation=IrObligation(
            type=ConceptRef(key="event.recurring_bill"),
            cadence=Recurrence(freq="monthly", by_monthday=10),
            facts=[_amount("129.90")],
        ),
    )
    assessment = assessor.assess(_candidate(lookup, ir, time=None))
    assert assessment.validation.valid
    assert assessment.persistable
    assert "place" in assessment.completeness.useful_missing


def test_negative_amount_rejected(
    assessor: KnowledgeAssessor, lookup: InMemoryEntityLookup
) -> None:
    assessment = assessor.assess(
        _candidate(
            lookup,
            _maintenance_ir(_amount("-320")),
            bindings=[
                _binding(
                    "Corolla",
                    "entity.automobile",
                    _resolution(
                        ResolutionStatus.CREATE_CANDIDATE,
                        create_type=core_concept_id("entity.automobile"),
                    ),
                )
            ],
        )
    )
    assert assessment.validation.valid is False
    assert any(i.code == "value.amount_negative" for i in assessment.validation.errors)
    assert assessment.persistable is False


def test_approximate_not_promoted_to_exact(
    assessor: KnowledgeAssessor, lookup: InMemoryEntityLookup
) -> None:
    bad = IrFact(
        attribute=ConceptRef(key="attribute.amount"),
        value={"amount": "180", "currency": "BRL"},
        qualifier=Qualifier.EXACT,
        epistemic_status=EpistemicStatus.UNCERTAIN,
        confidence=0.4,
    )
    assessment = assessor.assess(
        _candidate(
            lookup,
            _maintenance_ir(bad),
            bindings=[
                _binding(
                    "Corolla",
                    "entity.automobile",
                    _resolution(
                        ResolutionStatus.CREATE_CANDIDATE,
                        create_type=core_concept_id("entity.automobile"),
                    ),
                )
            ],
        )
    )
    assert any(i.code == "epistemic.exact_vs_uncertain" for i in assessment.validation.errors)
    ok = assessor.assess(
        _candidate(
            lookup,
            _maintenance_ir(_amount("180", approx=True, confidence=0.4)),
            bindings=[
                _binding(
                    "Corolla",
                    "entity.automobile",
                    _resolution(
                        ResolutionStatus.CREATE_CANDIDATE,
                        create_type=core_concept_id("entity.automobile"),
                    ),
                )
            ],
        )
    )
    assert ok.validation.valid


def test_correction_without_concrete_target_rejected(
    assessor: KnowledgeAssessor, lookup: InMemoryEntityLookup
) -> None:
    ir = IngestIR(
        intent=IngestIntent.CORRECT,
        raw_input="Não, achei a nota. Foi 186,50.",
        correction=IrCorrection(
            strategy=CorrectionStrategy.LAST_EVENT,
            facts=[_amount("186.50")],
        ),
    )
    assessment = assessor.assess(_candidate(lookup, ir, time=None))
    assert assessment.persistable is False
    assert any(i.code == "correction.target_unresolved" for i in assessment.validation.errors)


def test_correction_with_concrete_target_valid(
    assessor: KnowledgeAssessor, lookup: InMemoryEntityLookup
) -> None:
    ir = IngestIR(
        intent=IngestIntent.CORRECT,
        raw_input="Não, achei a nota. Foi 186,50.",
        correction=IrCorrection(
            strategy=CorrectionStrategy.EXPLICIT,
            event_id="evt:1",
            facts=[_amount("186.50")],
        ),
    )
    assessment = assessor.assess(_candidate(lookup, ir, time=None))
    assert assessment.validation.valid
    assert assessment.persistable
    assert assessment.completeness.essential_missing == []


def test_ambiguous_entity_blocks(
    assessor: KnowledgeAssessor, lookup: InMemoryEntityLookup
) -> None:
    assessment = assessor.assess(
        _candidate(
            lookup,
            _maintenance_ir(_amount("320")),
            bindings=[
                _binding(
                    "João",
                    "entity.person",
                    _resolution(ResolutionStatus.AMBIGUOUS, text="João"),
                ),
                _binding(
                    "Corolla",
                    "entity.automobile",
                    _resolution(
                        ResolutionStatus.CREATE_CANDIDATE,
                        create_type=core_concept_id("entity.automobile"),
                    ),
                ),
            ],
        )
    )
    assert any(i.code == "entity.ambiguous" for i in assessment.validation.errors)
    assert assessment.persistable is False


def test_create_candidate_allowed(
    assessor: KnowledgeAssessor, lookup: InMemoryEntityLookup
) -> None:
    assessment = assessor.assess(
        _candidate(
            lookup,
            _maintenance_ir(_amount("320"), _mileage()),
            bindings=[
                _binding(
                    "Corolla",
                    "entity.automobile",
                    _resolution(
                        ResolutionStatus.CREATE_CANDIDATE,
                        create_type=core_concept_id("entity.automobile"),
                    ),
                )
            ],
        )
    )
    assert assessment.validation.valid
    assert any(i.code == "entity.create_pending" for i in assessment.validation.warnings)
    assert assessment.persistable


def test_contextual_unresolved_blocks_essential(
    assessor: KnowledgeAssessor, lookup: InMemoryEntityLookup
) -> None:
    assessment = assessor.assess(
        _candidate(
            lookup,
            _maintenance_ir(_amount("320")),
            bindings=[
                _binding(
                    "o carro",
                    "entity.vehicle",
                    _resolution(ResolutionStatus.UNRESOLVED, text="o carro"),
                    contextual=True,
                )
            ],
        )
    )
    assert any(i.code == "entity.contextual_unresolved" for i in assessment.validation.errors)
    assert assessment.persistable is False


def test_incompatible_kind_rejected(
    assessor: KnowledgeAssessor, lookup: InMemoryEntityLookup
) -> None:
    ir = _maintenance_ir(
        IrFact(attribute=ConceptRef(key="event.appointment"), value="nope"),
        _amount("320"),
    )
    assessment = assessor.assess(
        _candidate(
            lookup,
            ir,
            bindings=[
                _binding(
                    "Corolla",
                    "entity.automobile",
                    _resolution(
                        ResolutionStatus.CREATE_CANDIDATE,
                        create_type=core_concept_id("entity.automobile"),
                    ),
                )
            ],
        )
    )
    assert any(i.code == "ontology.kind_mismatch" for i in assessment.validation.errors)


def test_checked_rules_recorded(
    assessor: KnowledgeAssessor, lookup: InMemoryEntityLookup
) -> None:
    assessment = assessor.assess(
        _candidate(
            lookup,
            _maintenance_ir(_amount("320")),
            bindings=[
                _binding(
                    "Corolla",
                    "entity.automobile",
                    _resolution(
                        ResolutionStatus.CREATE_CANDIDATE,
                        create_type=core_concept_id("entity.automobile"),
                    ),
                )
            ],
        )
    )
    assert "ontology.refs" in assessment.validation.checked_rules
    assert "value.money" in assessment.validation.checked_rules


def test_warning_does_not_block(
    assessor: KnowledgeAssessor, lookup: InMemoryEntityLookup
) -> None:
    assessment = assessor.assess(
        _candidate(
            lookup,
            _maintenance_ir(_amount("320"), _mileage()),
            bindings=[
                _binding(
                    "Corolla",
                    "entity.automobile",
                    _resolution(
                        ResolutionStatus.CREATE_CANDIDATE,
                        create_type=core_concept_id("entity.automobile"),
                    ),
                )
            ],
        )
    )
    assert assessment.validation.warnings
    assert assessment.validation.valid
    assert assessment.persistable


def test_validation_error_blocks(
    assessor: KnowledgeAssessor, lookup: InMemoryEntityLookup
) -> None:
    assessment = assessor.assess(
        _candidate(lookup, _maintenance_ir(_amount("-1")), bindings=[])
    )
    assert assessment.validation.valid is False
    assert assessment.persistable is False


def test_persistable_derivation(
    assessor: KnowledgeAssessor, lookup: InMemoryEntityLookup
) -> None:
    ok = assessor.assess(
        _candidate(
            lookup,
            _maintenance_ir(_amount("320")),
            bindings=[
                _binding(
                    "Corolla",
                    "entity.automobile",
                    _resolution(
                        ResolutionStatus.CREATE_CANDIDATE,
                        create_type=core_concept_id("entity.automobile"),
                    ),
                )
            ],
        )
    )
    bad = assessor.assess(
        _candidate(lookup, _maintenance_ir(_amount("320")), time=None, bindings=[])
    )
    assert ok.persistable is True
    assert bad.persistable is False


def test_user_a_cannot_use_entity_of_b(
    assessor: KnowledgeAssessor, lookup: InMemoryEntityLookup
) -> None:
    lookup.add(
        Entity(
            id="ent:b:car",
            user_id="u2",
            type_id=core_concept_id("entity.automobile"),
            canonical_name="Corolla",
            created_at=datetime(2026, 9, 1, tzinfo=UTC),
        )
    )
    assessment = assessor.assess(
        _candidate(
            lookup,
            _maintenance_ir(_amount("320")),
            user_id="u1",
            bindings=[
                _binding(
                    "Corolla",
                    "entity.automobile",
                    _resolution(ResolutionStatus.RESOLVED, entity_id="ent:b:car"),
                )
            ],
        )
    )
    assert any(i.code == "entity.foreign" for i in assessment.validation.errors)
    assert assessment.persistable is False


def test_completeness_has_no_ui_copy(
    assessor: KnowledgeAssessor, lookup: InMemoryEntityLookup
) -> None:
    assessment = assessor.assess(
        _candidate(
            lookup,
            _maintenance_ir(_amount("320")),
            bindings=[
                _binding(
                    "Corolla",
                    "entity.automobile",
                    _resolution(
                        ResolutionStatus.CREATE_CANDIDATE,
                        create_type=core_concept_id("entity.automobile"),
                    ),
                )
            ],
        )
    )
    key = assessment.clarification.question_key if assessment.clarification else ""
    assert key.startswith("clarify.")
    assert "?" not in key
    assert "Qual" not in key
    assert "quilometragem" not in key


def test_core_schema_is_deterministic() -> None:
    a = CompletenessSchemaRegistry.core()
    b = CompletenessSchemaRegistry.core()
    assert a.version == b.version == "1"
    assert a.get("event.vehicle_maintenance") == b.get("event.vehicle_maintenance")


def test_assessor_does_not_persist(
    assessor: KnowledgeAssessor, lookup: InMemoryEntityLookup
) -> None:
    before = len(lookup)
    assessor.assess(
        _candidate(
            lookup,
            _maintenance_ir(_amount("320")),
            bindings=[
                _binding(
                    "Corolla",
                    "entity.automobile",
                    _resolution(
                        ResolutionStatus.CREATE_CANDIDATE,
                        create_type=core_concept_id("entity.automobile"),
                    ),
                )
            ],
        )
    )
    assert len(lookup) == before
    assert normalize_lexical("Corolla") == "corolla"
