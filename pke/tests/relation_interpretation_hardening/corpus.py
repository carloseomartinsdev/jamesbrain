"""I12.16 Relation interpretation hardening — deterministic corpus (>=220)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Literal

from pke.interpretation.semantic.models import (
    SemanticEntityMention,
    SemanticProposal,
    SemanticTime,
)

ExpectedOutcome = Literal[
    "auto_execute",
    "clarify",
    "unsupported",
    "safe_abstain",
    "partial_execute",
]


@dataclass(frozen=True)
class RelationCase:
    case_id: str
    family: str
    proposal_factory: Callable[[], SemanticProposal]
    expected_outcome: ExpectedOutcome
    expected_primitive: str | None = "relation"
    notes: str = ""


def _ent(text: str, kind: str | None = None) -> SemanticEntityMention:
    return SemanticEntityMention(text=text, kind_hint=kind)


def _happened() -> SemanticTime:
    return SemanticTime(occurrence_aspect="happened")


def _ongoing() -> SemanticTime:
    return SemanticTime(occurrence_aspect="ongoing")


def rel_prop(
    *,
    raw: str,
    subject: str | None,
    obj: str | None,
    expr: str | None,
    link: bool = True,
    subj_kind: str | None = "person",
    obj_kind: str | None = "organization",
) -> SemanticProposal:
    return SemanticProposal(
        raw_input=raw,
        subject=_ent(subject, subj_kind) if subject else None,
        object=_ent(obj, obj_kind) if obj else None,
        link_semantics=link,
        relation_expression=expr,
        primitive_hint="relation",
        temporal=_ongoing(),
    )


def build_corpus() -> list[RelationCase]:
    cases: list[RelationCase] = []

    # CORE-covered relations → auto_execute
    core = [
        ("trabalha em", "Alice", "Acme", "person", "organization"),
        ("trabalha na", "João", "Empresa", "person", "organization"),
        ("works at", "Bob", "Corp", "person", "organization"),
        ("mora em", "Ana", "Recife", "person", "place"),
        ("lives in", "Carl", "Fortaleza", "person", "place"),
        ("possui", "Maria", "Corolla", "person", None),
        ("owns", "Pedro", "Bike", "person", None),
        ("casado com", "João", "Maria", "person", "person"),
        ("casada com", "Ana", "Bruno", "person", "person"),
        ("married to", "Alex", "Sam", "person", "person"),
        ("pai de", "Carlos", "Lia", "person", "person"),
        ("mãe de", "Helena", "Lia", "person", "person"),
        ("parent of", "Pat", "Kid", "person", "person"),
        ("médico", "Dr Silva", "Paciente", "person", "person"),
        ("provider", "Nurse", "Patient", "person", "person"),
        ("gosta de", "Carlos", "café", "person", "thing"),
        ("gosto de", "Ana", "jazz", "person", "thing"),
    ]
    for i, (expr, s, o, sk, ok) in enumerate(core):
        for j in range(3):
            cases.append(
                RelationCase(
                    f"CORE_OK_{i:02d}_{j}",
                    "core_relation",
                    lambda expr=expr, s=s, o=o, sk=sk, ok=ok, i=i, j=j: rel_prop(
                        raw=f"{s} {expr} {o} {i}-{j}",
                        subject=f"{s}-{j}",
                        obj=f"{o}-{j}",
                        expr=expr,
                        subj_kind=sk,
                        obj_kind=ok,
                    ),
                    "auto_execute",
                )
            )

    # Present expression outside CORE aliases → learned EXTENDED relation (not endpoint clarify)
    unknown = [
        "é segurado por",
        "is insured by",
        "member of",
        "é membro de",
        "responsável por",
        "responsible for",
        "fica em",
        "located in",
        "owned by",
        "é do",
        "has",
        "não trabalha mais",
        "nunca trabalhou",
        "nunca trabalhou em",
        "amigo de",
        "chefe de",
        "cliente de",
        "fornecedor de",
        "estudante em",
        "blorp-rel",
        "parceiro de",
        "colega de",
        "vizinho de",
        "contratado por",
    ]
    for i, expr in enumerate(unknown):
        for j in range(2):
            cases.append(
                RelationCase(
                    f"CANON_GAP_{i:02d}_{j}",
                    "canonical_gap",
                    lambda expr=expr, i=i, j=j: rel_prop(
                        raw=f"gap {expr} {i}-{j}",
                        subject=f"A-{i}-{j}",
                        obj=f"B-{i}-{j}",
                        expr=expr,
                    ),
                    "auto_execute",
                    notes="expression present; learned relation type when CORE has no alias",
                )
            )

    # Canonical gap + missing subject → clarify subject (expression alone insufficient
    # when endpoint missing); keep separate family from both-ends canonical gap.
    for i in range(12):
        cases.append(
            RelationCase(
                f"CANON_EXPR_NOSUBJ_{i:02d}",
                "missing_subject",
                lambda i=i: rel_prop(
                    raw=f"gap nosubj {i}",
                    subject=None,
                    obj=f"Acme-{i}",
                    expr="trabalha em",
                ),
                "clarify",
                notes="CORE expr + missing subject → entity_reference clarify",
            )
        )

    # Missing object with CORE expression → clarify relation_object
    for i in range(30):
        cases.append(
            RelationCase(
                f"MISS_OBJ_{i:02d}",
                "missing_object",
                lambda i=i: rel_prop(
                    raw=f"trabalha em {i}",
                    subject=f"Alice-{i}",
                    obj=None,
                    expr="trabalha em",
                ),
                "clarify",
            )
        )

    # Missing subject with CORE expression → clarify relation_subject
    for i in range(25):
        cases.append(
            RelationCase(
                f"MISS_SUBJ_{i:02d}",
                "missing_subject",
                lambda i=i: rel_prop(
                    raw=f"trabalha na Acme {i}",
                    subject=None,
                    obj=f"Acme-{i}",
                    expr="trabalha em",
                ),
                "clarify",
            )
        )

    # State controls — must not become Relation
    for i in range(15):
        cases.append(
            RelationCase(
                f"STATE_CTRL_{i:02d}",
                "state_control",
                lambda i=i: SemanticProposal(
                    raw_input=f"porta aberta {i}",
                    subject=_ent(f"porta-{i}"),
                    condition_semantics=True,
                    state_expression="aberta",
                    link_semantics=False,
                    primitive_hint="state",
                    temporal=_ongoing(),
                ),
                "auto_execute",
                expected_primitive="state",
            )
        )

    # Attribute controls
    for i in range(15):
        cases.append(
            RelationCase(
                f"ATTR_CTRL_{i:02d}",
                "attribute_control",
                lambda i=i: SemanticProposal(
                    raw_input=f"carro vermelho {i}",
                    subject=_ent("carro", "vehicle"),
                    attribute_expression="vermelho",
                    stable_property_semantics=True,
                    link_semantics=False,
                    primitive_hint="attribute",
                    temporal=_happened(),
                ),
                "auto_execute",
                expected_primitive="attribute",
            )
        )

    # Event controls — no false Relation / causal start
    for i in range(15):
        cases.append(
            RelationCase(
                f"EVT_CTRL_{i:02d}",
                "event_control",
                lambda i=i: SemanticProposal(
                    raw_input=f"troquei embreagem {i}",
                    subject=_ent("corolla", "vehicle"),
                    change_semantics=True,
                    action_expression="troquei a embreagem",
                    event_expression="troquei a embreagem",
                    link_semantics=False,
                    primitive_hint="event",
                    temporal=_happened(),
                ),
                "auto_execute",
                expected_primitive="event",
            )
        )

    # Direction / endpoint presence control (both ends + CORE)
    for i in range(15):
        cases.append(
            RelationCase(
                f"DIR_OK_{i:02d}",
                "direction",
                lambda i=i: rel_prop(
                    raw=f"dir {i}",
                    subject=f"Subj-{i}",
                    obj=f"Org-{i}",
                    expr="trabalha em",
                ),
                "auto_execute",
                notes="subject/object order preserved from proposal",
            )
        )

    return cases


I1216_RELATION_CORPUS = build_corpus()
