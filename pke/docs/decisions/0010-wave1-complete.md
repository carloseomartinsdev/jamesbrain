# 0010 — PKE Core — Wave 1 COMPLETE

Marco funcional da Onda 1. Sem LLM real, CLI ou HTTP.

## Write path

```
Natural Language
  → Interpreter
  → IngestIR
  → Resolution
  → KnowledgeCandidate
  → Validation
  → Completeness
  → Materialization
  → Commit
```

## Read path

```
Natural Language
  → Interpreter
  → QueryIR
  → Query Resolution
  → ResolvedQuerySpec
  → QueryEngine
  → QueryResult
```

## Schema

`storage_schema_version = 1`  
`STORAGE_SCHEMA_FROZEN = True`

A partir deste marco:

* mudança estrutural no banco → Alembic;
* mudança de contrato do CORE deve ser deliberada/versionada;
* LLM continua não sendo fonte de verdade;
* QueryEngine continua determinístico.

## Princípio adicional

> Linguagem define intenção; limites determinísticos definem execução.

Intervalos linguísticos inclusivos são interpretados **antes** do
QueryEngine. O engine só executa `[start, end)`.

## Fora da Onda 1

LLM real, resposta textual, CLI, HTTP, embeddings, conversation log,
câmbio, ontologia financeira completa, follow-up conversacional.
