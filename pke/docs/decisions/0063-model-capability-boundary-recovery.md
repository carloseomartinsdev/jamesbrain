# ADR 0063 — Model Capability Boundary and Semantic Recovery Strategy (I12.12)

## Status

**CLOSED — strategy defined**

```text
NO Knowledge Core change
NO SemanticProposal / Wire / Router / Prompt / Model change
```

## Context

I12.11 concluded:

```text
BEST_CANDIDATE = NONE
baseline (deepseek-chat) not autonomously capable enough
SemanticProposal expressiveness = YES
language boundary safe = YES / reliable = NO
highest blocker = SEMANTIC_COMPLETENESS
```

Prior evidence:

- I12.8: prompt tuning failed (v5-event rejected)
- I12.9: multi-pass not justified
- I12.10: valid incomplete proposals are detectable and safely non-success
- I12.11: no callable model improves useful capture without safety regression

## Decision

### Engine v1 reliability (explicit)

Engine v1 reliability does **not** mean 100% automatic useful capture.

It means:

```text
safe autonomous execution when semantics are sufficient
+
safe bounded clarification when a detectable, user-answerable gap blocks execution
+
safe abstention when the gap cannot be recovered without guessing
```

Safety remains non-negotiable: wrong commit ≫ missed automatic capture.

### Capability outcomes

| Outcome | Meaning |
|---------|---------|
| AUTO_EXECUTE | Valid + fully materializable |
| PARTIAL_EXECUTE | ≥1 ready primitive; COMMIT_VALID_INDEPENDENTLY |
| CLARIFY | Detectable high/medium-value user-answerable gap; zero ready |
| SAFE_ABSTAIN | Not executable; clarification not useful/eligible |
| INVALID | Unparseable / contract-invalid |

Authority:

```text
pke.interpretation.semantic.capability_strategy.decide_capability
```

composes `execution_readiness`. Not an Interpreter. No model call.

### Recovery sources (allowed)

```text
A. existing structured proposal
B. deterministic resolvers
C. persisted user knowledge/context (for already-present references)
D. explicit user clarification (= new evidence)
```

Forbidden: raw-NL reinterpretation, majority vote, proposal union, silent guessing, arbitrary canonical fallback.

### Clarification answer

```text
clarification answer = new explicit user evidence
```

Fill only the requested slot on a pending proposal copy. Reassess readiness.
Do **not** run `original + answer → unrestricted SemanticProposal`.

### Ask vs write recovery

| System | Role |
|--------|------|
| AskService | Query-path ambiguity only (ADR 0009) |
| CompletenessEngine | Post-candidate schema completeness |
| CapabilityStrategy + ExecutionReadiness | Write-path execute/clarify/abstain |
| Product `answer_clarification` concat | **Not** Engine recovery (debt: replace with bounded slot fill) |

No CLARIFICATION_AUTHORITY_CONFLICT: single write-path decision authority is CapabilityStrategy.

### Rejected strategies

```text
multi-pass = NO (I12.9)
model switch = NO (I12.11 BEST_CANDIDATE=NONE)
prompt change = NO
second Interpreter = NO
```

## Consequences

- MP1 null-subject → CLARIFY(measured_entity); subject stays null until user evidence
- Safe partial Event taxonomy → SAFE_ABSTAIN (do not interrogate for category)
- Application/Product must implement bounded clarification recovery next
- Knowledge Core v1 remains FROZEN

## Evidence

Deterministic corpus ≥220 + live reclassification of I12.11 baseline (354 runs).
See `docs/reports/I12.12-MODEL-CAPABILITY-STRATEGY.md`.
