# I11 — Generalization Baseline (Development Set)

**Gerado:** 2026-09-02 02:15 UTC  
**Model:** deepseek-chat  
**Prompt:** pke.interpret.v2  
**Holdout:** não executado (reservado)

## Resumo

| Métrica | Valor |
|---------|-------|
| Casos development | 30 |
| Runs totais | 135 |
| Provider JSON validity | 61.5% |
| Wire validity | 61.5% |
| Canonical validity | 61.5% |
| Semantic pass rate | 16.3% |
| Forbidden inference rate | 0.0% |
| Unsupported rate | 0.0% |

### Estabilidade (por caso, 3 runs)

| Bucket | Casos |
|--------|-------|
| 3/3 stable | 3 |
| 2/3 acceptable but unstable | 4 |
| 1/3 weak | 3 |
| 0/3 failed | 20 |

## Por domínio

| domain | cases | stable | unstable | weak | failed |
| --- | --- | --- | --- | --- | --- |
| documents | 2 | 0 | 0 | 0 | 2 |
| education | 3 | 0 | 0 | 0 | 3 |
| finance | 3 | 1 | 0 | 1 | 1 |
| general | 1 | 0 | 0 | 0 | 1 |
| health | 2 | 0 | 2 | 0 | 0 |
| home | 6 | 1 | 1 | 2 | 2 |
| people | 3 | 1 | 0 | 0 | 2 |
| services | 3 | 0 | 0 | 0 | 3 |
| shopping | 2 | 0 | 1 | 0 | 1 |
| travel | 3 | 0 | 0 | 0 | 3 |
| vehicle | 2 | 0 | 0 | 0 | 2 |

## Por construção linguística

| structure | cases | stable | unstable | weak | failed |
| --- | --- | --- | --- | --- | --- |
| colloquial | 2 | 0 | 0 | 1 | 1 |
| declarative | 24 | 3 | 3 | 1 | 17 |
| equivalence_group | 1 | 0 | 0 | 0 | 1 |
| minimal | 1 | 0 | 1 | 0 | 0 |
| passive | 2 | 0 | 0 | 1 | 1 |

## Por ação

| action | cases | stable | unstable | weak | failed |
| --- | --- | --- | --- | --- | --- |
| anomaly | 1 | 0 | 0 | 1 | 0 |
| buy | 1 | 0 | 0 | 0 | 1 |
| cancel | 2 | 0 | 0 | 0 | 2 |
| deplete | 1 | 0 | 1 | 0 | 0 |
| documents | 1 | 0 | 0 | 0 | 1 |
| education | 1 | 0 | 0 | 0 | 1 |
| end_relation | 1 | 0 | 0 | 0 | 1 |
| finance | 2 | 1 | 0 | 1 | 0 |
| general | 1 | 0 | 0 | 0 | 1 |
| health | 2 | 0 | 2 | 0 | 0 |
| home | 2 | 0 | 1 | 1 | 0 |
| install | 2 | 0 | 0 | 0 | 2 |
| lend | 2 | 1 | 0 | 0 | 1 |
| renew | 1 | 0 | 0 | 0 | 1 |
| repair | 1 | 0 | 0 | 0 | 1 |
| replace | 2 | 1 | 0 | 0 | 1 |
| reserve | 2 | 0 | 0 | 0 | 2 |
| return | 1 | 0 | 0 | 0 | 1 |
| start | 2 | 0 | 0 | 0 | 2 |
| travel | 1 | 0 | 0 | 0 | 1 |
| vehicle | 1 | 0 | 0 | 0 | 1 |

## Gaps identificados

- **Ontology gaps:** nenhum marcado nesta rodada
- **Core capability gaps:** nenhum
- **Context gaps (PARTIALLY_SUPPORTED):** HEALTH_001, CTX_FRIDGE_04
- **ATEMPORAL_KNOWLEDGE_CANDIDATE:** HEALTH_002

## Padrões de erro

