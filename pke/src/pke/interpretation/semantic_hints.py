"""Dicas semânticas para o Interpreter — não altera CORE seeds."""

from __future__ import annotations

SEMANTIC_HINTS: dict[str, str] = {
    "event.vehicle_maintenance": "manutenção/gastos realizados em veículo",
    "event.payment": "ato de pagamento; não cobre todo gasto monetário genérico",
    "event.appointment": "compromisso agendado (consulta, reunião)",
    "event.recurring_bill": "conta recorrente (internet, assinatura)",
    "entity.automobile": "automóvel individual identificável",
    "entity.thing": "coisa ou item identificável (não veículo)",
    "entity.person": "pessoa individual identificável",
    "relation.likes": "pessoa gosta de alguém ou algo",
    "entity.organization": "organização/empresa identificável",
    "attribute.amount": "valor monetário de um fato",
    "role.provider": "prestador do serviço (médico, oficina)",
    "role.subject": "sujeito do evento (veículo, paciente)",
}
