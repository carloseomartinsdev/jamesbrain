"""IngestService — orquestra o pipeline. Não persiste candidato inválido."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable

from pke.application.builder import KnowledgeCandidateBuilder
from pke.application.clock import Clock
from pke.application.correction_ingest import CorrectionIngestOrchestrator
from pke.application.materializer import ApprovedKnowledge, KnowledgeMaterializer
from pke.application.results import IngestResult, IngestStatus, MaterializationResult
from pke.interpretation.semantic.execution_readiness import (
    question_key_for_reason,
)
from pke.application.principal import PrincipalBindingService
from pke.application.session import SessionContext
from pke.domain.temporal_knowledge import TemporalKnowledge
from pke.domain.value_objects import SourceKind, TimeValue, UserContext
from pke.interpretation.interpreter import InterpretationContext, InterpretationError, Interpreter
from pke.interpretation.models import (
    CorrectionStrategy,
    IngestIntent,
    IngestIR,
    MentionReferenceKind,
    QueryIR,
)
from pke.ontology.registry import OntologyRegistry
from pke.ontology.seeds import core_concept_id
from pke.persist.contracts import UnitOfWork
from pke.reasoning.assessment import KnowledgeAssessment, KnowledgeAssessor
from pke.reasoning.candidate import MentionBinding
from pke.reasoning.completeness import ClarificationCandidate
from pke.reasoning.issues import Issue, Severity
from pke.resolution.context import ResolutionContext
from pke.resolution.entities import EntityResolver
from pke.resolution.errors import InsufficientTemporalContextError, TemporalError
from pke.resolution.lookup import InMemoryEntityLookup
from pke.resolution.self_ref import is_self_entity_mention
from pke.resolution.temporal import TemporalContext, TemporalResolver


class IngestService:
    def __init__(
        self,
        interpreter: Interpreter,
        ontology: OntologyRegistry,
        open_uow: Callable[[], UnitOfWork],
        clock: Clock,
        *,
        temporal: TemporalResolver | None = None,
        builder: KnowledgeCandidateBuilder | None = None,
        materializer: KnowledgeMaterializer | None = None,
    ) -> None:
        self._interpreter = interpreter
        self._ontology = ontology
        self._open_uow = open_uow
        self._clock = clock
        self._temporal = temporal or TemporalResolver()
        self._builder = builder or KnowledgeCandidateBuilder()
        self._materializer = materializer or KnowledgeMaterializer(ontology)
        self._correction_ingest = CorrectionIngestOrchestrator(
            ontology, clock, builder=self._builder, materializer=self._materializer
        )
        self._principal = PrincipalBindingService()

    def ingest(self, raw: str, user: UserContext, session: SessionContext) -> IngestResult:
        if session.user_id != user.user_id:
            raise ValueError("SessionContext isolado por usuário")
        now = self._instant(user)
        try:
            interpreted = self._interpreter.interpret(
                raw,
                InterpretationContext(
                    user=user,
                    recent_event_ids=session.recent_event_ids,
                    recent_utterances=list(session.recent_utterances),
                ),
            )
        except InterpretationError as exc:
            mapped = ingest_result_from_interpretation_error(raw, exc)
            if mapped is not None:
                return mapped
            return IngestResult(
                status=IngestStatus.REJECTED,
                raw_text=raw,
                issues=[_issue("interpretation.failed", str(exc))],
            )
        if isinstance(interpreted, QueryIR):
            return IngestResult(status=IngestStatus.UNSUPPORTED, raw_text=raw)
        return self.ingest_from_ir(interpreted, user, session, now=now)

    def ingest_from_ir(
        self,
        ir: IngestIR,
        user: UserContext,
        session: SessionContext,
        *,
        now: dt.datetime | None = None,
    ) -> IngestResult:
        """Persist from an already-resolved IngestIR — no Interpreter call.

        Used by bounded clarification recovery (I12.13). Transaction owner: this method / UoW.
        """
        if session.user_id != user.user_id:
            raise ValueError("SessionContext isolado por usuário")
        raw = ir.raw_input
        if now is None:
            now = self._instant(user)
        from pke.interpretation.semantic.learned_relation import bind_learned_relation_types

        bind_learned_relation_types(self._ontology, ir)
        uow = self._open_uow()
        with uow:
            lookup = self._hydrate(uow, user.user_id)
            # Correction Engine path (I11.17.3) — operation+target; no LAST_EVENT authority
            if (
                ir.intent is IngestIntent.CORRECT
                and ir.correction is not None
                and ir.correction.operation is not None
            ):
                return self._correction_ingest.ingest(
                    ir=ir,
                    user=user,
                    session=session,
                    uow=uow,
                    lookup=lookup,
                    now=now,
                    resolve_entities=lambda ir_, user_, session_, lookup_: self._resolve_entities(
                        ir_, user_, session_, lookup_, uow=uow, now=now
                    ),
                    resolve_times=self._times,
                )
            ir = self._concretize_correction(ir, session, uow)
            try:
                resolved_temporal, resolved_due = self._times(ir, user, now)
            except InsufficientTemporalContextError as exc:
                return IngestResult(
                    status=IngestStatus.NEEDS_CLARIFICATION,
                    raw_text=ir.raw_input,
                    issues=[_issue("time.missing", str(exc), rule_id="time.event_resolved")],
                )
            except TemporalError as exc:
                return IngestResult(
                    status=IngestStatus.REJECTED,
                    raw_text=ir.raw_input,
                    issues=[_issue("time.invalid", str(exc), rule_id="time.event_resolved")],
                )
            bindings = self._resolve_entities(ir, user, session, lookup, uow=uow, now=now)
            source_kind = (
                SourceKind.CORRECTION
                if ir.intent is IngestIntent.CORRECT
                else SourceKind.USER_STATEMENT
            )
            candidate = self._builder.build(
                user_id=user.user_id,
                ir=ir,
                bindings=bindings,
                resolved_temporal=resolved_temporal,
                resolved_due=resolved_due,
                source_kind=source_kind,
            )
            assessor = KnowledgeAssessor(self._ontology, lookup)
            assessment = assessor.assess(candidate)
            if not assessment.persistable:
                return self._blocked(raw, assessment)
            approved = ApprovedKnowledge.certify(candidate, assessment, now)
            try:
                materialization = self._materializer.materialize(approved, uow)
                uow.commit()
            except Exception as exc:
                uow.rollback()
                from pke.application.errors import MaterializationDenied
                from pke.persist.errors import StorageIntegrityError

                if isinstance(exc, (MaterializationDenied, StorageIntegrityError)):
                    return IngestResult(
                        status=IngestStatus.REJECTED,
                        raw_text=raw,
                        assessment=assessment,
                        issues=[_issue("materialization.denied", str(exc))],
                    )
                raise
            updated = self._touch_context(session, materialization, uow, bindings)
            return IngestResult(
                status=IngestStatus.COMMITTED,
                raw_text=raw,
                assessment=assessment,
                materialization=materialization,
                clarification=assessment.clarification,
                issues=[*assessment.validation.warnings],
                bound_entity_ids=[
                    *materialization.created_entity_ids,
                    *materialization.reused_entity_ids,
                ],
                context_updated=updated,
            )

    def _instant(self, user: UserContext) -> dt.datetime:
        instant = user.now if user.now is not None else self._clock.now()
        if instant.tzinfo is None:
            raise ValueError("instante operacional exige timezone")
        return instant

    def _hydrate(self, uow: UnitOfWork, user_id: str) -> InMemoryEntityLookup:
        lookup = InMemoryEntityLookup()
        for entity in uow.entities.all_for_user(user_id):
            lookup.add(entity)
        return lookup

    def _concretize_correction(
        self,
        ir: IngestIR,
        session: SessionContext,
        uow: UnitOfWork,
    ) -> IngestIR:
        corr = ir.correction
        if corr is None:
            return ir
        if corr.event_id or corr.fact_id:
            return ir
        if corr.strategy is not CorrectionStrategy.LAST_EVENT:
            return ir
        event_id = session.last_event_id
        fact_id = session.last_fact_ids.get("attribute.amount")
        if event_id and not fact_id:
            hist = uow.facts.history(
                session.user_id,
                event_id,
                core_concept_id("attribute.amount"),
            )
            current = next((fact for fact in reversed(hist) if fact.is_current), None)
            fact_id = current.id if current else None
        if event_id is None and fact_id is None:
            return ir
        return ir.model_copy(
            update={
                "correction": corr.model_copy(update={"event_id": event_id, "fact_id": fact_id})
            }
        )

    def _times(
        self,
        ir: IngestIR,
        user: UserContext,
        now: dt.datetime,
    ) -> tuple[TemporalKnowledge | None, TimeValue | None]:
        resolved_temporal: TemporalKnowledge | None = None
        resolved_due: TimeValue | None = None
        if ir.event is not None:
            resolved_temporal = self._temporal.resolve(
                ir.event.time,
                TemporalContext(user=user, event_status=ir.event.status, reference_at=now),
            )
        elif ir.state is not None:
            resolved_temporal = self._temporal.resolve(
                ir.state.time,
                TemporalContext(user=user, reference_at=now),
            )
        elif ir.attribute is not None:
            # Descriptive Attribute: unknown fact time is valid; do not force calendar resolution
            try:
                resolved_temporal = self._temporal.resolve(
                    ir.attribute.time,
                    TemporalContext(user=user, reference_at=now),
                )
            except (InsufficientTemporalContextError, TemporalError):
                from pke.domain.temporal_knowledge import TemporalUnknownReason

                resolved_temporal = TemporalKnowledge.unknown(
                    ir.attribute.time.original_text or "",
                    unknown_reason=TemporalUnknownReason.NOT_PROVIDED,
                    tense_evidence=ir.attribute.time.tense_evidence,
                )
        elif ir.measurement is not None:
            try:
                resolved_temporal = self._temporal.resolve(
                    ir.measurement.time,
                    TemporalContext(user=user, reference_at=now),
                )
            except (InsufficientTemporalContextError, TemporalError):
                from pke.domain.temporal_knowledge import TemporalUnknownReason

                resolved_temporal = TemporalKnowledge.unknown(
                    ir.measurement.time.original_text or "",
                    unknown_reason=TemporalUnknownReason.NOT_PROVIDED,
                    tense_evidence=ir.measurement.time.tense_evidence,
                )
        elif ir.relation is not None:
            resolved_temporal = self._temporal.resolve(
                ir.relation.time,
                TemporalContext(user=user, reference_at=now),
            )
        if ir.obligation is not None and ir.obligation.due is not None:
            due_temporal = self._temporal.resolve(
                ir.obligation.due,
                TemporalContext(user=user, reference_at=now),
            )
            resolved_due = due_temporal.calendar if due_temporal.has_calendar_anchor() else None
        return resolved_temporal, resolved_due

    def _resolve_entities(
        self,
        ir: IngestIR,
        user: UserContext,
        session: SessionContext,
        lookup: InMemoryEntityLookup,
        *,
        uow: UnitOfWork | None = None,
        now: dt.datetime | None = None,
    ) -> list[MentionBinding]:
        mentions = list(self._builder.collect_mentions(ir))
        principal_entity_id: str | None = None
        owned_vehicle_ids: list[str] = []
        needs_principal = any(is_self_entity_mention(m) for m in mentions) or any(
            m.reference_kind in {MentionReferenceKind.CONTEXTUAL, MentionReferenceKind.POSSESSIVE}
            and m.type_hint is not None
            and m.type_hint.key
            in {"entity.vehicle", "entity.automobile", "vehicle", "automobile"}
            for m in mentions
        )
        # Wire entity_type is entity.vehicle — also accept kind-like keys from type_hint.
        if not needs_principal:
            for m in mentions:
                key = m.type_hint.key if m.type_hint else ""
                if m.reference_kind in {
                    MentionReferenceKind.CONTEXTUAL,
                    MentionReferenceKind.POSSESSIVE,
                } and (
                    key.endswith(".vehicle") or key == "vehicle" or "vehicle" in key
                ):
                    needs_principal = True
                    break
        if uow is not None and needs_principal:
            principal_entity_id = self._principal.ensure_principal_entity(
                uow, user.user_id, now=now
            )
            # Re-hydrate so CREATE/RESOLVE see the new principal Entity.
            for entity in uow.entities.all_for_user(user.user_id):
                lookup.add(entity)
            from pke.application.ownership import owned_vehicle_entity_ids

            entities_map = {e.id: e for e in uow.entities.all_for_user(user.user_id)}
            owned_vehicle_ids = owned_vehicle_entity_ids(
                principal_entity_id=principal_entity_id,
                relations=uow.relations.for_entity(user.user_id, principal_entity_id),
                entities=entities_map,
                ontology=self._ontology,
            )
        resolver = EntityResolver(lookup, self._ontology)
        context = ResolutionContext(
            user_id=user.user_id,
            personal=session.personal,
            principal_entity_id=principal_entity_id,
            owned_vehicle_entity_ids=owned_vehicle_ids,
        )
        bindings: list[MentionBinding] = []
        for mention in mentions:
            bindings.append(
                MentionBinding(mention=mention, resolution=resolver.resolve(mention, context))
            )
        return bindings

    def _blocked(self, raw: str, assessment: KnowledgeAssessment) -> IngestResult:
        issues = [*assessment.validation.errors, *assessment.validation.warnings]
        if assessment.validation.valid and assessment.completeness.blocking:
            status = IngestStatus.NEEDS_CLARIFICATION
        elif _only_unresolved_target(assessment):
            status = IngestStatus.NEEDS_CLARIFICATION
        else:
            status = IngestStatus.REJECTED
        return IngestResult(
            status=status,
            raw_text=raw,
            assessment=assessment,
            clarification=assessment.clarification,
            issues=issues,
        )

    def _touch_context(
        self,
        session: SessionContext,
        materialization: MaterializationResult,
        uow: UnitOfWork,
        bindings: list[MentionBinding],
    ) -> bool:
        try:
            for entity_id in [
                *materialization.created_entity_ids,
                *materialization.reused_entity_ids,
            ]:
                entity = uow.entities.get(session.user_id, entity_id)
                if entity is None:
                    continue
                role = next(
                    (
                        b.mention.role.key
                        for b in bindings
                        if b.mention.text
                        and (
                            b.resolution.entity_id == entity_id
                            or b.resolution.create_canonical_name == entity.canonical_name
                        )
                        and b.mention.role is not None
                    ),
                    None,
                )
                session.personal.record_mention(entity, role)
            if materialization.event_ids:
                session.last_event_id = materialization.event_ids[-1]
                session.recent_event_ids.extend(materialization.event_ids)
            for fact_id in materialization.fact_ids:
                fact = uow.facts.get(session.user_id, fact_id)
                if fact is not None and fact.key == "attribute.amount":
                    session.last_fact_ids["attribute.amount"] = fact.id
            return True
        except Exception:
            return False


def ingest_result_from_interpretation_error(
    raw: str,
    exc: InterpretationError,
    *,
    proposal_dump: dict | None = None,
) -> IngestResult | None:
    """Map execution-incomplete Interpreter outcomes via CapabilityStrategy (E1.3)."""
    msg = str(exc)
    if not msg.startswith("semantic_resolution:execution_incomplete"):
        return None
    reason = msg.split(":", 2)[-1] if msg.count(":") >= 2 else "execution_incomplete"
    first = reason.split(",")[0] if reason else "execution_incomplete"
    issue = _issue("execution.incomplete", first, rule_id="execution_readiness")

    from pke.application.pending_operation import PendingSemanticOperation
    from pke.interpretation.semantic.capability_strategy import (
        CapabilityOutcome,
        decide_capability,
    )
    from pke.interpretation.semantic.execution_readiness import assess_execution_readiness
    from pke.interpretation.semantic.models import SemanticProposal
    from pke.interpretation.semantic.pipeline import resolve_proposal

    decision = None
    pending = None
    if proposal_dump is not None:
        try:
            proposal = SemanticProposal.model_validate(proposal_dump)
            readiness = assess_execution_readiness(resolve_proposal(proposal))
            decision = decide_capability(readiness, proposal=proposal)
            if (
                decision.outcome is CapabilityOutcome.CLARIFY
                and decision.clarification is not None
            ):
                pending = PendingSemanticOperation(
                    originating_raw=raw,
                    proposal_dump=proposal_dump,
                    missing_slot=decision.clarification.missing_slot,
                    expected_answer_kind=decision.clarification.expected_answer_kind,
                    primitive=decision.clarification.primitive.value,
                    reason=decision.clarification.reason,
                    question_key=decision.clarification.question_key,
                )
        except Exception:
            decision = None
            pending = None

    if decision is not None and decision.outcome is CapabilityOutcome.CLARIFY:
        clar_reason = decision.primary_reason or first
        return IngestResult(
            status=IngestStatus.NEEDS_CLARIFICATION,
            raw_text=raw,
            clarification=ClarificationCandidate(
                concept_key=clar_reason,
                priority=1,
                reason=clar_reason,
                question_key=(
                    decision.clarification.question_key
                    if decision.clarification is not None
                    else question_key_for_reason(clar_reason)
                ),
                blocking=True,
            ),
            issues=[issue],
            pending_operation=pending,
        )

    if decision is not None and decision.outcome is CapabilityOutcome.UNSUPPORTED:
        return IngestResult(
            status=IngestStatus.UNSUPPORTED,
            raw_text=raw,
            issues=[issue],
        )

    if decision is not None and decision.outcome is CapabilityOutcome.SAFE_ABSTAIN:
        return IngestResult(
            status=IngestStatus.UNSUPPORTED,
            raw_text=raw,
            issues=[issue],
        )

    # Fallback without proposal dump: do not default missing_attribute_dimension to CLARIFY.
    unlockable_fallback = {
        "missing_entity",
        "missing_relation_object",
        "missing_relation_subject",
        "missing_state_value",
        "missing_measurement_dimension",
        "missing_measurement_value",
        "missing_attribute_value",
        "ambiguous_correction_target",
    }
    if first in unlockable_fallback:
        return IngestResult(
            status=IngestStatus.NEEDS_CLARIFICATION,
            raw_text=raw,
            clarification=ClarificationCandidate(
                concept_key=first,
                priority=1,
                reason=first,
                question_key=question_key_for_reason(first),
                blocking=True,
            ),
            issues=[issue],
            pending_operation=pending,
        )
    return IngestResult(
        status=IngestStatus.UNSUPPORTED,
        raw_text=raw,
        issues=[issue],
    )


def _only_unresolved_target(assessment: KnowledgeAssessment) -> bool:
    codes = {issue.code for issue in assessment.validation.errors}
    return codes <= {"correction.target_unresolved"} and bool(codes)


def _issue(code: str, message: str, rule_id: str = "application") -> Issue:
    return Issue(code=code, rule_id=rule_id, message=message, severity=Severity.ERROR)
