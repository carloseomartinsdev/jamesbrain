# ADR 0091 — Conversation Discourse Context and Cross-Turn Reference Resolution

## Status

**Accepted** — incremental on ADR 0081 / 0082 / 0074. Does not reopen:

- ADR 0076 — Principal Identity Binding (`self` / `__principal__`)
- ADR 0081 — Language Independence (Engine still does not re-read `qual` / `ele` / `e a`)
- ADR 0082 — Class vs Instance
- ADR 0090 — Owned Object Semantic Decomposition

## Context

Turns were interpreted correctly in isolation. Follow-ups such as `qual o nome?`
after `eu tenho uma gata?` were completed as if the omitted referent were the
speaker (`self.name`), because:

1. `recent_utterances` existed only as raw prior text for the LLM prompt.
2. Engine-resolved entity IDs never returned to the Interpreter as structured focus.
3. Knowledge Store and conversation focus were not separated — there was no
   conversation-scoped `DiscourseState`.

Persistent knowledge answers what is known. It does not record that the current
conversation is about Luna.

## Decision

```text
Knowledge answers what is known.
Discourse State tracks what the conversation is currently about.
```

```text
The LLM Interpreter resolves language and discourse references.
The PKE executes the resulting semantic representation without
reinterpreting conversation text.
```

```text
Natural Language
        ↓
LLM Interpreter  ↔  Conversation Discourse State
        ↓
Semantic IR
        ↓
PKE
        ↓
Knowledge Store
        ↓
Engine result → Discourse State update
```

### A. Storage and lifecycle

`DiscourseState` lives on `SessionContext.discourse` and is persisted only as
`engine_session_json` keyed by `conversation_id`. It is not written as facts,
relations, or entities.

- Isolated by `conversation_id` (and user session).
- Knowledge may survive conversations; discourse focus does not.
- Default empty state loads for sessions saved before this increment.
- Idle turns without a new resolved referent increment `idle_turns`; after
  `MAX_IDLE_TURNS` (8) the active focus is cleared. Explicit new topics replace
  the current focus immediately (previous IDs demoted to `recent_referents`
  with salience 0.6). No wall-clock expiry.

Do not persist:

```text
relation.current_topic
attribute.last_mentioned
entity.conversation_focus
fact(active_focus, Luna)
```

Do not place `__principal__` in `active_focus.entity_ids`.

### B. Two prompt channels

| Channel | Role |
|---|---|
| `recent_user_utterances` | Linguistic form: pronouns, ellipsis, topic shift |
| `discourse.structured` | Engine-resolved IDs, class/relation last queried, allowed_entity_ids |

The Interpreter may copy `known_entity_id` only from
`discourse.structured.allowed_entity_ids`. Invented IDs are
`discourse.invalid_binding` and are not executed.

### C. Interpreter decisions

`discourse_decision`: `continue` | `new_topic` | `ambiguous` | `none`

- **continue** — complete IR from active focus (set of IDs is a valid SET reference).
- **new_topic** — current utterance semantics outrank inherited focus.
- **ambiguous** — `AskStatus.NEEDS_CLARIFICATION`; do not pick Carlos vs João.

A set of owned cats is not ambiguity. Incompatible humans without focus are.

### D. Engine update

After a successful Ask (`answered` / `no_results`) or Ingest (`committed` /
`partial`), focus is rebuilt from Canonical IR + Engine result:

1. Relation object IDs (owned instances), excluding principal
2. Else non-principal `resolved_entity_ids`
3. Else query item entity IDs

Queries update focus even when nothing was written.

### E. Opaque raw_input

After discourse binding, `raw_input = OPAQUE-DISCOURSE-001` must still execute.
The PKE must not recover the referent from Portuguese/English/Spanish text.

### F. Out of scope

No dialogue manager, topic graph, intent stack, long-term conversational memory,
or PT/EN/ES follow-up word lists / regex repairs in the PKE.

Presenter does not resolve discourse.

## Consequences

- Follow-up `qual o nome?` binds the previously resolved owned cat(s).
- Topic switch `eu tenho um carro?` replaces cat focus; `e a cor?` stays on the car.
- Explicit `qual o nome da minha gata?` / `qual o modelo do meu carro?` wins
  over a salient inherited referent.
- Conversation B does not inherit Conversation A's focus.
- Prompts v4 and v5 carry the same conceptual discourse block.

## Mental test

```text
User: eu tenho uma gata?
PKE: Luna
Discourse: focus = Luna
User: qual o nome?
Interpreter: name + discourse focus Luna
Semantic IR: attribute(name, Luna)
PKE: Luna
```

Never: PKE reads `qual o nome?` to discover linguistically who is meant.
