# 0013 — I10.2 Wire Robustness

## Objetivo

Reduzir schema rejects sem parser permissivo e sem inventar informação.

## Diagnóstico (live)

Padrões observados nos rejects v2:

| Padrão | Categoria | Causa |
|--------|-----------|-------|
| `event.time` ausente | C | LLM omite tempo quando frase não tem expressão temporal explícita (caso D) |
| `event.time: null` | C | Mesmo significado que ausência |
| `event.time: {}` | C | Objeto vazio sem `original_text` |
| `original_text: null` | D | null → `""` (lossless) |
| `reference_kind: "explicit"` | B | Alias observado → `named` |
| `domain.finance` / `domain.services` | E | Domínio inexistente — **não reparar** |
| `qualifier=exact` + `uncertain` | E | Contradição — **hard fail** |

Caso D: diferença PASS vs REJECT era quase sempre **estrutura de `time`**, não Money/uncertainty.

## `normalize_wire_shape()`

Etapa explícita antes de `WireEnvelope.model_validate`:

```
raw provider JSON → normalize_wire_shape() → WireEnvelope → wire_to_canonical → canonical
```

Transformações permitidas:

- `event.time` ausente/null → `{"original_text": ""}`
- `time: {}` → `original_text: ""`
- `original_text: null` → `""` (não usa `raw_input`)
- `""` em campos textuais opcionais de tempo → `""`
- `weekday` casing → lowercase
- `value` → `money` (alias estrutural)
- `by_month_day` → `by_monthday`
- `reference_kind: explicit` → `named`

Recusadas deliberadamente:

- preencher `original_text` a partir de `raw_input`
- inferir `confidence` ausente
- aceitar texto linguístico em `money.amount`
- `extra="ignore"` no envelope
- domínios/conceitos inexistentes

## Wire vs canônico

- `WireIrTime.original_text` default `""`
- `WireIrEvent.time` default factory (evento sem bloco temporal explícito)
- IR canônico `IrTime.original_text: str` permanece; `""` representa ausência

## Observabilidade

`LlmSchemaValidationError.issues` + `DeepSeekInterpreter.last_validation_issues`
com `path`, `type`, `reason` (sem payload na exceção).

## Prompt

Sem v3 nesta iteração.
