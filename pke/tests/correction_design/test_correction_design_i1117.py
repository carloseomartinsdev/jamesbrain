"""I11.17 — Correction / retraction / evidence lineage design characterization (no implementation)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pke.ontology import OntologyRegistry
from pke.persist.versions import STORAGE_SCHEMA_VERSION


class ScenarioKind(StrEnum):
    CORRECTION = "correction"
    EVOLUTION = "evolution"
    TERMINATION = "termination"
    NEW_EVIDENCE = "new_evidence"
    RETRACTION = "retraction"
    AMBIGUOUS = "ambiguous"
    ADMIN = "admin_privacy"
    UNSAFE_LEGACY = "unsafe_legacy"


@dataclass(frozen=True)
class CorrectionCase:
    code: str
    summary: str
    correction: bool
    evolution: bool
    termination: bool
    new_evidence: bool
    retraction: bool
    kind: ScenarioKind
    notes: str = ""


# C1–C18 + additional safety/design cases (≥40)
CORRECTION_BENCHMARK: tuple[CorrectionCase, ...] = (
    CorrectionCase("C1", "Attribute blue→black with corrigindo", True, False, False, False, False, ScenarioKind.CORRECTION),
    CorrectionCase("C2", "wall blue 2024 → black 2025", False, True, False, False, False, ScenarioKind.EVOLUTION),
    CorrectionCase("C3", "Measurement 38→36 reading error", True, False, False, False, False, ScenarioKind.CORRECTION),
    CorrectionCase("C4", "Measurement 38@10:00 and 36@11:00", False, False, False, True, False, ScenarioKind.NEW_EVIDENCE),
    CorrectionCase("C5", "João no longer works at Acme", False, False, True, False, False, ScenarioKind.TERMINATION),
    CorrectionCase("C6", "João never worked at Acme", True, False, False, False, True, ScenarioKind.CORRECTION),
    CorrectionCase("C7", "Event clutch 2024→2025 correction", True, False, False, False, False, ScenarioKind.CORRECTION),
    CorrectionCase("C8", "door open 10:00 → closed 11:00", False, True, False, False, False, ScenarioKind.EVOLUTION),
    CorrectionCase("C9", "door open looked wrong → closed", True, False, False, False, False, ScenarioKind.CORRECTION),
    CorrectionCase("C10", "retraction only owns Corolla", True, False, False, False, True, ScenarioKind.RETRACTION),
    CorrectionCase("C11", "Corolla blue + Civic blue → é preto", False, False, False, False, False, ScenarioKind.AMBIGUOUS, "no mutation"),
    CorrectionCase("C12", "duplicate blue; retract P1 only", True, False, False, False, True, ScenarioKind.CORRECTION, "P2 remains"),
    CorrectionCase("C13", "correction-of-correction P→Q→R", True, False, False, False, False, ScenarioKind.CORRECTION, "acyclic lineage"),
    CorrectionCase("C14", "replacement unresolved", False, False, False, False, False, ScenarioKind.AMBIGUOUS, "no mutation / wait"),
    CorrectionCase("C15", "replacement non-materializable", False, False, False, False, False, ScenarioKind.AMBIGUOUS, "NO_RETRACTION_UNTIL_MATERIALIZES"),
    CorrectionCase("C16", "cross-user target", False, False, False, False, False, ScenarioKind.AMBIGUOUS, "reject"),
    CorrectionCase("C17", "apague isso do sistema", False, False, False, False, False, ScenarioKind.ADMIN),
    CorrectionCase("C18", "esquece isso (ambiguous product)", False, False, False, False, False, ScenarioKind.AMBIGUOUS),
    # Extra design cases
    CorrectionCase("C19", "enrichment azul→azul-marinho", False, False, False, True, False, ScenarioKind.NEW_EVIDENCE),
    CorrectionCase("C20", "negation carro não é azul alone", False, False, False, True, False, ScenarioKind.NEW_EVIDENCE, "not auto-retract"),
    CorrectionCase("C21", "State supersession bookkeeping", False, True, False, False, False, ScenarioKind.EVOLUTION),
    CorrectionCase("C22", "Attribute supersedes_id lineage", False, True, False, False, False, ScenarioKind.EVOLUTION),
    CorrectionCase("C23", "Relation DENY_CURRENT without never", False, False, False, False, False, ScenarioKind.TERMINATION, "not full correction"),
    CorrectionCase("C24", "query Eu disse que era azul?", False, False, False, False, False, ScenarioKind.AMBIGUOUS, "ASK not WRITE"),
    CorrectionCase("C25", "LAST_EVENT strategy as target", False, False, False, False, False, ScenarioKind.UNSAFE_LEGACY, "forbidden authority"),
    CorrectionCase("C26", "created_at DESC as target", False, False, False, False, False, ScenarioKind.UNSAFE_LEGACY),
    CorrectionCase("C27", "highest id as target", False, False, False, False, False, ScenarioKind.UNSAFE_LEGACY),
    CorrectionCase("C28", "Event two occurrences from time typo", True, False, False, False, False, ScenarioKind.CORRECTION, "one corrected occurrence"),
    CorrectionCase("C29", "Measurement same value same time two rows; retract one", True, False, False, False, True, ScenarioKind.CORRECTION),
    CorrectionCase("C30", "proposition-level retract all blue", False, False, False, False, False, ScenarioKind.AMBIGUOUS, "out of minimal scope"),
    CorrectionCase("C31", "primitive change employee→contractor", True, False, False, False, False, ScenarioKind.CORRECTION, "replacement may differ concept"),
    CorrectionCase("C32", "recorded_at as corrected fact time", False, False, False, False, False, ScenarioKind.UNSAFE_LEGACY),
    CorrectionCase("C33", "correction recorded_at vs fact time 2025", True, False, False, False, False, ScenarioKind.CORRECTION),
    CorrectionCase("C34", "unresolved target", False, False, False, False, False, ScenarioKind.AMBIGUOUS, "no mutation"),
    CorrectionCase("C35", "user isolation mismatch", False, False, False, False, False, ScenarioKind.AMBIGUOUS, "reject"),
    CorrectionCase("C36", "retract asserts opposite ownership", False, False, False, False, False, ScenarioKind.UNSAFE_LEGACY, "forbidden"),
    CorrectionCase("C37", "DELETE FROM as correction", False, False, False, False, False, ScenarioKind.UNSAFE_LEGACY),
    CorrectionCase("C38", "UPDATE overwrite value in place", False, False, False, False, False, ScenarioKind.UNSAFE_LEGACY),
    CorrectionCase("C39", "is_current reused as retraction flag", False, False, False, False, False, ScenarioKind.UNSAFE_LEGACY),
    CorrectionCase("C40", "cyclic correction lineage", False, False, False, False, False, ScenarioKind.UNSAFE_LEGACY),
    CorrectionCase("C41", "partial REPLACE commit", False, False, False, False, False, ScenarioKind.UNSAFE_LEGACY),
    CorrectionCase("C42", "retraction-only with resolved target", True, False, False, False, True, ScenarioKind.RETRACTION),
)

FUTURE_SAFETY_METRICS = (
    "CORRECTION_TARGET_SELECTED_BY_INSERTION_ORDER",
    "CORRECTION_TARGET_AMBIGUITY_IGNORED",
    "CORRECTION_DESTROYED_ORIGINAL_EVIDENCE",
    "CORRECTION_RETRACTION_ASSERTED_OPPOSITE",
    "CORRECTION_CONFLATED_WITH_TEMPORAL_EVOLUTION",
    "CORRECTION_CONFLATED_WITH_RELATION_TERMINATION",
    "CORRECTION_CONFLATED_WITH_STATE_SUPERSESSION",
    "CORRECTION_CONFLATED_WITH_NEW_MEASUREMENT",
    "CORRECTION_RETRACTED_UNTARGETED_DUPLICATE_EVIDENCE",
    "CORRECTION_CROSSED_USER_BOUNDARY",
    "CORRECTION_REPLACEMENT_PARTIALLY_COMMITTED",
    "CORRECTION_LINEAGE_CYCLE",
    "CREATED_AT_USED_AS_CORRECTION_TARGET_AUTHORITY",
    "RECORDED_AT_USED_AS_FACT_TIME",
)

# Frozen architecture decisions (characterization)
PERSISTENCE_CHOICE = "GENERIC_CORRECTION_LEDGER"
NON_MATERIALIZABLE_POLICY = "NO_RETRACTION_UNTIL_REPLACEMENT_MATERIALIZES"
RETRACTION_ASSERTS_OPPOSITE = False
SCHEMA_V10_REQUIRED = True  # for implementation; not applied in I11.17
EVIDENCE01_REQUIRED_FULL = False  # PARTIALLY: ledger without full Evidence layer
EFFECTIVENESS_AUTHORITY = "AssertionEffectivenessResolver"
LAST_EVENT_STRATEGY_FORBIDDEN_AS_AUTHORITY = True


def test_i1117_benchmark_size_and_distribution() -> None:
    assert len(CORRECTION_BENCHMARK) >= 40
    codes = {c.code for c in CORRECTION_BENCHMARK}
    for i in range(1, 19):
        assert f"C{i}" in codes
    target_res = sum(1 for c in CORRECTION_BENCHMARK if c.kind in {ScenarioKind.AMBIGUOUS, ScenarioKind.UNSAFE_LEGACY} or c.code in {"C11", "C14", "C16", "C34"})
    evol = sum(1 for c in CORRECTION_BENCHMARK if c.evolution)
    retract = sum(1 for c in CORRECTION_BENCHMARK if c.retraction)
    replace = sum(1 for c in CORRECTION_BENCHMARK if c.correction and not c.retraction)
    assert target_res >= 8
    assert evol >= 4  # evolution subset; more in full table via notes
    assert retract >= 4
    assert replace >= 6
    assert sum(1 for c in CORRECTION_BENCHMARK if c.kind is ScenarioKind.UNSAFE_LEGACY) >= 8


def test_i1117_classification_c1_c6_c11() -> None:
    by = {c.code: c for c in CORRECTION_BENCHMARK}
    assert by["C1"].correction and not by["C1"].evolution
    assert by["C2"].evolution and not by["C2"].correction
    assert by["C5"].termination and not by["C5"].correction
    assert by["C6"].correction and by["C6"].retraction
    assert by["C4"].new_evidence and not by["C4"].correction
    assert by["C11"].kind is ScenarioKind.AMBIGUOUS


def test_i1117_frozen_invariants() -> None:
    assert RETRACTION_ASSERTS_OPPOSITE is False
    assert NON_MATERIALIZABLE_POLICY == "NO_RETRACTION_UNTIL_REPLACEMENT_MATERIALIZES"
    assert PERSISTENCE_CHOICE == "GENERIC_CORRECTION_LEDGER"
    assert LAST_EVENT_STRATEGY_FORBIDDEN_AS_AUTHORITY is True
    assert EVIDENCE01_REQUIRED_FULL is False
    assert EFFECTIVENESS_AUTHORITY == "AssertionEffectivenessResolver"
    assert len(FUTURE_SAFETY_METRICS) >= 14


def test_i1117_no_schema_change() -> None:
    assert STORAGE_SCHEMA_VERSION == "11"
    assert SCHEMA_V10_REQUIRED is True  # future implementation only
    assert len(OntologyRegistry.with_core_seeds().concepts()) == 67
