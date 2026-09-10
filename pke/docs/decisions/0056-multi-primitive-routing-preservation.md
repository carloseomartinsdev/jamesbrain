# ADR 0056 — Multi-Primitive Routing and Semantic Preservation Boundary (I12.5)

## Status

Accepted — **I12.5 closed** (deterministic engine preservation green).

```text
ENGINE V1 HARDENING
MULTI-PRIMITIVE ROUTING
SEMANTIC INFORMATION PRESERVATION
```

No Knowledge Core change. No schema/migration. No CORE expansion.
No SemanticProposal / Wire redesign. No prompt / model / provider change.
Correction Acceptance Guard unchanged. Holdout untouched.

## Context

I12.3: highest-risk unsafe family = `multi_primitive` (13 unsafe cases).
MS18 (MP2): expected Event+Measurement; observed Measurement-only on 5/5 runs.

I12.4 closed Correction S4 safety. Next blocker: multi-primitive routing / semantic loss.

## Root analysis

### Pipeline authority

```text
SemanticProposal
  → route_primitive (primary)
  → collect_assertions (sole assertion-set authority)
  → resolve_proposal / resolution_to_wire
  → materialization (COMMIT_VALID_INDEPENDENTLY)
```

### Engine defect (fixed)

`route_primitive` returned `MEASUREMENT` whenever measurement evidence was present,
**before** residual `action_expression` / `event_expression` were considered.
`collect_assertions` only attached Measurement when primary was already `EVENT`.

Therefore a proposal that already contained:

```text
action_expression / event_expression
+ measurement_semantics
```

(without `change_semantics`) lost the Event frame — **ROUTER_LOSS**, not invention.

### MS18

I12.3 did **not** persist raw SemanticProposal payloads.

```text
DID_THE_CAPTURED_PROPOSAL_CONTAIN_EXPLICIT_EVENT_SEMANTICS? = UNKNOWN_NOT_PERSISTED

MS18 conclusion = MS18_MIXED_FAILURE
```

- Engine path: fixed for proposals that already encode occurrence + measurement.
- Interpreter path: if the live model emitted Measurement-only proposals, Event must
  **not** be fabricated (`INTERPRETER_SEMANTIC_LOSS`).

## Decision

### Preservation only

```text
has_explicit_occurrence_evidence(proposal)
AND has_measurement_evidence(proposal)
→ Event + Measurement frames
```

Occurrence evidence uses **proposal fields only** (change_semantics, lifecycle,
action_expression, event_expression, happened aspect). Raw text is not used to
build frames.

### MP5 protection

Instrument reading reports (`is_instrument_reading_report`) stay Measurement-only
even if `action_expression` is a measure-report verb on an instrument subject.

### Forbidden

- Measurement ⇒ invent Event
- Event ⇒ invent Measurement
- verb+number+unit lexical auto-Event
- second Interpreter reconstructing frames from raw text
- dual assertion-set authorities

### Partial materialization

Unchanged: `COMMIT_VALID_INDEPENDENTLY`.

## Evidence artifacts

- Ledger: `docs/reports/I12.5-MP-FAILURE-LEDGER.json`
- Suite: `tests/multi_primitive_routing_hardening/` (≥200 cases)
- Helpers: `src/pke/interpretation/semantic/multi_primitive_evidence.py`
- Router: `src/pke/interpretation/semantic/router.py`

## Freeze

```text
prompt = v4
model/provider unchanged
SemanticProposal unchanged
Wire unchanged
RetryPolicy unchanged
Correction Guard unchanged
Knowledge Core v1 = FROZEN
schema = v10
CORE = 65
migration = none
holdout untouched
```

## Debt

```text
INTERPRETER-RETRY-01 = CLOSED
Correction Acceptance Guard = CLOSED
INTERPRETER-EVENT-01 = OPEN (model often omits Event on multi-primitive)
INTERPRETER-STATE-01 = OPEN
INTERPRETER-RELATION-01 = OPEN
LIVE-INTERPRETER-RELIABILITY-01 = PARTIALLY_MITIGATED
```

## Recommendation

```text
I12.5_CLOSE_PROCEED_TO_MODEL_PROVIDER_EVALUATION
```

Highest remaining Engine v1 blocker after deterministic preservation:

```text
MODEL_VARIANCE
```

Engine no longer drops explicit dual assertions; live completeness still depends on
the model proposing Event when required.
