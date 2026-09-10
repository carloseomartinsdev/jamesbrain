"""Correction Engine ingest orchestration — semantic path into CorrectionService."""

from __future__ import annotations

import datetime as dt
import logging

from pke.application.builder import KnowledgeCandidateBuilder
from pke.application.clock import Clock
from pke.application.correction_service import CorrectionRejected, CorrectionService
from pke.application.correction_target import (
    CorrectionTargetDescription,
    CorrectionTargetResolver,
    CorrectionTargetStatus,
)
from pke.interpretation.acceptance.correction_guard import (
    AcceptanceOutcome,
    evaluate_correction_acceptance,
)
from pke.application.materializer import ApprovedKnowledge, KnowledgeMaterializer
from pke.application.results import (
    CorrectionIngestOutcome,
    IngestResult,
    IngestStatus,
    MaterializationResult,
)
from pke.domain.corrections import KnowledgePrimitiveKind
from pke.interpretation.models import IngestIntent, IngestIR, IrCorrectionTarget
from pke.ontology.registry import OntologyRegistry
from pke.persist.contracts import UnitOfWork
from pke.reasoning.assessment import KnowledgeAssessor
from pke.reasoning.issues import Issue, Severity
from pke.resolution.lookup import InMemoryEntityLookup
from pke.domain.value_objects import SourceKind, UserContext
from pke.application.session import SessionContext

_LOG = logging.getLogger(__name__)


def _issue(code: str, message: str) -> Issue:
    return Issue(code=code, message=message, severity=Severity.ERROR, rule_id="correction.ingest")


def _target_description(target: IrCorrectionTarget | None) -> CorrectionTargetDescription:
    if target is None:
        return CorrectionTargetDescription()
    kind = None
    if target.kind is not None:
        kind = KnowledgePrimitiveKind(target.kind)
    return CorrectionTargetDescription(
        kind=kind,
        entity_text=target.entity_text,
        object_text=target.object_text,
        dimension_key=target.dimension_key,
        value_text=target.value_text,
        numeric_value=target.numeric_value,
        year=target.year,
        relation_concept_key=target.relation_concept_key,
        state_value_key=target.state_value_key,
        action_key=target.action_key,
        explicit_assertion_id=target.explicit_assertion_id,
        conversation_assertion_id=target.conversation_assertion_id,
    )


def _has_replacement_payload(ir: IngestIR) -> bool:
    return any(
        [
            ir.attribute is not None,
            ir.measurement is not None,
            ir.event is not None,
            ir.state is not None,
            ir.relation is not None,
        ]
    )


def _replacement_intent(ir: IngestIR) -> IngestIntent | None:
    if ir.measurement is not None:
        return IngestIntent.RECORD_MEASUREMENT
    if ir.attribute is not None:
        return IngestIntent.RECORD_ATTRIBUTE
    if ir.event is not None:
        return IngestIntent.RECORD_EVENT
    if ir.state is not None:
        return IngestIntent.RECORD_STATE
    if ir.relation is not None:
        return IngestIntent.RECORD_RELATION
    return None


def _replacement_ref_from_mat(
    mat: MaterializationResult,
    intended: IngestIntent | None = None,
) -> tuple[KnowledgePrimitiveKind, str] | None:
    """Pick replacement id for the intended primitive only — never a sibling co-write."""
    if intended is IngestIntent.RECORD_ATTRIBUTE and mat.attribute_ids:
        return KnowledgePrimitiveKind.ATTRIBUTE, mat.attribute_ids[-1]
    if intended is IngestIntent.RECORD_MEASUREMENT and mat.measurement_ids:
        return KnowledgePrimitiveKind.MEASUREMENT, mat.measurement_ids[-1]
    if intended is IngestIntent.RECORD_EVENT and mat.event_ids:
        return KnowledgePrimitiveKind.EVENT, mat.event_ids[-1]
    if intended is IngestIntent.RECORD_STATE and mat.state_ids:
        return KnowledgePrimitiveKind.STATE, mat.state_ids[-1]
    if intended is IngestIntent.RECORD_RELATION and mat.relation_ids:
        return KnowledgePrimitiveKind.RELATION, mat.relation_ids[-1]
    # Fallback only when intent unknown — still prefer attribute over event
    if mat.attribute_ids:
        return KnowledgePrimitiveKind.ATTRIBUTE, mat.attribute_ids[-1]
    if mat.measurement_ids:
        return KnowledgePrimitiveKind.MEASUREMENT, mat.measurement_ids[-1]
    if mat.state_ids:
        return KnowledgePrimitiveKind.STATE, mat.state_ids[-1]
    if mat.relation_ids:
        return KnowledgePrimitiveKind.RELATION, mat.relation_ids[-1]
    if mat.event_ids:
        return KnowledgePrimitiveKind.EVENT, mat.event_ids[-1]
    return None


