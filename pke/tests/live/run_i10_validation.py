"""Validação live I10. Não loga chave. Banco isolado em tempfile. Sem Core change."""

from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
import traceback
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from pke.application import AskService, AskStatus, FixedClock, IngestService, IngestStatus, SessionContext
from pke.domain import UserContext
from pke.interpretation import DeepSeekInterpreter, InterpretationContext, InterpretationError
from pke.interpretation.prompts import PROMPT_VERSION_V2
from pke.llm.errors import LlmInvalidResponseError, LlmSchemaValidationError
from pke.interpretation.models import IngestIR, QueryIR
from pke.llm import DeepSeekConfig, DeepSeekProvider
from pke.ontology import OntologyRegistry
from pke.domain import Money
from pke.persist import open_sqlite_read_store, open_sqlite_uow
from pke.resolution import PersonalContext

FORTALEZA = ZoneInfo("America/Fortaleza")
NOW = dt.datetime(2026, 9, 1, 15, 0, tzinfo=FORTALEZA)
RUNS = 3
SECRET_MARKERS = ("sk-", "Bearer ", "DEEPSEEK_API_KEY=")

CASES = {
    "A": "Troquei o óleo do Corolla hoje por 320 reais.",
    "B": "Tenho dentista quinta às 15h com a Dra. Ana.",
    "C": "A internet vence todo dia 10 e é 129,90.",
    "D1": "Acho que a revisão do Corolla hoje ficou em uns 180 reais.",
    "D2": "Acho que a revisão ficou em uns 180 reais.",
    "E": "Não, achei a nota. Foi 186,50.",
    "F": "Quanto gastei com o Corolla este mês?",
}


def load_env_silent() -> None:
    path = Path(__file__).resolve().parents[2] / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _scrub(text: str) -> str:
    out = text
    for marker in SECRET_MARKERS:
        if marker.lower() in out.lower():
            out = "[redacted]"
            break
    return out


def _amount(value: object) -> Decimal | None:
    raw = value["amount"] if isinstance(value, dict) else value
    try:
        return Decimal(str(raw))
    except Exception:
        return None


def _currency(value: object) -> str | None:
    if isinstance(value, dict):
        return value.get("currency")
    return None


def check_a(ir: object, raw: str) -> list[str]:
    fails: list[str] = []
    if not isinstance(ir, IngestIR):
        return ["kind=IngestIR"]
    if ir.raw_input != raw:
        fails.append("raw_input_identical")
    if ir.intent.value != "record_event":
        fails.append("intent=record_event")
    if ir.event is None:
        return [*fails, "has_event"]
    if ir.event.type.key != "event.vehicle_maintenance":
        fails.append("event.vehicle_maintenance")
    if ir.event.action is None or ir.event.action.key != "action.oil_change":
        fails.append("action.oil_change")
    mentions = ir.entities_mentioned or []
    if not any(item.text.lower() == "corolla" for item in mentions):
        fails.append("mention=Corolla")
    hints = [
        (item.type_hint.key if item.type_hint else "")
        for item in mentions
        if item.text.lower() == "corolla"
    ]
    if hints and not any(h in {"entity.vehicle", "entity.automobile"} for h in hints):
        fails.append("type_hint=vehicle/automobile")
    if not any(d.key == "domain.vehicle" for d in ir.domains):
        fails.append("domain.vehicle")
    if ir.event.time.relative_day is None or ir.event.time.relative_day.value != "today":
        fails.append("relative_day=today")
    if ir.event.time.instant is not None or ir.event.time.date is not None:
        fails.append("no_absolute_date")
    amounts = [f for f in ir.event.facts if f.attribute.key == "attribute.amount"]
    if not amounts or _amount(amounts[0].value) != Decimal("320"):
        fails.append("amount=320")
    if amounts and _currency(amounts[0].value) not in {None, "BRL"}:
        if _currency(amounts[0].value) != "BRL":
            fails.append("currency=BRL")
    if any(f.attribute.key == "attribute.mileage" for f in ir.event.facts):
        fails.append("mileage_absent")
    return fails


