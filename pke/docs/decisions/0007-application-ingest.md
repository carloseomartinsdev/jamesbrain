# 0007 — Application ingest + materialization

## Princípio novo

Conhecimento só existe depois do commit.

`create_candidate` não é Entity. Candidate não é Fact.
Resolution não é persistência. Contexto só vê entidades após commit.

## Camadas

`IngestService` orquestra. `KnowledgeMaterializer` só aceita
`ApprovedKnowledge` (`assessment.persistable`).
`KnowledgeCandidateBuilder` monta o candidato a partir de IR + resoluções.

persist não importa application. reasoning não importa persist.

## Clarificação

Essential missing → `needs_clarification`, zero writes.
Useful missing → `committed` + clarification não bloqueante.

## RawInput

Persistido só quando a ingestão é materializada.
Ingestões bloqueadas guardam o texto no `IngestResult`, sem conversation log.

## Correção

`last_event` é estratégia. Application resolve para event_id/fact_id
via SessionContext. Materializer nunca persiste `last_event`.

## Relógio

`UserContext.now` / `FixedClock`. Sem `datetime.now()` na application.

## Event.actor_id

Opcional. Obrigação sem entidade (conta de internet) não inventa Casa.
