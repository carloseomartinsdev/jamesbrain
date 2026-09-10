"""Casos do benchmark ingest-path I11.3-R2."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class CaseMode(StrEnum):
    TEMPORAL_ONLY = "TEMPORAL_ONLY"
    FULL_PIPELINE = "FULL_PIPELINE"
    QUERY_CHAIN = "QUERY_CHAIN"
    DETERMINISTIC = "DETERMINISTIC"


class DevIngestStatus(StrEnum):
    RUNNABLE_NOW = "RUNNABLE_NOW"
    BLOCKED_BY_KNOWN_ARCHITECTURE = "BLOCKED_BY_KNOWN_ARCHITECTURE"
    NOT_APPLICABLE_TO_INGEST = "NOT_APPLICABLE_TO_INGEST"


class StageStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_REACHED = "NOT_REACHED"
    NA = "N/A"


class FailureFrontierV2(StrEnum):
    PROVIDER = "PROVIDER"
    WIRE = "WIRE"
    CANONICAL = "CANONICAL"
    ENTITY_RESOLUTION = "ENTITY_RESOLUTION"
    TEMPORAL_RESOLUTION = "TEMPORAL_RESOLUTION"
    CONCEPT_RESOLUTION = "CONCEPT_RESOLUTION"
    VALIDATION = "VALIDATION"
    COMPLETENESS = "COMPLETENESS"
    MATERIALIZATION = "MATERIALIZATION"
    STORAGE = "STORAGE"
    QUERY = "QUERY"
    SEMANTIC_ASSERTION = "SEMANTIC_ASSERTION"
    CONTEXT = "CONTEXT"
    OTHER = "OTHER"
    PASS = "PASS"


class ArchitecturalGap(StrEnum):
    STATE = "STATE"
    RELATION = "RELATION"
    LEXICAL = "LEXICAL"
    CONCEPT = "CONCEPT"
    CONTEXT = "CONTEXT"


@dataclass(frozen=True)
class TemporalExpectation:
    committed: bool = True
    kind: str | None = None
    relation: str | None = None
    occurrence: str | None = None
    unknown_reason: str | None = None
    calendar_required: bool = False
    calendar_forbidden: bool = True
    no_time_missing_block: bool = True
    no_invented_today: bool = True
    no_invented_recorded_at: bool = True
    month_interval: bool = False
    exact_day: dt.date | None = None
    future_prospective: bool = False


@dataclass(frozen=True)
class QueryExpectation:
    query_text: str
    answered: bool = True
    aggregate_value: str | None = None
    temporal_completeness: str | None = None
    membership_unknown: bool | None = None
    indeterminate_min: int | None = None
    latest_known_date: str | None = None
    count_value: int | None = None


@dataclass(frozen=True)
class IngestBenchmarkCase:
    case_id: str
    text: str
    mode: CaseMode
    seed_corolla: bool = False
    live_runs: int = 3
    temporal: TemporalExpectation | None = None
    query: QueryExpectation | None = None
    setup_key: str | None = None
    notes: str = ""
    gap: ArchitecturalGap | None = None


TEMPORAL_CASES: tuple[IngestBenchmarkCase, ...] = (
    IngestBenchmarkCase(
        "TP01",
        "Troquei a embreagem do Corolla.",
        CaseMode.TEMPORAL_ONLY,
        seed_corolla=True,
        temporal=TemporalExpectation(
            kind="partial",
            relation="before",
            occurrence="happened",
            unknown_reason="not_provided",
        ),
    ),
    IngestBenchmarkCase(
        "TP02",
        "Fui ao cardiologista, mas não lembro quando.",
        CaseMode.TEMPORAL_ONLY,
        temporal=TemporalExpectation(
            kind="partial",
            relation="before",
            unknown_reason="forgotten",
        ),
    ),
    IngestBenchmarkCase(
        "TP03",
        "Comprei laranja.",
        CaseMode.TEMPORAL_ONLY,
        temporal=TemporalExpectation(
            kind="partial",
            relation="before",
            calendar_forbidden=True,
            no_invented_today=True,
        ),
        notes="Shopping completo não exigido; registrar frontier se outro gap",
    ),
    IngestBenchmarkCase(
        "TP04",
        "Vou trocar o óleo do Corolla.",
        CaseMode.TEMPORAL_ONLY,
        seed_corolla=True,
        temporal=TemporalExpectation(
            committed=False,
            calendar_forbidden=True,
            future_prospective=True,
        ),
        notes="Future partial — registrar comportamento atual sem corrigir",
    ),
    IngestBenchmarkCase(
        "TP05",
        "Troquei o óleo do Corolla em agosto.",
        CaseMode.TEMPORAL_ONLY,
        seed_corolla=True,
        temporal=TemporalExpectation(
            kind="partial",
            month_interval=True,
            calendar_forbidden=True,
        ),
        notes="TimePrecision.PARTIAL audit — mês sem dia",
    ),
    IngestBenchmarkCase(
        "TP06",
        "Troquei o óleo do Corolla ontem.",
        CaseMode.TEMPORAL_ONLY,
        seed_corolla=True,
        temporal=TemporalExpectation(
            kind="relative",
            calendar_required=True,
            calendar_forbidden=False,
            exact_day=dt.date(2026, 8, 31),
        ),
        notes="EXACT vs RELATIVE — ontem resolve para 2026-08-31",
    ),
)

QUERY_CASES: tuple[IngestBenchmarkCase, ...] = (
    IngestBenchmarkCase(
        "QTP01",
        "Já troquei a embreagem do Corolla?",
        CaseMode.QUERY_CHAIN,
        setup_key="qtp01_ingest",
        live_runs=1,
        query=QueryExpectation(query_text="Já troquei a embreagem do Corolla?", answered=True, count_value=1),
    ),
    IngestBenchmarkCase(
        "QTP02",
        "Troquei a embreagem este mês?",
        CaseMode.QUERY_CHAIN,
        setup_key="qtp01_ingest",
        live_runs=1,
        query=QueryExpectation(
            query_text="Troquei a embreagem este mês?",
            answered=True,
            count_value=0,
            temporal_completeness="partial",
            membership_unknown=True,
        ),
    ),
    IngestBenchmarkCase(
        "QTP03",
        "Quanto gastei com o Corolla este mês?",
        CaseMode.QUERY_CHAIN,
        setup_key="qtp03_ingest",
        live_runs=1,
        query=QueryExpectation(
            query_text="Quanto gastei com o Corolla este mês?",
            answered=True,
            aggregate_value="320",
            temporal_completeness="partial",
        ),
    ),
    IngestBenchmarkCase(
        "QTP04",
        "latest oil change",
        CaseMode.QUERY_CHAIN,
        setup_key="qtp04_seed",
        live_runs=1,
        query=QueryExpectation(
            query_text="latest",
            answered=True,
            latest_known_date="2026-08-20",
            temporal_completeness="partial",
            indeterminate_min=1,
        ),
    ),
    IngestBenchmarkCase(
        "QTP05",
        "count historical",
        CaseMode.QUERY_CHAIN,
        setup_key="qtp05_seed",
        live_runs=1,
        query=QueryExpectation(
            query_text="count_no_period",
            answered=True,
            count_value=3,
        ),
    ),
)

DETERMINISTIC_TEMPORAL_IDS = frozenset({"TP01", "TP02", "TP03", "TP05", "TP06"})

DEV_INGEST_CLASSIFICATION: dict[str, tuple[DevIngestStatus, ArchitecturalGap | None, str]] = {
    "HOME_001": (DevIngestStatus.RUNNABLE_NOW, None, "anomaly event"),
    "HOME_002": (DevIngestStatus.RUNNABLE_NOW, None, "maintenance"),
    "HOME_003": (DevIngestStatus.RUNNABLE_NOW, None, "passive install"),
    "PEOPLE_001": (DevIngestStatus.RUNNABLE_NOW, None, "employment relation ended"),
    "PEOPLE_002": (DevIngestStatus.RUNNABLE_NOW, None, "cohabitation"),
    "PEOPLE_003": (DevIngestStatus.RUNNABLE_NOW, None, "lend money"),
    "DOC_001": (DevIngestStatus.RUNNABLE_NOW, None, "obligation expiry"),
    "DOC_002": (DevIngestStatus.RUNNABLE_NOW, None, "renewal without date"),
    "EDU_001": (DevIngestStatus.RUNNABLE_NOW, None, "exam result"),
    "EDU_002": (DevIngestStatus.RUNNABLE_NOW, None, "appointment"),
    "HEALTH_001": (DevIngestStatus.RUNNABLE_NOW, None, "vaccination"),
    "HEALTH_002": (DevIngestStatus.RUNNABLE_NOW, None, "forgotten time"),
    "SHOP_001": (DevIngestStatus.RUNNABLE_NOW, None, "purchase"),
    "SHOP_002": (DevIngestStatus.BLOCKED_BY_KNOWN_ARCHITECTURE, ArchitecturalGap.STATE, "depletion state"),
    "SVC_001": (DevIngestStatus.RUNNABLE_NOW, None, "repair with amount"),
    "SVC_002": (DevIngestStatus.RUNNABLE_NOW, None, "subscription"),
    "TRAVEL_001": (DevIngestStatus.RUNNABLE_NOW, None, "future travel"),
    "TRAVEL_002": (DevIngestStatus.RUNNABLE_NOW, None, "return yesterday"),
    "COLL_001": (DevIngestStatus.RUNNABLE_NOW, None, "colloquial"),
    "COLL_002": (DevIngestStatus.RUNNABLE_NOW, None, "colloquial finance"),
    "NEG_001": (DevIngestStatus.RUNNABLE_NOW, None, "negation"),
    "NEG_002": (DevIngestStatus.RUNNABLE_NOW, None, "negation finance"),
    "UNC_001": (DevIngestStatus.RUNNABLE_NOW, None, "uncertain amount"),
    "UNC_002": (DevIngestStatus.RUNNABLE_NOW, None, "hedged statement"),
    "EQUIV_G1": (DevIngestStatus.RUNNABLE_NOW, None, "equivalence"),
    "EQUIV_G2": (DevIngestStatus.RUNNABLE_NOW, None, "equivalence"),
    "EQUIV_G3": (DevIngestStatus.RUNNABLE_NOW, None, "equivalence"),
    "EQUIV_G4": (DevIngestStatus.RUNNABLE_NOW, None, "equivalence"),
    "EQUIV_G5": (DevIngestStatus.RUNNABLE_NOW, None, "equivalence"),
    "CTX_FRIDGE_04": (
        DevIngestStatus.BLOCKED_BY_KNOWN_ARCHITECTURE,
        ArchitecturalGap.CONTEXT,
        "context sequence",
    ),
}

ALL_INGEST_CASES: tuple[IngestBenchmarkCase, ...] = TEMPORAL_CASES + QUERY_CASES
