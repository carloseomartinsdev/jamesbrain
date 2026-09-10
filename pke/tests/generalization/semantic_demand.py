"""Demanda semântica conceitual do benchmark I11 — não é verbo literal."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class DemandCategory(StrEnum):
    ACTION = "action"
    EVENT = "event"
    ENTITY = "entity"
    STATE = "state"
    RELATION = "relation"
    ATTRIBUTE = "attribute"
    DOMAIN = "domain"


@dataclass(frozen=True)
class SemanticNeed:
    """Necessidade conceitual única, agnóstica de superfície linguística."""

    need_id: str
    category: DemandCategory
    description: str
    canonical_key: str | None
    generalizable_parent: str | None = None
    surface_forms: tuple[str, ...] = ()
    representation_note: str | None = None


# Catálogo de necessidades (agrupa equivalências como trocar/substituir/fazer a troca).
SEMANTIC_NEEDS: dict[str, SemanticNeed] = {
    # Actions
    "need.action.replace": SemanticNeed(
        "need.action.replace",
        DemandCategory.ACTION,
        "substituição de componente",
        "action.replace",
        "action.maintain",
        ("trocar", "substituir", "substituída", "troca", "substituição"),
    ),
    "need.action.install": SemanticNeed(
        "need.action.install",
        DemandCategory.ACTION,
        "instalação de equipamento",
        "action.install",
        None,
        ("instalar", "instalaram", "instalação"),
    ),
    "need.action.repair": SemanticNeed(
        "need.action.repair",
        DemandCategory.ACTION,
        "conserto/reparo",
        None,
        "action.maintain",
        ("consertar", "consertou", "reparar"),
    ),
    "need.action.cancel": SemanticNeed(
        "need.action.cancel",
        DemandCategory.ACTION,
        "cancelamento de serviço/assinatura",
        None,
        None,
        ("cancelar", "cancelei", "cancelamento"),
    ),
    "need.action.lend": SemanticNeed(
        "need.action.lend",
        DemandCategory.ACTION,
        "empréstimo de dinheiro (usuário → outro)",
        None,
        "action.pay",
        ("emprestei", "emprestar", "deve"),
    ),
    "need.action.renew": SemanticNeed(
        "need.action.renew",
        DemandCategory.ACTION,
        "renovação de documento",
        None,
        "action.maintain",
        ("renovei", "renovar", "renovação"),
    ),
    "need.action.buy": SemanticNeed(
        "need.action.buy",
        DemandCategory.ACTION,
        "compra",
        "action.buy",
        None,
        ("comprei", "comprar"),
    ),
    "need.action.reserve": SemanticNeed(
        "need.action.reserve",
        DemandCategory.ACTION,
        "reserva (hotel, mesa)",
        None,
        "action.attend",
        ("reservei", "reserva", "reservar"),
    ),
    "need.action.return_trip": SemanticNeed(
        "need.action.return_trip",
        DemandCategory.ACTION,
        "retorno de viagem",
        None,
        "action.attend",
        ("voltei", "retorno", "voltar"),
    ),
    "need.action.start": SemanticNeed(
        "need.action.start",
        DemandCategory.ACTION,
        "início (curso, moradia, relação)",
        None,
        "action.attend",
        ("comecei", "começou", "início", "começar a morar"),
    ),
    "need.action.attend": SemanticNeed(
        "need.action.attend",
        DemandCategory.ACTION,
        "comparecimento/consulta",
        "action.attend",
        None,
        ("fui ao", "consulta", "cardiologista"),
    ),
    "need.action.pay": SemanticNeed(
        "need.action.pay",
        DemandCategory.ACTION,
        "pagamento",
        "action.pay",
        None,
        ("paguei", "pagar", "foi paga"),
    ),
    "need.action.return_item": SemanticNeed(
        "need.action.return_item",
        DemandCategory.ACTION,
        "devolução de item",
        None,
        None,
        ("devolvi", "devolução", "devolver"),
    ),
    # Events
    "need.event.maintenance": SemanticNeed(
        "need.event.maintenance",
        DemandCategory.EVENT,
        "manutenção doméstica/veicular",
        "event.maintenance",
        None,
        ("manutenção", "troca", "revisão", "conserto"),
    ),
    "need.event.vehicle_maintenance": SemanticNeed(
        "need.event.vehicle_maintenance",
        DemandCategory.EVENT,
        "manutenção veicular",
        "event.vehicle_maintenance",
        "event.maintenance",
        ("embreagem", "revisão do carro", "óleo"),
    ),
    "need.event.anomaly": SemanticNeed(
        "need.event.anomaly",
        DemandCategory.EVENT,
        "anomalia/falha observada",
        None,
        "event.maintenance",
        ("barulho estranho", "desligando sozinho", "parou de gelar"),
    ),
    "need.event.installation": SemanticNeed(
        "need.event.installation",
        DemandCategory.EVENT,
        "instalação",
        None,
        "event.maintenance",
        ("ar-condicionado instalado",),
    ),
    "need.event.appointment": SemanticNeed(
        "need.event.appointment",
        DemandCategory.EVENT,
        "compromisso agendado",
        "event.appointment",
        None,
        ("dentista", "prova", "exame"),
    ),
    "need.event.payment": SemanticNeed(
        "need.event.payment",
        DemandCategory.EVENT,
        "pagamento",
        "event.payment",
        None,
        ("pagamento", "paguei"),
    ),
    "need.event.purchase": SemanticNeed(
        "need.event.purchase",
        DemandCategory.EVENT,
        "compra",
        "event.purchase",
        None,
        ("comprei", "compra"),
    ),
    "need.event.travel": SemanticNeed(
        "need.event.travel",
        DemandCategory.EVENT,
        "viagem/deslocamento",
        None,
        None,
        ("voltei de", "viagem"),
        representation_note="sem event.travel no CORE",
    ),
    "need.event.reservation": SemanticNeed(
        "need.event.reservation",
        DemandCategory.EVENT,
        "reserva",
        None,
        "event.appointment",
        ("hotel", "reserva"),
    ),
    "need.event.obligation_expiry": SemanticNeed(
        "need.event.obligation_expiry",
        DemandCategory.EVENT,
        "vencimento/validade",
        "event.obligation",
        None,
        ("vence", "vencimento", "habilitação vence"),
    ),
    "need.event.recurring_bill": SemanticNeed(
        "need.event.recurring_bill",
        DemandCategory.EVENT,
        "conta recorrente",
        "event.recurring_bill",
        "event.obligation",
        ("internet", "assinatura"),
    ),
    "need.event.service_cancel": SemanticNeed(
        "need.event.service_cancel",
        DemandCategory.EVENT,
        "cancelamento de serviço",
        None,
        "event.obligation",
        ("cancelei a internet",),
    ),
    "need.event.education": SemanticNeed(
        "need.event.education",
        DemandCategory.EVENT,
        "curso/educação",
        None,
        "event.appointment",
        ("curso de espanhol",),
    ),
    "need.event.health_vaccination": SemanticNeed(
        "need.event.health_vaccination",
        DemandCategory.EVENT,
        "vacinação",
        None,
        "event.appointment",
        ("dose da vacina", "vacina"),
    ),
    "need.event.health_visit": SemanticNeed(
        "need.event.health_visit",
        DemandCategory.EVENT,
        "consulta médica",
        "event.appointment",
        None,
        ("cardiologista",),
    ),
    "need.event.lend": SemanticNeed(
        "need.event.lend",
        DemandCategory.EVENT,
        "transação de empréstimo",
        None,
        "event.payment",
        ("emprestei", "deve"),
    ),
    # Entities
    "need.entity.appliance": SemanticNeed(
        "need.entity.appliance",
        DemandCategory.ENTITY,
        "eletrodoméstico/equipamento",
        None,
        "entity.vehicle",
        ("geladeira", "máquina de lavar", "notebook", "ar-condicionado"),
    ),
    "need.entity.home_component": SemanticNeed(
        "need.entity.home_component",
        DemandCategory.ENTITY,
        "componente doméstico",
        None,
        None,
        ("chuveiro", "resistência", "embreagem"),
    ),
    "need.entity.person": SemanticNeed(
        "need.entity.person",
        DemandCategory.ENTITY,
        "pessoa",
        "entity.person",
        None,
        ("joão", "mariana", "pedro", "mel"),
    ),
    "need.entity.organization": SemanticNeed(
        "need.entity.organization",
        DemandCategory.ENTITY,
        "organização",
        "entity.organization",
        None,
        ("acme",),
    ),
    "need.entity.document": SemanticNeed(
        "need.entity.document",
        DemandCategory.ENTITY,
        "documento oficial",
        None,
        None,
        ("cnh", "passaporte", "habilitação"),
    ),
    "need.entity.vehicle": SemanticNeed(
        "need.entity.vehicle",
        DemandCategory.ENTITY,
        "veículo",
        "entity.automobile",
        "entity.vehicle",
        ("corolla", "carro"),
    ),
    "need.entity.place": SemanticNeed(
        "need.entity.place",
        DemandCategory.ENTITY,
        "local/lugar",
        None,
        None,
        ("recife", "fortaleza", "quarto"),
    ),
    "need.entity.product": SemanticNeed(
        "need.entity.product",
        DemandCategory.ENTITY,
        "produto consumível",
        None,
        None,
        ("filtros de café", "detergente"),
    ),
    # States
    "need.state.anomaly": SemanticNeed(
        "need.state.anomaly",
        DemandCategory.STATE,
        "estado anômalo",
        None,
        None,
        ("barulho estranho", "desligando"),
        representation_note="STATE não modelado no wire IR",
    ),
    "need.state.depletion": SemanticNeed(
        "need.state.depletion",
        DemandCategory.STATE,
        "esgotamento/necessidade",
        None,
        None,
        ("acabou detergente",),
        representation_note="STATE não modelado no wire IR",
    ),
    "need.state.unpaid": SemanticNeed(
        "need.state.unpaid",
        DemandCategory.STATE,
        "obrigação não quitada",
        None,
        "event.obligation",
        ("não foi paga",),
        representation_note="negação + estado; IR limitada",
    ),
    # Relations
    "need.relation.employment": SemanticNeed(
        "need.relation.employment",
        DemandCategory.RELATION,
        "vínculo empregatício encerrado",
        None,
        "relation.provided_by",
        ("não trabalha mais", "trabalha na"),
        representation_note="relation.employment ausente no CORE",
    ),
    "need.relation.cohabitation": SemanticNeed(
        "need.relation.cohabitation",
        DemandCategory.RELATION,
        "início de coabitação",
        None,
        None,
        ("morar comigo",),
        representation_note="relation residência ausente",
    ),
    "need.relation.debt": SemanticNeed(
        "need.relation.debt",
        DemandCategory.RELATION,
        "dívida entre pessoas",
        None,
        "relation.owns",
        ("deve", "emprestei"),
        representation_note="direção credor/devedor não modelada",
    ),
    # Attributes
    "need.attr.amount": SemanticNeed(
        "need.attr.amount",
        DemandCategory.ATTRIBUTE,
        "valor monetário",
        "attribute.amount",
        None,
        ("reais", "conto", "180", "500"),
    ),
    "need.attr.quantity": SemanticNeed(
        "need.attr.quantity",
        DemandCategory.ATTRIBUTE,
        "quantidade",
        None,
        None,
        ("três", "3"),
        representation_note="attribute.quantity ausente no CORE",
    ),
    "need.attr.expiry": SemanticNeed(
        "need.attr.expiry",
        DemandCategory.ATTRIBUTE,
        "data de validade",
        None,
        None,
        ("vence em novembro",),
        representation_note="validade como atributo vs obligation",
    ),
    # Domains
    "need.domain.home": SemanticNeed("need.domain.home", DemandCategory.DOMAIN, "casa", "domain.home", None, ()),
    "need.domain.health": SemanticNeed("need.domain.health", DemandCategory.DOMAIN, "saúde", "domain.health", None, ()),
    "need.domain.finance": SemanticNeed("need.domain.finance", DemandCategory.DOMAIN, "finanças", "domain.finance", None, ()),
    "need.domain.travel": SemanticNeed("need.domain.travel", DemandCategory.DOMAIN, "viagem", None, None, ("viagem", "hotel")),
    "need.domain.education": SemanticNeed("need.domain.education", DemandCategory.DOMAIN, "educação", None, None, ("curso", "prova")),
    "need.domain.shopping": SemanticNeed("need.domain.shopping", DemandCategory.DOMAIN, "compras", "domain.shopping", None, ()),
    "need.domain.services": SemanticNeed("need.domain.services", DemandCategory.DOMAIN, "serviços", "domain.services", None, ()),
    "need.domain.vehicle": SemanticNeed("need.domain.vehicle", DemandCategory.DOMAIN, "veículos", "domain.vehicle", None, ()),
}

# Demanda por caso development (referencia need_ids).
CASE_SEMANTIC_DEMAND: dict[str, tuple[str, ...]] = {
    "HOME_001": ("need.event.anomaly", "need.state.anomaly", "need.entity.appliance", "need.domain.home"),
    "HOME_002": ("need.action.replace", "need.event.maintenance", "need.entity.home_component", "need.domain.home"),
    "HOME_003": ("need.action.install", "need.event.installation", "need.entity.appliance", "need.domain.home"),
    "PEOPLE_001": ("need.entity.person", "need.entity.organization", "need.relation.employment"),
    "PEOPLE_002": ("need.entity.person", "need.action.start", "need.relation.cohabitation"),
    "PEOPLE_003": ("need.action.lend", "need.event.lend", "need.entity.person", "need.attr.amount", "need.domain.finance"),
    "DOC_001": ("need.entity.document", "need.event.obligation_expiry", "need.attr.expiry"),
    "DOC_002": ("need.action.renew", "need.entity.document"),
    "EDU_001": ("need.event.education", "need.action.start", "need.domain.education"),
    "EDU_002": ("need.event.appointment", "need.domain.education"),
    "HEALTH_001": ("need.event.health_vaccination", "need.entity.person"),
    "HEALTH_002": ("need.event.health_visit", "need.action.attend", "need.domain.health"),
    "SHOP_001": ("need.action.buy", "need.event.purchase", "need.attr.quantity", "need.domain.shopping"),
    "SHOP_002": ("need.state.depletion", "need.entity.product", "need.domain.shopping"),
    "SVC_001": ("need.action.repair", "need.event.maintenance", "need.entity.appliance", "need.attr.amount"),
    "SVC_002": ("need.action.cancel", "need.event.service_cancel", "need.event.recurring_bill", "need.domain.services"),
    "TRAVEL_001": ("need.action.reserve", "need.event.reservation", "need.entity.place", "need.domain.travel"),
    "TRAVEL_002": ("need.action.return_trip", "need.event.travel", "need.entity.place", "need.domain.travel"),
    "COLL_001": ("need.state.anomaly", "need.entity.appliance"),
    "COLL_002": ("need.action.lend", "need.attr.amount", "need.entity.person", "need.domain.finance"),
    "NEG_001": ("need.entity.vehicle", "need.domain.vehicle"),
    "NEG_002": ("need.state.unpaid", "need.domain.finance"),
    "UNC_001": ("need.action.pay", "need.attr.amount", "need.domain.finance"),
    "UNC_002": ("need.event.appointment",),
    "UNC_003": ("need.entity.person",),
    "EQUIV_G1": ("need.action.replace", "need.event.vehicle_maintenance", "need.entity.vehicle"),
    "EQUIV_G2": ("need.action.return_item",),
    "EQUIV_G3": ("need.action.install", "need.event.installation"),
    "EQUIV_G4": ("need.action.cancel", "need.event.service_cancel"),
    "EQUIV_G5": ("need.action.reserve", "need.event.reservation"),
    "CTX_FRIDGE_04": ("need.attr.amount", "need.event.maintenance"),
}

POLYSEMOUS_EXPRESSIONS: tuple[dict[str, str], ...] = (
    {
        "surface": "trocar",
        "senses": "action.replace (embreagem) | mudança emprego | câmbio monetário",
        "benchmark_examples": "EQUIV_G1 vs (não no dev) troca emprego/moeda",
    },
    {
        "surface": "vencer",
        "senses": "obligation_expiry (CNH) | recurring_bill | prazo de prova",
        "benchmark_examples": "DOC_001, COLL_003 (holdout-like)",
    },
    {
        "surface": "ficou",
        "senses": "valor monetário (250 reais) | agendamento (prova sexta)",
        "benchmark_examples": "CTX_FRIDGE_04, EDU_002",
    },
)
