# Personal Knowledge Engine (PKE)

## Documento-base para desenvolvimento assistido --- Onda 1

**Status:** Fundação conceitual / arquitetura v0\
**Objetivo:** servir como contexto canônico inicial para desenvolvimento
no Cursor, preferencialmente em Python.

------------------------------------------------------------------------

## 1. Visão do produto

O produto não é apenas um chatbot, agenda, lista de tarefas ou
aplicativo de notas. O núcleo é um **Personal Knowledge Engine (PKE)**:
um motor capaz de transformar linguagem cotidiana em uma representação
estruturada e consultável da realidade pessoal do usuário.

A experiência deve ser natural:

> O usuário fala. O sistema entende, organiza, relaciona, identifica
> lacunas e pergunta apenas o necessário.

Exemplos de informações: - listas de compras; - contas a pagar e
pagamentos; - consultas; - exames e resultados; - veículos e
manutenções; - imóveis e manutenções; - compromissos; - documentos; -
compras; - pessoas; - prestadores; - locais; - eventos cotidianos; -
fatos e observações; - intenções futuras.

O sistema deve permitir consultas naturais posteriores sem depender da
"memória" da LLM.

------------------------------------------------------------------------

## 2. Princípio fundamental

O PKE deve separar claramente:

1.  **Linguagem** --- como o usuário expressa algo.
2.  **Interpretação** --- o significado extraído da linguagem.
3.  **Conhecimento** --- representação estruturada da realidade.
4.  **Persistência** --- armazenamento desse conhecimento.
5.  **Consulta/raciocínio** --- recuperação e composição de respostas.

Regra arquitetural:

> **LLM interpreta. PKE raciocina. Storage persiste.**

A LLM não deve ser o banco de dados e não deve decidir arbitrariamente
como a estrutura persistente é alterada.

------------------------------------------------------------------------

## 3. A gramática universal do cotidiano

Grande parte das informações cotidianas pode ser descrita pelas
seguintes dimensões:

  Papel                   Pergunta
  ----------------------- ------------------------------------
  Actor                   Quem?
  Action                  Fez/fará o quê?
  Subject                 Sobre quem/o quê?
  Object                  Com o quê?
  Time                    Quando?
  Place                   Onde?
  Manner                  Como?
  Cause                   Por quê?
  Purpose                 Para quê?
  Companion/Participant   Com quem?
  Quantity                Quanto?
  Result                  Qual foi o resultado?
  Source                  Como sabemos disso?
  Confidence              Qual a confiança nessa informação?

Esses são **papéis semânticos**, não necessariamente colunas fixas de
uma única tabela.

### Exemplo

Entrada:

> Levei o Corolla na oficina do João ontem porque estava fazendo barulho
> na suspensão. Trocaram as bieletas e ficou R\$ 480.

Representação conceitual:

``` yaml
actor: usuario
action: manutencao
subject: Corolla
time: ontem -> data absoluta
place: oficina_do_joao
cause: barulho_na_suspensao
provider: oficina_do_joao
performed:
  - troca_bieletas
quantity:
  type: monetary
  value: 480
  currency: BRL
result: concluido
```

------------------------------------------------------------------------

## 4. Primitivas do conhecimento

A ontologia inicial deve ser pequena e genérica.

### 4.1 Entity

Algo identificável que existe ou é tratado como objeto persistente.

Exemplos: - pessoa; - veículo; - residência; - empresa; - conta; -
medicamento; - documento; - estabelecimento; - produto; - aparelho.

Uma entidade deve possuir identidade própria e poder participar de
relações e eventos.

### 4.2 Event

Algo que aconteceu, está acontecendo ou deverá acontecer.

Exemplos: - pagamento; - compra; - consulta; - manutenção; -
abastecimento; - exame; - viagem; - vencimento.

Eventos devem ser temporalmente representáveis.

### 4.3 Action

A ação associada a um evento.

Exemplos: - pagar; - comprar; - levar; - trocar; - consultar; -
realizar; - agendar; - cancelar.

