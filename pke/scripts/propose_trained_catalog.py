"""Treino assistido do catálogo canônico.

Imprime o prompt, valida JSON, ou pede proposta à LLM.
Nunca grava em approved.json — o revisor copia o que aprovar.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pke.ontology.trained import (  # noqa: E402
    PROPOSAL_JSON_SCHEMA,
    TrainedCatalogFile,
    TrainedConcept,
    approved_catalog_path,
    load_trained_catalog,
    render_training_prompt,
    trained_catalog_dir,
    validate_trained_catalog,
)

PROPOSED_PATH = trained_catalog_dir() / "proposed.json"


def _cmd_print_prompt(instruction: str) -> int:
    print(render_training_prompt(extra_instruction=instruction))
    return 0


def _load_proposed_concepts(path: Path) -> list[TrainedConcept]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "catalog_proposal" in payload:
        raw = payload["catalog_proposal"].get("concepts") or []
    elif "concepts" in payload:
        raw = payload["concepts"]
    else:
        raise SystemExit(f"JSON sem catalog_proposal.concepts nem concepts: {path}")
    return [TrainedConcept.model_validate(item) for item in raw]


def _cmd_validate(path: Path | None) -> int:
    if path is None:
        load_trained_catalog()
        print(f"ok {approved_catalog_path()}")
        return 0
    incoming = _load_proposed_concepts(path)
    approved = load_trained_catalog()
    merged = TrainedCatalogFile(
        version=approved.version,
        concepts=[*approved.concepts, *incoming],
    )
    problems = validate_trained_catalog(merged)
    if problems:
        print("falhou:")
        for item in problems:
            print(f"  - {item}")
        return 1
    print(f"ok {path} ({len(incoming)} conceitos, sem colisão com approved+CORE)")
    return 0


def _cmd_propose(instruction: str) -> int:
    from pke.llm.config import DeepSeekConfig
    from pke.llm.deepseek import DeepSeekProvider
    from pke.llm.models import LlmMessage, LlmStructuredRequest

    prompt = render_training_prompt(extra_instruction=instruction)
    cfg = DeepSeekConfig.from_env(timeout_seconds=90.0)
    provider = DeepSeekProvider(cfg)
    try:
        response = provider.generate_structured(
            LlmStructuredRequest(
                messages=[
                    LlmMessage(role="system", content=prompt),
                    LlmMessage(
                        role="user",
                        content=(
                            "Proponha verbetes novos ou extends_core. "
                            "JSON no envelope catalog_proposal. Schema:\n"
                            + json.dumps(PROPOSAL_JSON_SCHEMA, ensure_ascii=False)
                        ),
                    ),
                ],
                json_schema=PROPOSAL_JSON_SCHEMA,
                schema_name="TrainedCatalogProposal",
            )
        )
    finally:
        provider.close()
    payload = json.loads(response.content)
    PROPOSED_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"proposta em {PROPOSED_PATH}")
    print("Revise e copie para approved.json só o que aprovar. Depois: --validate")
    return _cmd_validate(PROPOSED_PATH)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--print-prompt",
        action="store_true",
        help="Imprime o prompt preenchido com CORE + catálogo atual",
    )
    parser.add_argument(
        "--validate",
        nargs="?",
        const="",
        default=None,
        help="Valida approved.json, ou o JSON informado (proposta)",
    )
    parser.add_argument(
        "--propose",
        action="store_true",
        help="Chama a LLM (DEEPSEEK_API_KEY) e grava proposed.json",
    )
    parser.add_argument(
        "--instruction",
        default="",
        help="Pedido extra (ex.: relações de família, ações do cotidiano)",
    )
    args = parser.parse_args()
    if args.print_prompt:
        return _cmd_print_prompt(args.instruction)
    if args.propose:
        return _cmd_propose(args.instruction)
    if args.validate is not None:
        path = Path(args.validate) if args.validate else None
        return _cmd_validate(path)
    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
