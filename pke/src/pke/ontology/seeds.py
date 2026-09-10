"""Catálogo CORE mínimo para os casos A–F. IDs estáveis: `core:{key}`."""

from __future__ import annotations

from datetime import UTC, datetime

from pke.domain.ontology import (
    ConceptKind,
    ConceptPresentation,
    ConceptScope,
    OntologyConcept,
)

CORE_SCHEMA_VERSION = "1"
CORE_ID_PREFIX = "core:"
CORE_CREATED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def core_concept_id(key: str) -> str:
    """ID determinístico do CORE. Não é ULID; a estabilidade vem da chave."""
    return f"{CORE_ID_PREFIX}{key}"


class CoreSeed:
    __slots__ = ("key", "kind", "parent_key", "label")

    def __init__(
        self,
        key: str,
        kind: ConceptKind,
        *,
        parent_key: str | None = None,
        label: str | None = None,
    ) -> None:
        self.key = key
        self.kind = kind
        self.parent_key = parent_key
        self.label = label

    def to_concept(self) -> OntologyConcept:
        presentation = ConceptPresentation(label=self.label) if self.label else None
        return OntologyConcept(
            id=core_concept_id(self.key),
            key=self.key,
            kind=self.kind,
            scope=ConceptScope.CORE,
            parent_id=core_concept_id(self.parent_key) if self.parent_key else None,
            created_at=CORE_CREATED_AT,
            presentation=presentation,
        )