### 4.4 State

Como uma entidade, obrigação ou processo está em determinado momento.

Exemplos: - conta pendente; - conta paga; - consulta agendada; - exame
aguardando resultado; - veículo com 84.230 km.

Estados podem mudar com eventos.

### 4.5 Relation

Conexões entre elementos.

Exemplos:

``` text
usuario --possui--> Corolla
Corolla --segurado_por--> seguradora
usuario --reside_em--> Casa
Dra_Ana --atende--> usuario
conta_internet --pertence_a--> Casa
```

### 4.6 Attribute

Características de entidades, eventos ou relações.

Exemplos: - placa; - modelo; - valor; - quilometragem; -
especialidade; - vencimento.

### 4.7 Context

Informação usada para desambiguar linguagem e interpretar referências.

Exemplos: - "o carro" pode significar o Corolla; - "a internet" pode
significar a conta da residência principal; - "João" pode significar o
mecânico no contexto automotivo.

### 4.8 Source

Origem de um fato.

Exemplos: - declaração do usuário; - documento; - imagem; - sistema
externo; - inferência; - cálculo.

### 4.9 Confidence

O sistema deve representar incerteza.

Exemplo:

> Acho que paguei uns R\$ 180.

Não armazenar simplesmente `valor = 180` como certeza absoluta.

Representar:

``` yaml
value: 180
qualifier: approximately
confidence: low
source: user_statement
```

------------------------------------------------------------------------

## 5. Tempo como conceito de primeira classe

O PKE deve ser temporal desde o início.

Não assumir que fatos atuais substituem completamente fatos anteriores.

Exemplo:

``` text
10/08/2026 -> Corolla quilometragem = 82.000
01/09/2026 -> Corolla quilometragem = 84.500
```

Esses registros permitem responder futuramente:

> Quantos quilômetros rodei nos últimos meses?

O sistema deve considerar: - data do evento; - período; - validade de um
estado; - data de criação do registro; - data de atualização; - datas
aproximadas; - recorrência; - eventos futuros; - vencimentos.

------------------------------------------------------------------------

## 6. Estados e eventos

Eventos podem provocar transições de estado.

Exemplo:

``` text
ANTES
Conta Internet -> pendente

EVENTO
Pagamento da Conta Internet

DEPOIS
Conta Internet -> paga
```

Portanto, o PKE não deve apenas acumular frases. Deve representar
alterações no mundo conhecido.

Modelo mental:

> linguagem → interpretação → conhecimento atual → evento → novo estado

------------------------------------------------------------------------

## 7. Ontologia em três níveis

O sistema deve ser extensível sem permitir que a LLM transforme a
ontologia em uma estrutura caótica.

### CORE

Estrutura canônica mantida pelo produto.

Exemplos: - Entity; - Event; - State; - Relation; - Person; - Vehicle; -
Place; - Organization.

### EXTENDED

Estruturas aprendidas ou propostas pelo sistema e posteriormente
validadas/promovidas.

Exemplos: - garantia de manutenção; - pedágio; - estacionamento; -
categoria específica recorrente.

### PERSONAL

Conceitos particulares de um usuário.

Exemplo: - "revisão da viagem"; - nomes informais; - categorias
pessoais; - aliases.

**Regra:** a LLM pode propor extensões, mas não alterar silenciosamente
a ontologia CORE.

------------------------------------------------------------------------

## 8. Aprendizado progressivo

O PKE deve aprender em pelo menos quatro dimensões.

### 8.1 Ontologia

Aprender quais conceitos aparecem no cotidiano e quais atributos
normalmente os acompanham.

### 8.2 Semântica

Aprender o significado de expressões.

### 8.3 Relações

Aprender como entidades se conectam.

### 8.4 Contexto pessoal

Aprender como aquele usuário se refere às próprias coisas.

Exemplo:

``` text
"o carro" -> Corolla
"minha oficina" -> Oficina do João
"internet" -> conta da residência principal
```

O aprendizado pessoal deve ser isolado por usuário.