def check_b(ir: object, raw: str) -> list[str]:
    fails: list[str] = []
    if not isinstance(ir, IngestIR):
        return ["kind=IngestIR"]
    if ir.event is None:
        return ["has_event"]
    if ir.event.type.key != "event.appointment":
        fails.append("event.appointment")
    if ir.event.status.value != "scheduled":
        fails.append("status=scheduled")
    if ir.event.time.weekday != 3:
        fails.append("weekday=thursday(3)")
    if ir.event.time.time_of_day is None or ir.event.time.time_of_day.hour != 15:
        fails.append("time=15:00")
    mentions = ir.entities_mentioned or []
    if not any("ana" in item.text.lower() for item in mentions):
        fails.append("mention=Dra.Ana")
    ana = next((item for item in mentions if "ana" in item.text.lower()), None)
    if ana is not None and ana.role is not None and ana.role.key != "role.provider":
        fails.append("role=provider")
    if ana is not None and ana.role is None:
        fails.append("role=provider")
    if ir.event.time.instant is not None:
        fails.append("no_absolute_instant")
    dumped = " ".join(
        item.text.lower()
        for item in mentions
        if item.text
    )
    if dumped.strip() in {"dentista", "dentist", "mecânico", "mecanico"}:
        fails.append("no_invented_specialty")
    if any("local" in (item.text or "").lower() or "clínica" in (item.text or "").lower() for item in mentions):
        fails.append("no_invented_location")
    return fails


def check_c(ir: object, raw: str) -> list[str]:
    fails: list[str] = []
    if not isinstance(ir, IngestIR):
        return ["kind=IngestIR"]
    if ir.obligation is None:
        return ["has_obligation"]
    if ir.obligation.type.key != "event.recurring_bill":
        fails.append("event.recurring_bill")
    if ir.obligation.cadence.freq != "monthly":
        fails.append("freq=monthly")
    if ir.obligation.cadence.by_monthday != 10:
        fails.append("by_monthday=10")
    amounts = [f for f in ir.obligation.facts if f.attribute.key == "attribute.amount"]
    if not amounts or _amount(amounts[0].value) != Decimal("129.90"):
        fails.append("amount=129.90")
    if amounts and _currency(amounts[0].value) not in {None, "BRL"}:
        fails.append("currency=BRL")
    mentions = " ".join(item.text.lower() for item in ir.entities_mentioned)
    if "casa" in mentions or "resid" in mentions:
        fails.append("no_invented_home")
    return fails


def check_d1(ir: object, raw: str) -> list[str]:
    fails: list[str] = []
    if not isinstance(ir, IngestIR):
        return ["kind=IngestIR"]
    if ir.event is None:
        return ["has_event"]
    if ir.event.type.key != "event.vehicle_maintenance":
        fails.append("event.vehicle_maintenance")
    mentions = ir.entities_mentioned or []
    if not any(item.text.lower() == "corolla" for item in mentions):
        fails.append("mention=Corolla")
    if ir.event.time.relative_day is None or ir.event.time.relative_day.value != "today":
        fails.append("relative_day=today")
    if ir.event.time.instant is not None or ir.event.time.date is not None:
        fails.append("no_absolute_date")
    amounts = [f for f in ir.event.facts if f.attribute.key == "attribute.amount"]
    if not amounts:
        return [*fails, "has_amount"]
    fact = amounts[0]
    if fact.qualifier.value != "approximately":
        fails.append("qualifier=approximately")
    if fact.qualifier.value == "exact":
        fails.append("never_exact")
    if fact.epistemic_status.value == "confirmed":
        fails.append("never_confirmed")
    if fact.epistemic_status.value == "explicit" and fact.confidence >= 0.8:
        fails.append("uncertainty_preserved")
    if fact.confidence >= 0.8:
        fails.append("confidence<0.8")
    if _amount(fact.value) != Decimal("180"):
        fails.append("amount=180")
    return fails


