"""Avaliação semântica por invariantes — sem igualdade byte a byte de JSON."""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from pke.interpretation.models import IngestIR, QueryIR

from tests.generalization.cases import ForbiddenInference, SemanticInvariant

_NEGATION_MARKERS = re.compile(
    r"\b(não|nao|nunca|jamais|nem|sem)\b", re.IGNORECASE
)


def _mention_texts(ir: IngestIR) -> list[str]:
    return [m.text.lower() for m in ir.entities_mentioned if m.text]


def _all_facts(ir: IngestIR) -> list:
    facts: list = []
    if ir.event is not None:
        facts.extend(ir.event.facts)
    if ir.obligation is not None:
        facts.extend(ir.obligation.facts)
    if ir.correction is not None:
        facts.extend(ir.correction.facts)
    return facts


def _amount_facts(ir: IngestIR) -> list:
    return [f for f in _all_facts(ir) if f.attribute.key == "attribute.amount"]


def _dump_lower(ir: IngestIR | QueryIR) -> str:
    return ir.model_dump_json().lower()


def check_forbidden(ir: IngestIR | QueryIR, forbidden: list[ForbiddenInference]) -> list[str]:
    """Retorna códigos de inferências proibidas detectadas."""
    hits: list[str] = []
    if not isinstance(ir, IngestIR):
        return hits
    dump = _dump_lower(ir)
    mentions = _mention_texts(ir)

    for rule in forbidden:
        code = rule.code
        if rule.kind == "mention_absent":
            needle = rule.value.lower()
            if not any(needle in m for m in mentions) and needle not in dump:
                continue
            if rule.must_be_absent and any(needle in m for m in mentions):
                hits.append(code)
        elif rule.kind == "substring_absent":
            if rule.value.lower() in dump:
                hits.append(code)
        elif rule.kind == "no_absolute_date":
            if ir.event is not None and ir.event.time is not None:
                t = ir.event.time
                if t.instant is not None or t.date is not None:
                    if rule.must_be_absent:
                        hits.append(code)
        elif rule.kind == "no_invented_relative_day":
            if ir.event is not None and ir.event.time is not None:
                if ir.event.time.relative_day is not None and rule.must_be_absent:
                    if rule.value and rule.value not in ir.raw_input.lower():
                        hits.append(code)
                    elif not rule.value:
                        hits.append(code)
        elif rule.kind == "no_confirmed_amount_when_uncertain":
            for fact in _amount_facts(ir):
                if fact.epistemic_status.value == "confirmed" and fact.qualifier.value == "exact":
                    if fact.confidence >= 0.9:
                        hits.append(code)
        elif rule.kind == "negation_flipped_positive":
            raw_neg = _NEGATION_MARKERS.search(ir.raw_input)
            if raw_neg and ir.event is not None:
                status = ir.event.status.value
                if status == "completed" and "não" in ir.raw_input.lower():
                    if any(w in ir.raw_input.lower() for w in ("não foi paga", "não vendi", "não trabalha")):
                        hits.append(code)
        elif rule.kind == "custom":
            if rule.predicate and rule.predicate(ir):
                hits.append(code)
    return hits


