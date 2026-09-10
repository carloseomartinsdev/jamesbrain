"""Gera seção I11.1 Ontology Audit e anexa ao relatório baseline."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from tests.generalization.ontology_audit import render_audit_markdown, run_audit

ROOT = Path(__file__).resolve().parents[2]
BASELINE_MD = ROOT / "docs" / "reports" / "I11-GENERALIZATION-BASELINE.md"
BASELINE_JSON = ROOT / "docs" / "reports" / "I11-GENERALIZATION-BASELINE.json"
AUDIT_JSON = ROOT / "docs" / "reports" / "I11-ONTOLOGY-AUDIT.json"
MARKER = "## Ontology Coverage & Expressiveness Audit (I11.1)"


def main() -> int:
    audit = run_audit(BASELINE_JSON if BASELINE_JSON.is_file() else None)
    AUDIT_JSON.write_text(json.dumps(_serialize(audit), ensure_ascii=False, indent=2), encoding="utf-8")

    section = render_audit_markdown(audit)
    if BASELINE_MD.is_file():
        text = BASELINE_MD.read_text(encoding="utf-8")
        if MARKER in text:
            text = text.split(MARKER)[0].rstrip() + "\n\n"
        text = text.rstrip() + "\n\n" + section
    else:
        text = "# I11 — Generalization Baseline\n\n" + section
    BASELINE_MD.write_text(text, encoding="utf-8")

    print(f"audit_json={AUDIT_JSON}", flush=True)
    print(f"report={BASELINE_MD}", flush=True)
    print(json.dumps(audit["metrics"], ensure_ascii=False), flush=True)
    return 0


def _serialize(audit: dict) -> dict:
    return {
        "metrics": audit["metrics"],
        "inventory": {
            "total": audit["inventory"]["total"],
            "by_kind": audit["inventory"]["by_kind"],
            "max_hierarchy_depth": audit["inventory"]["max_hierarchy_depth"],
            "exposed_to_llm_count": audit["inventory"]["exposed_to_llm_count"],
            "catalog_exposed": audit["inventory"]["catalog_exposed"],
        },
        "coverage": [
            {
                "need_id": c.need_id,
                "classification": c.classification.value,
                "canonical_key": c.canonical_key,
                "case_ids": c.case_ids,
            }
            for c in audit["coverage"]
        ],
        "llm_key_observations": audit["llm_key_observations"],
        "concept_candidates": [
            {
                "proposed_kind": c.proposed_kind,
                "proposed_meaning": c.proposed_meaning,
                "observed_llm_keys": c.observed_llm_keys,
                "occurrences": c.occurrences,
            }
            for c in audit["concept_candidates"]
        ],
        "recommendations": audit["recommendations"],
    }


if __name__ == "__main__":
    raise SystemExit(main())
