# jamesCore

Serviço de orquestração do James. **Não** é vertical PHP MOMSYS.

> Portal apresenta. jamesCore orquestra. PKE sabe. Tools observa.

Fronteira: `james/docs/JAMESCORE-ARCHITECTURE.md`.

## J1.1

- Orchestrator, identidade, conversa James, Social, PkeClient, envelope público, health
- **Tool Registry vazio** (`src/jamescore/tooling/`) — contratos/gateway, não as Tools
- PKE **não** entra no Tool Registry
- Sem Weather, Search, Scheduler, Notifications
- PKE v1 congelado

## Subir

```bat
Jamesbrain\core\start.bat
```

API: `http://127.0.0.1:8010` — `GET /v1/health`, `POST /v1/turns`.

Portal (`james/.env`): `JAMESCORE_API_URL` e o mesmo `JAMESCORE_ASSERTION_SECRET`.
