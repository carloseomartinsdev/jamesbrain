# 0006 — Storage / persistência

O pacote Python é `pke.persist` (`**/storage/` está ignorado no monorepo).
O papel arquitetural continua sendo Storage.

## Princípios

- Texto é representação; conceitos têm identidade.
- LLM interpreta. PKE raciocina. Storage persiste.
- Inferência resolve ambiguidade; não cria certeza onde ela não existe.
- Validade e completude são problemas diferentes.
- Persistível não significa materializado.

Storage não interpreta linguagem, não resolve entidades, não decide
completude, não altera confidence, não infere fatos e não escolhe conceitos.

## Persistível ≠ materializado

`KnowledgeAssessment.persistable` significa: não há impedimento
epistemológico/semântico para persistir.

Não significa: todas as dependências já existem no banco.

`create_candidate` pode ser warning e `persistable=True`. A etapa futura
`materialization` (Application) transforma o candidato em Entity concreta
antes do commit. Storage recusa FKs pendentes
(`event.subject_id` / `actor_id` / relation endpoints / fact.about
para id inexistente).

## Ontologia

CORE continua no `OntologyRegistry`. O banco guarda só `type_id` /
`concept_id` (`core:entity.vehicle`). Sem tabela de conceitos — o Registry
é a autoridade conceitual.

## Tempo

Colunas no `events` (híbrido, não um único DATETIME):

instant, date, time_of_day, período, timezone, precision, day_period,
recurrence, original_text, reference_at, reference_timezone,
resolution_rule, confidence.

Instantes técnicos (`created_at`) são UTC.
Tempos de domínio preservam timezone civil e `original_text`.
`created_at` do registro ≠ quando o evento ocorreu.
`reference_at` é normalizado para UTC na coluna; `reference_timezone`
reconstrói a semântica civil.

## Fact values

`value_kind`: string | integer | decimal | boolean | money | concept_ref |
entity_ref | temporal | json.

Money = Decimal + currency. Nunca float.
SQLite não tem NUMERIC real: Decimal é persistido como texto canônico
(`DecimalAsText`) e rematerializado como `Decimal`.

## UnitOfWork

`begin` / `__enter__`, `commit`, `rollback`, repositórios.
Atomicidade: metade de um conhecimento nunca é commitada.

## IDs

Instâncias: ULID (PK de domínio). Conceitos: `core:...`.
SQLite não gera PK de domínio. PKs inteiros só em tabelas auxiliares
(`entity_aliases`, `event_domains`, `schema_meta`) e não vazam.

## Schema

`create_all` nesta fase. `schema_meta` guarda
`storage_schema_version=1` e `core_schema_version`.

## Schema v1 — FROZEN

A partir do Incremento 9 o schema v1 está **congelado**.
`STORAGE_SCHEMA_FROZEN = True`. Qualquer alteração estrutural
(`CREATE`/`ALTER`/`DROP`) exige migration Alembic.
Alembic só entra na primeira mudança estrutural real — não agora.

## Source

`user_id` é obrigatório. Ownership não depende só de RawInput/Fact.
`raw_input_id` é opcional (inference, document, system, correction).
Quando presente, RawInput e Source devem ser do mesmo usuário.
Fact não referencia Source de outro usuário.

## Supersession

Cadeia linear: um Fact tem no máximo um sucessor direto
(`UNIQUE supersedes_id`). Sucessor exige mesmo `user_id`,
`about_kind`+`about_id` e `concept_id`.
`about_kind` discrimina a âncora polimórfica (entity | event | relation).
CURRENT = Fact sem sucessor na cadeia.

## Isolamento

Repositórios filtram por `user_id`. Triggers + validações impedem
relation/event/fact/state cross-user.

## RawInput

Imutável. Re-add do mesmo id falha. Correção gera novo RawInput.