SEMANTIC=61, CANONICAL=52, CONTEXT_GAP=2

## Falhas representativas

_Nenhuma falha parcial registrada._

---

*Experimento I11 — nenhuma alteração de prompt, wire, ontology ou Core nesta rodada.*

## Ontology Coverage & Expressiveness Audit (I11.1)

### Current ontology size

- **Total CORE concepts:** 33
- **Max hierarchy depth:** 1
- **Exposed to LLM (InterpreterOntologyView):** 33
- **Registry presentation labels (aliases):** 33
- **SEMANTIC_HINTS (interpreter-only):** 10

| kind | count |
| --- | --- |
| entity | 4 |
| event | 8 |
| action | 6 |
| state | 0 |
| relation | 2 |
| attribute | 3 |
| domain | 7 |
| other | 3 |

**ConceptCatalog exposto ao wire:**
- `entity_types`: 4 keys
- `event_types`: 8 keys
- `actions`: 6 keys
- `attributes`: 3 keys
- `domains`: 7 keys
- `roles`: 3 keys

### Benchmark semantic demand

**action** (13 necessidades): need.action.attend, need.action.buy, need.action.cancel, need.action.install, need.action.lend, need.action.pay, need.action.renew, need.action.repair, need.action.replace, need.action.reserve, need.action.return_item, need.action.return_trip, need.action.start
**attribute** (3 necessidades): need.attr.amount, need.attr.expiry, need.attr.quantity
**domain** (8 necessidades): need.domain.education, need.domain.finance, need.domain.health, need.domain.home, need.domain.services, need.domain.shopping, need.domain.travel, need.domain.vehicle
**entity** (8 necessidades): need.entity.appliance, need.entity.document, need.entity.home_component, need.entity.organization, need.entity.person, need.entity.place, need.entity.product, need.entity.vehicle
**event** (15 necessidades): need.event.anomaly, need.event.appointment, need.event.education, need.event.health_vaccination, need.event.health_visit, need.event.installation, need.event.lend, need.event.maintenance, need.event.obligation_expiry, need.event.purchase, need.event.recurring_bill, need.event.reservation, need.event.service_cancel, need.event.travel, need.event.vehicle_maintenance
**relation** (2 necessidades): need.relation.cohabitation, need.relation.employment
**state** (3 necessidades): need.state.anomaly, need.state.depletion, need.state.unpaid

### Concept coverage

