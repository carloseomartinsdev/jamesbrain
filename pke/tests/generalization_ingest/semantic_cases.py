"""Casos I11.6-R — Semantic Resolution Re-evaluation (medida apenas)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Callable

from pke.interpretation.semantic.models import PrimitiveKind
from tests.semantic_resolution import fixtures as sf


class SemanticCaseGroup(StrEnum):
    PRIMITIVE = "primitive"
    CANONICAL_POSITIVE = "canonical_positive"
    SAFETY = "safety"
    AMBIGUITY = "ambiguity"
    EVENT = "event"
    ATTRIBUTE = "attribute"
    HINT_OVERRIDE = "hint_override"
    CONFLICTING = "conflicting"
    DETERMINISM = "determinism"


class ExpectedOutcome(StrEnum):
    KNOWLEDGE_COMMITTED = "knowledge_committed"
    SAFE_PARTIAL = "safe_partial"
    SAFE_UNRESOLVED = "safe_unresolved"
    SAFE_AMBIGUOUS = "safe_ambiguous"
    ONTOLOGY_GAP = "ontology_gap"
    CANONICAL_RESOLVED = "canonical_resolved"


@dataclass(frozen=True)
class CanonicalExpectation:
    relation_type: str | None = None
    action: str | None = None
    state_dimension: str | None = None
    state_value: str | None = None
    attribute: str | None = None


@dataclass(frozen=True)
class ForbiddenCanonical:
    actions: frozenset[str] = frozenset()
    state_values: frozenset[str] = frozenset()
    relation_types: frozenset[str] = frozenset()


@dataclass(frozen=True)
class SemanticBenchmarkCase:
    case_id: str
    group: SemanticCaseGroup
    text: str | None = None
    fixture: Callable[[], Any] | None = None
    expected_primitive: PrimitiveKind | None = None
    expected_sense: str | None = None
    expected_canonical: CanonicalExpectation | None = None
    forbid: ForbiddenCanonical | None = None
    acceptable_deterministic: tuple[ExpectedOutcome, ...] = (ExpectedOutcome.CANONICAL_RESOLVED,)
    safe_abstention_expected: bool = False
    false_canonical_negative: bool = False
    ontology_gap_expected: bool = False
    live_runs: int = 3
    notes: str = ""
    event_e6_install: bool = False


def _p7_unemployed():
    from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal

    return SemanticProposal(
        raw_input="João está desempregado.",
        subject=SemanticEntityMention(text="João", kind_hint="person"),
        state_expression="desempregado",
        condition_semantics=True,
        primitive_hint="state",
    )


def _p8_parent():
    from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal

    return SemanticProposal(
        raw_input="Maria é mãe de João.",
        subject=SemanticEntityMention(text="Maria", kind_hint="person"),
        object=SemanticEntityMention(text="João", kind_hint="person"),
        relation_expression="mãe de",
        link_semantics=True,
        primitive_hint="relation",
    )


def _c7_owns():
    from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal

    return SemanticProposal(
        raw_input="O Corolla é meu.",
        subject=SemanticEntityMention(text="eu", kind_hint="person"),
        object=SemanticEntityMention(text="Corolla", kind_hint="vehicle"),
        relation_expression="é meu",
        link_semantics=True,
        primitive_hint="relation",
    )


def _c8_married():
    from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal

    return SemanticProposal(
        raw_input="Ana é casada com João.",
        subject=SemanticEntityMention(text="Ana", kind_hint="person"),
        object=SemanticEntityMention(text="João", kind_hint="person"),
        relation_expression="casada com",
        link_semantics=True,
        primitive_hint="relation",
    )


def _e1_oil_change():
    from pke.interpretation.semantic.models import SemanticProposal

    return SemanticProposal(
        raw_input="Troquei o óleo do Corolla.",
        action_expression="troquei o óleo",
        change_semantics=True,
        event_expression="troquei o óleo do corolla",
        primitive_hint="event",
        temporal=sf._happened(),
    )


def _shop_002():
    from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal

    return SemanticProposal(
        raw_input="Acabou detergente.",
        subject=SemanticEntityMention(text="detergente", kind_hint="thing"),
        state_expression="acabou",
        condition_semantics=True,
        primitive_hint="state",
    )


def _hint_override_relation():
    from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal

    return SemanticProposal(
        raw_input="João trabalha na Acme.",
        subject=SemanticEntityMention(text="João", kind_hint="person"),
        object=SemanticEntityMention(text="Acme", kind_hint="organization"),
        relation_expression="trabalha na",
        link_semantics=True,
        change_semantics=False,
        primitive_hint="event",
    )


def _hint_override_event():
    from pke.interpretation.semantic.models import SemanticProposal

    return SemanticProposal(
        raw_input="A geladeira quebrou.",
        subject=sf.pr2_fridge_broke().subject,
        change_semantics=True,
        event_expression="quebrou",
        primitive_hint="state",
        temporal=sf._happened(),
    )


def _conflicting_signals():
    from pke.interpretation.semantic.models import SemanticEntityMention, SemanticProposal

    return SemanticProposal(
        raw_input="João está desempregado mas trabalha na Acme.",
        subject=SemanticEntityMention(text="João", kind_hint="person"),
        object=SemanticEntityMention(text="Acme", kind_hint="organization"),
        state_expression="desempregado",
        relation_expression="trabalha na",
        condition_semantics=True,
        link_semantics=True,
        primitive_hint="unknown",
    )


PRIMITIVE_CASES: tuple[SemanticBenchmarkCase, ...] = (
    SemanticBenchmarkCase("P1", SemanticCaseGroup.PRIMITIVE, fixture=sf.pr1_fridge_broken, expected_primitive=PrimitiveKind.STATE),
    SemanticBenchmarkCase("P2", SemanticCaseGroup.PRIMITIVE, fixture=sf.pr2_fridge_broke, expected_primitive=PrimitiveKind.EVENT),
    SemanticBenchmarkCase("P3", SemanticCaseGroup.PRIMITIVE, fixture=sf.pr3_employment, expected_primitive=PrimitiveKind.RELATION),
    SemanticBenchmarkCase("P4", SemanticCaseGroup.PRIMITIVE, fixture=sf.pr4_color, expected_primitive=PrimitiveKind.ATTRIBUTE),
    SemanticBenchmarkCase("P5", SemanticCaseGroup.PRIMITIVE, fixture=sf.pr5_door_open, expected_primitive=PrimitiveKind.STATE),
    SemanticBenchmarkCase("P6", SemanticCaseGroup.PRIMITIVE, fixture=sf.pr6_door_opened, expected_primitive=PrimitiveKind.EVENT),
    SemanticBenchmarkCase("P7", SemanticCaseGroup.PRIMITIVE, fixture=_p7_unemployed, expected_primitive=PrimitiveKind.STATE),
    SemanticBenchmarkCase("P8", SemanticCaseGroup.PRIMITIVE, fixture=_p8_parent, expected_primitive=PrimitiveKind.RELATION),
)

CANONICAL_POSITIVE_CASES: tuple[SemanticBenchmarkCase, ...] = (
    SemanticBenchmarkCase(
        "C1", SemanticCaseGroup.CANONICAL_POSITIVE, fixture=sf.sc1_employment,
        expected_primitive=PrimitiveKind.RELATION,
        expected_canonical=CanonicalExpectation(relation_type="relation.employed_by"),
    ),
    SemanticBenchmarkCase(
        "C2", SemanticCaseGroup.CANONICAL_POSITIVE, fixture=sf.sc2_broken,
        expected_primitive=PrimitiveKind.STATE,
        expected_canonical=CanonicalExpectation(
            state_dimension="state.operational_condition", state_value="state.value.broken",
        ),
    ),
    SemanticBenchmarkCase(
        "C3", SemanticCaseGroup.CANONICAL_POSITIVE, fixture=sf.sc3_open,
        expected_primitive=PrimitiveKind.STATE,
        expected_canonical=CanonicalExpectation(state_dimension="state.openness", state_value="state.value.open"),
    ),
    SemanticBenchmarkCase(
        "C4", SemanticCaseGroup.CANONICAL_POSITIVE, fixture=sf.sc4_replace_clutch,
        expected_primitive=PrimitiveKind.EVENT,
        expected_canonical=CanonicalExpectation(action="action.replace"),
    ),
    SemanticBenchmarkCase(
        "C5", SemanticCaseGroup.CANONICAL_POSITIVE, fixture=sf.sc5_substitute_clutch,
        expected_primitive=PrimitiveKind.EVENT,
        expected_canonical=CanonicalExpectation(action="action.replace"),
    ),
    SemanticBenchmarkCase(
        "C6", SemanticCaseGroup.CANONICAL_POSITIVE, fixture=sf.sc6_overdue,
        expected_primitive=PrimitiveKind.STATE,
        expected_canonical=CanonicalExpectation(
            state_dimension="state.due_status", state_value="state.value.overdue",
        ),
    ),
    SemanticBenchmarkCase(
        "C7", SemanticCaseGroup.CANONICAL_POSITIVE, fixture=_c7_owns,
        expected_primitive=PrimitiveKind.RELATION,
        expected_canonical=CanonicalExpectation(relation_type="relation.owns"),
    ),
    SemanticBenchmarkCase(
        "C8", SemanticCaseGroup.CANONICAL_POSITIVE, fixture=_c8_married,
        expected_primitive=PrimitiveKind.RELATION,
        expected_canonical=CanonicalExpectation(relation_type="relation.married_to"),
    ),
)

SAFETY_CASES: tuple[SemanticBenchmarkCase, ...] = (
    SemanticBenchmarkCase(
        "SSAFE1", SemanticCaseGroup.SAFETY, text="O técnico instalou o ar-condicionado.",
        fixture=sf.ls1_installed_ac, expected_primitive=PrimitiveKind.EVENT, expected_sense="install",
        expected_canonical=CanonicalExpectation(action="action.install"),
        forbid=ForbiddenCanonical(actions=frozenset({"action.replace"})),
        acceptable_deterministic=(ExpectedOutcome.CANONICAL_RESOLVED,),
        false_canonical_negative=True,
    ),
    SemanticBenchmarkCase(
        "SSAFE2", SemanticCaseGroup.SAFETY, text="O técnico fez a instalação do ar.",
        fixture=sf.ls2_installation_service, expected_primitive=PrimitiveKind.EVENT, expected_sense="install",
        expected_canonical=CanonicalExpectation(action="action.install"),
        forbid=ForbiddenCanonical(actions=frozenset({"action.replace"})),
        acceptable_deterministic=(ExpectedOutcome.CANONICAL_RESOLVED,),
        false_canonical_negative=True,
    ),
    SemanticBenchmarkCase(
        "SSAFE3", SemanticCaseGroup.SAFETY, text="A instalação do ar foi ontem.",
        fixture=sf.ls3_installation_yesterday, expected_primitive=PrimitiveKind.EVENT, expected_sense="install",
        expected_canonical=CanonicalExpectation(action="action.install"),
        forbid=ForbiddenCanonical(
            actions=frozenset({"action.replace"}),
            state_values=frozenset({"state.value.working"}),
        ),
        acceptable_deterministic=(ExpectedOutcome.CANONICAL_RESOLVED,),
        false_canonical_negative=True,
    ),
    SemanticBenchmarkCase(
        "SSAFE4", SemanticCaseGroup.SAFETY, text="As instalações da empresa são novas.",
        fixture=sf.ls4_facilities_new, expected_primitive=PrimitiveKind.ATTRIBUTE, expected_sense="facilities",
        forbid=ForbiddenCanonical(
            actions=frozenset({"action.replace"}),
            state_values=frozenset({"state.value.working"}),
        ),
        acceptable_deterministic=(ExpectedOutcome.ONTOLOGY_GAP, ExpectedOutcome.SAFE_PARTIAL),
        safe_abstention_expected=True, ontology_gap_expected=True, false_canonical_negative=True,
    ),
    SemanticBenchmarkCase(
        "SSAFE5", SemanticCaseGroup.SAFETY, text="Troquei ideia com João.",
        fixture=sf.ls7_exchange_idea, expected_sense="exchange_idea",
        forbid=ForbiddenCanonical(actions=frozenset({"action.replace"})),
        acceptable_deterministic=(ExpectedOutcome.SAFE_UNRESOLVED, ExpectedOutcome.SAFE_AMBIGUOUS),
        safe_abstention_expected=True, false_canonical_negative=True,
    ),
    SemanticBenchmarkCase(
        "SSAFE6", SemanticCaseGroup.SAFETY, text="Troquei reais por dólares.",
        fixture=sf.ls8_currency_exchange, expected_sense="currency_exchange",
        forbid=ForbiddenCanonical(actions=frozenset({"action.replace"})),
        acceptable_deterministic=(ExpectedOutcome.ONTOLOGY_GAP,),
        ontology_gap_expected=True, false_canonical_negative=True,
    ),
    SemanticBenchmarkCase(
        "SSAFE7", SemanticCaseGroup.SAFETY, text="Troquei de roupa.",
        fixture=sf.ls9_clothing_change, expected_sense="clothing_change",
        forbid=ForbiddenCanonical(actions=frozenset({"action.replace"})),
        acceptable_deterministic=(ExpectedOutcome.SAFE_UNRESOLVED,),
        safe_abstention_expected=True, false_canonical_negative=True,
    ),
    SemanticBenchmarkCase(
        "SSAFE8", SemanticCaseGroup.SAFETY, text="A geladeira é nova.",
        fixture=sf.state_fridge_new, expected_primitive=PrimitiveKind.ATTRIBUTE, expected_sense="property_new",
        forbid=ForbiddenCanonical(state_values=frozenset({"state.value.working", "state.value.broken"})),
        acceptable_deterministic=(ExpectedOutcome.SAFE_UNRESOLVED, ExpectedOutcome.SAFE_PARTIAL),
        safe_abstention_expected=True, false_canonical_negative=True,
    ),
    SemanticBenchmarkCase(
        "SSAFE9", SemanticCaseGroup.SAFETY, text="A porta é nova.",
        fixture=sf.state_door_new, expected_primitive=PrimitiveKind.ATTRIBUTE, expected_sense="property_new",
        forbid=ForbiddenCanonical(state_values=frozenset({"state.value.open", "state.value.working"})),
        acceptable_deterministic=(ExpectedOutcome.SAFE_UNRESOLVED,),
        safe_abstention_expected=True, false_canonical_negative=True,
    ),
    SemanticBenchmarkCase(
        "SSAFE10", SemanticCaseGroup.SAFETY, text="O motor trabalha em alta rotação.",
        fixture=sf.relation_motor_works, expected_primitive=PrimitiveKind.RELATION,
        forbid=ForbiddenCanonical(relation_types=frozenset({"relation.employed_by"})),
        acceptable_deterministic=(ExpectedOutcome.SAFE_UNRESOLVED,),
        safe_abstention_expected=True, false_canonical_negative=True,
    ),
)

AMBIGUITY_CASES: tuple[SemanticBenchmarkCase, ...] = (
    SemanticBenchmarkCase(
        "A1", SemanticCaseGroup.AMBIGUITY, text="Passei no São Luiz.", fixture=sf.ls10_passed_sao_luiz,
        expected_sense="ambiguous_pass",
        acceptable_deterministic=(ExpectedOutcome.SAFE_AMBIGUOUS, ExpectedOutcome.SAFE_UNRESOLVED),
        safe_abstention_expected=True,
    ),
    SemanticBenchmarkCase(
        "A2", SemanticCaseGroup.AMBIGUITY, text="Passei no São Luiz.", fixture=sf.ls11_shopping_context,
        expected_sense="ambiguous_pass",
        acceptable_deterministic=(
            ExpectedOutcome.SAFE_AMBIGUOUS, ExpectedOutcome.SAFE_UNRESOLVED, ExpectedOutcome.ONTOLOGY_GAP,
        ),
        safe_abstention_expected=True,
        notes="shopping context — do not require purchase Event",
    ),
)

EVENT_CASES: tuple[SemanticBenchmarkCase, ...] = (
    SemanticBenchmarkCase(
        "E1", SemanticCaseGroup.EVENT, text="Troquei o óleo do Corolla.", fixture=_e1_oil_change,
        expected_primitive=PrimitiveKind.EVENT,
        expected_canonical=CanonicalExpectation(action="action.oil_change"),
    ),
    SemanticBenchmarkCase(
        "E2", SemanticCaseGroup.EVENT, text="A geladeira quebrou.", fixture=sf.pr2_fridge_broke,
        expected_primitive=PrimitiveKind.EVENT,
        acceptable_deterministic=(ExpectedOutcome.CANONICAL_RESOLVED, ExpectedOutcome.SAFE_UNRESOLVED),
    ),
    SemanticBenchmarkCase(
        "E3", SemanticCaseGroup.EVENT, text="A porta abriu.", fixture=sf.pr6_door_opened,
        expected_primitive=PrimitiveKind.EVENT,
        acceptable_deterministic=(ExpectedOutcome.CANONICAL_RESOLVED, ExpectedOutcome.SAFE_UNRESOLVED),
    ),
    SemanticBenchmarkCase(
        "E4", SemanticCaseGroup.EVENT, text="Troquei a embreagem.", fixture=sf.ls5_replace_clutch,
        expected_primitive=PrimitiveKind.EVENT,
        expected_canonical=CanonicalExpectation(action="action.replace"),
    ),
    SemanticBenchmarkCase(
        "E5", SemanticCaseGroup.EVENT, text="Substituí a embreagem.", fixture=sf.ls6_substitute_clutch,
        expected_primitive=PrimitiveKind.EVENT,
        expected_canonical=CanonicalExpectation(action="action.replace"),
    ),
    SemanticBenchmarkCase(
        "E6", SemanticCaseGroup.EVENT, text="O técnico instalou o ar-condicionado.", fixture=sf.ls1_installed_ac,
        expected_primitive=PrimitiveKind.EVENT, expected_sense="install",
        expected_canonical=CanonicalExpectation(action="action.install"),
        forbid=ForbiddenCanonical(actions=frozenset({"action.replace"})),
        acceptable_deterministic=(ExpectedOutcome.CANONICAL_RESOLVED,),
        notes="install now CORE — not ontology gap",
    ),
)

ATTRIBUTE_CASES: tuple[SemanticBenchmarkCase, ...] = (
    SemanticBenchmarkCase(
        "A_ATTR1", SemanticCaseGroup.ATTRIBUTE, text="O Corolla é prata.", fixture=sf.pr4_color,
        expected_primitive=PrimitiveKind.ATTRIBUTE,
        acceptable_deterministic=(ExpectedOutcome.SAFE_UNRESOLVED, ExpectedOutcome.SAFE_PARTIAL),
        safe_abstention_expected=True,
    ),
    SemanticBenchmarkCase(
        "A_ATTR2", SemanticCaseGroup.ATTRIBUTE, text="A porta é nova.", fixture=sf.state_door_new,
        expected_primitive=PrimitiveKind.ATTRIBUTE, expected_sense="property_new",
        forbid=ForbiddenCanonical(state_values=frozenset({"state.value.open"})),
        acceptable_deterministic=(ExpectedOutcome.SAFE_UNRESOLVED,),
        safe_abstention_expected=True,
    ),
)

HINT_OVERRIDE_CASES: tuple[SemanticBenchmarkCase, ...] = (
    SemanticBenchmarkCase(
        "HINT1", SemanticCaseGroup.HINT_OVERRIDE, fixture=_hint_override_relation,
        expected_primitive=PrimitiveKind.RELATION,
        notes="primitive_hint=event but link semantics → RELATION",
    ),
    SemanticBenchmarkCase(
        "HINT2", SemanticCaseGroup.HINT_OVERRIDE, fixture=_hint_override_event,
        expected_primitive=PrimitiveKind.EVENT,
        notes="primitive_hint=state but change semantics → EVENT",
    ),
)

CONFLICTING_CASES: tuple[SemanticBenchmarkCase, ...] = (
    SemanticBenchmarkCase(
        "CONF1", SemanticCaseGroup.CONFLICTING, fixture=_conflicting_signals,
        notes="condition + link — document router priority",
    ),
)

DETERMINISM_CASES: tuple[SemanticBenchmarkCase, ...] = (
    SemanticBenchmarkCase("DET1", SemanticCaseGroup.DETERMINISM, fixture=sf.ls5_replace_clutch),
    SemanticBenchmarkCase("DET2", SemanticCaseGroup.DETERMINISM, fixture=sf.ls2_installation_service),
)

LIVE_MATRIX: tuple[SemanticBenchmarkCase, ...] = (
    SemanticBenchmarkCase(
        "S1", SemanticCaseGroup.PRIMITIVE, text="A geladeira está quebrada.", fixture=sf.pr1_fridge_broken,
        expected_primitive=PrimitiveKind.STATE,
        expected_canonical=CanonicalExpectation(state_value="state.value.broken"),
    ),
    SemanticBenchmarkCase(
        "S4", SemanticCaseGroup.PRIMITIVE, text="A porta está aberta.", fixture=sf.pr5_door_open,
        expected_primitive=PrimitiveKind.STATE,
        expected_canonical=CanonicalExpectation(state_value="state.value.open"),
    ),
    SemanticBenchmarkCase(
        "SHOP_002", SemanticCaseGroup.PRIMITIVE, text="Acabou detergente.", fixture=_shop_002,
        expected_primitive=PrimitiveKind.STATE,
        expected_canonical=CanonicalExpectation(state_value="state.value.depleted"),
    ),
    SemanticBenchmarkCase(
        "PEOPLE_001", SemanticCaseGroup.CANONICAL_POSITIVE, text="João trabalha na Acme.",
        fixture=sf.sc1_employment, expected_primitive=PrimitiveKind.RELATION,
        expected_canonical=CanonicalExpectation(relation_type="relation.employed_by"),
    ),
    SemanticBenchmarkCase(
        "R3", SemanticCaseGroup.CANONICAL_POSITIVE, text="O Corolla é meu.", fixture=_c7_owns,
        expected_canonical=CanonicalExpectation(relation_type="relation.owns"),
    ),
    SemanticBenchmarkCase(
        "R4", SemanticCaseGroup.CANONICAL_POSITIVE, text="Ana é casada com João.", fixture=_c8_married,
        expected_canonical=CanonicalExpectation(relation_type="relation.married_to"),
    ),
    *EVENT_CASES,
    ATTRIBUTE_CASES[0],
    ATTRIBUTE_CASES[1],
    SAFETY_CASES[1],
    SAFETY_CASES[3],
    SAFETY_CASES[4],
    SAFETY_CASES[9],
)

ALL_DETERMINISTIC_CASES: tuple[SemanticBenchmarkCase, ...] = (
    *PRIMITIVE_CASES,
    *CANONICAL_POSITIVE_CASES,
    *SAFETY_CASES,
    *AMBIGUITY_CASES,
    *EVENT_CASES,
    *ATTRIBUTE_CASES,
    *HINT_OVERRIDE_CASES,
    *CONFLICTING_CASES,
    *DETERMINISM_CASES,
)
