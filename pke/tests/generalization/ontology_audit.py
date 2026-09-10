"""I11.1 — Ontology Coverage & Expressiveness Audit (somente leitura)."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from pke.domain.ontology import ConceptKind
from pke.interpretation.ontology_view import InterpreterOntologyView
from pke.interpretation.semantic_hints import SEMANTIC_HINTS
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology.registry import OntologyRegistry

from tests.generalization.cases import DEVELOPMENT_CASES
from tests.generalization.semantic_demand import (
    CASE_SEMANTIC_DEMAND,
    POLYSEMOUS_EXPRESSIONS,
    SEMANTIC_NEEDS,
    DemandCategory,
    SemanticNeed,
)

_KIND_INVENTORY_MAP = {
    ConceptKind.ENTITY_TYPE: "entity",
    ConceptKind.EVENT_TYPE: "event",
    ConceptKind.ACTION: "action",
    ConceptKind.RELATION_TYPE: "relation",
    ConceptKind.ATTRIBUTE: "attribute",
    ConceptKind.STATE_DIMENSION: "state_dimension",
    ConceptKind.STATE_VALUE: "state_value",
    ConceptKind.DOMAIN: "domain",
    ConceptKind.ROLE: "other",
}


class CoverageClass(StrEnum):
    DIRECT = "DIRECT"
    ALIAS_NEEDED = "ALIAS_NEEDED"
    GENERALIZABLE = "GENERIZABLE"
    NEW_CONCEPT_CANDIDATE = "NEW_CONCEPT_CANDIDATE"
    REPRESENTATION_GAP = "REPRESENTATION_GAP"


@dataclass
class ConceptRow:
    key: str
    kind: str
    parent: str | None
    description: str
    aliases: list[str]
    exposed_to_llm: bool
    depth: int


@dataclass
class CoverageResult:
    need_id: str
    category: str
    description: str
    canonical_key: str | None
    classification: CoverageClass
    nearest_concepts: list[str] = field(default_factory=list)
    case_ids: list[str] = field(default_factory=list)


@dataclass
class ConceptCandidate:
    proposed_kind: str
    proposed_meaning: str
    observed_surface_forms: list[str]
    observed_llm_keys: list[str]
    existing_nearest_concepts: list[str]
    occurrences: int


@dataclass
class AliasCandidate:
    surface_forms: list[str]
    canonical_candidate: str
    classification: str = "CANONICAL_ALIAS_CANDIDATE"


_KEY_RE = re.compile(r"\b((?:action|event|entity|attribute|domain|relation|role)\.[a-z][a-z0-9_.]*)\b")


def inventory_core(registry: OntologyRegistry) -> dict[str, Any]:
    ConceptCatalog.load(registry)
    view = InterpreterOntologyView.from_registry(registry)
    exposed = {c.key for c in view.concepts}
    by_id = {c.id: c for c in registry.concepts()}
    counts: Counter[str] = Counter()
    max_depth = 0
    rows: list[ConceptRow] = []

    for concept in registry.concepts():
        bucket = _KIND_INVENTORY_MAP.get(concept.kind, "other")
        counts[bucket] += 1
        parent_key = None
        depth = 0
        current = concept
        seen: set[str] = set()
        while current.parent_id and current.parent_id not in seen:
            seen.add(current.parent_id)
            depth += 1
            parent = by_id.get(current.parent_id)
            if parent is None:
                break
            parent_key = parent.key if parent_key is None else parent_key
            current = parent
        max_depth = max(max_depth, depth)
        label = concept.presentation.label if concept.presentation else ""
        hint = SEMANTIC_HINTS.get(concept.key, "")
        desc = hint or label or ""
        aliases: list[str] = []
        if label and label.lower() not in concept.key:
            aliases.append(label)
        rows.append(
            ConceptRow(
                key=concept.key,
                kind=concept.kind.value,
                parent=parent_key,
                description=desc,
                aliases=aliases,
                exposed_to_llm=concept.key in exposed,
                depth=depth,
            )
        )

    catalog_exposed = {
        "entity_types": sorted(ConceptCatalog.entity_types),
        "event_types": sorted(ConceptCatalog.event_types),
        "actions": sorted(ConceptCatalog.actions),
        "attributes": sorted(ConceptCatalog.attributes),
        "domains": sorted(ConceptCatalog.domains),
        "roles": sorted(ConceptCatalog.roles),
    }

    return {
        "total": len(rows),
        "by_kind": dict(counts),
        "max_hierarchy_depth": max_depth,
        "registry_aliases": sum(len(r.aliases) for r in rows),
        "semantic_hints_count": len(SEMANTIC_HINTS),
        "exposed_to_llm_count": sum(1 for r in rows if r.exposed_to_llm),
        "catalog_exposed": catalog_exposed,
        "rows": rows,
    }


def _classify_need(need: SemanticNeed, registry: OntologyRegistry) -> CoverageResult:
    if need.representation_note:
        return CoverageResult(
            need.need_id,
            need.category.value,
            need.description,
            need.canonical_key,
            CoverageClass.REPRESENTATION_GAP,
            nearest_concepts=_nearest(need, registry),
        )
    key = need.canonical_key
    if key and registry.exists(key):
        if need.surface_forms and not _surfaces_covered(need, key, registry):
            return CoverageResult(
                need.need_id,
                need.category.value,
                need.description,
                key,
                CoverageClass.ALIAS_NEEDED,
                nearest_concepts=[key],
            )
        return CoverageResult(
            need.need_id,
            need.category.value,
            need.description,
            key,
            CoverageClass.DIRECT,
            nearest_concepts=[key],
        )
    if need.generalizable_parent and registry.exists(need.generalizable_parent):
        return CoverageResult(
            need.need_id,
            need.category.value,
            need.description,
            need.canonical_key,
            CoverageClass.GENERALIZABLE,
            nearest_concepts=[need.generalizable_parent],
        )
    parent = need.generalizable_parent or _infer_parent_prefix(need)
    if parent and registry.exists(parent):
        return CoverageResult(
            need.need_id,
            need.category.value,
            need.description,
            need.canonical_key,
            CoverageClass.GENERALIZABLE,
            nearest_concepts=[parent],
        )
    return CoverageResult(
        need.need_id,
        need.category.value,
        need.description,
        need.canonical_key,
        CoverageClass.NEW_CONCEPT_CANDIDATE,
        nearest_concepts=_nearest(need, registry),
    )


def _surfaces_covered(need: SemanticNeed, key: str, registry: OntologyRegistry) -> bool:
    concept = registry.get_by_key(key)
    if concept is None:
        return False
    label = (concept.presentation.label or "").lower() if concept.presentation else ""
    hint = SEMANTIC_HINTS.get(key, "").lower()
    corpus = f"{label} {hint} {key}"
    return any(s.lower() in corpus for s in need.surface_forms)


def _infer_parent_prefix(need: SemanticNeed) -> str | None:
    if need.category is DemandCategory.ACTION:
        return "action.maintain"
    if need.category is DemandCategory.EVENT:
        return "event.maintenance"
    return None


def _nearest(need: SemanticNeed, registry: OntologyRegistry) -> list[str]:
    prefix = {
        DemandCategory.ACTION: "action.",
        DemandCategory.EVENT: "event.",
        DemandCategory.ENTITY: "entity.",
        DemandCategory.RELATION: "relation.",
        DemandCategory.ATTRIBUTE: "attribute.",
        DemandCategory.DOMAIN: "domain.",
    }.get(need.category, "")
    if not prefix:
        return []
    return sorted(c.key for c in registry.concepts() if c.key.startswith(prefix))[:5]


def benchmark_demand_coverage(registry: OntologyRegistry) -> list[CoverageResult]:
    need_to_cases: dict[str, list[str]] = defaultdict(list)
    for case_id, need_ids in CASE_SEMANTIC_DEMAND.items():
        for nid in need_ids:
            need_to_cases[nid].append(case_id)
    results: list[CoverageResult] = []
    seen: set[str] = set()
    for case in DEVELOPMENT_CASES:
        for nid in CASE_SEMANTIC_DEMAND.get(case.case_id, ()):
            if nid in seen:
                continue
            seen.add(nid)
            need = SEMANTIC_NEEDS[nid]
            row = _classify_need(need, registry)
            row.case_ids = need_to_cases.get(nid, [])
            results.append(row)
    return sorted(results, key=lambda r: (r.category, r.need_id))


def compute_coverage_metrics(coverage: list[CoverageResult]) -> dict[str, float]:
    def rate(cat: str) -> float:
        subset = [c for c in coverage if c.category == cat]
        if not subset:
            return 1.0
        ok = sum(1 for c in subset if c.classification in {CoverageClass.DIRECT, CoverageClass.GENERALIZABLE})
        return round(ok / len(subset), 4)

    direct_or_gen = sum(
        1 for c in coverage if c.classification in {CoverageClass.DIRECT, CoverageClass.GENERALIZABLE}
    )
    total = len(coverage) or 1
    alias_ok = sum(1 for c in coverage if c.classification is CoverageClass.ALIAS_NEEDED)
    return {
        "overall_concept_coverage": round(direct_or_gen / total, 4),
        "action_coverage": rate("action"),
        "event_coverage": rate("event"),
        "state_coverage": rate("state"),
        "relation_coverage": rate("relation"),
        "entity_type_coverage": rate("entity"),
        "alias_coverage": round((direct_or_gen + alias_ok) / total, 4),
        "new_concept_candidates": sum(
            1 for c in coverage if c.classification is CoverageClass.NEW_CONCEPT_CANDIDATE
        ),
        "representation_gaps": sum(
            1 for c in coverage if c.classification is CoverageClass.REPRESENTATION_GAP
        ),
        "alias_gaps": alias_ok,
    }


def extract_llm_keys_from_baseline(runs: list[dict]) -> Counter[str]:
    keys: Counter[str] = Counter()
    for row in runs:
        summary = row.get("ir_summary")
        if summary:
            if summary.get("event_type"):
                keys[summary["event_type"]] += 1
            if summary.get("action"):
                keys[summary["action"]] += 1
            for d in summary.get("domains") or []:
                keys[d] += 1
        for fail in row.get("semantic_fails") or []:
            keys.update(_KEY_RE.findall(str(fail)))
    return keys


def cluster_concept_candidates(
    llm_keys: Counter[str],
    registry: OntologyRegistry,
    coverage: list[CoverageResult],
) -> list[ConceptCandidate]:
    unknown = {k: v for k, v in llm_keys.items() if not registry.exists(k)}
    clusters: dict[str, ConceptCandidate] = {}
    for key, count in unknown.items():
        kind = key.split(".", 1)[0]
        stem = key.split(".")[-1]
        cluster_id = f"{kind}.{stem}"
        if cluster_id not in clusters:
            clusters[cluster_id] = ConceptCandidate(
                proposed_kind=kind,
                proposed_meaning=stem.replace("_", " "),
                observed_surface_forms=[],
                observed_llm_keys=[],
                existing_nearest_concepts=_nearest_by_kind(kind, registry),
                occurrences=0,
            )
        c = clusters[cluster_id]
        c.observed_llm_keys.append(key)
        c.occurrences += count

    for cov in coverage:
        if cov.classification is CoverageClass.NEW_CONCEPT_CANDIDATE:
            cid = cov.need_id.replace("need.", "")
            if cid not in clusters:
                need = SEMANTIC_NEEDS[cov.need_id]
                clusters[cid] = ConceptCandidate(
                    proposed_kind=need.category.value,
                    proposed_meaning=need.description,
                    observed_surface_forms=list(need.surface_forms),
                    observed_llm_keys=[],
                    existing_nearest_concepts=cov.nearest_concepts,
                    occurrences=len(cov.case_ids),
                )

    return sorted(clusters.values(), key=lambda c: -c.occurrences)


def _nearest_by_kind(kind_prefix: str, registry: OntologyRegistry) -> list[str]:
    return sorted(c.key for c in registry.concepts() if c.key.startswith(f"{kind_prefix}."))[:5]


def alias_candidates_from_needs(coverage: list[CoverageResult]) -> list[AliasCandidate]:
    out: list[AliasCandidate] = []
    for cov in coverage:
        if cov.classification is not CoverageClass.ALIAS_NEEDED and cov.canonical_key:
            need = SEMANTIC_NEEDS.get(cov.need_id)
            if need and need.surface_forms and cov.canonical_key:
                if cov.classification is CoverageClass.DIRECT:
                    continue
        if cov.classification is CoverageClass.ALIAS_NEEDED and cov.canonical_key:
            need = SEMANTIC_NEEDS[cov.need_id]
            out.append(
                AliasCandidate(
                    surface_forms=list(need.surface_forms),
                    canonical_candidate=cov.canonical_key,
                )
            )
    replace_need = SEMANTIC_NEEDS["need.action.replace"]
    out.append(
        AliasCandidate(
            surface_forms=list(replace_need.surface_forms),
            canonical_candidate="action.replace",
        )
    )
    return out


def duplicate_concept_warnings(registry: OntologyRegistry) -> list[str]:
    warnings: list[str] = []
    events = [c for c in registry.concepts() if c.kind is ConceptKind.EVENT_TYPE]
    for a, b in [("event.maintenance", "event.vehicle_maintenance"), ("event.obligation", "event.recurring_bill")]:
        if registry.exists(a) and registry.exists(b):
            warnings.append(f"{a} vs {b}: hierarquia pai/filho — não duplicar, usar GENERALIZABLE")
    return warnings


def recommended_evolution(
    coverage: list[CoverageResult],
    candidates: list[ConceptCandidate],
) -> list[str]:
    recs: list[str] = []
    new_actions = [c for c in coverage if c.category == "action" and c.classification is CoverageClass.NEW_CONCEPT_CANDIDATE]
    if new_actions:
        samples = [SEMANTIC_NEEDS[x.need_id].description for x in new_actions[:5]]
        recs.append(f"Expandir família action.maintain com: {', '.join(samples)}")
    if any(c.classification is CoverageClass.REPRESENTATION_GAP for c in coverage if c.category == "state"):
        recs.append("STATE/relation não têm kind no wire — avaliar primitives IR antes de novos conceitos CORE")
    if any(c.classification is CoverageClass.REPRESENTATION_GAP for c in coverage if c.category == "relation"):
        recs.append("Adicionar relation.employment / relation.residence como candidatos EXTENDED, não CORE imediato")
    for cand in candidates[:5]:
        if cand.occurrences >= 2:
            recs.append(
                f"Candidato {cand.proposed_kind}.{cand.proposed_meaning}: observado {cand.occurrences}× — "
                f"mais próximo: {', '.join(cand.existing_nearest_concepts[:3]) or 'nenhum'}"
            )
    recs.append("Priorizar aliases em SEMANTIC_HINTS/prompt antes de novos seeds CORE")
    return recs


def run_audit(baseline_path: Path | None = None) -> dict[str, Any]:
    registry = OntologyRegistry.with_core_seeds()
    inventory = inventory_core(registry)
    coverage = benchmark_demand_coverage(registry)
    metrics = compute_coverage_metrics(coverage)

    runs: list[dict] = []
    if baseline_path and baseline_path.is_file():
        data = json.loads(baseline_path.read_text(encoding="utf-8"))
        runs = data.get("runs", [])

    llm_keys = extract_llm_keys_from_baseline(runs)
    candidates = cluster_concept_candidates(llm_keys, registry, coverage)
    aliases = alias_candidates_from_needs(coverage)

    demand_by_category: dict[str, list[str]] = defaultdict(list)
    for case_id, nids in CASE_SEMANTIC_DEMAND.items():
        for nid in nids:
            demand_by_category[SEMANTIC_NEEDS[nid].category.value].append(nid)
    for k in demand_by_category:
        demand_by_category[k] = sorted(set(demand_by_category[k]))

    return {
        "inventory": inventory,
        "coverage": coverage,
        "metrics": metrics,
        "llm_key_observations": dict(llm_keys.most_common(30)),
        "concept_candidates": candidates,
        "alias_candidates": aliases,
        "polysemy": list(POLYSEMOUS_EXPRESSIONS),
        "duplicate_warnings": duplicate_concept_warnings(registry),
        "recommendations": recommended_evolution(coverage, candidates),
        "demand_by_category": dict(demand_by_category),
    }


def render_audit_markdown(audit: dict[str, Any]) -> str:
    inv = audit["inventory"]
    metrics = audit["metrics"]
    lines = [
        "## Ontology Coverage & Expressiveness Audit (I11.1)",
        "",
        "### Current ontology size",
        "",
        f"- **Total CORE concepts:** {inv['total']}",
        f"- **Max hierarchy depth:** {inv['max_hierarchy_depth']}",
        f"- **Exposed to LLM (InterpreterOntologyView):** {inv['exposed_to_llm_count']}",
        f"- **Registry presentation labels (aliases):** {inv['registry_aliases']}",
        f"- **SEMANTIC_HINTS (interpreter-only):** {inv['semantic_hints_count']}",
        "",
        "| kind | count |",
        "| --- | --- |",
    ]
    for kind in ("entity", "event", "action", "state", "relation", "attribute", "domain", "other"):
        lines.append(f"| {kind} | {inv['by_kind'].get(kind, 0)} |")
    lines.append("")
    lines.append("**ConceptCatalog exposto ao wire:**")
    for bucket, keys in inv["catalog_exposed"].items():
        lines.append(f"- `{bucket}`: {len(keys)} keys")

    lines.extend(["", "### Benchmark semantic demand", ""])
    for cat, nids in sorted(audit["demand_by_category"].items()):
        lines.append(f"**{cat}** ({len(nids)} necessidades): " + ", ".join(nids))

    lines.extend(["", "### Concept coverage", "", "| need | class | canonical | cases |", "| --- | --- | --- | --- |"])
    for cov in audit["coverage"]:
        lines.append(
            f"| `{cov.need_id}` | {cov.classification.value} | {cov.canonical_key or '—'} | {', '.join(cov.case_ids[:3])} |"
        )

    lines.extend(["", "### Coverage metrics", "", "| metric | value |", "| --- | --- |"])
    for k, v in metrics.items():
        if isinstance(v, float) and v <= 1:
            lines.append(f"| {k} | {v:.1%} |")
        else:
            lines.append(f"| {k} | {v} |")

    lines.extend(
        [
            "",
            "_Separação: falta de conceito (NEW_CONCEPT_CANDIDATE) ≠ falta de alias (ALIAS_NEEDED) ≠ erro LLM (baseline semantic_accuracy)_",
            "",
            "### Alias gaps",
            "",
        ]
    )
    for alias in audit["alias_candidates"]:
        lines.append(
            f"- **{alias.canonical_candidate}** ← {', '.join(alias.surface_forms[:6])} (`{alias.classification}`)"
        )

    lines.extend(["", "### New concept candidates", ""])
    for cand in audit["concept_candidates"]:
        if cand.observed_llm_keys or cand.observed_surface_forms:
            lines.append(
                f"- **{cand.proposed_kind}** / {cand.proposed_meaning} "
                f"(×{cand.occurrences}) LLM keys: {cand.observed_llm_keys or '—'} "
                f"| surfaces: {cand.observed_surface_forms[:4]} "
                f"| nearest: {', '.join(cand.existing_nearest_concepts[:3])}"
            )

    lines.extend(["", "### Representation gaps", ""])
    for cov in audit["coverage"]:
        if cov.classification is CoverageClass.REPRESENTATION_GAP:
            need = SEMANTIC_NEEDS[cov.need_id]
            lines.append(f"- `{cov.need_id}`: {need.representation_note}")

    lines.extend(["", "### Potential duplicate concepts", ""])
    for w in audit["duplicate_warnings"]:
        lines.append(f"- {w}")

    lines.extend(["", "### Polysemous expressions", ""])
    for p in audit["polysemy"]:
        lines.append(f"- **{p['surface']}**: {p['senses']} _(ex.: {p['benchmark_examples']})_")

    lines.extend(["", "### Recommended ontology evolution (proposals only)", ""])
    for r in audit["recommendations"]:
        lines.append(f"- {r}")

    lines.extend(["", "### Actions & events — full vocabulary", ""])
    lines.append("| key | kind | parent | description | aliases | exposed_to_llm |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for row in inv["rows"]:
        if row.kind in {"action", "event_type"}:
            lines.append(
                f"| `{row.key}` | {row.kind} | {row.parent or '—'} | {row.description or '—'} | "
                f"{', '.join(row.aliases) or '—'} | {row.exposed_to_llm} |"
            )

    return "\n".join(lines) + "\n"
