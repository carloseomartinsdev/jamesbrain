"""Casos I11.5-R — Relation re-evaluation (medida; não altera produção)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RelationCaseKind(StrEnum):
    SINGLE = "single"
    LIFECYCLE = "lifecycle"
    LIFECYCLE_QUERY = "lifecycle_query"
    CONCURRENCY = "concurrency"
    TARGETED_TERMINATION = "targeted_termination"
    SYMMETRY = "symmetry"
    DENY_CURRENT = "deny_current"
    NEGATION_CONTRAST = "negation_contrast"
    CORRECTION_AUDIT = "correction_audit"
    VALID_TO_AUDIT = "valid_to_audit"
    PROVENANCE = "provenance"
    COLLAPSE_CONTRAST = "collapse_contrast"


@dataclass(frozen=True)
class RelationExpectation:
    relation_key: str | None = None
    max_events: int = 0
    max_states: int = 0
    min_relations: int = 1
    max_relations: int = 1
    forbid_causal_event: bool = True
    symmetric_single_row: bool = False
    canonical_direction: str | None = None
    termination_known: bool | None = None
    termination_calendar_known: bool | None = None
    valid_to_null: bool | None = None
    valid_from_null: bool | None = None
    is_current: bool | None = None
    query_answer: str | None = None
    query_kind: str | None = None
    provenance_distinct: bool = False
    no_recorded_at_start: bool = False
    no_recorded_at_termination: bool = False
    both_current: bool = False
    acme_ended_beta_current: bool = False
    deny_invents_termination: bool = False
    known_gap_only: bool = False


@dataclass(frozen=True)
class RelationBenchmarkCase:
    case_id: str
    kind: RelationCaseKind
    texts: tuple[str, ...]
    expectation: RelationExpectation
    live_runs: int = 3
    notes: str = ""
    relation_key: str = "relation.employed_by"
    subject_type: str = "entity.person"
    object_type: str = "entity.organization"
    subject_text: str = "João"
    object_text: str = "Acme"


RELATION_CASES: tuple[RelationBenchmarkCase, ...] = (
    RelationBenchmarkCase(
        "R1",
        RelationCaseKind.SINGLE,
        ("João trabalha na Acme.",),
        RelationExpectation(
            relation_key="relation.employed_by",
            is_current=True,
            valid_from_null=True,
            no_recorded_at_start=True,
        ),
        notes="employment; 0 State/Event",
    ),
    RelationBenchmarkCase(
        "R2",
        RelationCaseKind.SINGLE,
        ("Eu moro em Fortaleza.",),
        RelationExpectation(relation_key="relation.resides_at"),
        subject_text="eu",
        object_text="Fortaleza",
        object_type="entity.place",
        notes="residence; no move Event",
    ),
    RelationBenchmarkCase(
        "R3",
        RelationCaseKind.SINGLE,
        ("O Corolla é meu.",),
        RelationExpectation(
            relation_key="relation.owns",
            canonical_direction="person_owns_thing",
        ),
        subject_text="eu",
        object_text="Corolla",
        object_type="entity.automobile",
        notes="person owns Corolla",
    ),
    RelationBenchmarkCase(
        "R4",
        RelationCaseKind.SINGLE,
        ("Ana é casada com João.",),
        RelationExpectation(
            relation_key="relation.married_to",
            symmetric_single_row=True,
        ),
        subject_text="Ana",
        object_text="João",
        object_type="entity.person",
        notes="single canonical symmetric row",
    ),
    RelationBenchmarkCase(
        "R5",
        RelationCaseKind.SINGLE,
        ("Maria é mãe de João.",),
        RelationExpectation(relation_key="relation.parent_of"),
        subject_text="Maria",
        object_text="João",
        object_type="entity.person",
    ),
    RelationBenchmarkCase(
        "R6",
        RelationCaseKind.SINGLE,
        ("Dr. Pedro é meu cardiologista.",),
        RelationExpectation(relation_key="relation.provider_for"),
        subject_text="Dr. Pedro",
        object_text="eu",
        subject_type="entity.person",
        notes="provider_for; no appointment Event",
    ),
    RelationBenchmarkCase(
        "PEOPLE_001",
        RelationCaseKind.SINGLE,
        ("João trabalha na Acme.",),
        RelationExpectation(
            relation_key="relation.employed_by",
            max_events=0,
            max_states=0,
        ),
        notes="sentinel — employment relation commits",
    ),
    RelationBenchmarkCase(
        "RL1",
        RelationCaseKind.SINGLE,
        ("João trabalha na Acme.",),
        RelationExpectation(
            is_current=True,
            termination_known=False,
            valid_from_null=True,
            no_recorded_at_start=True,
        ),
        notes="assertion; start calendar not invented",
    ),
    RelationBenchmarkCase(
        "RL2",
        RelationCaseKind.LIFECYCLE,
        ("João trabalha na Acme.", "João não trabalha mais na Acme."),
        RelationExpectation(
            is_current=False,
            termination_known=True,
            termination_calendar_known=False,
            valid_to_null=True,
            provenance_distinct=True,
            no_recorded_at_termination=True,
        ),
        notes="termination known; calendar unknown",
    ),
    RelationBenchmarkCase(
        "RL3",
        RelationCaseKind.LIFECYCLE,
        ("João trabalha na Acme.", "João saiu da Acme em 15/08/2026."),
        RelationExpectation(
            is_current=False,
            termination_known=True,
            termination_calendar_known=True,
            valid_to_null=False,
        ),
        notes="exact termination date",
    ),
    RelationBenchmarkCase(
        "RL4",
        RelationCaseKind.LIFECYCLE,
        ("João trabalha na Acme.", "João saiu da Acme em agosto."),
        RelationExpectation(
            is_current=False,
            termination_known=True,
            termination_calendar_known=False,
            valid_to_null=True,
        ),
        notes="partial month; no invented day",
    ),
    RelationBenchmarkCase(
        "RL5_HIST",
        RelationCaseKind.LIFECYCLE_QUERY,
        ("João trabalha na Acme.", "João não trabalha mais na Acme.", "João já trabalhou na Acme?"),
        RelationExpectation(query_answer="yes", query_kind="historical_existence"),
        live_runs=0,
        notes="historical YES after termination",
    ),
    RelationBenchmarkCase(
        "RL6_CURR",
        RelationCaseKind.LIFECYCLE_QUERY,
        ("João trabalha na Acme.", "João não trabalha mais na Acme."),
        RelationExpectation(query_answer="no", query_kind="current_boolean"),
        live_runs=0,
        notes="current NO after termination",
    ),
    RelationBenchmarkCase(
        "RL7_TERM_DATE",
        RelationCaseKind.LIFECYCLE_QUERY,
        ("João trabalha na Acme.", "João não trabalha mais na Acme.", "Quando João saiu da Acme?"),
        RelationExpectation(query_answer="unknown", query_kind="termination_date"),
        live_runs=0,
        notes="termination date UNKNOWN without calendar",
    ),
    RelationBenchmarkCase(
        "RL8_PERIOD",
        RelationCaseKind.LIFECYCLE_QUERY,
        ("João trabalha na Acme.", "João não trabalha mais na Acme."),
        RelationExpectation(query_answer="unknown", query_kind="held_during"),
        live_runs=0,
        notes="period ambiguity UNKNOWN",
    ),
    RelationBenchmarkCase(
        "PROVENANCE",
        RelationCaseKind.PROVENANCE,
        ("João trabalha na Acme.", "João não trabalha mais na Acme."),
        RelationExpectation(provenance_distinct=True),
        live_runs=0,
    ),
    RelationBenchmarkCase(
        "CONCURRENT",
        RelationCaseKind.CONCURRENCY,
        ("João trabalha na Acme.", "João também consulta para Beta."),
        RelationExpectation(
            min_relations=2,
            max_relations=2,
            both_current=True,
        ),
        object_text="Beta",
        notes="no auto-supersession",
    ),
    RelationBenchmarkCase(
        "TARGETED_TERM",
        RelationCaseKind.TARGETED_TERMINATION,
        (
            "João trabalha na Acme.",
            "João também consulta para Beta.",
            "João não trabalha mais na Acme.",
        ),
        RelationExpectation(acme_ended_beta_current=True, min_relations=2, max_relations=2),
        notes="terminate Acme only; Beta stays current",
    ),
    RelationBenchmarkCase(
        "SYMMETRY",
        RelationCaseKind.SYMMETRY,
        ("Ana é casada com João.",),
        RelationExpectation(
            relation_key="relation.married_to",
            symmetric_single_row=True,
            max_relations=1,
        ),
        subject_text="Ana",
        object_text="João",
        object_type="entity.person",
        live_runs=0,
        notes="João married_to Ana query YES; single storage row",
    ),
    RelationBenchmarkCase(
        "DENY_CURRENT",
        RelationCaseKind.DENY_CURRENT,
        ("João trabalha na Acme.", "João não trabalha na Acme."),
        RelationExpectation(
            deny_invents_termination=True,
            is_current=False,
        ),
        live_runs=0,
        notes="DENY_CURRENT must not invent termination evidence",
    ),
    RelationBenchmarkCase(
        "CORRECTION",
        RelationCaseKind.CORRECTION_AUDIT,
        ("João trabalha na Acme.", "Não, eu me enganei. Ele nunca trabalhou lá."),
        RelationExpectation(known_gap_only=True),
        live_runs=0,
        notes="CORRECTION_ENGINE_DEBT — not silent termination",
    ),
    RelationBenchmarkCase(
        "VALID_TO_PARTIAL",
        RelationCaseKind.VALID_TO_AUDIT,
        ("João trabalha na Acme.", "João saiu da Acme em agosto."),
        RelationExpectation(
            termination_known=True,
            valid_to_null=True,
        ),
        live_runs=0,
        notes="valid_to must not exceed termination_temporal certainty",
    ),
)

NEGATION_LIVE_CASES: tuple[RelationBenchmarkCase, ...] = (
    RelationBenchmarkCase(
        "NEG_A",
        RelationCaseKind.NEGATION_CONTRAST,
        ("João não trabalha na Acme.",),
        RelationExpectation(max_relations=0, min_relations=0),
        live_runs=3,
        notes="current non-holding — no prior relation",
    ),
    RelationBenchmarkCase(
        "NEG_B",
        RelationCaseKind.NEGATION_CONTRAST,
        ("João trabalha na Acme.", "João não trabalha mais na Acme."),
        RelationExpectation(termination_known=True, is_current=False),
        live_runs=3,
        notes="prior relation + termination",
    ),
)

COLLAPSE_CASES: tuple[RelationBenchmarkCase, ...] = (
    RelationBenchmarkCase(
        "COLLAPSE_RELATION",
        RelationCaseKind.COLLAPSE_CONTRAST,
        ("João trabalha na Acme.",),
        RelationExpectation(relation_key="relation.employed_by"),
        notes="should be Relation not Event/State",
    ),
    RelationBenchmarkCase(
        "COLLAPSE_EVENT_START",
        RelationCaseKind.COLLAPSE_CONTRAST,
        ("João começou a trabalhar na Acme.",),
        RelationExpectation(max_relations=0, min_relations=0),
        notes="occurrence semantics — detect collapse to Relation",
    ),
    RelationBenchmarkCase(
        "COLLAPSE_EVENT_END",
        RelationCaseKind.COLLAPSE_CONTRAST,
        ("João saiu da Acme.",),
        RelationExpectation(max_relations=0, min_relations=0),
        notes="occurrence semantics — detect collapse",
    ),
    RelationBenchmarkCase(
        "COLLAPSE_STATE",
        RelationCaseKind.COLLAPSE_CONTRAST,
        ("João está desempregado.",),
        RelationExpectation(max_relations=0, min_relations=0),
        notes="unemployment State when representable; not employed_by absence",
    ),
    RelationBenchmarkCase(
        "COLLAPSE_ATTRIBUTE",
        RelationCaseKind.COLLAPSE_CONTRAST,
        ("O Corolla é prata.",),
        RelationExpectation(max_relations=0, min_relations=0),
        notes="color Attribute not Relation",
    ),
)

LIVE_RELATION_IDS = frozenset(
    {
        "R1",
        "R2",
        "R3",
        "R4",
        "R5",
        "R6",
        "PEOPLE_001",
        "RL2",
        "NEG_A",
        "NEG_B",
    }
)
