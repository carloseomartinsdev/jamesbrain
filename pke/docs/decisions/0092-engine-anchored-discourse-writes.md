# ADR 0092 — Engine-Anchored Discourse Writes, Pending Intent, Identity/Role

## Status

**Accepted** — incremental on ADR 0091 / 0090 / 0081. Does not reopen:

- ADR 0081 — Language Independence
- ADR 0090 — Owned Object Semantic Decomposition
- ADR 0091 — Conversation Discourse Context (query follow-ups)

## Context

0091 connected Engine-resolved entity IDs to conversation-scoped Discourse State
so query follow-ups (`qual o nome?`) could bind `known_entity_id` without the
PKE rereading pronouns.

Write follow-ups still failed:

```text
eu tenho uma casa chamada Casa da Praia  → committed
ela tem 3 quartos                        → FAIL
```

Knowledge State (the house exists) is not Discourse State (the conversation is
about that house now). Identity/role utterances such as `meu contador se chama
Angelo` also decomposed into two entities linked by `relation.learned.named`.

## Decision

```text
LLM Interpreter interprets language and discourse.
Discourse State interprets continuity, not knowledge.
PKE interprets structured knowledge.
Engine results anchor discourse in real entity_ids.
```

```text
User utterance
      ↓
LLM Interpreter  ↔  Discourse State
      ↓
Semantic IR
      ↓
PKE
      ↓
Engine
      ↓
Knowledge
      ↓
Discourse Update
      ↓
Presenter
```

### A. Engine-anchored focus

After committed ingest / answered query, `active_focus` is taken from the
entity that actually participated:

1. Attribute/measurement subject (`known_entity_id` or unique name match)
2. Event participant that is the central actor (first bound participant)
3. Owns-relation object (created/reused instance), never principal
4. Created non-principal entities, dropping secondary place/store types

Display names from `canonical_name` travel with referents so the Interpreter
sees structured identity, not last-message text.

Traces: `discourse_input` (what the Interpreter received) and
`discourse_update` (`previous_focus`, `new_focus`, `reason`).

### B. Pending query intent

When an attribute query is `entity.ambiguous` (several compatible instances),
the conversation stores `DiscoursePendingIntent` (operation, attribute,
candidates, frozen QueryIR). A later subject-only reply (`do Atlas`) is merged
in AskService — the LLM does not reconstruct the whole query from the last
phrase. Interpreter-declared `discourse_decision=ambiguous` (incompatible
attribute vs focus) does **not** store pending: that is clarification, not a
forced write on the last focus.

### C. Identity vs role

Closed identity-naming lemmas (`named` / `called` / `name` / `is_called` /
`aka` / `identity`) plus a possessive role noun and a named person fold to:

- one persistable person (the given name)
- `type = person`
- role/relation from the role lemma (`accountant`) to self

`relation.learned.named` is never persisted. The role noun is not a second
entity. Thing-side `called X` folds to one owned named instance (0090).

After the final repair, persistable identity from Atomic Claims must match
persistable identity from proposal slots (semantic equality).

### D. Opacity and isolation

After Interpreter binding, `raw_input = OPAQUE-DISCOURSE-HOUSE-001` /
`OPAQUE-DISCOURSE-NOTEBOOK-001` still writes the bound entity. Discourse is
strictly `conversation_id`-scoped. PT / EN / ES share the same IR, discourse
mechanism, and execution path. No PKE lists of `ela` / `it` / `tiene`.

## Consequences

- House/notebook write follow-ups, ellipsis, topic switch, explicit return,
  and mixed-domain conversations bind one `entity_id`.
- Two owned notebooks + `qual o modelo do meu notebook?` → clarification;
  `do Atlas` completes the pending model query.
- `Atlas foi comprado na loja TechStore` does not steal `active_focus` for the
  store by default.
- `meu contador se chama Angelo` is one person Angelo with accountant relation
  to self.

## Out of scope

No pronoun regex in the PKE. No `house_context.py` / `ela_repair.py`. No
persisting `relation.current_topic`. Presenter only formats Engine candidates.