| need | class | canonical | cases |
| --- | --- | --- | --- |
| `need.action.attend` | ALIAS_NEEDED | action.attend | HEALTH_002 |
| `need.action.buy` | DIRECT | action.buy | SHOP_001 |
| `need.action.cancel` | GENERIZABLE | — | SVC_002, EQUIV_G4 |
| `need.action.install` | GENERIZABLE | — | HOME_003, EQUIV_G3 |
| `need.action.lend` | GENERIZABLE | — | PEOPLE_003, COLL_002 |
| `need.action.pay` | DIRECT | action.pay | UNC_001 |
| `need.action.renew` | GENERIZABLE | — | DOC_002 |
| `need.action.repair` | GENERIZABLE | — | SVC_001 |
| `need.action.replace` | DIRECT | action.replace | HOME_002, EQUIV_G1 |
| `need.action.reserve` | GENERIZABLE | — | TRAVEL_001, EQUIV_G5 |
| `need.action.return_item` | GENERIZABLE | — | EQUIV_G2 |
| `need.action.return_trip` | GENERIZABLE | — | TRAVEL_002 |
| `need.action.start` | GENERIZABLE | — | PEOPLE_002, EDU_001 |
| `need.attr.amount` | ALIAS_NEEDED | attribute.amount | PEOPLE_003, SVC_001, COLL_002 |
| `need.attr.expiry` | REPRESENTATION_GAP | — | DOC_001 |
| `need.attr.quantity` | REPRESENTATION_GAP | — | SHOP_001 |
| `need.domain.education` | NEW_CONCEPT_CANDIDATE | — | EDU_001, EDU_002 |
| `need.domain.finance` | DIRECT | domain.finance | PEOPLE_003, COLL_002, NEG_002 |
| `need.domain.health` | DIRECT | domain.health | HEALTH_002 |
| `need.domain.home` | DIRECT | domain.home | HOME_001, HOME_002, HOME_003 |
| `need.domain.services` | DIRECT | domain.services | SVC_002 |
| `need.domain.shopping` | DIRECT | domain.shopping | SHOP_001, SHOP_002 |
| `need.domain.travel` | NEW_CONCEPT_CANDIDATE | — | TRAVEL_001, TRAVEL_002 |
| `need.domain.vehicle` | DIRECT | domain.vehicle | NEG_001 |
| `need.entity.appliance` | GENERIZABLE | — | HOME_001, HOME_003, SVC_001 |
| `need.entity.document` | NEW_CONCEPT_CANDIDATE | — | DOC_001, DOC_002 |
| `need.entity.home_component` | NEW_CONCEPT_CANDIDATE | — | HOME_002 |
| `need.entity.organization` | ALIAS_NEEDED | entity.organization | PEOPLE_001 |
| `need.entity.person` | ALIAS_NEEDED | entity.person | PEOPLE_001, PEOPLE_002, PEOPLE_003 |
| `need.entity.place` | NEW_CONCEPT_CANDIDATE | — | TRAVEL_001, TRAVEL_002 |
| `need.entity.product` | NEW_CONCEPT_CANDIDATE | — | SHOP_002 |
| `need.entity.vehicle` | ALIAS_NEEDED | entity.automobile | NEG_001, EQUIV_G1 |
| `need.event.anomaly` | GENERIZABLE | — | HOME_001 |
| `need.event.appointment` | ALIAS_NEEDED | event.appointment | EDU_002, UNC_002 |
| `need.event.education` | GENERIZABLE | — | EDU_001 |
| `need.event.health_vaccination` | GENERIZABLE | — | HEALTH_001 |
| `need.event.health_visit` | ALIAS_NEEDED | event.appointment | HEALTH_002 |
| `need.event.installation` | GENERIZABLE | — | HOME_003, EQUIV_G3 |
| `need.event.lend` | GENERIZABLE | — | PEOPLE_003 |
| `need.event.maintenance` | DIRECT | event.maintenance | HOME_002, SVC_001, CTX_FRIDGE_04 |
| `need.event.obligation_expiry` | ALIAS_NEEDED | event.obligation | DOC_001 |
| `need.event.purchase` | DIRECT | event.purchase | SHOP_001 |
| `need.event.recurring_bill` | DIRECT | event.recurring_bill | SVC_002 |
| `need.event.reservation` | GENERIZABLE | — | TRAVEL_001, EQUIV_G5 |
| `need.event.service_cancel` | GENERIZABLE | — | SVC_002, EQUIV_G4 |
| `need.event.travel` | REPRESENTATION_GAP | — | TRAVEL_002 |
| `need.event.vehicle_maintenance` | ALIAS_NEEDED | event.vehicle_maintenance | EQUIV_G1 |
| `need.relation.cohabitation` | REPRESENTATION_GAP | — | PEOPLE_002 |
| `need.relation.employment` | REPRESENTATION_GAP | — | PEOPLE_001 |
| `need.state.anomaly` | REPRESENTATION_GAP | — | HOME_001, COLL_001 |
| `need.state.depletion` | REPRESENTATION_GAP | — | SHOP_002 |
| `need.state.unpaid` | REPRESENTATION_GAP | — | NEG_002 |

### Coverage metrics

| metric | value |
| --- | --- |
| overall_concept_coverage | 55.8% |
| action_coverage | 92.3% |
| event_coverage | 66.7% |
| state_coverage | 0.0% |
| relation_coverage | 0.0% |
| entity_type_coverage | 12.5% |
| alias_coverage | 73.1% |
| new_concept_candidates | 6 |
| representation_gaps | 8 |
| alias_gaps | 9 |

