"""Schema wire compacto para o prompt. Pydantic canônico permanece autoridade."""

from __future__ import annotations

WIRE_SCHEMA_HINT = {
    "type": "object",
    "required": ["ir_kind", "ir"],
    "properties": {
        "ir_kind": {"enum": ["ingest", "query"]},
        "ir": {"type": "object"},
    },
}

WIRE_SHAPE = """
Envelope: {"ir_kind":"ingest|query","ir":{...}}

Ingest ir:
  intent: record_event|record_state|record_relation|record_obligation|correct|...
  raw_input, domains[], entities_mentioned[], event?, state?, relation?, obligation?, correction?
  EntityMention: {text, entity_type?, role?, reference_kind?, confidence?}
    entity_type: ONLY entity_types keys (never event/action/domain)
  WireIrTime: {original_text, relative_day?, weekday?: monday|tuesday|...|sunday, weekday_policy?, time_of_day?:"HH:MM"}
  WireIrFact: {attribute, money:{amount:number, currency}, qualifier, epistemic_status, confidence}
  event: {type, action?, status, time, participants[], facts[]}
  relation: {type, subject:EntityMention, object:EntityMention, mode?, time?}
  obligation: {type, cadence:{freq, by_monthday}, facts[]}
  correction: {strategy, facts[]}  (intent=correct)

Query ir:
  intent:"query", raw_input, query:{
    intent:list|aggregate, entities[], entity_association?, event_types[], facts[],
    aggregate, version_policy, currency?, time?:{relative_period, original_text?}
  }
"""

FEW_SHOT_INGEST = {
    "ir_kind": "ingest",
    "ir": {
        "intent": "record_event",
        "raw_input": "Troquei o óleo hoje por 320 reais.",
        "domains": ["domain.vehicle"],
        "entities_mentioned": [{"text": "Corolla", "entity_type": "entity.automobile", "role": "role.subject"}],
        "event": {
            "type": "event.vehicle_maintenance",
            "action": "action.oil_change",
            "status": "completed",
            "time": {"original_text": "hoje", "relative_day": "today"},
            "facts": [
                {
                    "attribute": "attribute.amount",
                    "money": {"amount": 320, "currency": "BRL"},
                    "qualifier": "exact",
                    "epistemic_status": "explicit",
                    "confidence": 1.0,
                }
            ],
        },
    },
}

FEW_SHOT_QUERY = {
    "ir_kind": "query",
    "ir": {
        "intent": "query",
        "raw_input": "Quanto gastei este mês?",
        "query": {
            "intent": "aggregate",
            "entities": [{"text": "Corolla", "entity_type": "entity.automobile"}],
            "entity_association": "subject",
            "event_types": ["event.vehicle_maintenance"],
            "facts": ["attribute.amount"],
            "aggregate": "sum",
            "version_policy": "current",
            "time": {"relative_period": "this_month", "original_text": "este mês"},
        },
    },
}

FEW_SHOT_OBLIGATION = {
    "ir_kind": "ingest",
    "ir": {
        "intent": "record_obligation",
        "raw_input": "A internet vence todo dia 10 e é 129,90.",
        "obligation": {
            "type": "event.recurring_bill",
            "cadence": {"freq": "monthly", "by_monthday": 10},
            "facts": [
                {
                    "attribute": "attribute.amount",
                    "money": {"amount": 129.9, "currency": "BRL"},
                    "qualifier": "exact",
                    "epistemic_status": "explicit",
                    "confidence": 1.0,
                }
            ],
        },
    },
}

FEW_SHOT_CORRECTION = {
    "ir_kind": "ingest",
    "ir": {
        "intent": "correct",
        "raw_input": "Não, achei a nota. Foi 186,50.",
        "correction": {
            "strategy": "last_event",
            "facts": [
                {
                    "attribute": "attribute.amount",
                    "money": {"amount": 186.5, "currency": "BRL"},
                    "qualifier": "exact",
                    "epistemic_status": "explicit",
                    "confidence": 1.0,
                }
            ],
        },
    },
}
