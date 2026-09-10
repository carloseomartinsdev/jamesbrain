"""Avaliador do benchmark I11 — interpretação + métricas por camada."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

from pke.interpretation import DeepSeekInterpreter, InterpretationContext, InterpretationError
from pke.interpretation.models import IngestIR, QueryIR
from pke.llm.errors import LlmInvalidResponseError, LlmSchemaValidationError
from pke.domain import UserContext

from tests.generalization.cases import (
    CONTEXT_PREFIXES,
    FailureCategory,
    GeneralizationCase,
    SupportLevel,
)
from tests.generalization.invariants import check_forbidden, check_semantic, stability_label


@dataclass
class RunResult:
    case_id: str
    run: int
    text: str
    variant_index: int = 0
    provider_json_valid: bool = False
    wire_valid: bool = False
    canonical_valid: bool = False
    semantic_required_pass: bool = False
    forbidden_inference_count: int = 0
    forbidden_hits: list[str] = field(default_factory=list)
    semantic_fails: list[str] = field(default_factory=list)
    failure_category: FailureCategory | None = None
    unsupported_case: bool = False
    error_class: str | None = None
    error_message: str | None = None
    raw_content_preview: str | None = None
    validation_issues: list[dict] | None = None
    ir_summary: dict | None = None
    latency_ms: float | None = None
    model: str | None = None


@dataclass
class CaseAggregate:
    case_id: str
    pass_count: int
    total_runs: int
    stability: str
    failure_categories: dict[str, int] = field(default_factory=dict)
    representative_failure: RunResult | None = None


class GeneralizationEvaluator:
    def __init__(self, interpreter: DeepSeekInterpreter, ctx: InterpretationContext) -> None:
        self._interpreter = interpreter
        self._ctx = ctx

    def evaluate_text(self, case: GeneralizationCase, text: str, *, run: int, variant_index: int = 0) -> RunResult:
        row = RunResult(case_id=case.case_id, run=run, text=text, variant_index=variant_index)
        if case.support_level is SupportLevel.UNSUPPORTED:
            row.unsupported_case = True
            row.semantic_required_pass = True
            row.provider_json_valid = True
            row.wire_valid = True
            row.canonical_valid = True
            return row

        try:
            ir = self._interpreter.interpret(text, self._ctx)
        except InterpretationError as exc:
            row.error_class = type(exc).__name__
            row.error_message = str(exc)[:500]
            cause = exc.__cause__
            if isinstance(cause, LlmInvalidResponseError):
                row.failure_category = FailureCategory.PROVIDER
            elif isinstance(cause, LlmSchemaValidationError):
                issues = getattr(self._interpreter, "last_validation_issues", None) or []
                row.validation_issues = issues[:8]
                if issues and issues[0].get("type") == "json_invalid":
                    row.failure_category = FailureCategory.PROVIDER
                elif any(str(i.get("path", "")).startswith(("ir.", "ir_kind")) for i in issues):
                    row.failure_category = FailureCategory.WIRE
                else:
                    row.failure_category = FailureCategory.CANONICAL
            else:
                row.failure_category = FailureCategory.PROVIDER
            raw = getattr(self._interpreter, "last_raw_content", None)
            if raw:
                row.raw_content_preview = raw[:2000]
            return row

        meta = self._interpreter.last_metadata
        if meta is not None:
            row.latency_ms = round(meta.latency_ms, 1)
            row.model = meta.model

        row.provider_json_valid = True
        row.wire_valid = True
        row.canonical_valid = True

        if case.support_level is SupportLevel.PARTIALLY_SUPPORTED and case.sequence_id:
            row.failure_category = FailureCategory.CONTEXT_GAP
            # ainda avalia semântica parcial

        semantic_fails = check_semantic(ir, case.expected_invariants)
        forbidden_hits = check_forbidden(ir, list(case.forbidden_inferences))
        row.semantic_fails = semantic_fails
        row.forbidden_hits = forbidden_hits
        row.forbidden_inference_count = len(forbidden_hits)
        row.semantic_required_pass = not semantic_fails and not forbidden_hits

        if not row.semantic_required_pass:
            row.failure_category = FailureCategory.SEMANTIC
            if case.support_level is SupportLevel.PARTIALLY_SUPPORTED:
                row.failure_category = FailureCategory.CONTEXT_GAP

        row.ir_summary = _ir_summary(ir)
        return row

    def evaluate_case(self, case: GeneralizationCase, *, runs: int = 3) -> list[RunResult]:
        results: list[RunResult] = []
        texts = case.all_texts()
        for run in range(1, runs + 1):
            if case.variants:
                for vi, text in enumerate(texts):
                    results.append(self.evaluate_text(case, text, run=run, variant_index=vi))
            elif case.sequence_id and case.sequence_id in CONTEXT_PREFIXES:
                prefix = "\n".join(CONTEXT_PREFIXES[case.sequence_id])
                contextual = f"{prefix}\n{case.raw_text}"
                results.append(self.evaluate_text(case, contextual, run=run))
            else:
                results.append(self.evaluate_text(case, case.raw_text, run=run))
        return results

    def aggregate_case(self, case: GeneralizationCase, runs: list[RunResult]) -> CaseAggregate:
        if case.variants:
            by_run: dict[int, list[RunResult]] = {}
            for r in runs:
                by_run.setdefault(r.run, []).append(r)
            total = len(by_run)
            pass_count = sum(
                1
                for group in by_run.values()
                if all(x.semantic_required_pass and x.canonical_valid for x in group)
            )
        else:
            run_ids = sorted({r.run for r in runs})
            total = len(run_ids)
            pass_count = 0
            for run_id in run_ids:
                subset = [r for r in runs if r.run == run_id]
                if subset and all(r.semantic_required_pass and r.canonical_valid for r in subset):
                    pass_count += 1

        cats: dict[str, int] = {}
        rep: RunResult | None = None
        for r in runs:
            if r.failure_category is not None:
                cats[r.failure_category.value] = cats.get(r.failure_category.value, 0) + 1
                if rep is None and not (r.semantic_required_pass and r.canonical_valid):
                    rep = r

        return CaseAggregate(
            case_id=case.case_id,
            pass_count=pass_count,
            total_runs=total,
            stability=stability_label(pass_count, total),
            failure_categories=cats,
            representative_failure=rep,
        )


def _ir_summary(ir: IngestIR | QueryIR) -> dict[str, Any]:
    if isinstance(ir, QueryIR):
        return {"kind": "QueryIR", "intent": ir.intent}
    summary: dict[str, Any] = {
        "kind": "IngestIR",
        "intent": ir.intent.value,
        "domains": [d.key for d in ir.domains],
        "mentions": [m.text for m in ir.entities_mentioned],
    }
    if ir.event is not None:
        summary["event_type"] = ir.event.type.key
        summary["action"] = ir.event.action.key if ir.event.action else None
        summary["time"] = {
            "original_text": ir.event.time.original_text,
            "relative_day": ir.event.time.relative_day.value if ir.event.time.relative_day else None,
            "weekday": ir.event.time.weekday,
        }
    return summary


def compute_global_metrics(all_runs: list[RunResult]) -> dict[str, Any]:
    n = len(all_runs) or 1
    unsupported = sum(1 for r in all_runs if r.unsupported_case)
    evaluated = [r for r in all_runs if not r.unsupported_case]
    en = len(evaluated) or 1
    return {
        "total_runs": n,
        "provider_json_valid_rate": round(sum(1 for r in evaluated if r.provider_json_valid) / en, 4),
        "wire_valid_rate": round(sum(1 for r in evaluated if r.wire_valid) / en, 4),
        "canonical_valid_rate": round(sum(1 for r in evaluated if r.canonical_valid) / en, 4),
        "semantic_accuracy": round(sum(1 for r in evaluated if r.semantic_required_pass) / en, 4),
        "forbidden_inference_rate": round(
            sum(1 for r in evaluated if r.forbidden_inference_count > 0) / en, 4
        ),
        "unsupported_rate": round(unsupported / n, 4),
        "provider_failures": sum(1 for r in evaluated if r.failure_category == FailureCategory.PROVIDER),
        "wire_failures": sum(1 for r in evaluated if r.failure_category == FailureCategory.WIRE),
        "canonical_failures": sum(1 for r in evaluated if r.failure_category == FailureCategory.CANONICAL),
        "semantic_failures": sum(1 for r in evaluated if r.failure_category == FailureCategory.SEMANTIC),
        "context_gaps": sum(1 for r in evaluated if r.failure_category == FailureCategory.CONTEXT_GAP),
    }


def bucket_by(field: str, cases: list[GeneralizationCase], aggregates: dict[str, CaseAggregate]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for case in cases:
        key = getattr(case, field, "") or case.domain_hint
        bucket = out.setdefault(key, {"cases": 0, "stable": 0, "unstable": 0, "weak": 0, "failed": 0})
        bucket["cases"] += 1
        agg = aggregates[case.case_id]
        if "failed" in agg.stability:
            bucket["failed"] += 1
        elif "weak" in agg.stability:
            bucket["weak"] += 1
        elif "unstable" in agg.stability:
            bucket["unstable"] += 1
        elif agg.stability.endswith(" stable"):
            bucket["stable"] += 1
    return out


def make_context(now_user: UserContext | None = None) -> InterpretationContext:
    import datetime as dt
    from zoneinfo import ZoneInfo

    fortaleza = ZoneInfo("America/Fortaleza")
    now = dt.datetime(2026, 9, 1, 15, 0, tzinfo=fortaleza)
    user = now_user or UserContext(user_id="i11-gen", timezone="America/Fortaleza", now=now)
    return InterpretationContext(user=user)