_Separação: falta de conceito (NEW_CONCEPT_CANDIDATE) ≠ falta de alias (ALIAS_NEEDED) ≠ erro LLM (baseline semantic_accuracy)_

### Alias gaps

- **action.attend** ← fui ao, consulta, cardiologista (`CANONICAL_ALIAS_CANDIDATE`)
- **attribute.amount** ← reais, conto, 180, 500 (`CANONICAL_ALIAS_CANDIDATE`)
- **entity.organization** ← acme (`CANONICAL_ALIAS_CANDIDATE`)
- **entity.person** ← joão, mariana, pedro, mel (`CANONICAL_ALIAS_CANDIDATE`)
- **entity.automobile** ← corolla, carro (`CANONICAL_ALIAS_CANDIDATE`)
- **event.appointment** ← dentista, prova, exame (`CANONICAL_ALIAS_CANDIDATE`)
- **event.appointment** ← cardiologista (`CANONICAL_ALIAS_CANDIDATE`)
- **event.obligation** ← vence, vencimento, habilitação vence (`CANONICAL_ALIAS_CANDIDATE`)
- **event.vehicle_maintenance** ← embreagem, revisão do carro, óleo (`CANONICAL_ALIAS_CANDIDATE`)
- **action.replace** ← trocar, substituir, substituída, troca, substituição (`CANONICAL_ALIAS_CANDIDATE`)

### New concept candidates

- **action** / return (×13) LLM keys: ['action.return'] | surfaces: [] | nearest: action.attend, action.buy, action.maintain
- **action** / install (×11) LLM keys: ['action.install'] | surfaces: [] | nearest: action.attend, action.buy, action.maintain
- **action** / give (×11) LLM keys: ['action.give'] | surfaces: [] | nearest: action.attend, action.buy, action.maintain
- **action** / cancel (×9) LLM keys: ['action.cancel'] | surfaces: [] | nearest: action.attend, action.buy, action.maintain
- **action** / reserve (×9) LLM keys: ['action.reserve'] | surfaces: [] | nearest: action.attend, action.buy, action.maintain
- **action** / book (×9) LLM keys: ['action.book'] | surfaces: [] | nearest: action.attend, action.buy, action.maintain
- **domain** / education (×5) LLM keys: ['domain.education'] | surfaces: [] | nearest: domain.appointments, domain.finance, domain.health
- **action** / renew (×3) LLM keys: ['action.renew'] | surfaces: [] | nearest: action.attend, action.buy, action.maintain
- **action** / update (×3) LLM keys: ['action.update'] | surfaces: [] | nearest: action.attend, action.buy, action.maintain
- **domain** / work (×2) LLM keys: ['domain.work'] | surfaces: [] | nearest: domain.appointments, domain.finance, domain.health
- **domain** / people (×2) LLM keys: ['domain.people'] | surfaces: [] | nearest: domain.appointments, domain.finance, domain.health
- **action** / travel (×2) LLM keys: ['action.travel'] | surfaces: [] | nearest: action.attend, action.buy, action.maintain
- **action** / arrive (×2) LLM keys: ['action.arrive'] | surfaces: [] | nearest: action.attend, action.buy, action.maintain
- **domain** / travel (×2) LLM keys: ['domain.travel'] | surfaces: [] | nearest: domain.appointments, domain.finance, domain.health
- **entity** / documento oficial (×2) LLM keys: — | surfaces: ['cnh', 'passaporte', 'habilitação'] | nearest: entity.automobile, entity.organization, entity.person
- **entity** / local/lugar (×2) LLM keys: — | surfaces: ['recife', 'fortaleza', 'quarto'] | nearest: entity.automobile, entity.organization, entity.person
- **action** / start (×1) LLM keys: ['action.start'] | surfaces: [] | nearest: action.attend, action.buy, action.maintain
- **action** / move (×1) LLM keys: ['action.move'] | surfaces: [] | nearest: action.attend, action.buy, action.maintain
- **action** / live (×1) LLM keys: ['action.live'] | surfaces: [] | nearest: action.attend, action.buy, action.maintain
- **entity** / componente doméstico (×1) LLM keys: — | surfaces: ['chuveiro', 'resistência', 'embreagem'] | nearest: entity.automobile, entity.organization, entity.person
- **entity** / produto consumível (×1) LLM keys: — | surfaces: ['filtros de café', 'detergente'] | nearest: entity.automobile, entity.organization, entity.person