def _scrub_replacement_ir(ir: IngestIR, intent: IngestIntent) -> IngestIR:
    """Keep only the replacement primitive required by intent (correction atomicity)."""
    keep = {
        IngestIntent.RECORD_ATTRIBUTE: {
            "attribute": ir.attribute,
            "event": None,
            "measurement": None,
            "state": None,
            "relation": None,
            "obligation": None,
        },
        IngestIntent.RECORD_MEASUREMENT: {
            "measurement": ir.measurement,
            "event": None,
            "attribute": None,
            "state": None,
            "relation": None,
            "obligation": None,
        },
        IngestIntent.RECORD_EVENT: {
            "event": ir.event,
            "measurement": None,
            "attribute": None,
            "state": None,
            "relation": None,
            "obligation": None,
        },
        IngestIntent.RECORD_STATE: {
            "state": ir.state,
            "event": None,
            "measurement": None,
            "attribute": None,
            "relation": None,
            "obligation": None,
        },
        IngestIntent.RECORD_RELATION: {
            "relation": ir.relation,
            "event": None,
            "measurement": None,
            "attribute": None,
            "state": None,
            "obligation": None,
        },
    }.get(intent)
    if keep is None:
        return ir.model_copy(update={"intent": intent, "correction": None})
    return ir.model_copy(update={"intent": intent, "correction": None, **keep})


