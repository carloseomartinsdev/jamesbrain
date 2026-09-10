"""Prompt v3 — semantic proposal wire (I11.6 / I11.7 reliability)."""

from __future__ import annotations

import json
from typing import Any

from pke.interpretation.interpreter import InterpretationContext
from pke.interpretation.ontology_view import InterpreterOntologyView
from pke.llm.models import LlmMessage

PROMPT_VERSION = "pke.interpret.v3"

SYSTEM_PROMPT = """Você é um parser semântico do Personal Knowledge Engine (PKE).

Você NÃO responde ao usuário.
Você NÃO persiste conhecimento.
Você produz uma PROPOSTA SEMÂNTICA — não IR canônico.

Responda com UM ÚNICO objeto JSON. Sem markdown. Sem texto antes ou depois.

Envelope obrigatório:
{"ir_kind":"semantic_proposal"|"semantic_query","ir":{...}}

Princípios:
- Descreva SIGNIFICADO. Não adivinhe keys canônicas (relation.employed_by, action.replace).
- Use expressões naturais: relation_expression, state_expression, action_expression.
- Use kind_hint em entidades: person|organization|place|appliance|vehicle|document|medication|thing.
- Omita campos desconhecidos ou use null — não invente fatos.
- Proposta parcial honesta é melhor que certeza fabricada.

Sinais semânticos (marque quando evidentes):
- change_semantics: algo aconteceu/mudou (quebrou, abriu, troquei)
- condition_semantics: condição persistente (está quebrada, está aberta)
- link_semantics: vínculo entre entidades (trabalha em, casado com)
- stable_property_semantics: propriedade descritiva (é prata, tem 200 m²)
- classification_semantics: classificação/tipo da entidade (é um carro, é um cachorro)

Campos mínimos por tipo (primitive_hint é opcional se sinais bastarem):
- RELATION: subject + object + link_semantics + relation_expression
- STATE: subject + condition_semantics + state_expression
- EVENT: change_semantics + (action_expression ou event_expression)
- ATTRIBUTE: subject + stable_property_semantics + attribute_expression
- TYPE: subject + classification_semantics (+ attribute_expression com rótulo de classe se útil)

Distinções:
- "está quebrada" → condition_semantics, state_expression
- "quebrou" → change_semantics, event_expression
- "trabalha na Acme" → link_semantics, subject person, object organization
- "é prata" → stable_property_semantics, attribute_expression (NÃO classification)
- "é um carro" → classification_semantics (NÃO Attribute)
- "é médica" / marca / PDF → analise: occupation/relation, brand, document type — não force Attribute

Polysemia:
- "troquei ideia" → NÃO é replace físico
- Não marque change_semantics de componente físico sem evidência

Tempo: temporal.original_text e occurrence_aspect quando evidente.
Consultas → ir_kind=semantic_query.
"""

PROPOSAL_SHAPE = """
semantic_proposal ir:
  raw_input (obrigatório)
  utterance_kind?, primitive_hint? (opcional)
  subject?, object?, participants[], entities_mentioned[]
  action_expression?, relation_expression?, state_expression?, attribute_expression?, event_expression?
  temporal: {original_text, occurrence_aspect?, relative_day?, ...}
  change_semantics, condition_semantics, link_semantics, stable_property_semantics (bool, default false)
  lifecycle_cue?, negation?, domain_hints[], confidence?

semantic_query ir (mesma gramática conceitual que semantic_proposal + utterance_kind=query):
  raw_input (obrigatório)
  primitive_hint?, subject?, object?, participants[], entities_mentioned[]
  action_expression?, relation_expression?, state_expression?, event_expression?
  temporal: {original_text, occurrence_aspect?, partial_month?, partial_year?, ...}
  change_semantics?, condition_semantics?, link_semantics?
  query_kind legado (list|state|relation) — omitir quando campos semânticos bastarem
"""

FEW_SHOT_STATE = {
    "ir_kind": "semantic_proposal",
    "ir": {
        "raw_input": "A geladeira está quebrada.",
        "utterance_kind": "assert",
        "subject": {"text": "geladeira", "kind_hint": "appliance"},
        "state_expression": "broken",
        "condition_semantics": True,
        "temporal": {"original_text": "", "occurrence_aspect": "ongoing"},
    },
}

FEW_SHOT_EVENT = {
    "ir_kind": "semantic_proposal",
    "ir": {
        "raw_input": "A geladeira quebrou.",
        "utterance_kind": "assert",
        "subject": {"text": "geladeira", "kind_hint": "appliance"},
        "event_expression": "broke",
        "change_semantics": True,
        "temporal": {"original_text": "", "occurrence_aspect": "happened"},
    },
}

FEW_SHOT_RELATION = {
    "ir_kind": "semantic_proposal",
    "ir": {
        "raw_input": "João trabalha na Acme.",
        "utterance_kind": "assert",
        "subject": {"text": "João", "kind_hint": "person"},
        "object": {"text": "Acme", "kind_hint": "organization"},
        "relation_expression": "works at",
        "link_semantics": True,
        "temporal": {"original_text": "", "occurrence_aspect": "ongoing"},
    },
}

FEW_SHOT_PARTIAL = {
    "ir_kind": "semantic_proposal",
    "ir": {
        "raw_input": "O técnico instalou o ar-condicionado.",
        "subject": {"text": "técnico", "kind_hint": "person"},
        "object": {"text": "ar-condicionado", "kind_hint": "appliance"},
        "action_expression": "instalou",
        "change_semantics": True,
        "temporal": {"original_text": "", "occurrence_aspect": "happened"},
    },
}


def build_messages(
    raw: str,
    ctx: InterpretationContext,
    ontology: InterpreterOntologyView,
    *,
    schema: dict[str, Any] | None = None,
) -> list[LlmMessage]:
    _ = schema
    now = ctx.user.now.isoformat() if ctx.user.now is not None else None
    context = {
        "prompt_version": PROMPT_VERSION,
        "locale": ctx.user.locale,
        "timezone": ctx.user.timezone,
        "reference_at": now,
        "entity_kind_hints": list(
            "person organization place appliance vehicle document medication thing".split()
        ),
        "examples": {
            "state": FEW_SHOT_STATE,
            "event": FEW_SHOT_EVENT,
            "relation": FEW_SHOT_RELATION,
            "partial_unknown_concept": FEW_SHOT_PARTIAL,
        },
        "note": "JSON only. No canonical keys. Partial proposals OK.",
    }
    _ = ontology.compact_grouped()
    system = SYSTEM_PROMPT + PROPOSAL_SHAPE
    user = (
        "Contexto operacional:\n"
        f"{json.dumps(context, ensure_ascii=False, default=str)}\n\n"
        "USER_CONTENT_FOLLOWS:\n"
        f"{raw}"
    )
    return [
        LlmMessage(role="system", content=system),
        LlmMessage(role="user", content=user),
    ]
