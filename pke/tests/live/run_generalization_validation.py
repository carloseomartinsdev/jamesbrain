"""I11 — primeira rodada do development set (3 runs/caso). Holdout não executado."""

from __future__ import annotations

import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from pke.interpretation import DeepSeekInterpreter
from pke.interpretation.prompts import PROMPT_VERSION_V2
from pke.llm import DeepSeekConfig, DeepSeekProvider
from pke.ontology import OntologyRegistry

from tests.generalization.cases import DEVELOPMENT_CASES, FailureCategory, SupportLevel
from tests.generalization.evaluator import (
    GeneralizationEvaluator,
    bucket_by,
    compute_global_metrics,
    make_context,
)
from tests.live.run_i10_validation import load_env_silent

RUNS = 3
REPORT_PATH = Path(__file__).resolve().parents[2] / "docs" / "reports" / "I11-GENERALIZATION-BASELINE.md"
JSON_PATH = Path(__file__).resolve().parents[2] / "docs" / "reports" / "I11-GENERALIZATION-BASELINE.json"


def _scrub(text: str) -> str:
    for marker in ("sk-", "Bearer ", "DEEPSEEK_API_KEY="):
        if marker.lower() in text.lower():
            return "[redacted]"
    return text


def _md_table(rows: list[tuple[str, ...]], headers: tuple[str, ...]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return "\n".join(lines)


def build_report(
    *,
    all_runs: list,
    aggregates: dict,
    metrics: dict,
    model: str,
) -> str:
    dev_cases = list(DEVELOPMENT_CASES)
    stable = sum(1 for a in aggregates.values() if a.stability.endswith(" stable"))
    unstable = sum(1 for a in aggregates.values() if "unstable" in a.stability)
    weak = sum(1 for a in aggregates.values() if "weak" in a.stability)
    failed = sum(1 for a in aggregates.values() if "failed" in a.stability)

    ontology_gaps = [
        c.case_id
        for c in dev_cases
        if any(
            r.failure_category == FailureCategory.ONTOLOGY_GAP
            for r in all_runs
            if r.case_id == c.case_id
        )
    ]
    core_gaps = [c.case_id for c in dev_cases if c.support_level is SupportLevel.UNSUPPORTED]
    context_gaps = [
        c.case_id
        for c in dev_cases
        if c.support_level is SupportLevel.PARTIALLY_SUPPORTED
        or any(
            r.failure_category == FailureCategory.CONTEXT_GAP
            for r in all_runs
            if r.case_id == c.case_id
        )
    ]
    atemporal = [c.case_id for c in dev_cases if c.atemporal_knowledge_candidate]

    by_domain = bucket_by("domain_hint", dev_cases, aggregates)
    by_structure = bucket_by("sentence_structure", dev_cases, aggregates)
    by_action = bucket_by("action_type", dev_cases, aggregates)

    failures: list = []
    for case in dev_cases:
        agg = aggregates[case.case_id]
        if agg.pass_count < agg.total_runs and agg.representative_failure:
            r = agg.representative_failure
            failures.append((case, r, agg))

    domain_rows = [
        (k, v["cases"], v["stable"], v["unstable"], v["weak"], v["failed"])
        for k, v in sorted(by_domain.items())
    ]
    struct_rows = [
        (k, v["cases"], v["stable"], v["unstable"], v["weak"], v["failed"])
        for k, v in sorted(by_structure.items())
    ]
    action_rows = [
        (k or "(unspecified)", v["cases"], v["stable"], v["unstable"], v["weak"], v["failed"])
        for k, v in sorted(by_action.items())
    ]

    fail_sections = []
    for case, r, agg in failures[:25]:
        fail_sections.append(
            f"### {case.case_id}\n\n"
            f"- **Input:** {case.raw_text}\n"
            f"- **Stability:** {agg.stability}\n"
            f"- **Category:** {r.failure_category.value if r.failure_category else 'SEMANTIC'}\n"
            f"- **Error:** {_scrub(r.error_message or '')}\n"
            f"- **Semantic fails:** {r.semantic_fails}\n"
            f"- **Forbidden:** {r.forbidden_hits}\n"
            f"- **IR summary:** `{json.dumps(r.ir_summary, ensure_ascii=False) if r.ir_summary else None}`\n"
            f"- **Raw preview:** ```\n{_scrub(r.raw_content_preview or '')[:800]}\n```\n"
        )

    cat_counter = Counter(
        r.failure_category.value for r in all_runs if r.failure_category is not None
    )
    patterns = ", ".join(f"{k}={v}" for k, v in cat_counter.most_common())

    return f"""# I11 — Generalization Baseline (Development Set)

**Gerado:** {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}  
**Model:** {model}  
**Prompt:** {PROMPT_VERSION_V2}  
**Holdout:** não executado (reservado)

## Resumo

| Métrica | Valor |
|---------|-------|
| Casos development | {len(dev_cases)} |
| Runs totais | {metrics['total_runs']} |
| Provider JSON validity | {metrics['provider_json_valid_rate']:.1%} |
| Wire validity | {metrics['wire_valid_rate']:.1%} |
| Canonical validity | {metrics['canonical_valid_rate']:.1%} |
| Semantic pass rate | {metrics['semantic_accuracy']:.1%} |
| Forbidden inference rate | {metrics['forbidden_inference_rate']:.1%} |
| Unsupported rate | {metrics['unsupported_rate']:.1%} |

### Estabilidade (por caso, {RUNS} runs)

| Bucket | Casos |
|--------|-------|
| 3/3 stable | {stable} |
| 2/3 acceptable but unstable | {unstable} |
| 1/3 weak | {weak} |
| 0/3 failed | {failed} |

## Por domínio

{_md_table(domain_rows, ("domain", "cases", "stable", "unstable", "weak", "failed"))}

## Por construção linguística

{_md_table(struct_rows, ("structure", "cases", "stable", "unstable", "weak", "failed"))}

## Por ação

{_md_table(action_rows, ("action", "cases", "stable", "unstable", "weak", "failed"))}

## Gaps identificados

- **Ontology gaps:** {", ".join(ontology_gaps) or "nenhum marcado nesta rodada"}
- **Core capability gaps:** {", ".join(core_gaps) or "nenhum"}
- **Context gaps (PARTIALLY_SUPPORTED):** {", ".join(context_gaps) or "nenhum"}
- **ATEMPORAL_KNOWLEDGE_CANDIDATE:** {", ".join(atemporal) or "nenhum"}

## Padrões de erro

{patterns or "nenhum padrão dominante"}

## Falhas representativas

{"".join(fail_sections) if fail_sections else "_Nenhuma falha parcial registrada._"}

---

*Experimento I11 — nenhuma alteração de prompt, wire, ontology ou Core nesta rodada.*
"""


def main() -> int:
    load_env_silent()
    if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
        print("ABORT: DEEPSEEK_API_KEY ausente")
        return 2

    config = DeepSeekConfig.from_env(timeout_seconds=90.0)
    ontology = OntologyRegistry.with_core_seeds()
    interpreter = DeepSeekInterpreter(
        DeepSeekProvider(config), ontology, prompt_version=PROMPT_VERSION_V2
    )
    evaluator = GeneralizationEvaluator(interpreter, make_context())

    all_runs = []
    aggregates = {}
    print(f"I11 development set: {len(DEVELOPMENT_CASES)} cases × {RUNS} runs", flush=True)

    for case in DEVELOPMENT_CASES:
        runs = evaluator.evaluate_case(case, runs=RUNS)
        all_runs.extend(runs)
        agg = evaluator.aggregate_case(case, runs)
        aggregates[case.case_id] = agg
        print(f"  {case.case_id} {agg.stability} ({agg.pass_count}/{agg.total_runs})", flush=True)

    metrics = compute_global_metrics(all_runs)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    md = build_report(
        all_runs=all_runs,
        aggregates=aggregates,
        metrics=metrics,
        model=config.model,
    )
    REPORT_PATH.write_text(md, encoding="utf-8")

    payload = {
        "model": config.model,
        "prompt_version": PROMPT_VERSION_V2,
        "development_cases": len(DEVELOPMENT_CASES),
        "holdout_executed": False,
        "runs_per_case": RUNS,
        "metrics": metrics,
        "aggregates": {
            k: {
                "pass_count": v.pass_count,
                "total_runs": v.total_runs,
                "stability": v.stability,
                "failure_categories": v.failure_categories,
            }
            for k, v in aggregates.items()
        },
        "runs": [
            {
                "case_id": r.case_id,
                "run": r.run,
                "text": r.text,
                "provider_json_valid": r.provider_json_valid,
                "wire_valid": r.wire_valid,
                "canonical_valid": r.canonical_valid,
                "semantic_required_pass": r.semantic_required_pass,
                "forbidden_inference_count": r.forbidden_inference_count,
                "failure_category": r.failure_category.value if r.failure_category else None,
                "semantic_fails": r.semantic_fails,
                "forbidden_hits": r.forbidden_hits,
                "error_class": r.error_class,
                "ir_summary": r.ir_summary,
            }
            for r in all_runs
        ],
    }
    JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"report={REPORT_PATH}", flush=True)
    print(f"json={JSON_PATH}", flush=True)
    print(json.dumps(metrics, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