def check_d2(ir: object, raw: str) -> list[str]:
    fails: list[str] = []
    if not isinstance(ir, IngestIR):
        return ["kind=IngestIR"]
    if ir.event is None:
        return ["has_event"]
    amounts = [f for f in ir.event.facts if f.attribute.key == "attribute.amount"]
    if not amounts:
        return ["has_amount"]
    fact = amounts[0]
    if fact.qualifier.value != "approximately":
        fails.append("qualifier=approximately")
    if fact.qualifier.value == "exact":
        fails.append("never_exact")
    if fact.epistemic_status.value == "confirmed":
        fails.append("never_confirmed")
    if fact.epistemic_status.value == "explicit" and fact.confidence >= 0.8:
        fails.append("uncertainty_preserved")
    if fact.confidence >= 0.8:
        fails.append("confidence<0.8")
    if _amount(fact.value) != Decimal("180"):
        fails.append("amount=180")
    if ir.event.time.relative_day is not None:
        fails.append("no_invented_relative_day")
    if ir.event.time.instant is not None or ir.event.time.date is not None:
        fails.append("no_invented_absolute_time")
    original = (ir.event.time.original_text or "").lower()
    if original and "hoje" in original:
        fails.append("no_invented_hoje")
    return fails


def check_e(ir: object, raw: str) -> list[str]:
    fails: list[str] = []
    if not isinstance(ir, IngestIR):
        return ["kind=IngestIR"]
    if ir.intent.value != "correct":
        fails.append("intent=correct")
    if ir.correction is None:
        return [*fails, "has_correction"]
    if ir.correction.strategy.value not in {"last_event", "explicit"}:
        fails.append("strategy_contextual")
    if ir.correction.fact_id is not None:
        fails.append("no_invented_fact_id")
    if ir.correction.strategy.value == "last_event" and ir.correction.event_id is not None:
        fails.append("no_invented_event_id")
    if not ir.correction.facts:
        return [*fails, "has_correction_amount"]
    if _amount(ir.correction.facts[0].value) != Decimal("186.50"):
        fails.append("amount=186.50")
    return fails


def check_f(ir: object, raw: str) -> list[str]:
    fails: list[str] = []
    if not isinstance(ir, QueryIR):
        return ["kind=QueryIR"]
    if ir.query.aggregate != "sum":
        fails.append("aggregate=sum")
    if ir.query.version_policy != "current":
        fails.append("version=current")
    if not any(item.text.lower() == "corolla" for item in ir.query.entities):
        fails.append("mention=Corolla")
    if ir.query.entity_association != "subject":
        fails.append("association=subject")
    if not any(ref.key == "event.vehicle_maintenance" for ref in ir.query.event_types):
        fails.append("event.vehicle_maintenance")
    if not any(ref.key == "attribute.amount" for ref in ir.query.facts):
        fails.append("attribute.amount")
    if ir.query.time is None or ir.query.time.relative_period is None:
        fails.append("relative_period=this_month")
    elif ir.query.time.relative_period.value != "this_month":
        fails.append("relative_period=this_month")
    if ir.query.time is not None and ir.query.time.start is not None:
        fails.append("no_absolute_query_range")
    dumped = ir.model_dump_json()
    if "506" in dumped or "R$" in dumped:
        fails.append("no_llm_monetary_answer")
    return fails


CHECKS = {
    "A": check_a,
    "B": check_b,
    "C": check_c,
    "D1": check_d1,
    "D2": check_d2,
    "E": check_e,
    "F": check_f,
}


def _ctx() -> InterpretationContext:
    return InterpretationContext(
        user=UserContext(user_id="live-i10", timezone="America/Fortaleza", now=NOW)
    )


def _sanitize_ir(ir: object) -> dict:
    if hasattr(ir, "model_dump"):
        return ir.model_dump(mode="json")
    return {"type": type(ir).__name__}