------------------------------------------------------------------------

## 9. Modelos pré-definidos e aprendizado

O sistema deve começar com modelos que cubram grande parte do cotidiano,
mas não ficar limitado a eles.

Exemplo inicial de manutenção veicular:

``` yaml
essential:
  - vehicle
  - maintenance_type
  - date

useful:
  - mileage
  - amount
  - provider

optional:
  - parts
  - warranty
  - invoice
  - notes
  - next_service
```

Ao longo do uso, o sistema pode observar novos campos recorrentes e
propor evolução.

A frequência de um atributo não deve automaticamente torná-lo parte do
CORE.

------------------------------------------------------------------------

## 10. Motor de completude

Uma das funções centrais do PKE é identificar informações faltantes.

Entretanto:

> **Nem toda informação faltante merece uma pergunta.**

Cada modelo pode classificar atributos como: - essenciais; - úteis; -
opcionais.

O motor deve considerar: - impacto da informação; - contexto; -
confiança; - possibilidade de inferência segura; - custo de interromper
o usuário; - se a informação pode ser obtida posteriormente.

### Exemplo

Usuário:

> Troquei o óleo do Corolla hoje por R\$ 320.

Possível resposta:

> Registrei. Qual era a quilometragem do Corolla?

Não perguntar de uma só vez: - marca do óleo; - oficina; - forma de
pagamento; - número da nota; - nome do atendente; - endereço.

O assistente não deve parecer um formulário.

------------------------------------------------------------------------

## 11. Inferência versus confirmação

Toda informação extraída deve poder carregar um status epistemológico.

Sugestão inicial:

``` text
explicit      usuário informou diretamente
inferred      sistema inferiu
confirmed     inferência posteriormente confirmada
uncertain     informação ambígua
contradicted  existe conflito
```

Exemplo:

> Tenho dentista quinta às 15h com a Dra. Ana.

A data pode ser resolvida usando a data atual/contexto. A especialidade
de Dra. Ana não deve ser inventada caso não exista evidência.

------------------------------------------------------------------------

## 12. Preservar a entrada original

Todo processamento deve manter a mensagem original.

Exemplo:

``` yaml
raw_input: "Troquei o óleo do Corolla hoje, ficou 320."
normalized_interpretation: ...
```

Isso é importante para: - auditoria; - reprocessamento com modelos
futuros; - correção; - debugging; - explicabilidade.

Nunca depender somente da interpretação gerada naquele momento.

------------------------------------------------------------------------

## 13. Pipeline conceitual

Fluxo esperado:

``` text
User Input
    ↓
Input Normalization
    ↓
Intent Detection
    ↓
Semantic Extraction
    ↓
Entity Resolution
    ↓
Temporal Resolution
    ↓
Context Resolution
    ↓
Knowledge Candidate
    ↓
Validation
    ↓
Completeness Analysis
    ↓
Clarification Decision
    ↓
Commit
    ↓
State Transition
    ↓
Knowledge Graph / Storage
```

Uma mensagem pode gerar: - nenhuma alteração; - uma entidade; -
múltiplas entidades; - relações; - um ou vários eventos; - alterações de
estado; - perguntas complementares.

------------------------------------------------------------------------

## 14. Representação intermediária

A LLM não deve escrever diretamente no banco.

Ela deve produzir uma representação intermediária validável.

Exemplo:

``` json
{
  "intent": "record_event",
  "domain": "health",
  "event": {
    "type": "appointment",
    "action": "attend",
    "actor": {"ref": "current_user"},
    "participants": [
      {
        "name": "Dra. Ana",
        "type": "person",
        "role": "provider",
        "confidence": 0.8
      }
    ],
    "time": {
      "date": "2026-09-03",
      "time": "15:00",
      "confidence": 1.0
    },
    "status": "scheduled"
  },
  "missing": [],
  "raw_input": "Tenho dentista quinta às 15h com a Dra. Ana"
}
```

Essa estrutura deve passar por validação determinística antes da
persistência.

