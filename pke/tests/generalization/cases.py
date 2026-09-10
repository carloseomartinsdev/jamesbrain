"""Casos do benchmark I11 — development (30) + holdout (15). Não reutiliza A–F."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any, Callable, Literal


class SupportLevel(StrEnum):
    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"


class FailureCategory(StrEnum):
    PROVIDER = "PROVIDER"
    WIRE = "WIRE"
    CANONICAL = "CANONICAL"
    SEMANTIC = "SEMANTIC"
    ONTOLOGY_GAP = "ONTOLOGY_GAP"
    CORE_CAPABILITY_GAP = "CORE_CAPABILITY_GAP"
    CONTEXT_GAP = "CONTEXT_GAP"


@dataclass(frozen=True)
class SemanticInvariant:
    intent: str | None = "record_event"
    has_event: bool | None = True
    has_obligation: bool | None = None
    mentions_any: tuple[str, ...] = ()
    event_type_any: tuple[str, ...] = ()
    action_any: tuple[str, ...] = ()
    domain_any: tuple[str, ...] = ()
    relative_day: str | None = None  # today|yesterday|absent|None=don't check
    weekday: int | Literal["any"] | None = None
    no_absolute_date: bool = False
    no_invented_time: bool = False
    amount_equals: Decimal | None = None
    amount_approximate: bool = False
    epistemic_uncertain: bool = False
    confidence_max: float | None = None
    quantity_equals: int | None = None
    accept_query: bool = False


@dataclass(frozen=True)
class ForbiddenInference:
    code: str
    kind: str
    value: str = ""
    must_be_absent: bool = True
    predicate: Callable[[Any], bool] | None = None


@dataclass(frozen=True)
class GeneralizationCase:
    case_id: str
    raw_text: str
    category: str
    domain_hint: str
    expected_capability: str
    expected_invariants: SemanticInvariant
    forbidden_inferences: tuple[ForbiddenInference, ...] = ()
    support_level: SupportLevel = SupportLevel.SUPPORTED
    split: Literal["development", "holdout"] = "development"
    variants: tuple[str, ...] = ()
    sequence_id: str | None = None
    sequence_step: int | None = None
    atemporal_knowledge_candidate: bool = False
    action_type: str = ""
    sentence_structure: str = ""
    temporal_type: str = ""
    epistemic_type: str = ""
    tags: tuple[str, ...] = ()

    def all_texts(self) -> list[str]:
        if self.variants:
            return list(self.variants)
        return [self.raw_text]


def _f(code: str, kind: str, value: str = "", **kw: Any) -> ForbiddenInference:
    return ForbiddenInference(code=code, kind=kind, value=value, **kw)


def _case(
    case_id: str,
    raw_text: str,
    *,
    category: str,
    domain_hint: str,
    expected_capability: str,
    invariants: SemanticInvariant,
    forbidden: tuple[ForbiddenInference, ...] = (),
    support_level: SupportLevel = SupportLevel.SUPPORTED,
    split: Literal["development", "holdout"] = "development",
    variants: tuple[str, ...] = (),
    sequence_id: str | None = None,
    sequence_step: int | None = None,
    atemporal: bool = False,
    action_type: str = "",
    sentence_structure: str = "declarative",
    temporal_type: str = "unspecified",
    epistemic_type: str = "explicit",
    tags: tuple[str, ...] = (),
) -> GeneralizationCase:
    return GeneralizationCase(
        case_id=case_id,
        raw_text=raw_text,
        category=category,
        domain_hint=domain_hint,
        expected_capability=expected_capability,
        expected_invariants=invariants,
        forbidden_inferences=forbidden,
        support_level=support_level,
        split=split,
        variants=variants,
        sequence_id=sequence_id,
        sequence_step=sequence_step,
        atemporal_knowledge_candidate=atemporal,
        action_type=action_type,
        sentence_structure=sentence_structure,
        temporal_type=temporal_type,
        epistemic_type=epistemic_type,
        tags=tags,
    )


# --- Development set (30) ---

DEVELOPMENT_CASES: tuple[GeneralizationCase, ...] = (
    # Casa / estado
    _case(
        "HOME_001",
        "A geladeira começou a fazer um barulho estranho.",
        category="home_state",
        domain_hint="home",
        expected_capability="state_or_anomaly_event",
        invariants=SemanticInvariant(
            domain_any=("domain.home", "domain.services"),
            mentions_any=("geladeira",),
            no_absolute_date=True,
            no_invented_time=True,
        ),
        forbidden=(
            _f("invented_absolute_date", "no_absolute_date"),
            _f("invented_hoje", "no_invented_relative_day", "hoje"),
        ),
        action_type="anomaly",
        temporal_type="absent",
        tags=("home", "state"),
    ),
    _case(
        "HOME_002",
        "Troquei a resistência do chuveiro ontem.",
        category="home_maintenance",
        domain_hint="home",
        expected_capability="maintenance_with_relative_day",
        invariants=SemanticInvariant(
            domain_any=("domain.home",),
            mentions_any=("chuveiro",),
            relative_day="yesterday",
            action_any=("action.replace", "action.repair", "action.maintain"),
        ),
        action_type="replace",
        temporal_type="relative_day",
        tags=("home", "maintenance"),
    ),
    _case(
        "HOME_003",
        "Instalaram um ar-condicionado no quarto.",
        category="home_installation",
        domain_hint="home",
        expected_capability="passive_installation",
        invariants=SemanticInvariant(
            domain_any=("domain.home",),
            mentions_any=("ar", "condicionado", "quarto"),
            no_absolute_date=True,
            action_any=("action.install",),
        ),
        forbidden=(_f("invented_date", "no_absolute_date"),),
        sentence_structure="passive",
        temporal_type="absent",
        action_type="install",
        tags=("home", "passive"),
    ),
    # Pessoas / relações
    _case(
        "PEOPLE_001",
        "O João não trabalha mais na Acme.",
        category="people_relation",
        domain_hint="people",
        expected_capability="employment_relation_ended",
        invariants=SemanticInvariant(
            mentions_any=("joão", "joao", "acme"),
            domain_any=("domain.work", "domain.people"),
        ),
        forbidden=(
            _f("invented_start_date", "no_absolute_date"),
            _f("invented_role", "substring_absent", "gerente"),
        ),
        action_type="end_relation",
        epistemic_type="negation",
        tags=("people", "negation", "work"),
    ),
    _case(
        "PEOPLE_002",
        "A Mariana começou a morar comigo em julho.",
        category="people_relation",
        domain_hint="people",
        expected_capability="cohabitation_start",
        invariants=SemanticInvariant(
            mentions_any=("mariana",),
            action_any=("action.start", "action.move", "action.live"),
            no_absolute_date=True,
        ),
        forbidden=(_f("invented_day", "substring_absent", "2026-07-01"),),
        temporal_type="month_only",
        action_type="start",
        tags=("people", "relation"),
    ),
    _case(
        "PEOPLE_003",
        "Emprestei 500 reais pro Pedro.",
        category="people_finance",
        domain_hint="people",
        expected_capability="lend_money",
        invariants=SemanticInvariant(
            mentions_any=("pedro",),
            amount_equals=Decimal("500"),
            domain_any=("domain.finance", "domain.people"),
        ),
        forbidden=(_f("wrong_direction", "substring_absent", "recebi"),),
        action_type="lend",
        tags=("people", "finance", "lend"),
    ),
    # Documentos
    _case(
        "DOC_001",
        "Minha CNH vence em novembro.",
        category="document_expiry",
        domain_hint="documents",
        expected_capability="document_validity",
        invariants=SemanticInvariant(
            mentions_any=("cnh", "habilitação", "habilitacao"),
            has_obligation=True,
            intent="record_obligation",
        ),
        forbidden=(_f("invented_full_date", "substring_absent", "-11-15"),),
        temporal_type="month_only",
        tags=("documents", "expiry"),
    ),
    _case(
        "DOC_002",
        "Renovei meu passaporte.",
        category="document_renewal",
        domain_hint="documents",
        expected_capability="document_renewal",
        invariants=SemanticInvariant(
            mentions_any=("passaporte",),
            action_any=("action.renew", "action.update"),
            no_absolute_date=True,
            no_invented_time=True,
        ),
        forbidden=(_f("invented_renewal_date", "no_absolute_date"),),
        temporal_type="absent",
        action_type="renew",
        tags=("documents", "renew"),
    ),
    # Educação
    _case(
        "EDU_001",
        "Comecei um curso de espanhol na terça.",
        category="education",
        domain_hint="education",
        expected_capability="course_start",
        invariants=SemanticInvariant(
            domain_any=("domain.education",),
            mentions_any=("espanhol", "curso"),
            weekday="any",
            action_any=("action.start", "action.attend", "action.enroll"),
        ),
        temporal_type="weekday",
        action_type="start",
        tags=("education",),
    ),
    _case(
        "EDU_002",
        "A prova de estatística ficou para sexta.",
        category="education",
        domain_hint="education",
        expected_capability="scheduled_exam",
        invariants=SemanticInvariant(
            domain_any=("domain.education",),
            mentions_any=("prova", "estatística", "estatistica"),
            weekday=4,
            event_type_any=("event.appointment", "event.exam", "event.deadline"),
        ),
        temporal_type="weekday_future",
        tags=("education", "appointment"),
    ),
    # Saúde
    _case(
        "HEALTH_001",
        "A Mel tomou a segunda dose da vacina sábado.",
        category="health",
        domain_hint="health",
        expected_capability="vaccination_event",
        invariants=SemanticInvariant(
            domain_any=("domain.health",),
            mentions_any=("mel", "vacina", "dose"),
            weekday=5,
        ),
        support_level=SupportLevel.PARTIALLY_SUPPORTED,
        tags=("health", "vaccination"),
    ),
    _case(
        "HEALTH_002",
        "Fui ao cardiologista, mas não lembro quando.",
        category="health",
        domain_hint="health",
        expected_capability="event_with_unknown_time",
        invariants=SemanticInvariant(
            domain_any=("domain.health",),
            mentions_any=("cardiologista", "cardio"),
            no_invented_time=True,
        ),
        forbidden=(
            _f("invented_today", "no_invented_relative_day", "hoje"),
            _f("invented_yesterday", "no_invented_relative_day", "ontem"),
        ),
        atemporal=True,
        temporal_type="explicitly_unknown",
        epistemic_type="uncertain",
        tags=("health", "atemporal_candidate"),
    ),
    # Shopping
    _case(
        "SHOP_001",
        "Comprei três filtros de café.",
        category="shopping",
        domain_hint="shopping",
        expected_capability="purchase_with_quantity",
        invariants=SemanticInvariant(
            domain_any=("domain.shopping", "domain.finance"),
            mentions_any=("filtro", "café", "cafe"),
            action_any=("action.buy", "action.purchase"),
            quantity_equals=3,
        ),
        action_type="buy",
        tags=("shopping", "quantity"),
    ),
    _case(
        "SHOP_002",
        "Acabou detergente.",
        category="shopping_state",
        domain_hint="shopping",
        expected_capability="depletion_state",
        invariants=SemanticInvariant(
            mentions_any=("detergente",),
        ),
        forbidden=(_f("invented_purchase", "substring_absent", "comprei"),),
        action_type="deplete",
        sentence_structure="minimal",
        tags=("shopping", "state"),
    ),
    # Serviços
    _case(
        "SVC_001",
        "O técnico consertou a máquina de lavar por 180 reais.",
        category="services",
        domain_hint="services",
        expected_capability="repair_with_amount",
        invariants=SemanticInvariant(
            domain_any=("domain.services", "domain.home"),
            mentions_any=("máquina", "maquina", "lavar", "técnico", "tecnico"),
            amount_equals=Decimal("180"),
            action_any=("action.repair", "action.fix", "action.maintain"),
        ),
        forbidden=(_f("invented_technician_name", "substring_absent", "carlos"),),
        action_type="repair",
        tags=("services", "maintenance"),
    ),
    _case(
        "SVC_002",
        "Cancelei a internet da casa.",
        category="services",
        domain_hint="services",
        expected_capability="service_cancellation",
        invariants=SemanticInvariant(
            domain_any=("domain.services",),
            mentions_any=("internet",),
            action_any=("action.cancel",),
        ),
        forbidden=(_f("misread_as_payment", "substring_absent", "paguei"),),
        action_type="cancel",
        tags=("services", "cancel"),
    ),
    # Viagem
    _case(
        "TRAVEL_001",
        "Reservei um hotel em Recife para dezembro.",
        category="travel",
        domain_hint="travel",
        expected_capability="reservation",
        invariants=SemanticInvariant(
            domain_any=("domain.travel",),
            mentions_any=("recife", "hotel"),
            action_any=("action.reserve", "action.book"),
            no_absolute_date=True,
        ),
        forbidden=(_f("invented_hotel_brand", "substring_absent", "marriott"),),
        action_type="reserve",
        temporal_type="month_only",
        tags=("travel",),
    ),
    _case(
        "TRAVEL_002",
        "Voltei de Fortaleza ontem.",
        category="travel",
        domain_hint="travel",
        expected_capability="return_trip",
        invariants=SemanticInvariant(
            domain_any=("domain.travel",),
            mentions_any=("fortaleza",),
            relative_day="yesterday",
            action_any=("action.return", "action.travel", "action.arrive"),
        ),
        temporal_type="relative_day",
        tags=("travel",),
    ),
    # Coloquial
    _case(
        "COLL_001",
        "O notebook tá desligando sozinho.",
        category="colloquial",
        domain_hint="home",
        expected_capability="device_anomaly",
        invariants=SemanticInvariant(
            mentions_any=("notebook",),
            no_absolute_date=True,
        ),
        sentence_structure="colloquial",
        tags=("colloquial", "home"),
    ),
    _case(
        "COLL_002",
        "Dei 200 conto pro João pagar depois.",
        category="colloquial",
        domain_hint="finance",
        expected_capability="informal_lend",
        invariants=SemanticInvariant(
            mentions_any=("joão", "joao"),
            amount_equals=Decimal("200"),
            domain_any=("domain.finance",),
        ),
        sentence_structure="colloquial",
        action_type="lend",
        tags=("colloquial", "finance"),
    ),
    # Negação
    _case(
        "NEG_001",
        "Eu não vendi o Corolla.",
        category="negation",
        domain_hint="vehicle",
        expected_capability="negated_sale",
        invariants=SemanticInvariant(
            mentions_any=("corolla",),
            domain_any=("domain.vehicle",),
        ),
        forbidden=(
            _f("positive_sale", "negation_flipped_positive"),
            _f("sale_completed", "substring_absent", '"status": "completed"'),
        ),
        epistemic_type="negation",
        tags=("negation", "vehicle"),
    ),
    _case(
        "NEG_002",
        "A conta ainda não foi paga.",
        category="negation",
        domain_hint="finance",
        expected_capability="unpaid_obligation",
        invariants=SemanticInvariant(
            domain_any=("domain.finance",),
            mentions_any=("conta",),
        ),
        forbidden=(_f("paid_positive", "substring_absent", "paguei"),),
        sentence_structure="passive",
        epistemic_type="negation",
        tags=("negation", "finance"),
    ),
    # Incerteza
    _case(
        "UNC_001",
        "Acho que paguei uns 90 reais.",
        category="uncertainty",
        domain_hint="finance",
        expected_capability="uncertain_amount",
        invariants=SemanticInvariant(
            amount_equals=Decimal("90"),
            amount_approximate=True,
            epistemic_uncertain=True,
            confidence_max=0.8,
        ),
        epistemic_type="uncertain",
        tags=("uncertainty",),
    ),
    _case(
        "UNC_002",
        "Talvez tenha sido na terça.",
        category="uncertainty",
        domain_hint="general",
        expected_capability="uncertain_time",
        invariants=SemanticInvariant(
            weekday="any",
            epistemic_uncertain=True,
            confidence_max=0.8,
        ),
        epistemic_type="uncertain",
        temporal_type="uncertain_weekday",
        tags=("uncertainty", "temporal"),
    ),
    _case(
        "EQUIV_G1",
        "Troquei a embreagem do Corolla.",
        category="equivalence",
        domain_hint="vehicle",
        expected_capability="clutch_replacement",
        invariants=SemanticInvariant(
            mentions_any=("corolla", "embreagem"),
            event_type_any=("event.vehicle_maintenance",),
            action_any=("action.replace", "action.maintain", "action.repair"),
        ),
        variants=(
            "Troquei a embreagem do Corolla.",
            "Mandei trocar a embreagem do Corolla.",
            "A embreagem do Corolla foi substituída.",
            "Foi feita a troca da embreagem do Corolla.",
        ),
        sentence_structure="equivalence_group",
        action_type="replace",
        tags=("equivalence", "passive", "vehicle"),
    ),
    _case(
        "EQUIV_G2",
        "Devolvi o livro pra biblioteca.",
        category="equivalence",
        domain_hint="education",
        expected_capability="return_item",
        invariants=SemanticInvariant(
            mentions_any=("livro", "biblioteca"),
            action_any=("action.return", "action.give"),
        ),
        variants=(
            "Devolvi o livro pra biblioteca.",
            "Entreguei o livro de volta na biblioteca.",
            "O livro foi devolvido à biblioteca.",
            "Fiz a devolução do livro na biblioteca.",
        ),
        action_type="return",
        tags=("equivalence", "return"),
    ),
    _case(
        "EQUIV_G3",
        "Instalei uma câmera na garagem.",
        category="equivalence",
        domain_hint="home",
        expected_capability="installation",
        invariants=SemanticInvariant(
            mentions_any=("câmera", "camera", "garagem"),
            action_any=("action.install",),
        ),
        variants=(
            "Instalei uma câmera na garagem.",
            "Coloquei uma câmera na garagem.",
            "Uma câmera foi instalada na garagem.",
            "Fizeram a instalação de uma câmera na garagem.",
        ),
        action_type="install",
        tags=("equivalence", "install"),
    ),
    _case(
        "EQUIV_G4",
        "Cancelei a assinatura do streaming.",
        category="equivalence",
        domain_hint="services",
        expected_capability="subscription_cancel",
        invariants=SemanticInvariant(
            mentions_any=("streaming", "assinatura"),
            action_any=("action.cancel",),
        ),
        variants=(
            "Cancelei a assinatura do streaming.",
            "Pedi cancelamento da assinatura do streaming.",
            "A assinatura do streaming foi cancelada.",
            "Foi cancelada a assinatura do streaming.",
        ),
        action_type="cancel",
        tags=("equivalence", "cancel"),
    ),
    _case(
        "EQUIV_G5",
        "Reservei mesa no restaurante italiano.",
        category="equivalence",
        domain_hint="travel",
        expected_capability="reservation",
        invariants=SemanticInvariant(
            mentions_any=("restaurante", "mesa", "italiano"),
            action_any=("action.reserve", "action.book"),
        ),
        variants=(
            "Reservei mesa no restaurante italiano.",
            "Fiz reserva no restaurante italiano.",
            "A mesa no restaurante italiano foi reservada.",
            "Foi feita a reserva no restaurante italiano.",
        ),
        action_type="reserve",
        tags=("equivalence", "reserve"),
    ),
    _case(
        "CTX_FRIDGE_04",
        "Ficou 250 reais.",
        category="context_sequence",
        domain_hint="home",
        expected_capability="contextual_amount",
        invariants=SemanticInvariant(
            amount_equals=Decimal("250"),
        ),
        support_level=SupportLevel.PARTIALLY_SUPPORTED,
        sequence_id="CTX_FRIDGE",
        sequence_step=4,
        tags=("context", "amount"),
    ),
)

# Pré-textos de sequência (não contam como casos separados; usados no runner contextual)
CONTEXT_PREFIXES: dict[str, list[str]] = {
    "CTX_FRIDGE": [
        "Comprei uma geladeira nova.",
        "Ela começou a fazer um barulho estranho.",
        "Chamei um técnico ontem.",
    ],
}

# --- Holdout set (15) — não executar no I11 baseline ---

HOLDOUT_CASES: tuple[GeneralizationCase, ...] = (
    _case(
        "HOLD_WORK_001",
        "Assinei o contrato na segunda.",
        category="work",
        domain_hint="work",
        expected_capability="contract_signing",
        invariants=SemanticInvariant(
            domain_any=("domain.work",),
            mentions_any=("contrato",),
            weekday=0,
        ),
        split="holdout",
        action_type="sign",
        tags=("holdout", "work"),
    ),
    _case(
        "HOLD_HOME_001",
        "A torneira da cozinha está pingando.",
        category="home_state",
        domain_hint="home",
        expected_capability="plumbing_issue",
        invariants=SemanticInvariant(
            mentions_any=("torneira", "cozinha"),
            no_absolute_date=True,
        ),
        split="holdout",
        tags=("holdout", "home"),
    ),
    _case(
        "HOLD_PEOPLE_001",
        "Minha irmã se mudou para Salvador.",
        category="people",
        domain_hint="people",
        expected_capability="relocation",
        invariants=SemanticInvariant(
            mentions_any=("irmã", "irma", "salvador"),
            action_any=("action.move", "action.relocate"),
        ),
        split="holdout",
        tags=("holdout", "people"),
    ),
    _case(
        "HOLD_DOC_001",
        "Perdi a carteira de trabalho.",
        category="documents",
        domain_hint="documents",
        expected_capability="document_loss",
        invariants=SemanticInvariant(
            mentions_any=("carteira", "trabalho"),
            action_any=("action.lose", "action.report"),
        ),
        split="holdout",
        action_type="lose",
        tags=("holdout", "documents"),
    ),
    _case(
        "HOLD_EDU_001",
        "Terminei o mestrado em dezembro passado.",
        category="education",
        domain_hint="education",
        expected_capability="degree_completion",
        invariants=SemanticInvariant(
            mentions_any=("mestrado",),
            action_any=("action.finish", "action.complete", "action.graduate"),
        ),
        split="holdout",
        tags=("holdout", "education"),
    ),
    _case(
        "HOLD_HEALTH_001",
        "Marquei exame de sangue para amanhã.",
        category="health",
        domain_hint="health",
        expected_capability="exam_appointment",
        invariants=SemanticInvariant(
            domain_any=("domain.health",),
            mentions_any=("exame", "sangue"),
            relative_day="tomorrow",
        ),
        split="holdout",
        tags=("holdout", "health"),
    ),
    _case(
        "HOLD_SHOP_001",
        "Devolvi a calça na loja ontem.",
        category="shopping",
        domain_hint="shopping",
        expected_capability="return_purchase",
        invariants=SemanticInvariant(
            mentions_any=("calça", "calca", "loja"),
            relative_day="yesterday",
            action_any=("action.return",),
        ),
        split="holdout",
        action_type="return",
        tags=("holdout", "shopping"),
    ),
    _case(
        "HOLD_SVC_001",
        "Contratei um fotógrafo pro casamento.",
        category="services",
        domain_hint="services",
        expected_capability="hire_service",
        invariants=SemanticInvariant(
            mentions_any=("fotógrafo", "fotografo", "casamento"),
            action_any=("action.hire", "action.book", "action.contract"),
        ),
        split="holdout",
        tags=("holdout", "services"),
    ),
    _case(
        "HOLD_TRAVEL_001",
        "Perdi o voo de conexão em Guarulhos.",
        category="travel",
        domain_hint="travel",
        expected_capability="travel_disruption",
        invariants=SemanticInvariant(
            mentions_any=("voo", "guarulhos", "conexão", "conexao"),
            action_any=("action.lose", "action.miss"),
        ),
        split="holdout",
        action_type="lose",
        tags=("holdout", "travel"),
    ),
    _case(
        "HOLD_FIN_001",
        "Recebi o décimo terceiro hoje.",
        category="finance",
        domain_hint="finance",
        expected_capability="income_receipt",
        invariants=SemanticInvariant(
            domain_any=("domain.finance",),
            relative_day="today",
            action_any=("action.receive",),
        ),
        split="holdout",
        action_type="receive",
        tags=("holdout", "finance"),
    ),
    _case(
        "HOLD_FIN_002",
        "A fatura do cartão fechou em 2400.",
        category="finance",
        domain_hint="finance",
        expected_capability="billing_cycle",
        invariants=SemanticInvariant(
            domain_any=("domain.finance",),
            mentions_any=("fatura", "cartão", "cartao"),
            amount_equals=Decimal("2400"),
        ),
        split="holdout",
        tags=("holdout", "finance"),
    ),
    _case(
        "HOLD_GEN_001",
        "Choveu muito ontem à noite.",
        category="general",
        domain_hint="general",
        expected_capability="weather_event",
        invariants=SemanticInvariant(
            relative_day="yesterday",
            mentions_any=("choveu", "chuva"),
        ),
        split="holdout",
        tags=("holdout", "general"),
    ),
    _case(
        "HOLD_NEG_001",
        "Não encontrei minhas chaves.",
        category="negation",
        domain_hint="general",
        expected_capability="failed_search",
        invariants=SemanticInvariant(
            mentions_any=("chave",),
            action_any=("action.find", "action.search", "action.lose"),
        ),
        split="holdout",
        epistemic_type="negation",
        tags=("holdout", "negation"),
    ),
    _case(
        "HOLD_UNC_001",
        "Deve ter sido semana passada.",
        category="uncertainty",
        domain_hint="general",
        expected_capability="uncertain_past_period",
        invariants=SemanticInvariant(
            epistemic_uncertain=True,
            confidence_max=0.8,
        ),
        split="holdout",
        epistemic_type="uncertain",
        tags=("holdout", "uncertainty"),
    ),
    _case(
        "HOLD_ATEMP_001",
        "Troquei a embreagem do Corolla, mas não lembro quando.",
        category="atemporal",
        domain_hint="vehicle",
        expected_capability="historical_event_unknown_time",
        invariants=SemanticInvariant(
            mentions_any=("corolla", "embreagem"),
            no_invented_time=True,
        ),
        forbidden=(_f("invented_today", "no_invented_relative_day", "hoje"),),
        split="holdout",
        atemporal=True,
        tags=("holdout", "atemporal_candidate"),
    ),
)


@dataclass(frozen=True)
class GeneralizationBenchmark:
    development: tuple[GeneralizationCase, ...] = DEVELOPMENT_CASES
    holdout: tuple[GeneralizationCase, ...] = HOLDOUT_CASES

    @property
    def all_cases(self) -> tuple[GeneralizationCase, ...]:
        return self.development + self.holdout


BENCHMARK = GeneralizationBenchmark()

# Textos A–F (não devem aparecer no benchmark)
_ACCEPTANCE_TEXTS = frozenset(
    {
        "Troquei o óleo do Corolla hoje por 320 reais.",
        "Tenho dentista quinta às 15h com a Dra. Ana.",
        "A internet vence todo dia 10 e é 129,90.",
        "Acho que a revisão do Corolla hoje ficou em uns 180 reais.",
        "Acho que a revisão ficou em uns 180 reais.",
        "Não, achei a nota. Foi 186,50.",
        "Quanto gastei com o Corolla este mês?",
    }
)