def phase1(interpreter: DeepSeekInterpreter, *, label: str = "P1") -> dict:
    ctx = _ctx()
    rows: list[dict] = []
    for code, raw in CASES.items():
        for run in range(1, RUNS + 1):
            row: dict = {
                "phase": 1,
                "case": code,
                "run": run,
                "pass": False,
                "model": None,
                "latency_ms": None,
                "prompt_tokens": None,
                "completion_tokens": None,
                "total_tokens": None,
                "finish_reason": None,
                "failed_invariants": [],
                "error_class": None,
            }
            try:
                ir = interpreter.interpret(raw, ctx)
                meta = interpreter.last_metadata
                if meta is not None:
                    row.update(
                        {
                            "model": meta.model,
                            "latency_ms": round(meta.latency_ms, 1),
                            "prompt_tokens": meta.prompt_tokens,
                            "completion_tokens": meta.completion_tokens,
                            "total_tokens": meta.total_tokens,
                            "finish_reason": meta.finish_reason,
                        }
                    )
                fails = CHECKS[code](ir, raw)
                row["failed_invariants"] = fails
                row["pass"] = not fails
                row["ir"] = _sanitize_ir(ir)
            except Exception as exc:
                row["error_class"] = type(exc).__name__
                row["error"] = _scrub(str(exc))
                cause = exc.__cause__
                if isinstance(exc, InterpretationError) and isinstance(cause, LlmSchemaValidationError):
                    row["reject_kind"] = "schema"
                    issues = getattr(interpreter, "last_validation_issues", None)
                    if issues:
                        row["validation_issues"] = issues[:5]
                        first_type = issues[0].get("type")
                        if first_type == "json_invalid":
                            row["reject_kind"] = "provider_json"
                        elif any(
                            issue.get("path", "").startswith(("ir.", "ir_kind"))
                            for issue in issues
                        ):
                            row["reject_kind"] = "wire"
                        else:
                            row["reject_kind"] = "canonical"
                elif isinstance(cause, LlmInvalidResponseError) or isinstance(exc, LlmInvalidResponseError):
                    row["reject_kind"] = "provider_json"
                elif "JSON" in str(exc) or "conteúdo não é JSON" in str(exc):
                    row["reject_kind"] = "provider_json"
                elif row["error_class"] == "InterpretationError":
                    row["reject_kind"] = "provider"
                else:
                    row["reject_kind"] = "other"
                raw = getattr(interpreter, "last_raw_content", None)
                if raw:
                    row["raw_content_preview"] = _scrub(raw)[:2000]
            rows.append(row)
            status = "PASS" if row["pass"] else "FAIL"
            print(
                f"{label} {code}#{run} {status} model={row['model']} "
                f"latency_ms={row['latency_ms']} tokens={row['total_tokens']} "
                f"fails={row['failed_invariants'] or row['error_class']}",
                flush=True,
            )
    return {"rows": rows}


def _summarize(rows: list[dict]) -> dict:
    summary = {}
    for code in CASES:
        subset = [r for r in rows if r["case"] == code]
        ok = sum(1 for r in subset if r["pass"])
        label = "PASS" if ok == RUNS else ("UNSTABLE" if ok else "FAIL")
        summary[code] = {"valid": f"{ok}/{len(subset)}", "result": label, "ok": ok}
    return summary


def phase1_acceptable(summary: dict) -> bool:
    core = ("A", "B", "C", "D1", "E", "F")
    return all(summary[code]["ok"] >= 2 for code in core)


def _reject_count(rows: list[dict], kind: str) -> int:
    return sum(1 for r in rows if r.get("reject_kind") == kind)


def _schema_rejects(rows: list[dict]) -> int:
    return _reject_count(rows, "schema") + _reject_count(rows, "wire") + _reject_count(rows, "canonical")


def _provider_json_errors(rows: list[dict]) -> int:
    return _reject_count(rows, "provider_json")