------------------------------------------------------------------------

## 15. Consultas

A mesma filosofia vale para leitura.

Pergunta:

> Quando troquei o óleo do Corolla pela última vez?

A LLM interpreta a intenção de consulta.

O PKE transforma isso em uma consulta estruturada equivalente a:

``` text
entity = Corolla
event.type = vehicle_maintenance
maintenance.type = oil_change
sort = date DESC
limit = 1
```

A resposta deve ser construída a partir dos dados recuperados, não da
memória da LLM.

------------------------------------------------------------------------

## 16. Domínios iniciais

Os domínios servem para organização, UX, templates e heurísticas. Não
devem criar silos incompatíveis.

Sugestão v0:

``` text
general
people
home
vehicle
finance
health
shopping
documents
appointments
work
education
travel
services
```

Um evento pode atravessar domínios.

Exemplo: manutenção do carro possui dimensões de `vehicle`, `finance` e
`services`.

------------------------------------------------------------------------

## 17. Visões, não sistemas isolados

Evitar desenvolver bancos independentes para:

``` text
Sistema Financeiro
Sistema de Veículos
Sistema Médico
Sistema de Agenda
Sistema de Compras
```

Preferir um conhecimento central e construir **views**.

Exemplos:

**Financeiro** Eventos/obrigações que possuem dimensão monetária.

**Agenda** Eventos futuros com dimensão temporal.

**Veículos** Entidades `Vehicle` e fatos/eventos relacionados.

**Saúde** Eventos, entidades e documentos classificados no domínio de
saúde.

**Compras** Intenções, listas e eventos relacionados a aquisição.

------------------------------------------------------------------------

## 18. Listas e intenções

Nem tudo é um fato passado.

O PKE deve distinguir: - fato; - evento passado; - evento futuro; -
intenção; - obrigação; - lembrete; - item de lista; - hipótese.

Exemplo:

> Quando eu for ao supermercado preciso comprar café, leite e
> detergente.

Isso representa uma intenção/lista contextual, não compras realizadas.

Depois:

> Também acabou papel higiênico.

O contexto deve permitir associar o novo item à lista ativa adequada
quando houver confiança suficiente.

------------------------------------------------------------------------

## 19. Identidade e resolução de entidades

A mesma entidade pode aparecer sob diferentes nomes.

Exemplo:

``` text
Toyota Corolla
Corolla
meu carro
o carro
```

O PKE deve possuir mecanismo de `entity resolution`.

Nunca criar automaticamente uma nova entidade apenas porque o texto
utilizado mudou.

Quando houver ambiguidade relevante:

> Você está falando do Corolla ou do outro carro?

O resultado dessa confirmação também deve alimentar o contexto pessoal.

------------------------------------------------------------------------

## 20. Correções e contradições

O usuário precisa poder corrigir naturalmente.

Exemplo:

> A revisão não foi 180, foi 186,50.

O sistema deve: 1. identificar o registro referido; 2. registrar a
correção; 3. preservar histórico quando apropriado; 4. atualizar o
conhecimento atual; 5. não duplicar o evento.

Contradições devem ser explicitamente representáveis.

------------------------------------------------------------------------

## 21. Explicabilidade

O sistema deve conseguir explicar por que sabe algo.

Exemplo:

> Por que você diz que a próxima troca é em 94.230 km?

Resposta possível:

> Porque você informou 84.230 km na última troca e definiu intervalo de
> 10.000 km.

Isso exige rastreabilidade entre: - fatos; - fontes; - inferências; -
regras; - eventos.

------------------------------------------------------------------------

## 22. Princípios para Python

Python é a linguagem preferencial para esta implementação por
facilitar: - integração com LLMs; - NLP; - embeddings; - validação de
dados; - processamento assíncrono; - bibliotecas de IA; - evolução
futura do motor.

Entretanto, o projeto não deve acoplar o domínio a um fornecedor
específico de IA.

Interfaces devem abstrair: - LLM provider; - embedding provider; -
storage; - vector search; - event bus; - notification provider.

