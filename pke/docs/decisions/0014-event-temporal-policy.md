# ADR 0014 — Event temporal policy (Storage Schema v1)

**Status:** Accepted  
**Date:** 2026-09-01  
**Context:** I10.3 — diagnóstico E2E e revisão dos acceptance cases D

## Decisão

Eventos materializados no PKE v1 **exigem tempo do fato resolvível**.

Quando o tempo do fato não pode ser resolvido a partir da IR:

```text
needs_clarification
→ time.missing
→ zero writes
```

Isso é comportamento correto. Não introduzir eventos atemporais, `Event.time` nullable, nem usar `recorded_at`/`created_at` como substituto de `Event.time`.

## Dimensões temporais distintas

| Campo | Significado |
|-------|-------------|
| `Event.time` | Tempo do **fato** (quando o evento ocorreu ou ocorrerá) |
| `recorded_at` / `created_at` | Tempo do **registro** (quando o conhecimento entrou no PKE) |

`recorded_at` representa quando o conhecimento entrou no PKE e **não pode** ser usado como substituto de `Event.time`.

## Escopo v1 (não alterar agora)

- `Event.time`
- `KnowledgeValidator`
- `Completeness`
- `Materializer`
- storage schema
- `QueryEngine`

Nenhuma migration para tempo nullable neste incremento.

## Evolução futura

Eventos historicamente conhecidos mas sem tempo do fato resolvível podem ser reconsiderados em uma evolução futura do modelo, mediante **decisão arquitetural explícita** e **migration** de schema.

## Acceptance cases D — divisão

O antigo Caso D acumulava dois objetivos incompatíveis. Dividido em:

### D1 — uncertainty + evento persistível

Entrada: *"Acho que a revisão do Corolla hoje ficou em uns 180 reais."*

- uncertainty + approximation preservadas
- `relative_day=today`
- commit possível
- participa da cadeia `A → D1 → E → F`

### D2 — uncertainty + tempo essencial ausente

Entrada: *"Acho que a revisão ficou em uns 180 reais."*

- IR semanticamente válida (uncertainty, Money 180)
- nenhum tempo inventado
- ingest → `needs_clarification` / `time.missing` / zero writes
- **PASS** como clarification, não como commit
- **não** participa da cadeia E/F

## Consequências

- Fixtures de teste (`ir_d1`, `ir_d2`) devem refletir literalmente o texto representado — Fake não injeta informação ausente na frase.
- Suíte canônica: A, B, C, D1, D2, E, F (sete behaviors).
- E2E oficial: `A → D1 → E → B → C → F` (esperado BRL 506.50); D2 isolado com clarification.

## Relacionado

- ADR 0013 — I10 wire robustness
- I10.3 diagnóstico E2E (`tests/live/diagnose_e2e_boundary.py`)
