"""DeepSeekInterpreter — LLM só propõe IR. Pydantic valida. Sem persist/query.

I12.2: bounded provider retry lives here (pre-commit). Failed attempts never reach
materialization. Attempt outputs are never merged.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable

from pydantic import ValidationError

from pke.interpretation.envelope import LlmIrEnvelope, interpretation_json_schema
from pke.interpretation.interpreter import InterpretationContext, InterpretationError
from pke.interpretation.models import IngestIR, InterpretationResult, QueryIR
from pke.interpretation.ontology_view import InterpreterOntologyView
from pke.interpretation.prompts import (
    PROMPT_VERSION_V1,
    PROMPT_VERSION_V2,
    PROMPT_VERSION_V3,
    PROMPT_VERSION_V4,
    PROMPT_VERSION_V5_EVENT,
    build_messages,
)
from pke.interpretation.retry import (
    AttemptRecord,
    FailureClass,
    InterpreterRequestTrace,
    InterpreterRetryMetrics,
    RETRY_STRUCTURAL_REMINDER,
    RetryPolicy,
    new_interpreter_request_id,
)
from pke.interpretation.semantic.envelope_dispatch import ProviderRoute, dispatch_provider_payload
from pke.interpretation.semantic.proposal_assessment import SemanticActionability, assess_semantic_proposal
from pke.interpretation.semantic.pipeline import (
    SemanticResolutionOutcome,
    proposal_to_canonical_ir,
    resolve_proposal,
)
from pke.interpretation.transport.proposal_wire import WireSemanticEnvelope
from pke.interpretation.transport import ConceptCatalog, WireEnvelope, wire_to_canonical
from pke.interpretation.transport.schema import WIRE_SCHEMA_HINT
from pke.llm.errors import LlmError, LlmInvalidResponseError, LlmSchemaValidationError
from pke.llm.models import LlmCallMetadata, LlmMessage, LlmMetrics, LlmStructuredRequest
from pke.llm.provider import LlmProvider
from pke.llm.validation import format_validation_issues
from pke.ontology.registry import OntologyRegistry

_LOG = logging.getLogger("pke.interpretation.retry")


class DeepSeekInterpreter:
    """Satisfaz Interpreter. Saída do LLM é proposta, não conhecimento."""

    def __init__(
        self,
        provider: LlmProvider,
        ontology: OntologyRegistry | InterpreterOntologyView,
        *,
        metrics: LlmMetrics | None = None,
        prompt_version: str = PROMPT_VERSION_V4,
        retry_policy: RetryPolicy | None = None,
        sleeper: Callable[[float], None] | None = None,
        retry_metrics: InterpreterRetryMetrics | None = None,
    ) -> None:
        self._provider = provider
        self._prompt_version = prompt_version
        if isinstance(ontology, OntologyRegistry):
            ConceptCatalog.load(ontology)
            self._view = InterpreterOntologyView.from_registry(ontology)
        else:
            self._view = ontology
            ConceptCatalog.load_from_view(ontology)
        self._metrics = metrics or LlmMetrics()
        self._retry_policy = retry_policy or RetryPolicy()
        self._sleeper = sleeper or time.sleep
        self._retry_metrics = retry_metrics or InterpreterRetryMetrics()
        self._canonical_schema = interpretation_json_schema()
        self._wire_schema = WIRE_SCHEMA_HINT
        self.last_metadata: LlmCallMetadata | None = None
        self.last_raw_content: str | None = None
        self.last_validation_issues: list[dict] | None = None
        self.last_dispatch_route: str | None = None
        self.last_v2_compat_fallback: bool = False
        self.last_semantic_assessment: object | None = None
        self.last_execution_readiness: object | None = None
        self.last_interpreter_request_id: str | None = None
        self.last_provider_attempts: int = 0
        self.last_request_trace: InterpreterRequestTrace | None = None
        self.last_acceptance_decision: object | None = None
        self._prior_utterances: tuple[str, ...] = ()
        self._wire_stage_failed = False
        self._trace_file_id: str | None = None
        self._trace_client_request_id: str | None = None
        self._trace_pke_request_id: str | None = None
        self._trace_user_text: str = ""

    @property
    def metrics(self) -> LlmMetrics:
        return self._metrics

    @property
    def retry_metrics(self) -> InterpreterRetryMetrics:
        return self._retry_metrics

    @property
    def retry_policy(self) -> RetryPolicy:
        return self._retry_policy

    @property
    def prompt_version(self) -> str:
        return self._prompt_version

    def interpret(self, raw: str, ctx: InterpretationContext) -> InterpretationResult:
        self._metrics.interpret_attempts += 1
        self._retry_metrics.interpreter_requests += 1
        request_id = new_interpreter_request_id()
        self.last_interpreter_request_id = request_id
        trace = InterpreterRequestTrace(interpreter_request_id=request_id)
        self.last_request_trace = trace

        use_wire = self._prompt_version in {
            PROMPT_VERSION_V2,
            PROMPT_VERSION_V3,
            PROMPT_VERSION_V4,
            PROMPT_VERSION_V5_EVENT,
        }
        use_proposal = self._prompt_version in {
            PROMPT_VERSION_V3,
            PROMPT_VERSION_V4,
            PROMPT_VERSION_V5_EVENT,
        }
        schema = self._wire_schema if use_wire else self._canonical_schema
        self._prior_utterances = tuple(ctx.recent_utterances or ())
        self.last_acceptance_decision = None
        self.last_execution_readiness = None
        self._trace_file_id = (ctx.client_request_id or "").strip() or request_id
        self._trace_client_request_id = ctx.client_request_id
        self._trace_pke_request_id = ctx.pke_request_id
        self._trace_user_text = raw
        try:
            from pke.debug.trace_context import update_trace

            update_trace(
                client_request_id=ctx.client_request_id,
                pke_request_id=ctx.pke_request_id,
                interpreter_request_id=request_id,
            )
        except Exception:
            pass
        base_messages = build_messages(
            raw,
            ctx,
            self._view,
            prompt_version=self._prompt_version,
            schema=schema,
        )

        policy = self._retry_policy
        last_error: Exception | None = None
        provider_attempts = 0

        for attempt in range(1, policy.max_attempts + 1):
            record = AttemptRecord(attempt_number=attempt)
            messages = list(base_messages)
            if attempt > 1:
                messages.append(LlmMessage(role="user", content=RETRY_STRUCTURAL_REMINDER))

            request = LlmStructuredRequest(messages=messages, json_schema=schema)
            try:
                response = self._provider.generate_structured(request)
                provider_attempts += 1
                self._retry_metrics.provider_attempts += 1
                self.last_metadata = response.metadata
                # Discard previous attempt content — never merge
                self.last_raw_content = response.content
                self._metrics.record_call(response.metadata)
                record.provider_request_id = response.metadata.request_id
                self._log_llm_response(attempt=attempt, metadata=response.metadata)

                ir = self._parse_response(
                    response.content, use_wire=use_wire, use_proposal=use_proposal
                )
            except LlmInvalidResponseError as exc:
                provider_attempts += 1
                self._retry_metrics.provider_attempts += 1
                self._metrics.provider_json_failures += 1
                self._metrics.provider_failures += 1
                wrapped = InterpretationError(f"provider: {exc}")
                wrapped.__cause__ = exc
                last_error = wrapped
                klass = policy.classify(wrapped)
                self._note_failure_class(klass)
                record.failure_class = klass
                if policy.is_retryable(wrapped, attempt=attempt):
                    record.retry_decision = "retry"
                    self._retry_metrics.retry_triggered += 1
                    trace.attempts.append(record)
                    self._log_attempt(request_id, record)
                    self._sleeper(policy.delay_seconds)
                    continue
                self._mark_exhausted(trace, attempt)
                record.retry_decision = "fail"
                self._retry_metrics.non_retryable_failures += 1
                trace.attempts.append(record)
                self._log_attempt(request_id, record)
                self.last_provider_attempts = provider_attempts
                raise wrapped from exc
            except LlmError as exc:
                provider_attempts += 1
                self._retry_metrics.provider_attempts += 1
                self._metrics.provider_failures += 1
                wrapped = InterpretationError(f"provider: {exc}")
                wrapped.__cause__ = exc
                last_error = wrapped
                klass = policy.classify(wrapped)
                self._note_failure_class(klass)
                record.failure_class = klass
                if policy.is_retryable(wrapped, attempt=attempt):
                    record.retry_decision = "retry"
                    self._retry_metrics.retry_triggered += 1
                    trace.attempts.append(record)
                    self._log_attempt(request_id, record)
                    self._sleeper(policy.delay_seconds)
                    continue
                self._mark_exhausted(trace, attempt)
                record.retry_decision = "fail"
                self._retry_metrics.non_retryable_failures += 1
                trace.attempts.append(record)
                self._log_attempt(request_id, record)
                self.last_provider_attempts = provider_attempts
                raise wrapped from exc
            except json.JSONDecodeError as exc:
                self._metrics.provider_json_failures += 1
                self._metrics.schema_failures += 1
                issues = [
                    {
                        "path": "",
                        "type": "json_invalid",
                        "reason": str(exc),
                        "input": content_preview(self.last_raw_content or ""),
                    }
                ]
                self.last_validation_issues = issues
                schema_error = LlmSchemaValidationError(issues=issues)
                wrapped = InterpretationError(schema_error.summary())
                wrapped.__cause__ = schema_error
                last_error = wrapped
                klass = FailureClass.INVALID_JSON
                self._retry_metrics.invalid_json_responses += 1
                record.failure_class = klass
                if policy.is_retryable(wrapped, attempt=attempt):
                    record.retry_decision = "retry"
                    self._retry_metrics.retry_triggered += 1
                    trace.attempts.append(record)
                    self._log_attempt(request_id, record)
                    self._sleeper(policy.delay_seconds)
                    continue
                self._mark_exhausted(trace, attempt)
                record.retry_decision = "fail"
                self._retry_metrics.non_retryable_failures += 1
                trace.attempts.append(record)
                self.last_provider_attempts = provider_attempts
                raise wrapped from schema_error
            except ValidationError as exc:
                self._metrics.schema_failures += 1
                if use_wire and self._wire_stage_failed:
                    self._metrics.wire_failures += 1
                else:
                    self._metrics.canonical_failures += 1
                issues = format_validation_issues(exc)
                self.last_validation_issues = issues
                schema_error = LlmSchemaValidationError(issues=issues)
                wrapped = InterpretationError(schema_error.summary())
                wrapped.__cause__ = schema_error
                last_error = wrapped
                klass = FailureClass.SCHEMA_INVALID
                self._retry_metrics.schema_invalid_responses += 1
                record.failure_class = klass
                if policy.is_retryable(wrapped, attempt=attempt):
                    record.retry_decision = "retry"
                    self._retry_metrics.retry_triggered += 1
                    trace.attempts.append(record)
                    self._log_attempt(request_id, record)
                    self._sleeper(policy.delay_seconds)
                    continue
                self._mark_exhausted(trace, attempt)
                record.retry_decision = "fail"
                self._retry_metrics.non_retryable_failures += 1
                trace.attempts.append(record)
                self.last_provider_attempts = provider_attempts
                raise wrapped from schema_error
            except InterpretationError as exc:
                last_error = exc
                klass = policy.classify(exc)
                self._note_failure_class(klass)
                record.failure_class = klass
                # Schema/transport InterpretationErrors may be retryable; semantic are not
                if policy.is_retryable(exc, attempt=attempt):
                    if klass is FailureClass.SCHEMA_INVALID:
                        self._metrics.schema_failures += 1
                    record.retry_decision = "retry"
                    self._retry_metrics.retry_triggered += 1
                    trace.attempts.append(record)
                    self._log_attempt(request_id, record)
                    self._sleeper(policy.delay_seconds)
                    continue
                self._mark_exhausted(trace, attempt)
                record.retry_decision = "fail"
                self._retry_metrics.non_retryable_failures += 1
                trace.attempts.append(record)
                self._log_attempt(request_id, record)
                self.last_provider_attempts = provider_attempts
                raise

            # Success — single accepted proposal
            record.success = True
            record.retry_decision = "accept"
            trace.attempts.append(record)
            if attempt == 1:
                self._retry_metrics.first_attempt_success += 1
            else:
                self._retry_metrics.retry_succeeded += 1
                self._retry_metrics.recovered_requests += 1
                trace.recovered = True
            self.last_provider_attempts = provider_attempts
            self._log_attempt(request_id, record)
            accepted = ir.model_copy(update={"raw_input": raw})
            self._metrics.successes += 1
            return accepted

        # Exhausted (defensive — normal path raises inside the loop)
        trace.exhausted = True
        self._retry_metrics.retry_exhausted += 1
        self.last_provider_attempts = provider_attempts
        assert last_error is not None
        _LOG.info(
            "interpreter_retry_exhausted request_id=%s attempts=%s",
            request_id,
            provider_attempts,
        )
        raise last_error

    def _mark_exhausted(self, trace: InterpreterRequestTrace, attempt: int) -> None:
        """Count exhaustion when the final attempt fails after a prior retry."""
        if attempt > 1:
            trace.exhausted = True
            self._retry_metrics.retry_exhausted += 1

    def _note_failure_class(self, klass: FailureClass) -> None:
        if klass is FailureClass.TIMEOUT:
            self._retry_metrics.timeout_responses += 1
        elif klass in {FailureClass.HTTP_5XX, FailureClass.TEMPORARY_NETWORK, FailureClass.RATE_LIMITED}:
            self._retry_metrics.temporary_provider_failures += 1
        elif klass is FailureClass.INVALID_JSON:
            self._retry_metrics.invalid_json_responses += 1
        elif klass is FailureClass.SCHEMA_INVALID:
            self._retry_metrics.schema_invalid_responses += 1
        elif klass is FailureClass.EMPTY_RESPONSE:
            self._retry_metrics.invalid_json_responses += 1
        elif klass is FailureClass.TRUNCATED:
            self._retry_metrics.invalid_json_responses += 1

    def _log_attempt(self, request_id: str, record: AttemptRecord) -> None:
        _LOG.info(
            "interpreter_attempt request_id=%s attempt=%s failure=%s decision=%s success=%s",
            request_id,
            record.attempt_number,
            record.failure_class.value if record.failure_class else None,
            record.retry_decision,
            record.success,
        )

    def _log_llm_response(self, *, attempt: int, metadata: LlmCallMetadata) -> None:
        self._trace_stage(
            "llm_response",
            self.last_raw_content or "",
            provider_request_id=metadata.request_id,
            attempt=attempt,
            model=metadata.model,
            latency_ms=int(metadata.latency_ms),
        )

    def _trace_stage(self, stage: str, body: object = "", **meta: object) -> None:
        try:
            from pke.debug.request_log import append_stage
            from pke.debug.trace_context import current_trace

            if not isinstance(body, str):
                from pke.debug.request_log import dump_model

                body = dump_model(body)
            ids = current_trace()
            append_stage(
                self._trace_file_id,
                stage,
                body,
                client_request_id=self._trace_client_request_id or ids.client_request_id,
                pke_request_id=self._trace_pke_request_id or ids.pke_request_id,
                interpreter_request_id=self.last_interpreter_request_id,
                conversation_id=ids.conversation_id,
                user_message_id=ids.user_message_id,
                user_text=self._trace_user_text,
                **meta,
            )
        except Exception:
            return

    def _parse_response(
        self,
        content: str,
        *,
        use_wire: bool,
        use_proposal: bool = False,
    ) -> InterpretationResult:
        self._wire_stage_failed = False
        if use_wire and use_proposal:
            dispatched = dispatch_provider_payload(content)
            self.last_dispatch_route = dispatched.route.value
            self.last_v2_compat_fallback = dispatched.v2_compat_fallback
            self._trace_stage(
                "normalize",
                dispatched.payload,
                route=dispatched.route.value,
                notes=list(dispatched.notes),
                failure_stage=dispatched.failure_stage,
                failure_category=(
                    dispatched.failure_category.value
                    if dispatched.failure_category is not None
                    else None
                ),
            )

            if dispatched.route is ProviderRoute.INVALID:
                self._wire_stage_failed = True
                stage = dispatched.failure_stage or "NORMALIZATION"
                raise InterpretationError(
                    f"{stage.lower()}:{dispatched.notes[0] if dispatched.notes else 'invalid'}"
                )

            if dispatched.route is ProviderRoute.V2_CANONICAL:
                self.last_v2_compat_fallback = True
                ir = self._parse_v2_wire(content, dispatched.payload)
                self._trace_stage("canonical", ir, ir_type=type(ir).__name__, wire_stage="v2")
                return ir

            try:
                envelope = WireSemanticEnvelope.model_validate(dispatched.payload)
            except ValidationError as exc:
                self._wire_stage_failed = True
                self._trace_stage(
                    "parse_error",
                    format_validation_issues(exc),
                    reason="proposal_transport:schema",
                )
                raise InterpretationError("proposal_transport:schema") from exc

            if envelope.ir_kind in {"semantic_proposal", "semantic_query"}:
                proposal = (
                    envelope.parsed_query_proposal()
                    if envelope.ir_kind == "semantic_query"
                    else envelope.parsed_proposal()
                )
                self._trace_stage("proposal", proposal, ir_kind=envelope.ir_kind)
                from pke.interpretation.semantic.self_repair import (
                    apply_e1_self_repairs,
                    last_applied_repairs,
                )

                proposal = apply_e1_self_repairs(
                    proposal, prior_utterances=self._prior_utterances
                )
                applied = list(last_applied_repairs())
                self._trace_stage(
                    "repair",
                    proposal,
                    utterance_kind=proposal.utterance_kind,
                    primitive_hint=proposal.primitive_hint,
                    repairs_applied=applied or None,
                )
                from pke.debug.semantic_trace import claims_trace_body

                claims_body = claims_trace_body(proposal)
                if claims_body is not None:
                    self._trace_stage("claims", claims_body)
                assessment = assess_semantic_proposal(proposal)
                self.last_semantic_assessment = assessment
                self._trace_stage(
                    "assessment",
                    {
                        "status": assessment.status.value,
                        "routed_primitive": assessment.routed_primitive.value,
                        "missing_semantic_roles": list(assessment.missing_semantic_roles),
                        "conflicting_signals": list(assessment.conflicting_signals),
                        "notes": list(assessment.notes),
                    },
                )
                if assessment.status is SemanticActionability.INSUFFICIENT:
                    raise InterpretationError(
                        f"proposal_semantics:insufficient:{','.join(assessment.missing_semantic_roles)}"
                    )
                if assessment.status is SemanticActionability.CONTRADICTORY:
                    raise InterpretationError(
                        f"proposal_semantics:contradictory:{','.join(assessment.conflicting_signals)}"
                    )
                route_as_query = proposal.utterance_kind == "query"
                if route_as_query:
                    from pke.interpretation.semantic.query_resolution import proposal_to_query_ir

                    query_outcome = proposal_to_query_ir(proposal)
                    result = resolve_proposal(proposal)
                    if query_outcome.query_ir is None:
                        stage = (
                            "ONTOLOGY_GAP"
                            if query_outcome.status.value == "ontology_gap"
                            else "CONCEPT_RESOLUTION"
                        )
                        outcome = SemanticResolutionOutcome(
                            result=result,
                            ir=None,
                            wire_stage="unresolved",
                            failure_stage=stage,
                        )
                    else:
                        outcome = SemanticResolutionOutcome(
                            result=result,
                            ir=query_outcome.query_ir,
                            wire_stage="canonical",
                        )
                    self._trace_stage(
                        "query_resolution",
                        {
                            "status": query_outcome.status.value,
                            "primitive": query_outcome.primitive.value,
                            "notes": list(query_outcome.notes),
                        },
                    )
                else:
                    outcome = proposal_to_canonical_ir(
                        proposal, prior_utterances=self._prior_utterances
                    )
                self.last_execution_readiness = outcome
                self._trace_stage(
                    "canonical",
                    outcome.ir,
                    ir_type=type(outcome.ir).__name__ if outcome.ir is not None else None,
                    wire_stage=outcome.wire_stage,
                    failure_stage=outcome.failure_stage,
                    execution_outcome=outcome.execution_outcome,
                    execution_reasons=list(outcome.execution_reasons),
                    primitive=outcome.result.primitive.value,
                    concepts_status=outcome.result.concepts.resolution_status.value,
                    concepts_notes=list(outcome.result.concepts.notes),
                    attribute_dimension=outcome.result.concepts.attribute_dimension_key,
                    attribute_value=outcome.result.concepts.attribute_text_value
                    or outcome.result.concepts.attribute_year_value,
                    relation_type=outcome.result.concepts.relation_type,
                )
                if outcome.ir is None:
                    stage = outcome.failure_stage or "CONCEPT_RESOLUTION"
                    if stage.startswith("ACCEPTANCE_GUARD"):
                        raise InterpretationError(f"acceptance_guard:{stage.split(':', 1)[-1]}")
                    if stage == "EXECUTION_INCOMPLETE":
                        reasons = ",".join(outcome.execution_reasons) or "execution_incomplete"
                        raise InterpretationError(
                            f"semantic_resolution:execution_incomplete:{reasons}"
                        )
                    raise InterpretationError(f"semantic_resolution:{stage.lower()}")
                if isinstance(outcome.ir, IngestIR):
                    return IngestIR.model_validate(outcome.ir.model_dump())
                return QueryIR.model_validate(outcome.ir.model_dump())

            self._wire_stage_failed = True
            raise InterpretationError("proposal_transport:unsupported_ir_kind")

        if use_wire:
            return self._parse_v2_wire(content, None)

        envelope = LlmIrEnvelope.model_validate_json(content)
        return envelope.to_ir()

    def _parse_v2_wire(self, content: str, payload: dict | None) -> InterpretationResult:
        try:
            if payload is not None:
                wire = WireEnvelope.model_validate(payload)
            else:
                wire = WireEnvelope.parse_json(content)
        except (json.JSONDecodeError, ValidationError):
            self._wire_stage_failed = True
            raise
        try:
            ir = wire_to_canonical(wire)
        except ValidationError:
            self._wire_stage_failed = False
            raise
        if isinstance(ir, IngestIR):
            return IngestIR.model_validate(ir.model_dump())
        return QueryIR.model_validate(ir.model_dump())


def content_preview(content: str, limit: int = 120) -> str:
    text = content.strip()
    return text[:limit] + ("…" if len(text) > limit else "")