------------------------------------------------------------------------

## 23. Direção técnica sugerida para a Onda 1

A primeira onda **não deve tentar construir o assistente inteiro**.

Objetivo:

> provar que uma frase cotidiana pode ser transformada em conhecimento
> estruturado, validado e persistido sem acoplamento direto entre LLM e
> banco.

### Entregáveis da Onda 1

1.  estrutura Python do projeto;
2.  modelos de domínio CORE;
3.  representação intermediária;
4.  contratos/interfaces;
5.  pipeline básico de ingestão;
6.  entity resolution simples;
7.  temporal normalization básica;
8.  confidence/source;
9.  motor de completude inicial;
10. persistência local;
11. consultas estruturadas básicas;
12. testes;
13. CLI experimental.

------------------------------------------------------------------------

## 24. Estrutura de projeto sugerida

Não é obrigatória, mas é uma boa base:

``` text
pke/
├── pyproject.toml
├── README.md
├── docs/
│   ├── PKE-FOUNDATION.md
│   └── decisions/
├── src/
│   └── pke/
│       ├── domain/
│       │   ├── entities.py
│       │   ├── events.py
│       │   ├── states.py
│       │   ├── relations.py
│       │   ├── facts.py
│       │   └── value_objects.py
│       ├── ontology/
│       │   ├── core.py
│       │   ├── schemas.py
│       │   └── registry.py
│       ├── interpretation/
│       │   ├── models.py
│       │   ├── interpreter.py
│       │   └── prompts/
│       ├── resolution/
│       │   ├── entities.py
│       │   ├── temporal.py
│       │   └── context.py
│       ├── reasoning/
│       │   ├── completeness.py
│       │   ├── inference.py
│       │   ├── transitions.py
│       │   └── conflicts.py
│       ├── storage/
│       │   ├── repositories.py
│       │   └── sqlite/
│       ├── query/
│       │   ├── models.py
│       │   └── engine.py
│       ├── application/
│       │   ├── ingest.py
│       │   └── ask.py
│       └── cli.py
└── tests/
    ├── unit/
    └── integration/
```

Evitar criar abstrações vazias apenas para obedecer essa árvore. Criar
componentes conforme se tornarem necessários.

------------------------------------------------------------------------

## 25. Tecnologias iniciais

Sugestão conservadora:

-   Python 3.12+;
-   Pydantic para contratos/modelos de entrada e saída;
-   SQLAlchemy 2.x para persistência;
-   SQLite no desenvolvimento inicial;
-   Alembic quando migrations se tornarem necessárias;
-   pytest;
-   typing rigoroso;
-   Ruff;
-   opcionalmente mypy/pyright.

Não introduzir banco vetorial ou banco de grafos na Onda 1 sem
necessidade demonstrada.

A arquitetura deve permitir adicioná-los posteriormente.

------------------------------------------------------------------------

## 26. Banco relacional versus grafo

O conhecimento possui natureza de grafo, mas isso **não obriga** a
utilização imediata de um graph database.

A Onda 1 pode representar:

``` text
entities
events
relations
facts
states
sources
```

em banco relacional.

A camada de domínio deve impedir que decisões do banco físico contaminem
a ontologia.

------------------------------------------------------------------------

## 27. Segurança e privacidade

O produto armazenará dados altamente pessoais.

Desde o início: - isolamento obrigatório por usuário/tenant; - nenhum
dado pessoal deve entrar em logs sem necessidade; - preparar
criptografia de dados sensíveis; - permitir exclusão; - rastrear origem
e alteração; - separar dados operacionais de prompts; - minimizar envio
de contexto a provedores externos; - não utilizar dados de um usuário
para resolver contexto de outro.

Saúde e finanças exigirão atenção especial nas ondas posteriores.

------------------------------------------------------------------------

## 28. Regras constitucionais

Duas regras-mãe da Onda 1:

> **Texto é representação; conceitos têm identidade.**
>
> **LLM interpreta. PKE raciocina. Storage persiste.**