### Representation gaps

- `need.attr.expiry`: validade como atributo vs obligation
- `need.attr.quantity`: attribute.quantity ausente no CORE
- `need.event.travel`: sem event.travel no CORE
- `need.relation.cohabitation`: relation residência ausente
- `need.relation.employment`: relation.employment ausente no CORE
- `need.state.anomaly`: STATE não modelado no wire IR
- `need.state.depletion`: STATE não modelado no wire IR
- `need.state.unpaid`: negação + estado; IR limitada

### Potential duplicate concepts

- event.maintenance vs event.vehicle_maintenance: hierarquia pai/filho — não duplicar, usar GENERALIZABLE
- event.obligation vs event.recurring_bill: hierarquia pai/filho — não duplicar, usar GENERALIZABLE

### Polysemous expressions

- **trocar**: action.replace (embreagem) | mudança emprego | câmbio monetário _(ex.: EQUIV_G1 vs (não no dev) troca emprego/moeda)_
- **vencer**: obligation_expiry (CNH) | recurring_bill | prazo de prova _(ex.: DOC_001, COLL_003 (holdout-like))_
- **ficou**: valor monetário (250 reais) | agendamento (prova sexta) _(ex.: CTX_FRIDGE_04, EDU_002)_

### Recommended ontology evolution (proposals only)

- STATE/relation não têm kind no wire — avaliar primitives IR antes de novos conceitos CORE
- Adicionar relation.employment / relation.residence como candidatos EXTENDED, não CORE imediato
- Candidato action.return: observado 13× — mais próximo: action.attend, action.buy, action.maintain
- Candidato action.install: observado 11× — mais próximo: action.attend, action.buy, action.maintain
- Candidato action.give: observado 11× — mais próximo: action.attend, action.buy, action.maintain
- Candidato action.cancel: observado 9× — mais próximo: action.attend, action.buy, action.maintain
- Candidato action.reserve: observado 9× — mais próximo: action.attend, action.buy, action.maintain
- Priorizar aliases em SEMANTIC_HINTS/prompt antes de novos seeds CORE

### Actions & events — full vocabulary

| key | kind | parent | description | aliases | exposed_to_llm |
| --- | --- | --- | --- | --- | --- |
| `event.maintenance` | event_type | — | Manutenção | Manutenção | True |
| `event.vehicle_maintenance` | event_type | event.maintenance | manutenção/gastos realizados em veículo | Manutenção veicular | True |
| `event.appointment` | event_type | — | compromisso agendado (consulta, reunião) | Consulta | True |
| `event.obligation` | event_type | — | Obrigação | Obrigação | True |
| `event.recurring_bill` | event_type | event.obligation | conta recorrente (internet, assinatura) | Conta recorrente | True |
| `event.payment` | event_type | — | ato de pagamento; não cobre todo gasto monetário genérico | Pagamento | True |
| `event.purchase` | event_type | — | Compra | Compra | True |
| `event.intent` | event_type | — | Intenção | Intenção | True |
| `action.maintain` | action | — | Manter | Manter | True |
| `action.oil_change` | action | action.maintain | Troca de óleo | Troca de óleo | True |
| `action.replace` | action | action.maintain | Trocar | Trocar | True |
| `action.attend` | action | — | Comparecer | Comparecer | True |
| `action.pay` | action | — | Pagar | Pagar | True |
| `action.buy` | action | — | Comprar | Comprar | True |
