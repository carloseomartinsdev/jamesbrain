"""I12.8 raw event scoring helpers."""

from __future__ import annotations

from dataclasses import dataclass, field

from pke.interpretation.semantic.models import PrimitiveKind, SemanticProposal
from pke.interpretation.semantic.multi_primitive_evidence import (
    has_explicit_occurrence_evidence,
    has_measurement_evidence,
)
from pke.interpretation.semantic.router import collect_assertions
from tests.engine_v1_baseline.corpus import EngineCase


def expects_event(case: EngineCase) -> bool:
    return case.expected_primitive in {"event", "multi"}


def expects_measurement(case: EngineCase) -> bool:
    return case.expected_primitive in {"measurement", "multi"}


def expects_no_event(case: EngineCase) -> bool:
    return case.expected_primitive in {"measurement", "state", "relation", "attribute", "query", "type"}


def raw_has_event(proposal: SemanticProposal | None) -> bool:
    return proposal is not None and has_explicit_occurrence_evidence(proposal)


def raw_has_measurement(proposal: SemanticProposal | None) -> bool:
    return proposal is not None and has_measurement_evidence(proposal)


def raw_primitive_kinds(proposal: SemanticProposal) -> set[PrimitiveKind]:
    return {f.primitive for f in collect_assertions(proposal)}


@dataclass
class RawEventMetrics:
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0
    missing_event: int = 0
    missing_measurement: int = 0
    false_extra_event: int = 0
    false_extra_measurement: int = 0
    em_complete: int = 0
    em_expected: int = 0
    event_as_state: int = 0
    event_as_relation: int = 0
    measurement_as_event_only: int = 0
    query_as_event: int = 0
    state_as_event: int = 0
    relation_as_event: int = 0
    attribute_as_event: int = 0
    raw_s3: int = 0
    raw_s4: int = 0

    @property
    def precision(self) -> float | None:
        denom = self.tp + self.fp
        return self.tp / denom if denom else None

    @property
    def recall(self) -> float | None:
        denom = self.tp + self.fn
        return self.tp / denom if denom else None

    @property
    def explicit_event_recall(self) -> float | None:
        expected = self.tp + self.fn
        return self.tp / expected if expected else None

    def to_dict(self) -> dict:
        return {
            "RAW_EVENT_TRUE_POSITIVE": self.tp,
            "RAW_EVENT_FALSE_POSITIVE": self.fp,
            "RAW_EVENT_FALSE_NEGATIVE": self.fn,
            "RAW_EVENT_TRUE_NEGATIVE": self.tn,
            "RAW_EVENT_PRECISION": self.precision,
            "RAW_EVENT_RECALL": self.recall,
            "RAW_EXPLICIT_EVENT_RECALL": self.explicit_event_recall,
            "RAW_MISSING_EVENT": self.missing_event,
            "RAW_MISSING_MEASUREMENT": self.missing_measurement,
            "RAW_FALSE_EXTRA_EVENT_ON_NO_EVENT_CASES": self.false_extra_event,
            "RAW_FALSE_EXTRA_MEASUREMENT": self.false_extra_measurement,
            "RAW_EVENT_MEASUREMENT_COMPLETE": self.em_complete,
            "RAW_EVENT_MEASUREMENT_EXPECTED": self.em_expected,
            "RAW_EVENT_AS_STATE": self.event_as_state,
            "RAW_EVENT_AS_RELATION": self.event_as_relation,
            "RAW_MEASUREMENT_AS_EVENT": self.measurement_as_event_only,
            "QUERY_MISROUTED_AS_EVENT": self.query_as_event,
            "STATE_TO_EVENT_REGRESSION": self.state_as_event,
            "RELATION_TO_EVENT_REGRESSION": self.relation_as_event,
            "ATTRIBUTE_TO_EVENT_REGRESSION": self.attribute_as_event,
            "RAW_S3": self.raw_s3,
            "RAW_S4": self.raw_s4,
        }



def accumulate_raw(metrics: RawEventMetrics, case: EngineCase, proposal: SemanticProposal | None, *, raw_score: dict | None) -> None:
    has_e = raw_has_event(proposal)
    has_m = raw_has_measurement(proposal)
    exp_e = expects_event(case)
    exp_m = expects_measurement(case)

    if exp_e and has_e:
        metrics.tp += 1
    elif exp_e and not has_e:
        metrics.fn += 1
        metrics.missing_event += 1
    elif not exp_e and has_e:
        metrics.fp += 1
        metrics.false_extra_event += 1
    elif not exp_e and not has_e:
        metrics.tn += 1

    if exp_m and not has_m:
        metrics.missing_measurement += 1
    if not exp_m and has_m and case.expected_primitive != "multi":
        metrics.false_extra_measurement += 1

    if case.expected_primitive == "multi":
        metrics.em_expected += 1
        if has_e and has_m:
            metrics.em_complete += 1

    if proposal is not None:
        kinds = raw_primitive_kinds(proposal)
        if case.expected_primitive == "state" and PrimitiveKind.EVENT in kinds:
            metrics.state_as_event += 1
        if case.expected_primitive == "relation" and PrimitiveKind.EVENT in kinds:
            metrics.relation_as_event += 1
        if case.expected_primitive == "attribute" and PrimitiveKind.EVENT in kinds:
            metrics.attribute_as_event += 1
        if case.expected_intent == "query" and PrimitiveKind.EVENT in kinds:
            metrics.query_as_event += 1
        if case.expected_primitive == "measurement" and has_e:
            metrics.measurement_as_event_only += 1

    if raw_score:
        sev = raw_score.get("severity")
        if sev == "S3":
            metrics.raw_s3 += 1
        elif sev == "S4":
            metrics.raw_s4 += 1


@dataclass
class VariantAggregate:
    prompt_variant: str
    metrics: RawEventMetrics = field(default_factory=RawEventMetrics)
    stable_correct: int = 0
    stable_safe_abstention: int = 0
    unstable_but_safe: int = 0
    unsafe_variance: int = 0
    post_s3: int = 0
    post_s4: int = 0
    raw_event_present_post_event_lost: int = 0
    partial_event_false_canonicalization: int = 0
    mp_event_hits: dict[str, int] = field(default_factory=dict)
    mp_runs: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        out = self.metrics.to_dict()
        out.update(
            {
                "prompt_variant": self.prompt_variant,
                "STABLE_CORRECT": self.stable_correct,
                "STABLE_SAFE_ABSTENTION": self.stable_safe_abstention,
                "UNSTABLE_BUT_SAFE": self.unstable_but_safe,
                "UNSAFE_VARIANCE": self.unsafe_variance,
                "POST_S3": self.post_s3,
                "POST_S4": self.post_s4,
                "RAW_EVENT_PRESENT_POST_EVENT_LOST": self.raw_event_present_post_event_lost,
                "PARTIAL_EVENT_FALSE_CANONICALIZATION": self.partial_event_false_canonicalization,
                "MP_EVENT_HITS": dict(self.mp_event_hits),
                "MP_RUNS": dict(self.mp_runs),
            }
        )
        return out