Estas regras devem orientar qualquer código gerado pelo Cursor:

1.  LLM nunca é fonte de verdade persistente.
2.  LLM nunca escreve diretamente no banco.
3.  Toda interpretação passa por schema validável.
4.  Toda informação relevante mantém `source`.
5.  Inferências mantêm `confidence`.
6.  A entrada original é preservada.
7.  O sistema distingue fato, intenção, estado e evento.
8.  Tempo é primeira classe.
9.  Correções não devem apagar silenciosamente a história.
10. Entidades devem ser resolvidas antes de serem duplicadas.
11. Ausência de informação não autoriza invenção.
12. Perguntas complementares devem ter benefício real.
13. Ontologia CORE não é modificada autonomamente pela LLM.
14. Conhecimento pessoal é isolado por usuário.
15. Domínios são visões/contextos, não silos de dados.
16. O motor deve ser testável sem depender de uma LLM real.
17. Fornecedores externos devem ficar atrás de interfaces.
18. Primeiro construir conhecimento correto; depois otimizar UX.
19. Texto é representação; conceitos têm identidade.
20. Tipos, ações, relações, atributos e domínios apontam para `OntologyConcept`, não para strings livres nem enums Python fechados.
21. Inferência resolve ambiguidade; não cria certeza onde ela não existe.
22. Validade e completude são problemas diferentes.
23. Persistível não significa materializado.
24. Conhecimento só existe depois do commit.
25. Consulta recupera conhecimento; não completa conhecimento.
26. Tempo do fato e tempo do registro são dimensões diferentes.
27. Perguntar não altera o conhecimento consultado.
28. Linguagem define intenção; limites determinísticos definem execução.
29. Saída do LLM é proposta, não conhecimento.

### Storage Schema v1 — FROZEN

O schema de persistência (`pke.persist`) foi estabilizado.
Qualquer alteração estrutural exige migration. Alembic só entra
na primeira mudança real — ver `docs/decisions/0006-storage.md`
e `docs/decisions/0009-ask.md`.

Consulta: `AskService` orquestra Interpreter → resolução → QueryEngine.
Não materializa conhecimento.

------------------------------------------------------------------------

## 29. Casos de aceitação da Onda 1

### Caso A --- manutenção

Entrada:

> Troquei o óleo do Corolla hoje por 320 reais.

Esperado: - reconhecer evento de manutenção; - resolver/criar Corolla
como veículo; - normalizar data; - registrar R\$ 320; - identificar
quilometragem como informação útil faltante; - gerar no máximo uma
pergunta complementar prioritária.

### Caso B --- compromisso

Entrada:

> Tenho dentista quinta às 15h com a Dra. Ana.

Esperado: - evento futuro; - data absoluta; - horário; - participante
Dra. Ana; - não inventar especialidade se não houver base; - status
agendado.

### Caso C --- conta

Entrada:

> A internet vence todo dia 10 e é 129,90.

Esperado: - identificar obrigação recorrente; - valor; - recorrência
mensal; - vencimento; - relacionar à entidade adequada quando possível.

### Caso D --- incerteza

Entrada:

> Acho que a revisão ficou em uns 180 reais.

Esperado: - preservar aproximação; - confiança inferior a informação
explícita exata; - não representar R\$ 180 como valor exato confirmado.

### Caso E --- correção

Após Caso D:

> Não, achei a nota. Foi 186,50.

Esperado: - identificar referência ao evento anterior; -
atualizar/corrigir conhecimento; - manter rastreabilidade da alteração.

### Caso F --- consulta

Entrada:

> Quanto gastei com o Corolla este mês?

Esperado: - interpretar consulta; - resolver Corolla; - selecionar
eventos monetários relacionados; - aplicar intervalo temporal; - somar
deterministicamente; - LLM apenas redige/apresenta o resultado.

------------------------------------------------------------------------

## 30. O que NÃO fazer na Onda 1

