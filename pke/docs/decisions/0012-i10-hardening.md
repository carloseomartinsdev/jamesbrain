# 0012 — I10.1 DeepSeek Interpreter Hardening

## Princípio

> A representação oferecida ao modelo pode ser adaptada; a representação
> interna do PKE permanece canônica.

## Wire transport (v2)

Fluxo:

```
DeepSeek JSON
  → WireEnvelope (validação transport)
  → wire_to_canonical (mapeamento determinístico)
  → IngestIR | QueryIR (Pydantic canônico)
```

O **LLM transport model** é representação de integração, não IR do PKE.
Não há dois modelos de domínio concorrentes.

### Weekday

Wire usa `monday`…`sunday`. O adapter converte para `weekday` 0–6
(Monday=0) antes do `IrTime` canônico. TemporalResolver inalterado.

### EntityMention

Wire usa `entity_type` restrito a keys `entity_type` do catálogo.
`event.*` como type hint é rejeitado estruturalmente.

### Money

`WireIrFact.money: {amount: number, currency}` — texto linguístico
rejeitado no validator. `raw_input` preserva a frase original.

### Incerteza

Rubrica no prompt v2 + validação wire: `approximately`/`uncertain`
não combinam com `exact`/`confirmed`; confidence ≥ 0.8 bloqueado.

## Prompt v2 (`pke.interpret.v2`)

Diferenças vs v1:

- envelope `{ir_kind, ir}` com few-shot compacto (1 ingest + 1 query)
- ontologia compacta por kind (keys + dicas curtas)
- schema wire textual (sem `model_json_schema()` completo no user msg)
- papéis semânticos (profissão ≠ Entity)
- weekday por nome; rubrica de incerteza; Money estruturado
- dicas semânticas em `SEMANTIC_HINTS` (camada interpretation only)

v1 (`pke.interpret.v1`) permanece selecionável para comparação.

## Tokens

v2 omite JSON Schema canônico verboso e lista plana de conceitos.
Medir antes/depois no live runner (`metrics_v1` vs `metrics_v2`).

## Sem repair automático

Sem segunda chamada, fallback ou parser permissivo.
Mapeamento determinístico transport → canônico é permitido.

## TLS

Inalterado: `truststore`, sem `verify=False`.

## Critério Fase 2 (live)

Todos os casos A–F ≥ 2/3 e schema rejects ≤ 1/18 na rodada v2.