# Pais devem aparecer antes dos filhos.
CORE_SEEDS: tuple[CoreSeed, ...] = (
    CoreSeed("entity.person", ConceptKind.ENTITY_TYPE, label="Pessoa"),
    CoreSeed("entity.vehicle", ConceptKind.ENTITY_TYPE, label="Veículo"),
    CoreSeed(
        "entity.automobile",
        ConceptKind.ENTITY_TYPE,
        parent_key="entity.vehicle",
        label="Automóvel",
    ),
    CoreSeed("entity.organization", ConceptKind.ENTITY_TYPE, label="Organização"),
    CoreSeed("entity.place", ConceptKind.ENTITY_TYPE, label="Local"),
    CoreSeed("entity.home", ConceptKind.ENTITY_TYPE, label="Item doméstico"),
    CoreSeed(
        "entity.appliance",
        ConceptKind.ENTITY_TYPE,
        parent_key="entity.home",
        label="Eletrodoméstico",
    ),
    CoreSeed("entity.document", ConceptKind.ENTITY_TYPE, label="Documento"),
    CoreSeed("entity.medication", ConceptKind.ENTITY_TYPE, label="Medicamento"),
    CoreSeed("entity.thing", ConceptKind.ENTITY_TYPE, label="Coisa"),
    CoreSeed("state.dimension", ConceptKind.STATE_DIMENSION, label="Dimensão de estado"),
    CoreSeed(
        "state.operational_condition",
        ConceptKind.STATE_DIMENSION,
        parent_key="state.dimension",
        label="Condição operacional",
    ),
    CoreSeed(
        "state.availability",
        ConceptKind.STATE_DIMENSION,
        parent_key="state.dimension",
        label="Disponibilidade",
    ),
    CoreSeed(
        "state.payment_status",
        ConceptKind.STATE_DIMENSION,
        parent_key="state.dimension",
        label="Status de pagamento",
    ),
    CoreSeed(
        "state.due_status",
        ConceptKind.STATE_DIMENSION,
        parent_key="state.dimension",
        label="Status de vencimento",
    ),
    CoreSeed(
        "state.openness",
        ConceptKind.STATE_DIMENSION,
        parent_key="state.dimension",
        label="Abertura",
    ),
    CoreSeed(
        "state.validity",
        ConceptKind.STATE_DIMENSION,
        parent_key="state.dimension",
        label="Validade",
    ),
    CoreSeed(
        "state.observed_quantity",
        ConceptKind.STATE_DIMENSION,
        parent_key="state.dimension",
        label="Quantidade observada (provisório)",
    ),
    CoreSeed("state.value.broken", ConceptKind.STATE_VALUE, parent_key="state.operational_condition", label="Quebrado"),
    CoreSeed("state.value.working", ConceptKind.STATE_VALUE, parent_key="state.operational_condition", label="Funcionando"),
    CoreSeed("state.value.depleted", ConceptKind.STATE_VALUE, parent_key="state.availability", label="Esgotado"),
    CoreSeed("state.value.unpaid", ConceptKind.STATE_VALUE, parent_key="state.payment_status", label="Não pago"),
    CoreSeed("state.value.overdue", ConceptKind.STATE_VALUE, parent_key="state.due_status", label="Atrasado"),
    CoreSeed("state.value.open", ConceptKind.STATE_VALUE, parent_key="state.openness", label="Aberto"),
    CoreSeed("state.value.closed", ConceptKind.STATE_VALUE, parent_key="state.openness", label="Fechado"),
    CoreSeed("state.value.valid", ConceptKind.STATE_VALUE, parent_key="state.validity", label="Válido"),
    CoreSeed("state.value.expired", ConceptKind.STATE_VALUE, parent_key="state.validity", label="Vencido"),
    CoreSeed(
        "state.value.quantity_observation",
        ConceptKind.STATE_VALUE,
        parent_key="state.observed_quantity",
        label="Observação quantitativa",
    ),
    CoreSeed("event.maintenance", ConceptKind.EVENT_TYPE, label="Manutenção"),
    CoreSeed(
        "event.vehicle_maintenance",
        ConceptKind.EVENT_TYPE,
        parent_key="event.maintenance",
        label="Manutenção veicular",
    ),
    CoreSeed("event.appointment", ConceptKind.EVENT_TYPE, label="Consulta"),
    CoreSeed("event.obligation", ConceptKind.EVENT_TYPE, label="Obrigação"),
    CoreSeed(
        "event.recurring_bill",
        ConceptKind.EVENT_TYPE,
        parent_key="event.obligation",
        label="Conta recorrente",
    ),
    CoreSeed("event.payment", ConceptKind.EVENT_TYPE, label="Pagamento"),
    CoreSeed("event.purchase", ConceptKind.EVENT_TYPE, label="Compra"),
    CoreSeed("event.intent", ConceptKind.EVENT_TYPE, label="Intenção"),
    CoreSeed("action.maintain", ConceptKind.ACTION, label="Manter"),
    CoreSeed(
        "action.oil_change",
        ConceptKind.ACTION,
        parent_key="action.maintain",
        label="Troca de óleo",
    ),
    CoreSeed(
        "action.replace",
        ConceptKind.ACTION,
        parent_key="action.maintain",
        label="Trocar",
    ),
    CoreSeed("action.attend", ConceptKind.ACTION, label="Comparecer"),
    CoreSeed("action.pay", ConceptKind.ACTION, label="Pagar"),
    CoreSeed("action.buy", ConceptKind.ACTION, label="Comprar"),
    CoreSeed("action.install", ConceptKind.ACTION, label="Instalar"),
    CoreSeed("relation.employed_by", ConceptKind.RELATION_TYPE, label="Empregado por"),
    CoreSeed("relation.resides_at", ConceptKind.RELATION_TYPE, label="Reside em"),
    CoreSeed("relation.owns", ConceptKind.RELATION_TYPE, label="Possui"),
    CoreSeed("relation.likes", ConceptKind.RELATION_TYPE, label="Gosta de"),
    CoreSeed("relation.married_to", ConceptKind.RELATION_TYPE, label="Casado com"),
    CoreSeed("relation.parent_of", ConceptKind.RELATION_TYPE, label="Pai/mãe de"),
    CoreSeed("relation.provider_for", ConceptKind.RELATION_TYPE, label="Prestador para"),
    CoreSeed("attribute.amount", ConceptKind.ATTRIBUTE, label="Valor"),
    CoreSeed("attribute.mileage", ConceptKind.ATTRIBUTE, label="Quilometragem"),
    CoreSeed(
        "attribute.maintenance_type",
        ConceptKind.ATTRIBUTE,
        label="Tipo de manutenção",
    ),
    CoreSeed("domain.vehicle", ConceptKind.DOMAIN, label="Veículos"),
    CoreSeed("domain.finance", ConceptKind.DOMAIN, label="Finanças"),
    CoreSeed("domain.health", ConceptKind.DOMAIN, label="Saúde"),
    CoreSeed("domain.appointments", ConceptKind.DOMAIN, label="Agenda"),
    CoreSeed("domain.home", ConceptKind.DOMAIN, label="Casa"),
    CoreSeed("domain.shopping", ConceptKind.DOMAIN, label="Compras"),
    CoreSeed("domain.services", ConceptKind.DOMAIN, label="Serviços"),
    CoreSeed("role.actor", ConceptKind.ROLE, label="Autor"),
    CoreSeed("role.subject", ConceptKind.ROLE, label="Sujeito"),
    CoreSeed("role.object", ConceptKind.ROLE, label="Objeto"),
    CoreSeed("role.patient", ConceptKind.ROLE, label="Entidade afetada"),
    CoreSeed("role.context", ConceptKind.ROLE, label="Contexto"),
    CoreSeed("role.unspecified", ConceptKind.ROLE, label="Papel não especificado"),
    CoreSeed("role.provider", ConceptKind.ROLE, label="Prestador"),
)