Não implementar ainda: - aplicativo mobile completo; - dezenas de
módulos; - automações complexas; - recomendações médicas; - Open
Banking; - integração com calendários; - OCR avançado; - processamento
completo de documentos; - knowledge graph distribuído; - agentes
autônomos; - sistema complexo de plugins; - treinamento/fine-tuning; -
arquitetura de microserviços prematura.

O objetivo é validar o **núcleo cognitivo**.

------------------------------------------------------------------------

## 31. Instruções para o Cursor

Ao receber este documento:

1.  Leia integralmente antes de gerar código.
2.  Trate este arquivo como especificação conceitual canônica da Onda 1.
3.  Não tente implementar tudo em uma única alteração.
4.  Primeiro produza uma análise técnica da Onda 1.
5.  Proponha arquitetura concreta e decisões que precisem de aprovação.
6.  Identifique ambiguidades antes de assumir comportamentos
    estruturais.
7.  Não altere princípios constitucionais sem aprovação humana.
8.  Trabalhe incrementalmente.
9.  Para cada etapa, apresente:
    -   objetivo;
    -   arquivos criados/alterados;
    -   decisões;
    -   testes;
    -   limitações;
    -   próximo passo.
10. Não adicione dependências sem justificar.
11. Prefira código simples, tipado e testável.
12. Não introduza abstrações prematuras.
13. Não simule inteligência com regras hardcoded específicas apenas para
    fazer os exemplos passarem.
14. Os exemplos deste documento são testes conceituais, não exceções
    especiais.
15. Antes da persistência, toda saída de IA deve ser validada por
    contratos tipados.
16. O projeto deve funcionar inicialmente mesmo com um `Interpreter`
    fake/determinístico nos testes.

------------------------------------------------------------------------

## 32. Primeira tarefa solicitada ao Cursor

**Não comece codificando imediatamente.**

Execute primeiro uma **Fase 0 --- Design técnico da Onda 1**.

Produza:

1.  proposta da arquitetura Python;
2.  modelo inicial das primitivas (`Entity`, `Event`, `State`,
    `Relation`, `Fact`, `Source`, `Confidence`, `Time`);
3.  proposta da representação intermediária;
4.  fronteiras entre domínio, interpretação, reasoning e storage;
5.  estratégia inicial de IDs e entity resolution;
6.  modelo temporal inicial;
7.  estratégia de persistência SQLite/SQLAlchemy;
8.  interfaces que desacoplam LLM;
9.  plano de testes;
10. divisão da Onda 1 em incrementos pequenos.

Para cada decisão relevante, informe: - decisão; - motivo; -
alternativas consideradas; - consequência; - se exige aprovação humana.

**Pare após apresentar a Fase 0 e aguarde aprovação antes de implementar
a primeira estrutura do projeto.**

------------------------------------------------------------------------

## 33. Critério de sucesso

A Onda 1 será considerada bem-sucedida quando o sistema demonstrar que
consegue:

> receber linguagem cotidiana → produzir interpretação estruturada →
> validar → relacionar com conhecimento existente → identificar lacunas
> → persistir → consultar posteriormente de maneira determinística.

O objetivo ainda não é criar uma IA que "saiba tudo".

O objetivo é construir corretamente a **linguagem interna pela qual o
computador começa a compreender a estrutura do cotidiano**.

------------------------------------------------------------------------

## 34. PKE Core — Wave 1 COMPLETE

Marco funcional atingido. Ver `docs/decisions/0010-wave1-complete.md`.

**Write path:** linguagem → Interpreter → IngestIR → Resolution →
Candidate → Validation → Completeness → Materialization → Commit.

**Read path:** linguagem → Interpreter → QueryIR → Query Resolution →
`ResolvedQuerySpec` → QueryEngine → `QueryResult`.

`storage_schema_version = 1`. `STORAGE_SCHEMA_FROZEN = True`.

A partir daqui: mudança estrutural → Alembic; mudança de contrato CORE
deliberada/versionada; LLM não é fonte de verdade; QueryEngine
determinístico.