def _metrics(rows: list[dict], interpreter: DeepSeekInterpreter | None = None) -> dict:
    prompts = [r.get("prompt_tokens") for r in rows if r.get("prompt_tokens") is not None]
    completions = [r.get("completion_tokens") for r in rows if r.get("completion_tokens") is not None]
    latencies = [r.get("latency_ms") for r in rows if r.get("latency_ms") is not None]
    total = len(rows)
    accepted = sum(1 for r in rows if r.get("pass"))
    semantic = sum(
        1 for r in rows if r.get("error_class") is None and not r.get("pass")
    )
    semantic_chain = sum(
        1
        for r in rows
        if r.get("case") in {"A", "B", "C", "D1", "E", "F"}
        and r.get("error_class") is None
        and not r.get("pass")
    )
    provider_json = _provider_json_errors(rows)
    wire = _reject_count(rows, "wire")
    canonical = _reject_count(rows, "canonical")
    out = {
        "accepted": accepted,
        "total_runs": total,
        "provider_json_failures": provider_json,
        "provider_valid_json_rate": round((total - provider_json) / total, 4) if total else None,
        "wire_failures": wire,
        "wire_valid_rate": round((total - wire) / total, 4) if total else None,
        "canonical_failures": canonical,
        "canonical_valid_rate": round((total - canonical) / total, 4) if total else None,
        "schema_rejects": _schema_rejects(rows),
        "semantic_failures": semantic,
        "semantic_failures_chain": semantic_chain,
        "prompt_tokens_avg": round(sum(prompts) / len(prompts), 1) if prompts else None,
        "completion_tokens_avg": round(sum(completions) / len(completions), 1) if completions else None,
        "latency_ms_avg": round(sum(latencies) / len(latencies), 1) if latencies else None,
    }
    if interpreter is not None:
        m = interpreter.metrics
        out["interpreter_provider_valid_json_rate"] = m.provider_valid_json_rate
        out["interpreter_wire_valid_rate"] = m.wire_valid_rate
        out["interpreter_canonical_valid_rate"] = m.canonical_valid_rate
    return out


def phase2(config: DeepSeekConfig, *, prompt_version: str = PROMPT_VERSION_V2) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="pke-i10-live-"))
    db = tmp / "isolated.db"
    ontology = OntologyRegistry.with_core_seeds()
    provider = DeepSeekProvider(config)
    interpreter = DeepSeekInterpreter(provider, ontology, prompt_version=prompt_version)
    user = UserContext(user_id="live-i10", timezone="America/Fortaleza", now=NOW)
    session = SessionContext(personal=PersonalContext(user_id="live-i10"))
    ingest = IngestService(
        interpreter,
        ontology,
        lambda: open_sqlite_uow(db),
        FixedClock(NOW),
    )
    steps = []
    for code in ("A", "D1", "E", "B", "C"):
        result = ingest.ingest(CASES[code], user, session)
        meta = interpreter.last_metadata
        steps.append(
            {
                "case": code,
                "status": result.status.value,
                "committed": result.status is IngestStatus.COMMITTED,
                "model": meta.model if meta else None,
                "latency_ms": round(meta.latency_ms, 1) if meta else None,
                "total_tokens": meta.total_tokens if meta else None,
                "issues": [i.code for i in result.issues[:8]],
            }
        )
        print(f"P2 ingest {code} status={result.status.value}", flush=True)
    ask = AskService(interpreter, ontology, open_sqlite_read_store(db), FixedClock(NOW))
    asked = ask.ask(CASES["F"], user, session)
    meta = interpreter.last_metadata
    aggregate = None
    currency = None
    contributing: list[str] = []
    if asked.query_result and asked.query_result.aggregate:
        aggregate = (
            str(asked.query_result.aggregate.value)
            if asked.query_result.aggregate.value is not None
            else None
        )
        currency = asked.query_result.aggregate.currency
        contributing = list(asked.query_result.aggregate.contributing_fact_ids)
    graph = open_sqlite_read_store(db).load_user_graph("live-i10")
    provenance_amounts = []
    superseded_180_in_aggregate = False
    for fact in graph.facts:
        if isinstance(fact.value, Money):
            if fact.id in contributing and fact.superseded_at is None:
                provenance_amounts.append(str(fact.value.amount))
            if fact.value.amount == Decimal("180") and fact.id in contributing:
                superseded_180_in_aggregate = True
    e2e_f = {
        "case": "F",
        "status": asked.status.value,
        "aggregate": aggregate,
        "currency": currency,
        "answered_506": (
            asked.status is AskStatus.ANSWERED
            and asked.query_result is not None
            and asked.query_result.aggregate is not None
            and asked.query_result.aggregate.value == Decimal("506.50")
        ),
        "provenance_current_amounts": sorted(provenance_amounts),
        "superseded_180_in_aggregate": superseded_180_in_aggregate,
        "model": meta.model if meta else None,
        "latency_ms": round(meta.latency_ms, 1) if meta else None,
        "total_tokens": meta.total_tokens if meta else None,
        "db": str(db),
    }
    print(f"P2 ask F status={asked.status.value} aggregate={aggregate} {currency}", flush=True)

    return {"db": str(db), "ingest": steps, "ask": e2e_f}


