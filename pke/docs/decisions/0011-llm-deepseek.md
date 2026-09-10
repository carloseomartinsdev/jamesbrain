# 0011 — LLM Provider + DeepSeekInterpreter (Wave 2 / I10)

## Princípios

- LLM interpreta. PKE raciocina. Storage persiste.
- Saída do LLM é proposta, não conhecimento.

## TLS no Windows

`truststore` usa o store do SO (inclui CA corporativa).
Sem `verify=False`. Falha de issuer no certifi puro não é
desligar TLS — é usar as âncoras do sistema.

## Decisão HTTP

`httpx` + Chat Completions. Sem SDK OpenAI.

Motivo: timeout/retry/status explícitos, pouca superfície, sem acoplar
a um cliente de outro fornecedor. DeepSeek é OpenAI-compatible, mas o
contrato público é `LlmProvider`.

## Structured output

O endpoint estável documenta `response_format: {type: json_object}`,
não JSON Schema nativo no chat completion.

### v1 (legado)

Fluxo: schema Pydantic canônico (`LlmIrEnvelope`) → prompt → JSON mode →
`model_validate_json`.

### v2 (I10.1)

Fluxo: wire schema compacto → `WireEnvelope` → `wire_to_canonical` →
`IngestIR`/`QueryIR`. Pydantic canônico permanece autoridade final.

Ver `0012-i10-hardening.md`.

Sem repair automático por segundo LLM.

## Discriminador

`LlmIrEnvelope.ir_kind = ingest | query`. Sem heurística posterior.

## Ontologia

`InterpreterOntologyView.from_registry`. Keys/kind/parent/label.
Sem IDs persistentes. Sem ontologia paralela.

## Contexto enviado

locale, timezone, reference_at, catálogo, schema, raw text.
Sem banco, facts, histórico, IDs pessoais.

## Modelo

`deepseek-chat` (configurável). Sem raciocínio pesado por padrão.

## Retry

Timeout, 429 e 5xx. Sem retry em auth, JSON inválido ou schema.

## Logging

Sem API key, Authorization ou payload pessoal por padrão.
`log_payloads=True` é opt-in inseguro.
