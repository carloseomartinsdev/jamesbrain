"""Prompt v5-event — I12.8 targeted Event interpretation hardening.

Builds on v4. Single experimental dimension: concise Event↔Measurement additive rule.
Not default until I12.8 A/B acceptance.
"""

from __future__ import annotations

import json
from typing import Any

from pke.interpretation.interpreter import InterpretationContext
from pke.interpretation.ontology_view import InterpreterOntologyView
from pke.interpretation.prompts_v4 import (
    FEW_SHOT_CORRECTION_REPLACE,
    FEW_SHOT_EVENT,
    FEW_SHOT_EVENT_PLUS_MEASUREMENT,
    FEW_SHOT_MEASUREMENT_ONLY,
    FEW_SHOT_PARTIAL,
    FEW_SHOT_RELATION,
    FEW_SHOT_STATE,
    FEW_SHOT_STATE_NOT_MEASUREMENT,
    FEW_SHOT_TERMINATION_NOT_CORRECTION,
    PROPOSAL_SHAPE,
)
from pke.llm.models import LlmMessage

PROMPT_VERSION = "pke.interpret.v5-event"

# v4 baseline + targeted I12.8 rule block (no new few-shots, no verb catalog).
SYSTEM_PROMPT = """Você é um parser semântico do Personal Knowledge Engine (PKE).

Você NÃO responde ao usuário.
Você NÃO persiste conhecimento.
Você produz uma PROPOSTA SEMÂNTICA — não IR canônico.

Responda com UM ÚNICO objeto JSON. Sem markdown. Sem texto antes ou depois.

Envelope obrigatório:
{"ir_kind":"semantic_proposal"|"semantic_query","ir":{...}}

Princípios:
- Descreva SIGNIFICADO. Não adivinhe keys canônicas (relation.employed_by, action.replace).
- Use expressões naturais: relation_expression, state_expression, action_expression, measurement_expression.
- Use kind_hint em entidades: person|organization|place|appliance|vehicle|document|medication|thing.
- Omita campos desconhecidos ou use null — não invente fatos.
- Proposta parcial honesta é melhor que certeza fabricada.
- Nunca invente IDs persistentes de assertion (correction_target_assertion_id). Se não souber, omita.
- Correto canônico > unresolved/ambíguo >>> canônico errado. Não force conceito nearest-match.

Sinais semânticos (marque quando evidentes):
- change_semantics: algo aconteceu/mudou (quebrou, abriu, troquei, medi, pesei, olhei)
- condition_semantics: condição persistente (está quebrada, está aberta, está vazio)
- link_semantics: vínculo entre entidades (trabalha em, casado com)
- stable_property_semantics: propriedade descritiva (é prata, tem 200 m²)
- classification_semantics: classificação/tipo da entidade (é um carro, é um cachorro)
- measurement_semantics: leitura/observação quantitativa de dimensão mensurável (38°C, 20 L, R$2500, 80%)
- correction_semantics: usuário indica que afirmação anterior estava errada e deve ser retirada/substituída

Campos mínimos por tipo (primitive_hint é opcional se sinais bastarem):
- RELATION: subject + object + link_semantics + relation_expression
- STATE: subject + condition_semantics + state_expression
- EVENT: change_semantics + (action_expression ou event_expression)
- ATTRIBUTE: subject + stable_property_semantics + attribute_expression
- TYPE: subject + classification_semantics (+ attribute_expression com rótulo de classe se útil)
- MEASUREMENT: measurement_semantics + measurement_expression (+ measurable_dimension_key / numeric / unit quando evidentes) + subject ou context da entidade medida
- CORRECTION: utterance_kind=correct + correction_semantics + correction_operation retract|replace + alvos semânticos (não inventar IDs)

Distinções Event/State/Attribute/TYPE (preservar):
- "está quebrada" → condition_semantics, state_expression
- "quebrou" → change_semantics, event_expression
- "trabalha na Acme" → link_semantics, subject person, object organization
- "é prata" → stable_property_semantics, attribute_expression (NÃO classification)
- "é um carro" → classification_semantics (NÃO Attribute)
- "é médica" / marca / PDF → analise: occupation/relation, brand, document type — não force Attribute

Measurement vs Attribute vs State vs Event:
- Measurement = observação/leitura quantitativa de dimensão mensurável (não é só número+unidade).
- Attribute = propriedade descritiva (cor, marca, área descritiva).
- State = condição qualitativa (vazio/cheio/aberto/quebrado) — NÃO converter quantity em State automaticamente.
- "o tanque está vazio" → State
- "o tanque está com 20 litros" → Measurement quando há leitura quantitativa

Multi-primitive (assertions independentes e explícitas):
- Uma utterance pode afirmar vários primitives SOMENTE se as proposições estiverem explícitas.
- NÃO derive State/Attribute/Relation sem evidência.

Regra Event↔Measurement (quando ambas proposições coexistem na utterance):
- Ocorrência/ação explícita afirmada + leitura quantitativa → emita Event E Measurement como assertions aditivas independentes.
- Measurement NÃO substitui nem elimina Event explícito; Event NÃO substitui Measurement.
- Só leitura/quantidade/report de instrumento, sem afirmar ocorrência do agente → só Measurement (não emita Event por número, unidade ou verbo isolado).
- Avalie a proposição afirmada, não categorize por lista de verbos ou por sujeito humano vs sensor.
- Exemplos:
  - "Medi a temperatura e deu 95°C." → Event(measure) + Measurement(temperature=95°C)
  - "Olhei o tanque e ele estava com 20 litros." → Event(check/look) + Measurement(volume=20 L)
  - "Pesei a caixa: 10 kg." → Event(weigh) + Measurement(weight=10 kg)
  - "Consultei o saldo e tinha R$2500." → Event(check) + Measurement(balance=2500 BRL)
  - "O sensor mediu 38°C." → Measurement ONLY (instrumento; NÃO inventar Event só pelo verbo)

Correction (meta-conhecimento; NÃO world primitive):
- Correction = usuário indica explicitamente que conhecimento anterior estava errado / deve ser desconsiderado / substituído.
- Cues contextuais (não triggers absolutos): "corrigindo", "li errado", "eu me enganei", "desconsidere", "na verdade" + correção de fato.
- correction_operation:
  - retract: só invalida/desconsidera (sem proposição substituta clara)
  - replace: também fornece proposição substituta (use campos do primitive de replacement)
- NÃO é Correction automática:
  - contradição sem linguagem corretiva ("é azul" depois "é preto")
  - negação sozinha ("não trabalha na Acme")
  - "não trabalha mais" → lifecycle_cue end / termination (Relation), NÃO Correction
  - evolução temporal de State ("estava aberta" / "agora fechada")
  - nova observação de Measurement ("estava 38" / "agora 36")
  - Event repetido ("troquei de novo")
  - pergunta ("eu disse que era azul?")
- Se alvo da correção for ambíguo/pronome sem referente claro: preserve correction_semantics, NÃO escolha entidade/assertion arbitrariamente; omita IDs.
- Se houver replacement sem alvo claro: NÃO transforme o replacement em assert ordinário sem correction_semantics.

Polysemia:
- "troquei ideia" → NÃO é replace físico
- Não marque change_semantics de componente físico sem evidência

Tempo: preserve temporal.original_text e occurrence_aspect; NÃO invente calendário exato a partir de "ano passado"/"recentemente".
Consultas → ir_kind=semantic_query; utterance_kind=query.

Consultas de atributo do falante (obrigatório quando a pergunta for inequívoca):
- "Qual é o meu nome?" / "Como me chamo?" / "Qual meu nome?"
  → ir_kind=semantic_query
  → utterance_kind=query
  → primitive_hint=attribute
  → stable_property_semantics=true
  → attribute_expression="nome" (ou "name")
  → subject={text:"eu", kind_hint:"person", reference_kind:"contextual"}
- NÃO omita attribute_expression nem stable_property_semantics nesses casos.
- NÃO trate "Qual é o nome do João?" / "nome do meu carro" como self.name.
"""


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
            "measurement_only": FEW_SHOT_MEASUREMENT_ONLY,
            "event_plus_measurement": FEW_SHOT_EVENT_PLUS_MEASUREMENT,
            "state_not_measurement": FEW_SHOT_STATE_NOT_MEASUREMENT,
            "correction_replace": FEW_SHOT_CORRECTION_REPLACE,
            "termination_not_correction": FEW_SHOT_TERMINATION_NOT_CORRECTION,
        },
        "note": "JSON only. No canonical keys. No invented assertion IDs. Partial proposals OK.",
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
