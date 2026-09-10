# 0005 — Validation e Completeness

Validação: a combinação informada é lícita?
Completeness: falta algo que importe?

`persistable` = validation.valid e nenhum essential missing.

`persistable` não significa materializado: `create_candidate` pode
continuar warning e `persistable=True`. Application (ainda não
implementado) deve criar a Entity antes do commit. Storage recusa
`subject_id` / FKs para entidade inexistente.

Clarificação: no máximo uma. ESSENTIAL missing primeiro (blocking);
USEFUL só se `ask_if_missing` (mileage). OPTIONAL nunca pergunta.
`question_key` é intenção (`clarify.attribute.mileage`), não frase de UI.

Schemas CORE versionados (`CORE_COMPLETENESS_VERSION = 1`),
lookup por conceito + merge simples do ancestral.