def phase2_d2_isolated(config: DeepSeekConfig, *, prompt_version: str = PROMPT_VERSION_V2) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="pke-i10-d2-"))
    db = tmp / "isolated.db"
    ontology = OntologyRegistry.with_core_seeds()
    interpreter = DeepSeekInterpreter(
        DeepSeekProvider(config), ontology, prompt_version=prompt_version
    )
    user = UserContext(user_id="live-i10-d2", timezone="America/Fortaleza", now=NOW)
    session = SessionContext(personal=PersonalContext(user_id="live-i10-d2"))
    ingest = IngestService(
        interpreter,
        ontology,
        lambda: open_sqlite_uow(db),
        FixedClock(NOW),
    )
    result = ingest.ingest(CASES["D2"], user, session)
    graph = open_sqlite_read_store(db).load_user_graph("live-i10-d2")
    step = {
        "case": "D2",
        "status": result.status.value,
        "needs_clarification": result.status is IngestStatus.NEEDS_CLARIFICATION,
        "time_missing": any(i.code == "time.missing" for i in result.issues),
        "interpretation_failed": any(i.code == "interpretation.failed" for i in result.issues),
        "zero_writes": graph.events == [] and graph.facts == [],
        "issues": [i.code for i in result.issues[:8]],
        "db": str(db),
    }
    print(
        f"P2 D2 isolated status={result.status.value} "
        f"time_missing={step['time_missing']} zero_writes={step['zero_writes']}",
        flush=True,
    )
    return step


def main() -> int:
    load_env_silent()
    present = bool(os.environ.get("DEEPSEEK_API_KEY", "").strip())
    print(f"DEEPSEEK_API_KEY_present={present}", flush=True)
    if not present:
        print("ABORT: chave ausente", flush=True)
        return 2
    config = DeepSeekConfig.from_env(timeout_seconds=90.0)
    print(f"config={config!r}", flush=True)
    ontology = OntologyRegistry.with_core_seeds()
    interpreter = DeepSeekInterpreter(DeepSeekProvider(config), ontology, prompt_version=PROMPT_VERSION_V2)
    phase1_data = phase1(interpreter, label="P1v2")
    summary = _summarize(phase1_data["rows"])
    metrics = _metrics(phase1_data["rows"], interpreter)
    baseline_v2 = {
        "A": "2/3",
        "B": "2/3",
        "C": "3/3",
        "D1": "2/3",
        "D2": "2/3",
        "E": "3/3",
        "F": "3/3",
        "provider_json_failures": "stochastic",
        "semantic_failures_among_accepted": 0,
    }
    report = {
        "model": config.model,
        "prompt_version": PROMPT_VERSION_V2,
        "baseline_v2": baseline_v2,
        "phase1_summary": summary,
        "metrics": metrics,
        "phase1": phase1_data["rows"],
        "calls_phase1": len(phase1_data["rows"]),
    }
    acceptable = phase1_acceptable(summary)
    if metrics["semantic_failures_chain"] > 0:
        acceptable = False
    if acceptable:
        print("P1v2 acceptable (A,B,C,D1,E,F) -> P2 isolated DB", flush=True)
        report["phase2"] = phase2(config, prompt_version=PROMPT_VERSION_V2)
    else:
        print("P1v2 chain cases not acceptable -> skip P2 chain", flush=True)
        report["phase2"] = None
    report["phase2_d2_only"] = phase2_d2_isolated(config, prompt_version=PROMPT_VERSION_V2)
    out = Path(tempfile.gettempdir()) / "pke-i10-live-report.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"report={out}", flush=True)
    print(
        json.dumps(
            {"phase1_summary": summary, "metrics": metrics, "baseline_v2": baseline_v2},
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
