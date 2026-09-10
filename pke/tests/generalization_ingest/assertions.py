"""Asserções de conhecimento final para benchmark ingest-path."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from pke.application import AskStatus, IngestStatus
from pke.application.ask_results import AskResult
from pke.application.results import IngestResult
from pke.domain import Event, TemporalKind, TemporalUnknownReason
from pke.domain.events import Event as DomainEvent
from pke.query.results import TemporalCompleteness

from tests.generalization_ingest.cases import QueryExpectation, TemporalExpectation


def check_temporal_knowledge(event: DomainEvent, exp: TemporalExpectation) -> list[str]:
    fails: list[str] = []
    t = event.temporal
    if exp.kind:
        acceptable = {exp.kind}
        if exp.kind == "partial":
            acceptable.add("interval")
        if t.kind.value not in acceptable:
            fails.append(f"kind expected {exp.kind} got {t.kind.value}")
    if exp.relation and (t.relation_to_reference is None or t.relation_to_reference.value != exp.relation):
        got = t.relation_to_reference.value if t.relation_to_reference else None
        fails.append(f"relation expected {exp.relation} got {got}")
    if exp.occurrence and (t.occurrence_status is None or t.occurrence_status.value != exp.occurrence):
        got = t.occurrence_status.value if t.occurrence_status else None
        fails.append(f"occurrence expected {exp.occurrence} got {got}")
    if exp.unknown_reason:
        got = t.unknown_reason.value if t.unknown_reason else None
        if got != exp.unknown_reason:
            fails.append(f"unknown_reason expected {exp.unknown_reason} got {got}")
    if exp.calendar_forbidden and t.has_calendar_anchor():
        fails.append("calendar anchor forbidden but present")
    if exp.calendar_required and not t.has_calendar_anchor():
        fails.append("calendar anchor required but absent")
    if exp.exact_day and t.calendar and t.calendar.date != exp.exact_day:
        fails.append(f"expected date {exp.exact_day} got {t.calendar.date if t.calendar else None}")
    if exp.month_interval and not (t.interval_start and t.interval_end):
        fails.append("expected month interval bounds")
    if exp.no_invented_today and t.calendar and t.calendar.date == dt.date.today():
        fails.append("invented today as event date")
    return fails


def check_ingest_result(result: IngestResult, exp: TemporalExpectation) -> list[str]:
    fails: list[str] = []
    if exp.committed and result.status is not IngestStatus.COMMITTED:
        fails.append(f"expected COMMITTED got {result.status.value}")
    if not exp.committed and result.status is IngestStatus.COMMITTED:
        fails.append("expected not committed but got COMMITTED")
    if exp.no_time_missing_block:
        if any(issue.code == "time.missing" for issue in result.issues):
            fails.append("blocking time.missing")
    return fails


def check_query_result(result: AskResult, exp: QueryExpectation) -> list[str]:
    fails: list[str] = []
    if exp.answered and result.status is not AskStatus.ANSWERED:
        fails.append(f"expected ANSWERED got {result.status.value}")
    qr = result.query_result
    if qr is None:
        return fails + ["missing query_result"]
    if exp.count_value is not None:
        agg = qr.aggregate
        if agg is None or agg.value != exp.count_value:
            fails.append(f"count expected {exp.count_value} got {getattr(agg, 'value', None)}")
    if exp.aggregate_value is not None:
        agg = qr.aggregate
        if agg is None or str(agg.value) != exp.aggregate_value:
            fails.append(f"aggregate expected {exp.aggregate_value} got {getattr(agg, 'value', None)}")
    if exp.temporal_completeness:
        want = TemporalCompleteness(exp.temporal_completeness)
        if qr.temporal_completeness is not want:
            got = qr.temporal_completeness.value if qr.temporal_completeness else None
            fails.append(f"temporal_completeness expected {exp.temporal_completeness} got {got}")
    if exp.membership_unknown is not None and qr.temporal_membership_unknown is not exp.membership_unknown:
        fails.append(f"membership_unknown expected {exp.membership_unknown}")
    if exp.indeterminate_min is not None:
        count = qr.aggregate.indeterminate_event_count if qr.aggregate else qr.indeterminate_event_count
        if (count or 0) < exp.indeterminate_min:
            fails.append(f"indeterminate expected >= {exp.indeterminate_min} got {count}")
    if exp.latest_known_date and qr.aggregate:
        got = qr.aggregate.latest_known_event_time
        if not got or exp.latest_known_date not in str(got):
            fails.append(f"latest_known expected {exp.latest_known_date} got {got}")
    return fails


def invented_time_in_event(event: DomainEvent, *, benchmark_day: dt.date) -> list[str]:
    hits: list[str] = []
    if event.temporal.calendar:
        d = event.temporal.calendar.date
        if d == dt.date.today() and d != benchmark_day:
            hits.append("invented_today")
        if event.temporal.kind is TemporalKind.EXACT and "recorded" in (event.temporal.original_text or "").lower():
            hits.append("recorded_at_as_event_time")
    return hits
