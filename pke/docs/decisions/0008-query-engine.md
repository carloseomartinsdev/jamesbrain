# 0008 — QueryEngine determinístico

## Princípios

Consulta recupera conhecimento; não completa conhecimento.
Tempo do fato e tempo do registro são dimensões diferentes.

O engine recebe `ResolvedQuerySpec` (IDs e intervalo absoluto).
Não recebe texto, não chama Interpreter, não resolve `"este mês"`.

## Read store

`KnowledgeReadStore` / `UserKnowledgeSnapshot` atrás de interface
sem SQLAlchemy. Implementação: `SqliteKnowledgeReadStore`.
Não infla `EventRepository`.

## Versão

`CURRENT` = Fact sem sucessor direto na cadeia.
`HISTORY` = cadeia completa. SUM CURRENT não soma superseded.

## Tempo

Filtro `[start, end)` absoluto. Sem texto, sem “este mês”, sem
expansão linguística de “de 1 a 3”.

Instante consultável: `instant`, senão início civil de `date`,
senão `period_start`. Recorrência sem âncora civil **não** entra
no intervalo e **não** explode em ocorrências fictícias.

Inclusão: evento em `start` entra; evento em `end` não entra.
O dia linguístico final só entra se o Interpreter tiver emitido
`end` no início do dia seguinte (ver 0009).

`latest` usa tempo do evento, não `created_at`.

## SUM

Decimal + currency. Multi-currency é erro (`MultiCurrencyAggregateError`).
Sem câmbio. Proveniência: `contributing_fact_ids`.

## Ontologia

`EXACT` vs `INCLUDE_DESCENDANTS` no spec. Expansion via Registry.

## Isolamento

ID de outro usuário → `QueryIsolationError` (não visível).
Sem vazar dados.
