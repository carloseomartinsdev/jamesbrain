"""One-shot: freeze I12.14 clarification gap ledger from I12.11 baseline."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from pke.interpretation.semantic.capability_strategy import decide_capability
from pke.interpretation.semantic.execution_readiness import assess_execution_readiness
from pke.interpretation.semantic.models import SemanticProposal
from pke.interpretation.semantic.pipeline import resolve_proposal
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.ontology import OntologyRegistry

ConceptCatalog.load(OntologyRegistry.with_core_seeds())

ENTITY_SLOTS = {
    "measured_entity",
    "relation_subject",
    "relation_object",
    "state_entity",
    "attribute_entity",
}
SLOT_TO_FAMILY = {
    "state_value": "VALUE",
    "measurement_value": "VALUE",
    "attribute_value": "VALUE",
    "measurement_dimension": "DIMENSION",
    "attribute_dimension": "DIMENSION",
    "state_dimension": "DIMENSION",
    "correction_target": "CORRECTION_TARGET",
    "temporal": "TEMPORAL",
}

entries: list[dict] = []
seen_keys: Counter[str] = Counter()
root = Path(__file__).resolve().parents[1]
checkpoint = root / "docs/reports/i1211_artifacts/checkpoint.jsonl"

for line in checkpoint.read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    row = json.loads(line)
    if row.get("candidate_id") != "baseline_deepseek_chat" or not row.get("proposal_dump"):
        continue
    proposal = SemanticProposal.model_validate(row["proposal_dump"])
    decision = decide_capability(assess_execution_readiness(resolve_proposal(proposal)))
    if decision.outcome.value != "clarify" or not decision.clarification:
        continue
    clar = decision.clarification
    if clar.expected_answer_kind == "entity_reference" and clar.missing_slot in ENTITY_SLOTS:
        continue
    family = SLOT_TO_FAMILY.get(clar.missing_slot, "OTHER")
    if family == "VALUE" and clar.missing_slot == "state_value":
        handler = "state_value_via_catalog_aliases"
    elif family == "DIMENSION" and clar.missing_slot == "measurement_dimension":
        handler = "measurement_dimension_aliases"
    elif family == "DIMENSION":
        handler = "attribute_dimension_aliases"
    elif family == "CORRECTION_TARGET":
        handler = "correction_target_resolver"
    else:
        handler = "none"

    safety: list[str] = []
    if clar.missing_slot == "state_value" and not proposal.condition_semantics:
        safety.append("no_condition_semantics_on_proposal")
    if clar.missing_slot == "measurement_dimension" and proposal.measurable_dimension_key:
        safety.append("dimension_key_already_present_unit_currency_conflict_likely")
    if clar.missing_slot == "attribute_dimension":
        safety.append("attribute_may_lack_core_dimension_for_brand_name_plate")
    if row.get("category") == "correction":
        safety.append("live_case_category_correction_misrouted_to_state_or_attr")

    prim = clar.primitive.value if hasattr(clar.primitive, "value") else str(clar.primitive)
    key = f"{row['case_id']}|{clar.missing_slot}|{prim}"
    seen_keys[key] += 1
    entries.append(
        {
            "case_id": row["case_id"],
            "instance_index": seen_keys[key],
            "primitive": prim,
            "missing_slot": clar.missing_slot,
            "expected_answer_kind": clar.expected_answer_kind,
            "clarification_eligible": True,
            "current_recovery_supported": False,
            "proposed_recovery_family": family,
            "proposed_handler": handler,
            "frequency": 1,
            "live_category": row.get("category"),
            "safety_notes": "; ".join(safety) if safety else "none",
            "gap_taxonomy": family,
        }
    )

fam_counts = Counter(e["proposed_recovery_family"] for e in entries)
slot_counts = Counter(e["missing_slot"] for e in entries)
for e in entries:
    e["frequency"] = fam_counts[e["proposed_recovery_family"]]

dim_n = fam_counts.get("DIMENSION", 0)
val_n = fam_counts.get("VALUE", 0)
total_interactions = 354

ledger = {
    "increment": "I12.14",
    "title": "Clarification Gap Ledger",
    "source": (
        "I12.11 baseline_deepseek_chat checkpoint + CapabilityStrategy clarify "
        "outcomes unsupported by I12.13 entity_reference recovery"
    ),
    "frozen": True,
    "total_unsupported": len(entries),
    "family_counts": dict(fam_counts),
    "slot_counts": dict(slot_counts),
    "frequency_table": [
        {
            "gap_family": "dimension",
            "count": dim_n,
            "pct_unsupported": round(100.0 * dim_n / len(entries), 1) if entries else 0,
            "primitive_families": ["attribute", "measurement", "multi_primitive", "correction"],
            "candidate_for_v1": "YES",
        },
        {
            "gap_family": "value",
            "count": val_n,
            "pct_unsupported": round(100.0 * val_n / len(entries), 1) if entries else 0,
            "primitive_families": ["state", "correction", "ambiguity", "negative"],
            "candidate_for_v1": "YES (state_value only)",
        },
        {
            "gap_family": "correction_target",
            "count": 0,
            "pct_unsupported": 0.0,
            "primitive_families": [],
            "candidate_for_v1": "NO",
        },
        {
            "gap_family": "relation_endpoint",
            "count": 0,
            "pct_unsupported": 0.0,
            "primitive_families": [],
            "candidate_for_v1": "N/A (covered by entity_reference)",
        },
        {
            "gap_family": "temporal",
            "count": 0,
            "pct_unsupported": 0.0,
            "primitive_families": [],
            "candidate_for_v1": "NO",
        },
        {
            "gap_family": "other",
            "count": fam_counts.get("OTHER", 0),
            "pct_unsupported": round(100.0 * fam_counts.get("OTHER", 0) / len(entries), 1)
            if entries
            else 0,
            "primitive_families": [],
            "candidate_for_v1": "NO",
        },
    ],
    "prioritization_rule": [
        "epistemic_safety",
        "boundedness",
        "deterministic_resolution_feasibility",
        "frequency",
        "expected_useful_capture_gain",
        "implementation_complexity",
    ],
    "central_question_answer": {
        "WHICH_UNSUPPORTED_CLARIFICATION_SLOT_FAMILIES_CAN_BE_RECOVERED_WITH_BOUNDED_SEMANTICS_WITHOUT_REINTERPRETING_THE_ORIGINAL_UTTERANCE": [
            "DIMENSION (measurement_dimension, attribute_dimension) — SAFE_FOR_ENGINE_V1",
            "VALUE (state_value only) — SAFE_FOR_ENGINE_V1",
            "CORRECTION_TARGET — remain UNSUPPORTED_RECOVERY_SLOT (0 ledger hits; mutation sensitivity)",
            "TEMPORAL — remain UNSUPPORTED (no concrete gap in ledger)",
        ]
    },
    "candidate_evaluation": {
        "DIMENSION": {
            "unsupported_cases": dim_n,
            "slots": ["attribute_dimension", "measurement_dimension"],
            "theoretical_max_capture_gain_cases": dim_n,
            "safety_difficulty": "MEDIUM",
            "authority": (
                "attribute_resolution aliases / measurement dimension text map "
                "+ measurable_dimension_key"
            ),
            "classification": "SAFE_FOR_ENGINE_V1",
            "implement": True,
            "notes": (
                "Primitive-scoped; do not cross Attribute/Measurement. Many live attribute "
                "gaps are brand/name/plate absent from CORE — recovery may remain unresolved safely."
            ),
        },
        "VALUE": {
            "unsupported_cases": val_n,
            "slots": ["state_value"],
            "theoretical_max_capture_gain_cases": val_n,
            "safety_difficulty": "HIGH",
            "authority": (
                "ContextualAlias STATE expressions + OntologyRegistry STATE_VALUE "
                "labels/keys; require condition_semantics"
            ),
            "classification": "SAFE_FOR_ENGINE_V1",
            "implement": True,
            "notes": (
                "state_value only. No generic measurement/attribute value filler. "
                "Without condition_semantics remain unresolved. Values outside "
                "alias+label vocabulary remain unresolved."
            ),
        },
        "CORRECTION_TARGET": {
            "unsupported_cases": 0,
            "slots": ["correction_target"],
            "theoretical_max_capture_gain_cases": 0,
            "safety_difficulty": "VERY_HIGH",
            "authority": "CorrectionTargetResolver",
            "classification": "UNSUPPORTED_RECOVERY_SLOT",
            "implement": False,
            "notes": (
                "Zero structured clarification slots of this kind in the 66; correction "
                "live category often misrouted. Defer — mutation sensitivity."
            ),
        },
        "TEMPORAL": {
            "unsupported_cases": 0,
            "classification": "UNSUPPORTED_RECOVERY_SLOT",
            "implement": False,
            "notes": "No concrete temporal missing_slot in the 66 unsupported set.",
        },
        "ENTITY_REFERENCE": {
            "classification": "ALREADY_IMPLEMENTED",
            "notes": (
                "I12.13 MVP; Relation subject/object and State/Attribute entity slots "
                "are covered aliases."
            ),
        },
    },
    "expected_value_table": [
        {
            "family": "dimension",
            "unsupported_cases": dim_n,
            "theoretical_max_capture_gain": (
                f"{dim_n} cases (~{100.0 * dim_n / total_interactions:.1f}% of "
                f"{total_interactions} interactions if all succeed)"
            ),
            "safety_difficulty": "MEDIUM",
            "implement": "YES",
        },
        {
            "family": "value",
            "unsupported_cases": val_n,
            "theoretical_max_capture_gain": (
                f"{val_n} cases (~{100.0 * val_n / total_interactions:.1f}% of "
                f"{total_interactions})"
            ),
            "safety_difficulty": "HIGH",
            "implement": "YES (state_value only)",
        },
        {
            "family": "correction_target",
            "unsupported_cases": 0,
            "theoretical_max_capture_gain": "0 from this ledger",
            "safety_difficulty": "VERY_HIGH",
            "implement": "NO",
        },
    ],
    "cases": entries,
}

out = root / "docs/reports/I12.14-CLARIFICATION-GAP-LEDGER.json"
out.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
print("wrote", out)
print("total", len(entries))
print("families", dict(fam_counts))
print("slots", dict(slot_counts))
