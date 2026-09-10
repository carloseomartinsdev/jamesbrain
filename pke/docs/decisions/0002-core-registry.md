# 0002 — Ontology Registry CORE

## IDs CORE

`id = "core:" + key`

Exemplo: `entity.vehicle` → `core:entity.vehicle`

Motivo: determinístico, idempotente, auditável sem tabela de mapeamento.
Não é ULID. Instâncias do usuário continuam com ULID; conceitos CORE não.

## Versionamento

`OntologyRegistry.core_schema_version` = `"1"` (constante `CORE_SCHEMA_VERSION`).

Sem migrations nesta onda. Evolução futura do catálogo incrementa essa versão.

## Seeds

`load_core_seeds()` é idempotente: o mesmo `key` produz o mesmo `id` e o mesmo grafo.
Após o load, o CORE fica congelado. `register()` não aceita `scope=core`.
