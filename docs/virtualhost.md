# Jamesbrain — virtual hosts e portas

O **Portal** permanece em `james/` e **não** mora neste diretório.

Componentes **dentro** do Jamesbrain (nomes = host):

```text
Jamesbrain/
├── core/     →  core.james.sandbox.momsys.com.br
├── pke/      →  pke.james.sandbox.momsys.com.br
└── tools/    →  tools.james.sandbox.momsys.com.br
```

```text
Portal  →  james.sandbox.momsys.com.br
Core    →  core.james.sandbox.momsys.com.br
PKE     →  pke.james.sandbox.momsys.com.br
Tools   →  tools.james.sandbox.momsys.com.br
```

Apache (80/443) faz o proxy TLS. Os serviços Python escutam só em `127.0.0.1`.

## Mapa

| Papel | Host público | Pasta | Processo | Bind (proxy) |
|-------|----------------|-------|----------|----------------|
| **Portal** | `james.sandbox.momsys.com.br` | `james/` (fora do Jamesbrain) | Apache + PHP MOMSYS | `:80` / `:443` → `james/public` |
| **Core** | `core.james.sandbox.momsys.com.br` | `Jamesbrain/core/` | `python -m jamescore` | `127.0.0.1:8010` |
| **PKE** | `pke.james.sandbox.momsys.com.br` | `Jamesbrain/pke/` | `python -m pke.product` (instância James) | `127.0.0.1:8008` |
| **Tools** | `tools.james.sandbox.momsys.com.br` | `Jamesbrain/tools/` | reservado (sem Tool real no J1.1) | `127.0.0.1:8011` |

Pacotes Python internos continuam `jamescore` e `pke`. As **pastas** no Jamesbrain são `core`, `pke`, `tools`.

Alias de transição: `pke.sandbox.momsys.com.br` aponta para o mesmo backend PKE (`:8008`). O host canônico é `pke.james.sandbox.momsys.com.br`.

## Portas de execução

| Porta | Serviço | Como sobe | Observação |
|------:|---------|-----------|------------|
| 80 / 443 | Apache (todos os hosts acima) | XAMPP / `httpd` | TLS: `james/ssl/` (portal) e `Jamesbrain/ssl/` (core, pke, tools) |
| **8010** | Core | `Jamesbrain\core\start.bat` | Orquestrador. Portal PHP: `JAMESCORE_API_URL=http://127.0.0.1:8010` |
| **8008** | PKE (instância James) | `james\scripts\start_pke_james.bat` | SQLite em `james/data/pke/`. Core: `PKE_API_URL=http://127.0.0.1:8008` |
| **8011** | Tools | ainda não há daemon | Registry no Core permanece vazio. Proxy Apache já aponta para esta porta |
| 8000 | PKE genérico (`Jamesbrain\pke\start.bat`) | **não** é o host sandbox James | Só desenvolvimento avulso do engine |

## Proxy Apache (resumo)

```text
james.sandbox.momsys.com.br
    DocumentRoot  D:/00-LocalServer/htdocs/momsys/james/public

core.james.sandbox.momsys.com.br
    ProxyPass  /  http://127.0.0.1:8010/

pke.james.sandbox.momsys.com.br
    ProxyPass  /  http://127.0.0.1:8008/

tools.james.sandbox.momsys.com.br
    ProxyPass  /  http://127.0.0.1:8011/
```

## Hosts (Windows)

```text
127.0.0.1    james.sandbox.momsys.com.br
127.0.0.1    core.james.sandbox.momsys.com.br
127.0.0.1    pke.james.sandbox.momsys.com.br
127.0.0.1    tools.james.sandbox.momsys.com.br
```

Arquivo: `C:\Windows\System32\drivers\etc\hosts` (Administrador).

## Certificados

| Host | Cert |
|------|------|
| `james.sandbox.momsys.com.br` | `james/ssl/james.sandbox.momsys.com.br-*.pem` |
| core / pke / tools | `Jamesbrain/ssl/jamesbrain.sandbox-*.pem` (SAN dos três hosts) |

## Layout

```text
Jamesbrain/
├── docs/virtualhost.md
├── core/          orquestrador (python -m jamescore)
├── pke/           PKE v1 congelado (python -m pke.product)
├── tools/         domain Tools (conceitual no J1.1)
├── ssl/
└── www/           DocumentRoot vazio para o Apache (tráfego no ProxyPass)
```

## Depois de alterar vhost

Reiniciar Apache **como Administrador** (XAMPP ou `momsys\data\apache_restart.bat`).

```bat
C:\xampp\apache\bin\httpd.exe -t
```
