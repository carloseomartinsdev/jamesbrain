"""I11.17.1 contract constants — updated after I11.17.2 v10 implementation."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pke.application import ingest as ingest_mod
from pke.application import materializer as materializer_mod
from pke.application.results import MaterializationResult
from pke.ontology import OntologyRegistry
from pke.persist import migrations as migrations_mod
from pke.persist.sqlite import repositories as repos_mod
from pke.persist.sqlite import uow as uow_mod
from pke.persist.versions import STORAGE_SCHEMA_VERSION


class ContractOp(StrEnum):
    RETRACT = "retract"
    REPLACE = "replace"


@dataclass(frozen=True)
class ContractCase:
    code: str
    category: str
    summary: str


TARGET_REFERENCE_STRATEGY = "APPLICATION_VALIDATED_TYPED_REFERENCE"
EFFECTIVE_INVARIANT = (
    "An assertion is EFFECTIVE iff no committed Correction targets its KnowledgeReference."
)
QUERY_INTEGRATION = "PRIMITIVE_RESOLVERS_SHARED_EFFECTIVENESS"
BRANCHING_ALLOWED = False
CROSS_PRIMITIVE_REPLACEMENT = True
REPLACEMENT_FRAME_PERSISTED = False
REPLACE_REQUIRES_MATERIALIZED = True
NON_MATERIALIZABLE_CAN_RETRACT = False
EXPLICIT_RETRACT_WITHOUT_REPLACEMENT = True
SCHEMA_V10_REQUIRED_FOR_IMPL = True
EVIDENCE01_REQUIRED = False
SUPPORTED_KINDS = frozenset({"event", "measurement", "relation", "state", "attribute"})
UNIQUE_TARGET = True
LAST_EVENT_CANONICAL = False

CONTRACT_BENCHMARK: tuple[ContractCase, ...] = (
    ContractCase("K-R01", "reference", "valid event reference"),
    ContractCase("K-R02", "reference", "valid measurement reference"),
    ContractCase("K-R03", "reference", "valid relation reference"),
    ContractCase("K-R04", "reference", "valid state reference"),
    ContractCase("K-R05", "reference", "valid attribute reference"),
    ContractCase("K-R06", "reference", "reject unsupported kind"),
    ContractCase("K-R07", "reference", "reject missing assertion id"),
    ContractCase("K-R08", "reference", "reject wrong-user ownership"),
    ContractCase("K-R09", "reference", "reject kind/table mismatch"),
    ContractCase("K-R10", "reference", "orphan reference → effectiveness UNKNOWN"),
    ContractCase("K1", "retract", "Attribute RETRACT → ineffective, no opposite"),
    ContractCase("K6", "retract", "Relation RETRACT ≠ termination"),
    ContractCase("K-RT3", "retract", "Measurement RETRACT"),
    ContractCase("K-RT4", "retract", "State RETRACT"),
    ContractCase("K-RT5", "retract", "Event RETRACT"),
    ContractCase("K21", "retract", "repeated RETRACT rejected"),
    ContractCase("K-RT7", "retract", "RETRACT after REPLACE rejected"),
    ContractCase("K-RT8", "retract", "explicit RETRACT no replacement commit"),
    ContractCase("K2", "replace", "Attribute REPLACE blue→black"),
    ContractCase("K4", "replace", "Measurement REPLACE 38→36"),
    ContractCase("K8", "replace", "State REPLACE erroneous observation"),
    ContractCase("K9", "replace", "Event time REPLACE 2024→2025"),
    ContractCase("K-RP5", "replace", "Relation REPLACE"),
    ContractCase("K14", "replace", "replacement unresolved → no commit"),
    ContractCase("K15", "replace", "non-materializable → no commit"),
    ContractCase("K22", "replace", "self-replacement rejected"),
    ContractCase("K-RP9", "replace", "cross-primitive replacement allowed"),
    ContractCase("K-RP10", "replace", "REPLACE requires materialized id"),
    ContractCase("K10", "lineage", "P→Q→R chain"),
    ContractCase("K11", "lineage", "semantic return new assertion id"),
    ContractCase("K7", "lineage", "termination not correction"),
    ContractCase("K5", "lineage", "later Measurement both effective"),
    ContractCase("K20", "lineage", "branching REPLACE rejected"),
    ContractCase("K-L6", "lineage", "UNIQUE target constraint"),
    ContractCase("K-L7", "lineage", "acyclic enforced"),
    ContractCase("K-L8", "lineage", "no supersedes_correction_id dual authority"),
    ContractCase("K3", "duplicate", "P1/P2 blue; RETRACT P1; P2 remains"),
    ContractCase("K25", "duplicate", "Attribute proposition with remaining support"),
    ContractCase("K29", "duplicate", "Measurement duplicate rows"),
    ContractCase("K-D4", "duplicate", "untargeted sibling not retracted"),
    ContractCase("K-D5", "duplicate", "proposition not falsified by one retract"),
    ContractCase("K16", "transaction", "replacement persistence failure → rollback"),
    ContractCase("K17", "transaction", "correction persistence failure → rollback"),
    ContractCase("K-T3", "transaction", "flush before final commit"),
    ContractCase("K-T4", "transaction", "no materializer internal commit"),
    ContractCase("K-T5", "transaction", "IngestService owns commit today"),
    ContractCase("K-T6", "transaction", "CorrectionService owns future REPLACE txn"),
    ContractCase("K-T7", "transaction", "target effective after rollback"),
    ContractCase("K-T8", "transaction", "RETRACT single-row commit"),
    ContractCase("K-C1", "cross", "Event target"),
    ContractCase("K-C2", "cross", "Measurement target"),
    ContractCase("K-C3", "cross", "Relation target"),
    ContractCase("K-C4", "cross", "State target"),
    ContractCase("K-C5", "cross", "Attribute target"),
    ContractCase("K-C6", "cross", "Event→Event replacement"),
    ContractCase("K-C7", "cross", "Measurement→Measurement"),
    ContractCase("K-C8", "cross", "Attribute→Attribute"),
    ContractCase("K-C9", "cross", "Entity not a target kind"),
    ContractCase("K-C10", "cross", "TYPE not a target kind"),
    ContractCase("K23", "query", "retracted Event excluded"),
    ContractCase("K24", "query", "retracted Measurement not latest"),
    ContractCase("K25b", "query", "Attribute proposition excludes retracted"),
    ContractCase("K26", "query", "Relation historical ≠ audit"),
    ContractCase("K27", "query", "StateResolver excludes retracted"),
    ContractCase("K-Q6", "query", "INEFFECTIVE ≠ UNKNOWN temporal"),
    ContractCase("K-Q7", "query", "historical world uses EFFECTIVE only"),
    ContractCase("K-Q8", "query", "shared AssertionEffectivenessResolver"),
    ContractCase("K-Q9", "query", "repositories retrieval-only"),
    ContractCase("K-Q10", "query", "UNKNOWN effectiveness not silent include"),
    ContractCase("K18", "user", "cross-user target reject"),
    ContractCase("K19", "user", "cross-user replacement reject"),
    ContractCase("K12", "user", "ambiguous target no mutation"),
    ContractCase("K13", "user", "unresolved target no mutation"),
    ContractCase("K-U5", "user", "raw_input user matches correction user"),
)


def test_contract_constants() -> None:
    assert TARGET_REFERENCE_STRATEGY == "APPLICATION_VALIDATED_TYPED_REFERENCE"
    assert BRANCHING_ALLOWED is False
    assert CROSS_PRIMITIVE_REPLACEMENT is True
    assert QUERY_INTEGRATION == "PRIMITIVE_RESOLVERS_SHARED_EFFECTIVENESS"
    assert SUPPORTED_KINDS == {"event", "measurement", "relation", "state", "attribute"}


def test_benchmark_distribution() -> None:
    assert len(CONTRACT_BENCHMARK) >= 50
    assert sum(1 for c in CONTRACT_BENCHMARK if c.category == "reference") >= 10


def test_materialization_result_exposes_all_primitive_ids() -> None:
    fields = set(MaterializationResult.model_fields)
    for key in ("event_ids", "measurement_ids", "relation_ids", "state_ids", "attribute_ids"):
        assert key in fields


def test_no_premature_commit_in_materializer_or_repos() -> None:
    mat_src = Path(inspect.getfile(materializer_mod)).read_text(encoding="utf-8")
    assert "session.commit()" not in mat_src
    assert "uow.commit" not in mat_src
    repo_src = Path(inspect.getfile(repos_mod)).read_text(encoding="utf-8")
    assert "session.commit()" not in repo_src
    assert "self._session.commit()" not in repo_src
    ingest_src = Path(inspect.getfile(ingest_mod)).read_text(encoding="utf-8")
    assert "uow.commit()" in ingest_src
    uow_src = Path(inspect.getfile(uow_mod)).read_text(encoding="utf-8")
    assert "session.commit()" in uow_src


def test_schema_is_v10_with_correction_migration() -> None:
    assert STORAGE_SCHEMA_VERSION == "11"
    assert migrations_mod.CURRENT_SCHEMA_VERSION == 11
    mig_dir = Path(inspect.getfile(migrations_mod)).parent
    assert (mig_dir / "v9_to_v10.py").exists()
    assert len(OntologyRegistry.with_core_seeds().concepts()) == 67