def check_semantic(ir: IngestIR | QueryIR, spec: SemanticInvariant) -> list[str]:
    """Retorna lista de invariantes obrigatórios não satisfeitos."""
    fails: list[str] = []
    if spec.accept_query and isinstance(ir, QueryIR):
        return fails
    if not isinstance(ir, IngestIR):
        return ["kind=IngestIR"]
    if spec.intent is not None and ir.intent.value != spec.intent:
        fails.append(f"intent={spec.intent}")
    if spec.has_event is True and ir.event is None:
        fails.append("has_event")
    if spec.has_event is False and ir.event is not None:
        fails.append("no_event")
    if spec.has_obligation is True and ir.obligation is None:
        fails.append("has_obligation")
    if spec.mentions_any:
        texts = _mention_texts(ir)
        dump = _dump_lower(ir)
        for needle in spec.mentions_any:
            n = needle.lower()
            if not any(n in t for t in texts) and n not in dump:
                fails.append(f"mention={needle}")
    if spec.event_type_any:
        if ir.event is None:
            fails.append("has_event_for_type")
        elif ir.event.type.key not in spec.event_type_any:
            fails.append(f"event_type in {spec.event_type_any}")
    if spec.action_any and ir.event is not None:
        if ir.event.action is None or ir.event.action.key not in spec.action_any:
            fails.append(f"action in {spec.action_any}")
    if spec.domain_any:
        keys = {d.key for d in ir.domains}
        if not keys.intersection(set(spec.domain_any)):
            fails.append(f"domain in {spec.domain_any}")
    if spec.relative_day is not None:
        if ir.event is None:
            fails.append("time.relative_day")
        elif spec.relative_day == "absent":
            if ir.event.time.relative_day is not None:
                fails.append("no_relative_day")
        elif ir.event.time.relative_day is None or ir.event.time.relative_day.value != spec.relative_day:
            fails.append(f"relative_day={spec.relative_day}")
    if spec.weekday is not None:
        if ir.event is None:
            fails.append("time.weekday")
        elif spec.weekday == "any":
            if ir.event.time.weekday is None:
                fails.append("weekday=any")
        elif ir.event.time.weekday != spec.weekday:
            fails.append(f"weekday={spec.weekday}")
    if spec.no_absolute_date:
        if ir.event is not None:
            t = ir.event.time
            if t.instant is not None or t.date is not None:
                fails.append("no_absolute_date")
    if spec.no_invented_time:
        if ir.event is not None:
            t = ir.event.time
            raw = ir.raw_input.lower()
            ot = (t.original_text or "").lower()
            if t.relative_day is not None and "hoje" not in raw and "ontem" not in raw and "amanhã" not in raw and "amanha" not in raw:
                if t.relative_day.value in {"today", "yesterday", "tomorrow"}:
                    if ot and ot not in raw and "hoje" in ot:
                        fails.append("no_invented_time")
    if spec.amount_equals is not None:
        amounts = _amount_facts(ir)
        if not amounts:
            fails.append(f"amount={spec.amount_equals}")
        else:
            val = amounts[0].value
            raw_amt = val["amount"] if isinstance(val, dict) else val
            try:
                if Decimal(str(raw_amt)) != spec.amount_equals:
                    fails.append(f"amount={spec.amount_equals}")
            except (InvalidOperation, TypeError):
                fails.append(f"amount={spec.amount_equals}")
    if spec.amount_approximate:
        amounts = _amount_facts(ir)
        if amounts and amounts[0].qualifier.value != "approximately":
            fails.append("qualifier=approximately")
    if spec.epistemic_uncertain:
        amounts = _amount_facts(ir)
        if amounts:
            f = amounts[0]
            if f.epistemic_status.value == "explicit" and f.confidence >= 0.8:
                fails.append("epistemic_uncertain")
    if spec.confidence_max is not None:
        amounts = _amount_facts(ir)
        if amounts and amounts[0].confidence > spec.confidence_max:
            fails.append(f"confidence<={spec.confidence_max}")
    if spec.quantity_equals is not None:
        dump = _dump_lower(ir)
        if str(spec.quantity_equals) not in dump and f'"quantity": {spec.quantity_equals}' not in dump:
            fails.append(f"quantity={spec.quantity_equals}")
    return fails


def stability_label(pass_count: int, total_runs: int) -> str:
    if pass_count == total_runs:
        return "3/3 stable" if total_runs == 3 else f"{pass_count}/{total_runs} stable"
    if pass_count >= total_runs - 1 and total_runs >= 2:
        return "2/3 acceptable but unstable" if total_runs == 3 else f"{pass_count}/{total_runs} acceptable"
    if pass_count == 1:
        return "1/3 weak" if total_runs == 3 else f"{pass_count}/{total_runs} weak"
    return "0/3 failed" if total_runs == 3 else f"{pass_count}/{total_runs} failed"
