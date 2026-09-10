# ADR 0059 — Targeted Event Interpreter Hardening (I12.8)

## Status

**CLOSED — candidate REJECTED; prompt v4 remains baseline**

## Context

I12.7.1 closed downstream Event preservation:

- If proposal contains Event → semantics preserved (materialized or non-materialized).
- No false `event.intent` fallback.
- Missing Event in **raw proposal** is Interpreter-side debt.

I12.7-R showed MP1 (`"Medi a temperatura e deu 95°C."`) at **0/5** raw Event emission while MP2–MP4 were mostly correct.

## Decision boundary (I12.8)

**Single experimental dimension:** prompt v4 (control) vs `pke.interpret.v5-event` (candidate).

**Unchanged:** model, provider, SemanticProposal, Wire, router, persistability, materialization, guards, Core, ontology.

## Candidate change (v5-event)

One concise semantic rule block added to v4 multi-primitive section:

```text
Regra Event↔Measurement (quando ambas proposições coexistem na utterance):
- Ocorrência/ação explícita + leitura quantitativa → Event E Measurement (aditivas).
- Measurement NÃO elimina Event explícito; Event NÃO elimina Measurement.
- Só leitura/report instrumento → só Measurement (não emita Event por número/unidade/verbo isolado).
- Avalie proposição afirmada, não verbos ou sujeito humano vs sensor.
```

**Prompt size:** +456 chars (+8.23%). No new few-shots. No verb catalog.

## A/B experiment (I12.8)

| Parameter | Value |
|-----------|-------|
| Corpus | 75 cases (development; not holdout) |
| Runs | 470 total (N=3; MP N=5) |
| Provider | deepseek-chat |
| Artifacts | `docs/reports/i128_artifacts/checkpoint.jsonl` |

## Results summary

| Metric | v4 | v5-event | Delta |
|--------|---:|---:|---:|
| Raw Event precision | 1.00 | 1.00 | 0 |
| Raw Event recall | 0.541 | 0.510 | **−0.031** |
| Raw missing Event | 45 | 48 | +3 |
| False extra Event | 0 | 0 | 0 |
| E+M complete | 37/53 | 37/53 | 0 |
| POST S4 | 0 | 0 | 0 |
| POST event lost (when raw E) | 0 | 0 | 0 |
| False canonicalization | 0 | 0 | 0 |
| UNSAFE_VARIANCE cases | 17 | 13 | −4 |

### MP anchors

| Anchor | Expected | v4 Event | v5 Event |
|--------|----------|---:|---:|
| MP1 | E+M | 1/5 | **0/5** |
| MP2 | E+M | 5/5 | 5/5 |
| MP3 | E+M | 5/5 | 5/5 |
| MP4 | E+M | 1/5 | 2/5 |
| MP5 | M only | 0/5 ✓ | 0/5 ✓ |

## Acceptance gates

| Gate | Result |
|------|--------|
| POST_S4 = 0 | PASS |
| False extra Event = 0 | PASS |
| Recall material improvement | **FAIL** (−3.1 pp) |
| MP1 ≥ 4/5 | **FAIL** (0/5) |
| MP5 measurement-only | PASS |
| Post-engine Event loss = 0 | PASS |

**CANDIDATE_STATUS = REJECTED**

## Consequences

- **Active prompt remains `pke.interpret.v4`.**
- `pke.interpret.v5-event` retained in codebase for reproducibility; not default.
- Downstream hardening (I12.7 / I12.7.1) validated — when Event is emitted, engine preserves it.
- MP1 omission persists → strengthens **MODEL_VARIANCE / MODEL_CAPABILITY** hypothesis over prompt residual for this anchor.

## Debt reassessment

| Debt | Status |
|------|--------|
| INTERPRETER-EVENT-01 | PARTIALLY_MITIGATED |
| INTERPRETER-STATE-01 | OPEN |
| INTERPRETER-RELATION-01 | OPEN |
| LIVE-INTERPRETER-RELIABILITY-01 | PARTIALLY_MITIGATED |

## Recommendation

`I12.8_CLOSE_PROCEED_TO_MODEL_VARIANCE_STRATEGY`

## Core freeze

Knowledge Core v1 FROZEN · schema v10 · CORE 65 · holdout untouched.
