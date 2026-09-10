# ADR 0058 — Event Routing and Downstream Semantic Preservation (I12.7)

## Status

Accepted — **I12.7 closed** (downstream preservation).  
**I12.7.1 follow-up** — false `event.intent` fallback removed; partial Event → non-materialized (see Appendix A).

```text
ENGINE V1 HARDENING
EVENT ROUTING
EVENT CANONICALIZATION
SEMANTIC INFORMATION PRESERVATION
```

No Knowledge Core change. No schema/migration. No CORE expansion.
SemanticProposal / Wire / prompt v4 / model / provider unchanged.
Correction Acceptance Guard unchanged. Holdout untouched.

## Context

I12.6 captured raw provider output and SemanticProposal for MP1–MP4 and MS18:

```text
RAW MODEL OUTCOME: Event + Measurement correctly represented
POST ENGINE OUTCOME: Event lost (measurement-only S3)
```

The model did **not** omit Event on those runs. Loss was **downstream Engine**.

I12.5 fixed router-level ROUTER_LOSS (`route_primitive` / `collect_assertions`).
I12.6 proved a **second loss path** remained after assertions were correct.

## Root cause (exact)

```text
EVENT_LOSS_STAGE = S6_MATERIALIZATION_INPUT / persistability gate
EVENT_LOSS_COMPONENT = assess_persistability._assess_event
EVENT_LOSS_MECHANISM = event_identity_incomplete → wire_allowed=False
```

When `concepts.action` and `concepts.event_type` were both unresolved (no CORE alias
for verbs like *medi*, *olhei*, *pesei*, *consultei*), `_assess_event` treated missing
catalog keys as **critical** and set `wire_allowed=False` — even when compositional
anchors (`expression` + `entity_context`) and occurrence evidence were already on the
proposal.

`resolution_to_wire_ingest` then computed:

```text
event_ok = assessment.wire_allowed and event_type is not None
intent = record_event if event_block else record_measurement
```

With `event_ok=False`, Event was **silently dropped** and the wire became
measurement-only despite `ResolutionResult.assertions` containing EVENT + MEASUREMENT.

### Why I12.5 did not fully eliminate it

I12.5 fixed assertion collection and EVENT primary routing only. Persistability and
wire materialization remained stricter than the router: unresolved Event **category**
was treated as non-persistable instead of **partial canonical** (ADR 0023).

## Decision

### Compositional partial Event persistability

When occurrence evidence is present (same predicate as I12.5:
`has_explicit_occurrence_evidence`) and anchors include `expression` +
`entity_context`, missing catalog `action` / `event_type` are **noncritical** —
status `PARTIALLY_RESOLVED_PERSISTABLE`, `wire_allowed=True`.

### Wire event type fallback

For compositional partial Events without resolved category, wire uses existing CORE
type `event.intent` (generic occurrence bucket). Catalog-resolvable actions continue
to use maintenance-family types per prior logic.

### No Event invention

Measurement-only proposals (MP5, instrument readings) unchanged. No raw-text
reinterpretation. No second interpreter.

### Single authority preserved

```text
collect_assertions (router) → sole assertion-set authority
assess_persistability aligned with has_explicit_occurrence_evidence
resolution_to_wire_ingest consumes assessment — no independent assertion rebuild
```

## MP anchors (frozen)

| Case | Expected post-fix |
|------|-------------------|
| MP1–MP4 | Event + Measurement preserved |
| MP5 | Measurement only |
| MS18 | Event + Measurement preserved (partial Event type) |

## Metrics (deterministic)

```text
EXPLICIT_EVENT_PRESERVATION_RATE = 100%
EXPLICIT_EVENT_LOST_DOWNSTREAM = 0
UNSUPPORTED_EVENT_ADDITION = 0
DUPLICATE_EVENT_CREATED = 0
```

Regression: 3149 passed (112 new I12.7 tests), 8 live deselected.

## Focused live (development)

`tests/event_routing_hardening/run_i127_focused_live.py` — ~65 cases, N=3 (N=5 MP),
checkpoint/resume, `RAW_EVENT_PRESENT_POST_EVENT_LOST` target 0.

## Remaining debt

```text
INTERPRETER-EVENT-01 = PARTIALLY_MITIGATED  (raw model variance may still omit Event)
LIVE-INTERPRETER-RELIABILITY-01 = PARTIALLY_MITIGATED
Highest remaining blocker = EVENT_INTERPRETATION (model-side omission, not downstream loss)
```

## Recommendation

```text
I12.7_CLOSE_PROCEED_TO_TARGETED_INTERPRETER_HARDENING
```

(or relation/state routing hardening in parallel once interpreter Event omission is bounded)

---

## Appendix A — I12.7.1 Safe Partial Event (false canonicalization removal)

I12.7-R proved `event.intent` is `INTENTION_OR_PLANNED_EVENT_CONCEPT` — not a generic
fallback. Assigning it to completed observation acts (*medi*, *olhei*, *pesei*) violated:

```text
correct canonical > safe unresolved >>> wrong canonical
```

### I12.7.1 decision

1. **Remove** compositional fallback `event_type_for_wire → event.intent` (and maintenance catch-all).
2. **Split** semantic validity from materialization readiness:
   - compositional partial Event → `wire_allowed=False`, note `event_category_unresolved_safe_partial`
   - Event → `non_materialized_primitives` + reason preserved on `ResolutionResult`
3. **Measurement** continues independent wire/commit (`COMMIT_VALID_INDEPENDENTLY`).
4. **`event.intent`** remains valid only when `concepts.event_type` resolves legitimately.

### I12.7 preservation fix remains valid

The I12.7 `_assess_event` compositional identity gate (occurrence + expression + entity)
is preserved; only wire readiness and false type assignment changed.

### Metrics (I12.7.1 deterministic)

```text
PARTIAL_EVENT_FALSE_CANONICALIZATION = 0
PARTIAL_EVENT_SILENTLY_DISCARDED = 0
PARTIAL_EVENT_PRESERVED_NON_MATERIALIZED > 0
RESOLVED_EVENT_MATERIALIZED > 0
```

Regression: 3232 passed (+83 I12.7.1 tests), 8 live deselected.
