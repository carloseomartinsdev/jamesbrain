# Failure matrix (I12-R) — durable mutation expectations

| Failure mode | Durable mutation? | User-visible outcome | Safe? |
|---|---|---|---|
| provider timeout | NO (pre-commit) | safe failure / retry≤2 | YES |
| provider malformed JSON | NO | safe failure after retry exhaustion | YES |
| retry exhausted | NO | safe failure | YES |
| semantic proposal incomplete | NO (unless sibling commits independently) | CLARIFY or SAFE_ABSTAIN or PARTIAL_EXECUTE | YES |
| canonical unresolved | NO | SAFE_ABSTAIN | YES |
| entity unresolved | NO (until clarified) | CLARIFY entity_reference | YES |
| clarification needed | NO until recovery commits | pending clarification | YES |
| clarification unsupported | NO | SAFE_ABSTAIN / unsupported_slot | YES |
| clarification ambiguous | NO | non-success recovery | YES |
| correction ambiguous | NO | Correction Guard reject / CLARIFY | YES |
| replacement failure | NO retract of original | CorrectionRejected; original intact | YES |
| materialization partial | YES only for valid independent sibling | PARTIAL_EXECUTE + non-materialized sibling | YES |
| query temporal unknown | NO (read path) | epistemically uncertain (not false NO) | YES |
| wrong user | NO | isolation reject | YES |
| wrong conversation | NO | isolation reject | YES |
