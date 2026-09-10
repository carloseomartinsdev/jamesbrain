# PKE — Personal Knowledge Engine

Motor que transforma linguagem cotidiana em conhecimento estruturado, validado e consultável.

Documento canônico da Onda 1: [`docs/PKE-FOUNDATION-ONDA-1.md`](docs/PKE-FOUNDATION-ONDA-1.md).

## Princípios

> Texto é representação; conceitos têm identidade.
>
> LLM interpreta. PKE raciocina. Storage persiste.

A LLM nunca escreve no banco. Toda interpretação passa por um contrato tipado (`IngestIR` / `QueryIR`).

Decisões: [`docs/decisions/0001-principios.md`](docs/decisions/0001-principios.md).

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

## Onda 1

Incremento atual: **skeleton + primitivas de domínio + representação intermediária**.

Ainda não há persistência, resolution, ontology registry nem interpreter LLM.
