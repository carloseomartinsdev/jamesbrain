"""Avaliador I11.6-R — semantic resolution benchmark (medida apenas)."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from pke.application import FixedClock, IngestService, IngestStatus
from pke.domain import UserContext
from pke.interpretation import DeepSeekInterpreter, InterpretationContext, InterpretationError
from pke.interpretation.models import IngestIR
from pke.interpretation.semantic.models import PrimitiveKind, ResolutionStatus
from pke.interpretation.semantic.envelope_dispatch import ProviderRoute, dispatch_provider_payload
from pke.interpretation.semantic.pipeline import envelope_to_canonical_ir, proposal_to_canonical_ir, resolve_proposal
from pke.interpretation.semantic.proposal_assessment import SemanticActionability, assess_semantic_proposal
from pke.interpretation.semantic.router import route_primitive
from pke.interpretation.semantic.sense import recognize_senses
from pke.interpretation.transport.catalog import ConceptCatalog
from pke.interpretation.transport.proposal_wire import WireSemanticEnvelope
from pke.ontology import OntologyRegistry
from pke.persist import open_sqlite_uow

from tests.generalization_ingest.fixtures import BENCHMARK_NOW, USER_ID, benchmark_session, fresh_db_path
from tests.generalization_ingest.semantic_cases import (
    ALL_DETERMINISTIC_CASES,
    LIVE_MATRIX,
    DETERMINISM_CASES,
    ExpectedOutcome,
    ForbiddenCanonical,
    SemanticBenchmarkCase,
    SemanticCaseGroup,
)


class OutcomeTaxonomy(StrEnum):
    KNOWLEDGE_COMMITTED = "KNOWLEDGE_COMMITTED"
    SAFE_PARTIAL_RESOLUTION = "SAFE_PARTIAL_RESOLUTION"
    SAFE_UNRESOLVED = "SAFE_UNRESOLVED"
    SAFE_AMBIGUOUS = "SAFE_AMBIGUOUS"
    FALSE_CANONICALIZATION = "FALSE_CANONICALIZATION"
    WRONG_PRIMITIVE = "WRONG_PRIMITIVE"
    PROPOSAL_FAILURE = "PROPOSAL_FAILURE"
    CANONICAL_CONVERSION_FAILURE = "CANONICAL_CONVERSION_FAILURE"
    DOWNSTREAM_FAILURE = "DOWNSTREAM_FAILURE"


class FailureFrontier(StrEnum):
    PROVIDER_EMPTY = "PROVIDER_EMPTY"
    RAW_OUTPUT_FORMAT = "RAW_OUTPUT_FORMAT"
    NORMALIZATION = "NORMALIZATION"
    PROPOSAL_TRANSPORT = "PROPOSAL_TRANSPORT"
    PROPOSAL_SEMANTICS = "PROPOSAL_SEMANTICS"
    V2_COMPAT_FALLBACK = "V2_COMPAT_FALLBACK"
    PRIMITIVE_ROUTING = "PRIMITIVE_ROUTING"
    SENSE_RECOGNITION = "SENSE_RECOGNITION"
    ONTOLOGY_GAP = "ONTOLOGY_GAP"
    CONCEPT_RESOLUTION = "CONCEPT_RESOLUTION"
    CANONICAL_IR = "CANONICAL_IR"
    ENTITY_RESOLUTION = "ENTITY_RESOLUTION"
    VALIDATION = "VALIDATION"
    MATERIALIZATION = "MATERIALIZATION"
    STORAGE = "STORAGE"
    PASS = "PASS"
    OTHER = "OTHER"
    # Legacy alias retained for historical comparison imports
    PROVIDER = "PROVIDER_EMPTY"
    PROPOSAL_WIRE = "PROPOSAL_TRANSPORT"


class Severity(StrEnum):
    S0 = "S0"
    S1 = "S1"
    S2 = "S2"
    S3 = "S3"
    S4 = "S4"


@dataclass
class SemanticRunOutcome:
    case_id: str
    run: int
    deterministic: bool
    text: str
    group: str
    provider_response_success: bool = False
    raw_output_received: bool = False
    raw_recovery_success: bool = False
    transport_valid: bool = False
    semantic_proposal_valid: bool = False
    semantic_actionable: bool = False
    v2_compat_fallback: bool = False
    dispatch_route: str | None = None
    semantic_assessment_status: str | None = None
    proposal_parse_success: bool = False
    proposal_semantic_completeness: bool | None = None
    primitive_routing_success: bool | None = None
    sense_recognition_success: bool | None = None
    canonical_concept_resolution_success: bool | None = None
    safe_abstention: bool = False
    ambiguity_preserved: bool = False
    canonical_ir_success: bool = False
    knowledge_success: bool = False
    false_canonicalization: bool = False
    outcome_taxonomy: str = OutcomeTaxonomy.PROPOSAL_FAILURE.value
    frontier: str = FailureFrontier.PROVIDER.value
    severity: str = Severity.S1.value
    observed_primitive: str | None = None
    observed_sense: str | None = None
    observed_action: str | None = None
    observed_state_value: str | None = None
    observed_relation_type: str | None = None
    resolution_status: str | None = None
    primitive_hint: str | None = None
    hint_overridden: bool | None = None
    event_frontier_stage: str | None = None
    notes: list[str] = field(default_factory=list)
    benchmark_pass: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _classify_deterministic_outcome(concepts) -> ExpectedOutcome:
    if concepts.ontology_gap:
        return ExpectedOutcome.ONTOLOGY_GAP
    if concepts.resolution_status == ResolutionStatus.SAFE_PARTIAL:
        return ExpectedOutcome.SAFE_PARTIAL
    if concepts.resolution_status == ResolutionStatus.AMBIGUOUS:
        return ExpectedOutcome.SAFE_AMBIGUOUS
    if concepts.unresolved or concepts.safe_abstention:
        return ExpectedOutcome.SAFE_UNRESOLVED
    return ExpectedOutcome.CANONICAL_RESOLVED


def _forbidden_hit(concepts, forbid: ForbiddenCanonical | None) -> bool:
    if forbid is None:
        return False
    if concepts.action and concepts.action in forbid.actions:
        return True
    if concepts.state_value and concepts.state_value in forbid.state_values:
        return True
    if concepts.relation_type and concepts.relation_type in forbid.relation_types:
        return True
    return False


def _match_canonical(concepts, case: SemanticBenchmarkCase) -> bool:
    exp = case.expected_canonical
    if exp is None:
        return not concepts.unresolved
    if exp.relation_type and concepts.relation_type != exp.relation_type:
        return False
    if exp.action and concepts.action != exp.action:
        return False
    if exp.state_value and concepts.state_value != exp.state_value:
        return False
    if exp.state_dimension and concepts.state_dimension != exp.state_dimension:
        return False
    if exp.attribute and concepts.attribute != exp.attribute:
        return False
    return True


def _proposal_completeness(proposal, case: SemanticBenchmarkCase) -> bool:
    if case.group is SemanticCaseGroup.PRIMITIVE:
        if case.expected_primitive is PrimitiveKind.STATE:
            return bool(proposal.condition_semantics or proposal.state_expression)
        if case.expected_primitive is PrimitiveKind.EVENT:
            return bool(proposal.change_semantics or proposal.action_expression or proposal.event_expression)
        if case.expected_primitive is PrimitiveKind.RELATION:
            return bool(proposal.link_semantics or proposal.relation_expression)
        if case.expected_primitive is PrimitiveKind.ATTRIBUTE:
            return bool(proposal.stable_property_semantics or proposal.attribute_expression)
    if case.expected_sense:
        return bool(
            proposal.action_expression
            or proposal.state_expression
            or proposal.relation_expression
            or proposal.attribute_expression
            or proposal.event_expression
        )
    return True


def _severity_from_outcome(
    outcome: OutcomeTaxonomy,
    *,
    knowledge: bool,
    false_canonical: bool,
) -> Severity:
    if false_canonical and knowledge:
        return Severity.S4
    if false_canonical:
        return Severity.S3
    if outcome in {OutcomeTaxonomy.SAFE_UNRESOLVED, OutcomeTaxonomy.SAFE_AMBIGUOUS, OutcomeTaxonomy.SAFE_PARTIAL_RESOLUTION}:
        return Severity.S0
    if outcome is OutcomeTaxonomy.WRONG_PRIMITIVE:
        return Severity.S2
    if outcome is OutcomeTaxonomy.KNOWLEDGE_COMMITTED:
        return Severity.S0
    return Severity.S1


def evaluate_deterministic(case: SemanticBenchmarkCase) -> SemanticRunOutcome:
    assert case.fixture is not None
    proposal = case.fixture()
    text = case.text or proposal.raw_input
    result = resolve_proposal(proposal)
    concepts = result.concepts
    primitive = result.primitive
    senses = recognize_senses(proposal)
    pipe = proposal_to_canonical_ir(proposal)

    det_outcome = _classify_deterministic_outcome(concepts)
    false_can = _forbidden_hit(concepts, case.forbid)
    primitive_ok = case.expected_primitive is None or primitive is case.expected_primitive
    sense_ok = case.expected_sense is None or concepts.recognized_sense == case.expected_sense
    canonical_ok = _match_canonical(concepts, case) if case.expected_canonical else True
    acceptable = det_outcome in case.acceptable_deterministic

    if case.group is SemanticCaseGroup.DETERMINISM:
        result2 = resolve_proposal(proposal)
        det_ok = result.model_dump() == result2.model_dump()
        return SemanticRunOutcome(
            case_id=case.case_id,
            run=1,
            deterministic=True,
            text=text,
            group=case.group.value,
            provider_response_success=True,
            proposal_parse_success=True,
            proposal_semantic_completeness=True,
            primitive_routing_success=det_ok,
            sense_recognition_success=det_ok,
            canonical_concept_resolution_success=det_ok,
            canonical_ir_success=det_ok,
            knowledge_success=det_ok,
            benchmark_pass=det_ok,
            outcome_taxonomy=OutcomeTaxonomy.KNOWLEDGE_COMMITTED.value if det_ok else OutcomeTaxonomy.PROPOSAL_FAILURE.value,
            frontier=FailureFrontier.PASS.value if det_ok else FailureFrontier.OTHER.value,
            severity=Severity.S0.value if det_ok else Severity.S2.value,
            observed_primitive=primitive.value,
            observed_sense=concepts.recognized_sense,
            resolution_status=concepts.resolution_status.value,
            notes=[] if det_ok else ["determinism mismatch"],
        )

    if false_can:
        taxonomy = OutcomeTaxonomy.FALSE_CANONICALIZATION
        frontier = FailureFrontier.CONCEPT_RESOLUTION
    elif not primitive_ok:
        taxonomy = OutcomeTaxonomy.WRONG_PRIMITIVE
        frontier = FailureFrontier.PRIMITIVE_ROUTING
    elif not acceptable:
        taxonomy = OutcomeTaxonomy.SAFE_UNRESOLVED
        frontier = FailureFrontier.CONCEPT_RESOLUTION
    elif det_outcome is ExpectedOutcome.ONTOLOGY_GAP:
        taxonomy = OutcomeTaxonomy.SAFE_PARTIAL_RESOLUTION
        frontier = FailureFrontier.ONTOLOGY_GAP
    elif pipe.ir is not None:
        taxonomy = OutcomeTaxonomy.KNOWLEDGE_COMMITTED
        frontier = FailureFrontier.PASS
    else:
        taxonomy = OutcomeTaxonomy.SAFE_UNRESOLVED
        frontier = FailureFrontier.ONTOLOGY_GAP if concepts.ontology_gap else FailureFrontier.CONCEPT_RESOLUTION

    if case.group is SemanticCaseGroup.PRIMITIVE:
        benchmark_pass = primitive_ok
    elif case.group is SemanticCaseGroup.HINT_OVERRIDE:
        benchmark_pass = primitive_ok
    elif case.group is SemanticCaseGroup.CONFLICTING:
        benchmark_pass = primitive in {
            PrimitiveKind.STATE,
            PrimitiveKind.RELATION,
            PrimitiveKind.EVENT,
            PrimitiveKind.UNKNOWN,
        }
    elif false_can:
        benchmark_pass = False
    elif case.group is SemanticCaseGroup.CANONICAL_POSITIVE:
        benchmark_pass = canonical_ok and not false_can and primitive_ok
    elif case.group is SemanticCaseGroup.SAFETY:
        benchmark_pass = not false_can and primitive_ok and (case.expected_sense is None or sense_ok) and acceptable
    elif case.group is SemanticCaseGroup.AMBIGUITY:
        benchmark_pass = acceptable and not false_can
    elif case.group is SemanticCaseGroup.EVENT:
        if case.event_e6_install:
            benchmark_pass = acceptable and not false_can and primitive_ok
        else:
            benchmark_pass = canonical_ok and not false_can and primitive_ok
    elif case.group is SemanticCaseGroup.ATTRIBUTE:
        benchmark_pass = primitive_ok and not false_can and acceptable
    else:
        benchmark_pass = acceptable and not false_can and primitive_ok

    hint = proposal.primitive_hint
    hint_overridden = None
    if hint and hint != "unknown" and case.expected_primitive:
        hint_overridden = hint != case.expected_primitive.value

    return SemanticRunOutcome(
        case_id=case.case_id,
        run=1,
        deterministic=True,
        text=text,
        group=case.group.value,
        provider_response_success=True,
        proposal_parse_success=True,
        proposal_semantic_completeness=_proposal_completeness(proposal, case),
        primitive_routing_success=primitive_ok,
        sense_recognition_success=sense_ok,
        canonical_concept_resolution_success=canonical_ok and not false_can,
        safe_abstention=concepts.safe_abstention or concepts.unresolved,
        ambiguity_preserved=concepts.resolution_status is ResolutionStatus.AMBIGUOUS,
        canonical_ir_success=pipe.ir is not None,
        knowledge_success=pipe.ir is not None and not false_can and acceptable,
        false_canonicalization=false_can,
        benchmark_pass=benchmark_pass,
        outcome_taxonomy=taxonomy.value,
        frontier=frontier.value,
        severity=_severity_from_outcome(taxonomy, knowledge=False, false_canonical=false_can).value,
        observed_primitive=primitive.value,
        observed_sense=concepts.recognized_sense,
        observed_action=concepts.action,
        observed_state_value=concepts.state_value,
        observed_relation_type=concepts.relation_type,
        resolution_status=concepts.resolution_status.value,
        primitive_hint=hint,
        hint_overridden=hint_overridden,
        notes=[f"det_outcome={det_outcome.value}", f"senses={sorted(s.value for s in senses)}"],
    )


def _committed_false_canonical(ir: IngestIR, case: SemanticBenchmarkCase) -> bool:
    forbid = case.forbid
    if forbid is None:
        return False
    if ir.relation and ir.relation.type.key in forbid.relation_types:
        return True
    if ir.state and ir.state.value.key in forbid.state_values:
        return True
    if ir.event and ir.event.action and ir.event.action.key in forbid.actions:
        return True
    return False


def _event_frontier_stage(
    *,
    parse_ok: bool,
    proposal,
    primitive_ok: bool,
    concepts,
    ir,
    knowledge: bool,
    transport_ok: bool = True,
    semantic_actionable: bool = False,
) -> str:
    if not transport_ok:
        return "PROPOSAL_TRANSPORT"
    if not parse_ok:
        return "RAW_OUTPUT_FORMAT"
    if proposal is None:
        return "PROPOSAL_SEMANTICS"
    if not semantic_actionable:
        return "PROPOSAL_SEMANTICS"
    if not primitive_ok:
        return "PRIMITIVE_ROUTING"
    if concepts.recognized_sense and concepts.ontology_gap:
        return "ONTOLOGY_GAP"
    if concepts.unresolved and not concepts.ontology_gap:
        return "CONCEPT_RESOLUTION"
    if ir is None:
        return "CANONICAL_IR"
    if not knowledge:
        return "MATERIALIZATION"
    return "PASS"


def _frontier_from_interpret_error(exc: Exception, *, has_raw: bool) -> str:
    msg = str(exc).lower()
    if not has_raw:
        return FailureFrontier.PROVIDER_EMPTY.value
    if msg.startswith("provider:"):
        return FailureFrontier.PROVIDER_EMPTY.value
    if "normalization:" in msg or msg.startswith("normalization"):
        return FailureFrontier.NORMALIZATION.value
    if "raw_output" in msg:
        return FailureFrontier.RAW_OUTPUT_FORMAT.value
    if "proposal_transport:" in msg:
        return FailureFrontier.PROPOSAL_TRANSPORT.value
    if "proposal_semantics:" in msg:
        return FailureFrontier.PROPOSAL_SEMANTICS.value
    if "semantic_resolution:" in msg:
        return FailureFrontier.CANONICAL_IR.value
    return FailureFrontier.OTHER.value


def _stage_metrics_from_raw(raw: str | None) -> dict[str, bool]:
    if not raw:
        return {
            "raw_output_received": False,
            "raw_recovery_success": False,
            "transport_valid": False,
            "semantic_proposal_valid": False,
            "semantic_actionable": False,
        }
    dispatched = dispatch_provider_payload(raw)
    raw_recovery = dispatched.normalization is not None and dispatched.normalization.ok
    transport_valid = False
    proposal = None
    semantic_actionable = False
    if dispatched.route in {ProviderRoute.SEMANTIC_V3, ProviderRoute.V2_CANONICAL}:
        try:
            if dispatched.route is ProviderRoute.V2_CANONICAL:
                transport_valid = True
            else:
                envelope = WireSemanticEnvelope.model_validate(dispatched.payload)
                transport_valid = True
                proposal = envelope.parsed_proposal()
                assessment = assess_semantic_proposal(proposal)
                semantic_actionable = assessment.status is SemanticActionability.ACTIONABLE
        except Exception:  # noqa: BLE001
            transport_valid = False
    return {
        "raw_output_received": True,
        "raw_recovery_success": raw_recovery,
        "transport_valid": transport_valid,
        "semantic_proposal_valid": proposal is not None,
        "semantic_actionable": semantic_actionable,
    }


def evaluate_live(
    case: SemanticBenchmarkCase,
    *,
    run: int,
    interpreter: DeepSeekInterpreter,
    ontology: OntologyRegistry,
    work_dir: Path,
    user: UserContext,
) -> SemanticRunOutcome:
    text = case.text or (case.fixture().raw_input if case.fixture else "")
    row = SemanticRunOutcome(
        case_id=case.case_id,
        run=run,
        deterministic=False,
        text=text,
        group=case.group.value,
    )
    ctx = InterpretationContext(user=user)
    interpreter.last_raw_content = None
    interpreter.last_dispatch_route = None
    interpreter.last_v2_compat_fallback = False
    interpreter.last_semantic_assessment = None
    raw = None
    proposal = None
    parse_ok = False
    interpret_ok = False

    try:
        interpreter.interpret(text, ctx)
        interpret_ok = True
        parse_ok = True
        raw = interpreter.last_raw_content
    except (InterpretationError, KeyError, Exception) as exc:  # noqa: BLE001
        raw = interpreter.last_raw_content
        if not isinstance(exc, InterpretationError):
            row.notes.append(f"interpret_exc={type(exc).__name__}")
        if raw:
            stages = _stage_metrics_from_raw(raw)
            row.raw_output_received = stages["raw_output_received"]
            row.raw_recovery_success = stages["raw_recovery_success"]
            row.transport_valid = stages["transport_valid"]
            row.semantic_proposal_valid = stages["semantic_proposal_valid"]
            row.semantic_actionable = stages["semantic_actionable"]
            try:
                env = WireSemanticEnvelope.parse_json(raw)
                parse_ok = True
                proposal = env.parsed_proposal()
            except Exception:  # noqa: BLE001
                parse_ok = row.transport_valid
            row.frontier = _frontier_from_interpret_error(exc, has_raw=True)
            row.outcome_taxonomy = OutcomeTaxonomy.PROPOSAL_FAILURE.value
            row.severity = Severity.S1.value
            row.dispatch_route = interpreter.last_dispatch_route
            row.v2_compat_fallback = interpreter.last_v2_compat_fallback
            if interpreter.last_semantic_assessment is not None:
                row.semantic_assessment_status = interpreter.last_semantic_assessment.status.value
            row.provider_response_success = row.raw_output_received
            if not parse_ok and not row.transport_valid:
                return row
        else:
            row.provider_response_success = False
            row.raw_output_received = False
            row.frontier = FailureFrontier.PROVIDER_EMPTY.value
            row.outcome_taxonomy = OutcomeTaxonomy.PROPOSAL_FAILURE.value
            return row

    row.provider_response_success = raw is not None
    row.raw_output_received = raw is not None
    row.dispatch_route = interpreter.last_dispatch_route
    row.v2_compat_fallback = interpreter.last_v2_compat_fallback
    if interpreter.last_semantic_assessment is not None:
        row.semantic_assessment_status = interpreter.last_semantic_assessment.status.value
    if raw:
        stages = _stage_metrics_from_raw(raw)
        row.raw_recovery_success = stages["raw_recovery_success"]
        row.transport_valid = stages["transport_valid"]
        row.semantic_proposal_valid = stages["semantic_proposal_valid"]
        row.semantic_actionable = stages["semantic_actionable"]
    row.proposal_parse_success = parse_ok or row.transport_valid

    if proposal is None and raw:
        try:
            env = WireSemanticEnvelope.parse_json(raw)
            proposal = env.parsed_proposal()
            row.semantic_proposal_valid = True
        except Exception:  # noqa: BLE001
            if row.v2_compat_fallback:
                row.frontier = FailureFrontier.V2_COMPAT_FALLBACK.value
            elif not row.transport_valid:
                row.frontier = FailureFrontier.PROPOSAL_TRANSPORT.value
            return row

    if proposal is None and row.v2_compat_fallback:
        row.frontier = FailureFrontier.V2_COMPAT_FALLBACK.value if interpret_ok else FailureFrontier.PROPOSAL_TRANSPORT.value
        return row

    if proposal is None:
        row.frontier = FailureFrontier.PROPOSAL_SEMANTICS.value
        return row

    row.proposal_semantic_completeness = _proposal_completeness(proposal, case)
    resolved = resolve_proposal(proposal)
    concepts = resolved.concepts
    primitive = resolved.primitive
    primitive_ok = case.expected_primitive is None or primitive is case.expected_primitive
    row.primitive_routing_success = primitive_ok
    row.observed_primitive = primitive.value
    row.observed_sense = concepts.recognized_sense
    row.observed_action = concepts.action
    row.observed_state_value = concepts.state_value
    row.observed_relation_type = concepts.relation_type
    row.resolution_status = concepts.resolution_status.value
    row.sense_recognition_success = (
        case.expected_sense is None or concepts.recognized_sense == case.expected_sense
    )
    row.safe_abstention = concepts.safe_abstention or concepts.unresolved or concepts.ontology_gap
    row.ambiguity_preserved = concepts.resolution_status is ResolutionStatus.AMBIGUOUS

    false_det = _forbidden_hit(concepts, case.forbid)
    canonical_ok = _match_canonical(concepts, case) if case.expected_canonical else True
    row.canonical_concept_resolution_success = canonical_ok and not false_det
    row.false_canonicalization = false_det

    outcome = None
    ir = None
    if raw:
        try:
            env = WireSemanticEnvelope.parse_json(raw)
            pipe = envelope_to_canonical_ir(env)
            ir = pipe.ir if isinstance(pipe.ir, IngestIR) else None
            row.canonical_ir_success = ir is not None
        except Exception:  # noqa: BLE001
            row.canonical_ir_success = False

    db = fresh_db_path(work_dir, f"{case.case_id}_r{run}")
    knowledge = False
    if interpret_ok or (row.raw_output_received and row.transport_valid):
        svc = IngestService(
            interpreter,
            ontology,
            lambda p=db: open_sqlite_uow(p),
            FixedClock(BENCHMARK_NOW),
        )
        try:
            ingest = svc.ingest(text, user, benchmark_session())
            knowledge = ingest.status is IngestStatus.COMMITTED
            if ingest.status is not IngestStatus.COMMITTED:
                row.frontier = FailureFrontier.MATERIALIZATION.value
        except (InterpretationError, KeyError, Exception):  # noqa: BLE001
            row.frontier = FailureFrontier.CANONICAL_IR.value
        except Exception:  # noqa: BLE001
            row.frontier = FailureFrontier.DOWNSTREAM_FAILURE.value

    if ir and _committed_false_canonical(ir, case):
        row.false_canonicalization = True
        row.severity = Severity.S4.value
        row.outcome_taxonomy = OutcomeTaxonomy.FALSE_CANONICALIZATION.value
    elif false_det:
        row.outcome_taxonomy = OutcomeTaxonomy.FALSE_CANONICALIZATION.value
        row.severity = Severity.S3.value
        row.frontier = FailureFrontier.CONCEPT_RESOLUTION.value
    elif knowledge:
        row.outcome_taxonomy = OutcomeTaxonomy.KNOWLEDGE_COMMITTED.value
        row.frontier = FailureFrontier.PASS.value
        row.severity = Severity.S0.value
    elif concepts.ontology_gap or case.safe_abstention_expected:
        row.outcome_taxonomy = OutcomeTaxonomy.SAFE_PARTIAL_RESOLUTION.value
        row.frontier = FailureFrontier.ONTOLOGY_GAP.value
        row.severity = Severity.S0.value
    elif concepts.resolution_status is ResolutionStatus.AMBIGUOUS:
        row.outcome_taxonomy = OutcomeTaxonomy.SAFE_AMBIGUOUS.value
        row.severity = Severity.S0.value
    elif not row.proposal_semantic_completeness:
        row.outcome_taxonomy = OutcomeTaxonomy.PROPOSAL_FAILURE.value
        row.frontier = FailureFrontier.PROPOSAL_SEMANTICS.value
    elif not primitive_ok:
        row.outcome_taxonomy = OutcomeTaxonomy.WRONG_PRIMITIVE.value
        row.frontier = FailureFrontier.PRIMITIVE_ROUTING.value
        row.severity = Severity.S2.value
    else:
        row.outcome_taxonomy = OutcomeTaxonomy.SAFE_UNRESOLVED.value
        row.severity = Severity.S0.value

    row.knowledge_success = knowledge
    if case.group is SemanticCaseGroup.EVENT:
        row.event_frontier_stage = _event_frontier_stage(
            parse_ok=parse_ok or row.transport_valid,
            proposal=proposal,
            primitive_ok=primitive_ok,
            concepts=concepts,
            ir=ir,
            knowledge=knowledge,
            transport_ok=row.transport_valid,
            semantic_actionable=row.semantic_actionable,
        )
    if proposal.primitive_hint and proposal.primitive_hint != "unknown":
        row.primitive_hint = proposal.primitive_hint
        if case.expected_primitive:
            row.hint_overridden = proposal.primitive_hint != case.expected_primitive.value
    return row


def run_deterministic_suite() -> list[SemanticRunOutcome]:
    ConceptCatalog.load(OntologyRegistry.with_core_seeds())
    return [evaluate_deterministic(c) for c in ALL_DETERMINISTIC_CASES]


def run_live_suite(
    interpreter: DeepSeekInterpreter,
    ontology: OntologyRegistry,
    work_dir: Path,
    user: UserContext,
    *,
    runs: int = 3,
) -> list[SemanticRunOutcome]:
    ConceptCatalog.load(ontology)
    outcomes: list[SemanticRunOutcome] = []
    for case in LIVE_MATRIX:
        for run in range(1, runs + 1):
            outcomes.append(
                evaluate_live(case, run=run, interpreter=interpreter, ontology=ontology, work_dir=work_dir, user=user)
            )
    return outcomes


def _rate(vals: list[bool | None]) -> float | None:
    filtered = [v for v in vals if v is not None]
    if not filtered:
        return None
    return round(sum(1 for v in filtered if v) / len(filtered), 4)


def aggregate_metrics(det: list[SemanticRunOutcome], live: list[SemanticRunOutcome]) -> dict[str, Any]:
    prim = [o for o in det if o.group == SemanticCaseGroup.PRIMITIVE.value]
    prim_ok = sum(1 for o in prim if o.primitive_routing_success)
    prim_total = len(prim) or 1

    pos = [o for o in det if o.group == SemanticCaseGroup.CANONICAL_POSITIVE.value]
    pos_ok = sum(1 for o in pos if o.canonical_concept_resolution_success and not o.false_canonicalization)

    safety = [o for o in det if o.false_canonicalization or o.group == SemanticCaseGroup.SAFETY.value]
    false_count = sum(1 for o in det if o.false_canonicalization)
    safety_neg = [o for o in det if o.case_id.startswith("SSAFE")]
    false_rate = false_count / max(1, len(safety_neg))

    abstain_expected = [o for o in det if o.safe_abstention]
    abstain_ok = sum(1 for o in det if o.safe_abstention and o.severity == Severity.S0.value)

    sense_cases = [o for o in det if o.observed_sense is not None or o.sense_recognition_success is not None]
    sense_ok = sum(1 for o in sense_cases if o.sense_recognition_success)

    det_det = [o for o in det if o.group == SemanticCaseGroup.DETERMINISM.value]
    determinism = all(o.knowledge_success for o in det_det) if det_det else True

    collapse_confusions: dict[str, int] = {}
    for o in prim:
        if not o.primitive_routing_success and o.observed_primitive and o.case_id in {"P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"}:
            key = f"{o.case_id}_as_{o.observed_primitive}"
            collapse_confusions[key] = collapse_confusions.get(key, 0) + 1

    live_by_group: dict[str, list[SemanticRunOutcome]] = {}
    for o in live:
        g = _live_group(o.case_id)
        live_by_group.setdefault(g, []).append(o)

    return {
        "deterministic_cases": len(det),
        "deterministic_passed": sum(1 for o in det if o.benchmark_pass),
        "PRIMITIVE_ROUTING_ACCURACY": round(prim_ok / prim_total, 4),
        "PRIMITIVE_COLLAPSE_RATE": round(1 - prim_ok / prim_total, 4),
        "CANONICAL_POSITIVE_ACCURACY": round(pos_ok / max(1, len(pos)), 4),
        "FALSE_CANONICALIZATION_RATE": round(false_rate, 4),
        "FALSE_CANONICALIZATION_COUNT": false_count,
        "SAFE_ABSTENTION_COUNT": len(abstain_expected),
        "SAFE_ABSTENTION_CORRECT": abstain_ok,
        "SENSE_RECOGNITION_ACCURACY": round(sense_ok / max(1, len([o for o in det if o.sense_recognition_success is not None])), 4),
        "SEMANTIC_RESOLUTION_DETERMINISM": 1.0 if determinism else 0.0,
        "primitive_collapse_confusions": collapse_confusions,
        "live_runs": len(live),
        "PROVIDER_RESPONSE_SUCCESS_RATE": _rate([o.raw_output_received for o in live]),
        "RAW_OUTPUT_RECOVERY_RATE": _rate([o.raw_recovery_success for o in live if o.raw_output_received]),
        "TRANSPORT_VALIDITY_RATE": _rate([o.transport_valid for o in live if o.raw_output_received]),
        "VALID_SEMANTIC_PROPOSAL_RATE": _rate([o.semantic_proposal_valid for o in live if o.transport_valid]),
        "SEMANTIC_ACTIONABILITY_RATE": _rate([o.semantic_actionable for o in live if o.semantic_proposal_valid]),
        "V2_COMPAT_FALLBACK_RATE": _rate([o.v2_compat_fallback for o in live if o.raw_output_received]),
        "PROPOSAL_PARSE_SUCCESS_RATE": _rate([o.proposal_parse_success for o in live]),
        "PROPOSAL_SEMANTIC_COMPLETENESS_RATE": _rate([o.proposal_semantic_completeness for o in live]),
        "PRIMITIVE_ROUTING_SUCCESS_RATE": _rate([o.primitive_routing_success for o in live]),
        "SENSE_RECOGNITION_SUCCESS_RATE": _rate([o.sense_recognition_success for o in live]),
        "CANONICAL_RESOLUTION_SUCCESS_RATE": _rate([o.canonical_concept_resolution_success for o in live]),
        "SAFE_ABSTENTION_RATE": _rate([o.safe_abstention for o in live if o.safe_abstention]),
        "KNOWLEDGE_SUCCESS_RATE": _rate([o.knowledge_success for o in live]),
        "live_by_group": {
            g: {
                "knowledge_success_rate": _rate([o.knowledge_success for o in rows]),
                "runs": len(rows),
            }
            for g, rows in live_by_group.items()
        },
        "severity_counts": _severity_counts(det + live),
        "frontier_counts": _frontier_counts(live),
        "event_frontier_stages": _event_stages(live),
    }


def _live_group(case_id: str) -> str:
    if case_id in {"S1", "S4", "SHOP_002"}:
        return "state"
    if case_id in {"PEOPLE_001", "R3", "R4"}:
        return "relation"
    if case_id.startswith("E"):
        return "event"
    if case_id.startswith("A_ATTR"):
        return "attribute"
    if case_id.startswith("SSAFE"):
        return "safety"
    return "other"


def _severity_counts(runs: list[SemanticRunOutcome]) -> dict[str, int]:
    counts: dict[str, int] = {s.value: 0 for s in Severity}
    for o in runs:
        counts[o.severity] = counts.get(o.severity, 0) + 1
    return counts


def _frontier_counts(live: list[SemanticRunOutcome]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for o in live:
        counts[o.frontier] = counts.get(o.frontier, 0) + 1
    return counts


def _event_stages(live: list[SemanticRunOutcome]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for o in live:
        if o.event_frontier_stage:
            counts[o.event_frontier_stage] = counts.get(o.event_frontier_stage, 0) + 1
    return counts


def audit_static() -> dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    sense_path = root / "src" / "pke" / "interpretation" / "semantic" / "sense.py"
    semantic_dir = root / "src" / "pke" / "interpretation" / "semantic"
    sense_text = sense_path.read_text(encoding="utf-8")
    sense_enum_count = len(re.findall(r"^\s+\w+ = ", sense_text, re.M))
    pattern_count = len(re.findall(r"r\"\\", sense_text))
    raw_input_hits = []
    for py in semantic_dir.glob("*.py"):
        text = py.read_text(encoding="utf-8")
        if re.search(r'if\s+["\'].*["\']\s+in\s+.*raw_input', text):
            raw_input_hits.append(py.name)
        if re.search(r"proposal\.raw_input", text) and "collect_expressions" not in text:
            if "raw_input" in text and py.name == "resolver.py":
                pass

    deepseek_in_semantic = any(
        "deepseek" in p.read_text(encoding="utf-8").lower()
        for p in semantic_dir.glob("*.py")
    )

    pipeline_path = root / "src" / "pke" / "interpretation" / "semantic" / "pipeline.py"
    pipeline_text = pipeline_path.read_text(encoding="utf-8")
    query_shared = "semantic_query" in pipeline_text and "resolve_proposal" in pipeline_text

    return {
        "sense_registry_enum_count": sense_enum_count,
        "sense_pattern_count": pattern_count,
        "sense_registry_classification": "YES" if sense_enum_count <= 15 and pattern_count <= 40 else "GROWING_RISK",
        "raw_input_direct_routing_hits": raw_input_hits,
        "keyword_rule_classification": "CLEAN" if not raw_input_hits else "MINOR_RISK",
        "provider_independence": not deepseek_in_semantic,
        "query_shared_semantic_resolver": "PARTIALLY" if query_shared else "NO",
        "query_debt": "SEMANTIC-QUERY-01" if query_shared else None,
        "event_concept_action_required": "PARTIALLY",
        "event_audit_reason": (
            "resolution_to_wire_ingest emits Event wire when concepts.unresolved is False; "
            "action is optional (None allowed) but unresolved concepts block wire entirely. "
            "event_type defaults to event.maintenance when missing."
        ),
    }


def choose_recommendation(payload: dict[str, Any], *, increment: str = "I11.6") -> str:
    offline = payload["offline_gate"]
    m = payload["metrics"]
    fix_label = f"{increment}_FIX_REQUIRED"
    if not offline.get("ok"):
        return fix_label
    if m["FALSE_CANONICALIZATION_COUNT"] > 0:
        return fix_label
    if m.get("severity_counts", {}).get("S4", 0) > 0:
        return fix_label
    if m["SEMANTIC_RESOLUTION_DETERMINISM"] < 1.0:
        return fix_label
    if m["PRIMITIVE_ROUTING_ACCURACY"] < 1.0:
        return fix_label
    if m["CANONICAL_POSITIVE_ACCURACY"] < 1.0:
        return fix_label
    det_pass = m["deterministic_passed"] == m["deterministic_cases"]
    if not det_pass:
        return fix_label
    if payload.get("live_ran") and m.get("live_runs", 0) < 30:
        return "MORE_PROPOSAL_EVIDENCE_REQUIRED" if increment == "I11.7" else "MORE_SEMANTIC_EVIDENCE_REQUIRED"
    return "PROCEED"
