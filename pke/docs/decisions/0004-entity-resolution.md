# 0004 — Entity + Context Resolution

Menção nomeada com 2+ candidatos lexicais após filtro de tipo → `ambiguous`.
Contexto recente **não** desempata menção nomeada.

Referência contextual (`reference_kind=contextual`) usa só a janela recente
compatível com o type hint. Um candidato → resolve; dois → ambíguo.
`"o carro"` não é gravado como alias.

`create_candidate` só para menção nomeada com type hint e zero candidatos
**e** `ResolutionPurpose.INGEST`. Em `QUERY`, zero candidatos →
`unresolved` (consulta não cria Entity nem alias).
O resolver não persiste.

IDs de outro usuário: `ForeignEntityError`.
Normalização: casefold, acentos, pontuação, espaços — sem fuzzy/edit-distance.
