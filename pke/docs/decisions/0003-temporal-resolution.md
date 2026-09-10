# 0003 — Temporal Resolution

O Interpreter marca a expressão (`relative_day`, `weekday`, `date`, …).
O `TemporalResolver` só materializa `TimeValue`. Não parseia `"quinta"` em português.

Relógio: `TemporalContext.reference_at` → `IrTime.reference_at` → `UserContext.now`.
Nunca `datetime.now()`.

`weekday` sem `weekday_policy` e sem `event_status` é erro, não “próxima quinta” implícita.

`FROM_EVENT_STATUS`: `scheduled`/`pending` → `NEXT` (>= hoje); `completed`/`cancelled` → `PREVIOUS` (<= hoje).

`day_period` não gera `time_of_day`.
