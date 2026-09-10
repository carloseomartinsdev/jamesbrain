# 0001 — Princípios constitucionais da Onda 1

## Regras-mãe

1. **Texto é representação; conceitos têm identidade.**
2. **LLM interpreta. PKE raciocina. Storage persiste.**
3. **Inferência resolve ambiguidade; não cria certeza onde ela não existe.**
4. **Validade e completude são problemas diferentes.**
5. **Persistível não significa materializado.** (`persistable` ≠ entidades/fatos já existentes no banco)
6. **Conhecimento só existe depois do commit.** (`create_candidate` não é Entity; resolution não é persistência)
7. **Consulta recupera conhecimento; não completa conhecimento.**
8. **Tempo do fato e tempo do registro são dimensões diferentes.**
9. **Perguntar não altera o conhecimento consultado.**
10. **Linguagem define intenção; limites determinísticos definem execução.**
11. **Saída do LLM é proposta, não conhecimento.**

## Consequências no Incremento 1

- `Entity` / `Event` / `Relation` / `Fact` / `State` referenciam `OntologyConcept` por `id`.
- A IR usa `ConceptRef` (`key` estável do registry + `concept_id` após resolução).
- `"vehicle"`, `"maintenance"`, `"owns"` não são texto livre: são chaves de conceito.
- `last_event` é estratégia de resolução na IR, não conceito persistido.
- Locale/timezone pertencem a `UserContext`, não a `TimeValue`.
- O texto temporal original sobrevive à resolução absoluta.
- CORE é protegido; EXTENDED/PERSONAL existem na estrutura; a LLM não cria nem promove conceitos nesta onda.