class CorrectionIngestOrchestrator:
    """Natural-language correction → target resolution → CorrectionService.

    Never falls back to ordinary assertion write when correction fails.
    Never downgrades REPLACE → RETRACT.
    LAST_EVENT is not used.
    """

    def __init__(
        self,
        ontology: OntologyRegistry,
        clock: Clock,
        *,
        builder: KnowledgeCandidateBuilder | None = None,
        materializer: KnowledgeMaterializer | None = None,
    ) -> None:
        self._ontology = ontology
        self._clock = clock
        self._builder = builder or KnowledgeCandidateBuilder()
        self._materializer = materializer or KnowledgeMaterializer(ontology)
        self._targets = CorrectionTargetResolver()
        self._corrections = CorrectionService(clock)
        self.last_acceptance_decision = None
        self.target_resolver_calls = 0

    def ingest(
        self,
        *,
        ir: IngestIR,
        user: UserContext,
        session: SessionContext,
        uow: UnitOfWork,
        lookup: InMemoryEntityLookup,
        now: dt.datetime,
        resolve_entities,
        resolve_times,
    ) -> IngestResult:
        corr = ir.correction
        if corr is None or corr.operation is None:
            return IngestResult(
                status=IngestStatus.REJECTED,
                raw_text=ir.raw_input,
                correction_outcome=CorrectionIngestOutcome.CORRECTION_REJECTED,
                issues=[_issue("correction.operation_missing", "correction operation required")],
            )

        # I12.4 — Correction Acceptance Guard (before CorrectionTargetResolver).
        # Does not rewrite IR; rejection means Correction is not admissible.
        prior = list(getattr(session, "recent_utterances", None) or [])
        decision = evaluate_correction_acceptance(
            ir.raw_input,
            proposed_as_correction=True,
            prior_utterances=prior,
        )
        self.last_acceptance_decision = decision
        _LOG.info(
            "acceptance_guard_decision outcome=%s reason_code=%s proposal_intent=correct",
            decision.outcome.value,
            decision.reason_code.value,
        )
        if decision.outcome is AcceptanceOutcome.CLARIFICATION_REQUIRED:
            return IngestResult(
                status=IngestStatus.NEEDS_CLARIFICATION,
                raw_text=ir.raw_input,
                correction_outcome=CorrectionIngestOutcome.CORRECTION_TARGET_AMBIGUOUS,
                issues=[
                    _issue(
                        "acceptance_guard.clarification",
                        decision.reason_code.value,
                    )
                ],
            )
        if decision.outcome is AcceptanceOutcome.REJECT:
            return IngestResult(
                status=IngestStatus.REJECTED,
                raw_text=ir.raw_input,
                correction_outcome=CorrectionIngestOutcome.CORRECTION_REJECTED,
                issues=[
                    _issue(
                        "acceptance_guard.rejected",
                        decision.reason_code.value,
                    )
                ],
            )

        # Proposition-wide / underspecified multi-target remains unsupported
        if (corr.target is None or corr.target.kind is None) and not (
            corr.target and (corr.target.explicit_assertion_id or corr.target.conversation_assertion_id)
        ):
            # allow kind inferred later only if entity+dimension present
            if corr.target is None:
                return IngestResult(
                    status=IngestStatus.UNSUPPORTED,
                    raw_text=ir.raw_input,
                    correction_outcome=CorrectionIngestOutcome.CORRECTION_UNSUPPORTED,
                    issues=[_issue("correction.target_missing", "proposition-wide correction unsupported")],
                )

        self.target_resolver_calls += 1
        resolution = self._targets.resolve(
            user_id=user.user_id,
            description=_target_description(corr.target),
            uow=uow,
        )
        if resolution.status is CorrectionTargetStatus.AMBIGUOUS:
            return IngestResult(
                status=IngestStatus.NEEDS_CLARIFICATION,
                raw_text=ir.raw_input,
                correction_outcome=CorrectionIngestOutcome.CORRECTION_TARGET_AMBIGUOUS,
                issues=[_issue("correction.target_ambiguous", resolution.reason or "ambiguous")],
            )
        if resolution.status is CorrectionTargetStatus.UNRESOLVED or resolution.reference is None:
            return IngestResult(
                status=IngestStatus.NEEDS_CLARIFICATION,
                raw_text=ir.raw_input,
                correction_outcome=CorrectionIngestOutcome.CORRECTION_TARGET_UNRESOLVED,
                issues=[_issue("correction.target_unresolved", resolution.reason or "unresolved")],
            )

        target_ref = resolution.reference

        if corr.operation == "retract":
            from pke.domain.ids import new_ulid
            from pke.domain.value_objects import RawInput, Source

            raw = RawInput(
                id=new_ulid(),
                user_id=user.user_id,
                text=ir.raw_input,
                created_at=now,
            )
            uow.raw_inputs.add(raw)
            src = Source(
                id=new_ulid(),
                user_id=user.user_id,
                kind=SourceKind.CORRECTION,
                raw_input_id=raw.id,
            )
            uow.sources.add(src)
            try:
                committed = self._corrections.retract(
                    uow,
                    user_id=user.user_id,
                    target_kind=target_ref.kind,
                    target_id=target_ref.assertion_id,
                    raw_input_id=raw.id,
                    source_id=src.id,
                    commit=False,
                )
                uow.commit()
            except CorrectionRejected as exc:
                uow.rollback()
                return IngestResult(
                    status=IngestStatus.REJECTED,
                    raw_text=ir.raw_input,
                    correction_outcome=CorrectionIngestOutcome.CORRECTION_REJECTED,
                    issues=[_issue("correction.rejected", str(exc))],
                )
            return IngestResult(
                status=IngestStatus.COMMITTED,
                raw_text=ir.raw_input,
                correction_outcome=CorrectionIngestOutcome.CORRECTION_APPLIED,
                materialization=MaterializationResult(
                    correction_ids=[committed.id],
                    raw_input_id=raw.id,
                    source_ids=[src.id],
                ),
            )

        # REPLACE
        if not _has_replacement_payload(ir):
            return IngestResult(
                status=IngestStatus.NEEDS_CLARIFICATION,
                raw_text=ir.raw_input,
                correction_outcome=CorrectionIngestOutcome.CORRECTION_REPLACEMENT_UNRESOLVED,
                issues=[_issue("correction.replacement_unresolved", "replacement missing")],
            )

        repl_intent = _replacement_intent(ir)
        if repl_intent is None:
            return IngestResult(
                status=IngestStatus.NEEDS_CLARIFICATION,
                raw_text=ir.raw_input,
                correction_outcome=CorrectionIngestOutcome.CORRECTION_REPLACEMENT_UNRESOLVED,
                issues=[_issue("correction.replacement_unresolved", "replacement intent unknown")],
            )

        try:
            resolved_temporal, resolved_due = resolve_times(ir, user, now)
        except Exception as exc:  # noqa: BLE001
            return IngestResult(
                status=IngestStatus.NEEDS_CLARIFICATION,
                raw_text=ir.raw_input,
                correction_outcome=CorrectionIngestOutcome.CORRECTION_REPLACEMENT_NON_MATERIALIZABLE,
                issues=[_issue("correction.replacement_temporal", str(exc))],
            )

        repl_ir = _scrub_replacement_ir(ir, repl_intent)
        bindings = resolve_entities(repl_ir, user, session, lookup)
        candidate = self._builder.build(
            user_id=user.user_id,
            ir=repl_ir,
            bindings=bindings,
            resolved_temporal=resolved_temporal,
            resolved_due=resolved_due,
            source_kind=SourceKind.CORRECTION,
        )
        assessor = KnowledgeAssessor(self._ontology, lookup)
        assessment = assessor.assess(candidate)
        if not assessment.persistable:
            return IngestResult(
                status=IngestStatus.NEEDS_CLARIFICATION,
                raw_text=ir.raw_input,
                assessment=assessment,
                correction_outcome=CorrectionIngestOutcome.CORRECTION_REPLACEMENT_NON_MATERIALIZABLE,
                issues=[
                    _issue(
                        "correction.replacement_non_materializable",
                        "replacement not persistable",
                    ),
                    *assessment.validation.errors,
                ],
            )

        approved = ApprovedKnowledge.certify(candidate, assessment, now)
        try:
            materialization = self._materializer.materialize(approved, uow)
            repl = _replacement_ref_from_mat(materialization, repl_intent)
            if repl is None:
                uow.rollback()
                return IngestResult(
                    status=IngestStatus.NEEDS_CLARIFICATION,
                    raw_text=ir.raw_input,
                    correction_outcome=CorrectionIngestOutcome.CORRECTION_REPLACEMENT_NON_MATERIALIZABLE,
                    issues=[_issue("correction.replacement_id_missing", "no replacement id")],
                )
            repl_kind, repl_id = repl
            committed = self._corrections.replace(
                uow,
                user_id=user.user_id,
                target_kind=target_ref.kind,
                target_id=target_ref.assertion_id,
                replacement_kind=repl_kind,
                replacement_id=repl_id,
                raw_input_id=materialization.raw_input_id,
                source_id=materialization.source_ids[0] if materialization.source_ids else None,
                commit=False,
            )
            materialization = materialization.model_copy(
                update={"correction_ids": [committed.id]}
            )
            uow.commit()
        except Exception as exc:
            uow.rollback()
            if isinstance(exc, CorrectionRejected):
                return IngestResult(
                    status=IngestStatus.REJECTED,
                    raw_text=ir.raw_input,
                    correction_outcome=CorrectionIngestOutcome.CORRECTION_REJECTED,
                    issues=[_issue("correction.rejected", str(exc))],
                )
            raise

        return IngestResult(
            status=IngestStatus.COMMITTED,
            raw_text=ir.raw_input,
            assessment=assessment,
            materialization=materialization,
            correction_outcome=CorrectionIngestOutcome.CORRECTION_APPLIED,
            bound_entity_ids=[
                *materialization.created_entity_ids,
                *materialization.reused_entity_ids,
            ],
        )
