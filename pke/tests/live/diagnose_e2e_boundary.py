"""I10.3 — diagnóstico de fronteira E2E. Sem alterar Core. Salva em temp."""

from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
import traceback
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pke.application import FixedClock, IngestService, IngestStatus, SessionContext
from pke.domain import UserContext
from pke.interpretation import DeepSeekInterpreter, FakeInterpreter, InterpretationContext, InterpretationError
from pke.interpretation.models import IngestIR
from pke.llm import DeepSeekConfig, DeepSeekProvider
from pke.ontology import OntologyRegistry
from pke.persist import open_sqlite_uow
from pke.resolution import PersonalContext, TemporalResolver
from pke.resolution.errors import InsufficientTemporalContextError
from tests.integration.test_ingest import RAW_A, RAW_D1, RAW_D2, ir_a, ir_d1, ir_d2, ir_no_time

FORTALEZA = ZoneInfo("America/Fortaleza")
NOW = dt.datetime(2026, 9, 1, 15, 0, tzinfo=FORTALEZA)
RAW_A_LIVE = RAW_A


def load_env() -> None:
    path = Path(__file__).resolve().parents[2] / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        if key.strip() and key.strip() not in os.environ:
            os.environ[key.strip()] = value.strip().strip('"').strip("'")


def _ctx(user_id: str = "diag-a") -> InterpretationContext:
    return InterpretationContext(
        user=UserContext(user_id=user_id, timezone="America/Fortaleza", now=NOW)
    )


def _session(user_id: str = "diag-a") -> SessionContext:
    return SessionContext(personal=PersonalContext(user_id=user_id))


def _struct_path(obj: object, prefix: str = "") -> dict[str, Any]:
    if obj is None:
        return {prefix or "root": {"type": "NoneType", "value": None}}
    if isinstance(obj, (str, int, float, bool)):
        return {prefix or "root": {"type": type(obj).__name__, "value": obj}}
    if isinstance(obj, dt.datetime):
        return {prefix: {"type": "datetime", "value": obj.isoformat()}}
    if isinstance(obj, dt.time):
        return {prefix: {"type": "time", "value": obj.isoformat()}}
    if isinstance(obj, dt.date):
        return {prefix: {"type": "date", "value": obj.isoformat()}}
    if hasattr(obj, "model_dump"):
        out: dict[str, Any] = {}
        data = obj.model_dump()
        for key, value in data.items():
            child = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                for subk, subv in value.items():
                    out.update(_struct_path(subv, f"{child}.{subk}"))
            elif isinstance(value, list):
                for idx, item in enumerate(value):
                    out.update(_struct_path(item, f"{child}[{idx}]"))
            else:
                out.update(_struct_path(value, child))
        out[prefix or "root.__class__"] = type(obj).__name__
        return out
    return {prefix: {"type": type(obj).__name__, "repr": repr(obj)[:200]}}


def structural_diff(fake: IngestIR, deep: IngestIR) -> list[dict[str, Any]]:
    fake_map = _struct_path(fake)
    deep_map = _struct_path(deep)
    keys = sorted(set(fake_map) | set(deep_map))
    diffs: list[dict[str, Any]] = []
    for key in keys:
        f = fake_map.get(key)
        d = deep_map.get(key)
        if f != d:
            diffs.append({"path": key, "fake": f, "deepseek": d})
    return diffs


def diagnose_interpret_a(deep: DeepSeekInterpreter, attempts: int = 5) -> dict:
    rows = []
    for i in range(1, attempts + 1):
        row: dict[str, Any] = {"attempt": i}
        try:
            ir = deep.interpret(RAW_A_LIVE, _ctx())
            row["outcome"] = "ok"
            row["python_type"] = type(ir).__name__
            row["is_ingest_ir"] = isinstance(ir, IngestIR)
            row["raw_input"] = ir.raw_input
            row["intent"] = ir.intent.value
            row["relative_day"] = (
                ir.event.time.relative_day.value
                if ir.event and ir.event.time.relative_day
                else None
            )
            issues = getattr(deep, "last_validation_issues", None)
            row["validation_issues"] = issues
        except InterpretationError as exc:
            row["outcome"] = "interpretation_error"
            row["message"] = str(exc)
            row["cause_type"] = type(exc.__cause__).__name__ if exc.__cause__ else None
            row["cause_message"] = str(exc.__cause__) if exc.__cause__ else None
            row["cause_issues"] = getattr(exc.__cause__, "issues", None)
            row["raw_preview"] = (deep.last_raw_content or "")[:500]
        except Exception as exc:
            row["outcome"] = "other_error"
            row["error_type"] = type(exc).__name__
            row["message"] = str(exc)
            row["traceback"] = traceback.format_exc(limit=4)
        rows.append(row)
        print(f"A interpret #{i} {row['outcome']}", flush=True)
    return {"attempts": rows}


def diagnose_ingest_path(
    interpreter: object,
    raw: str,
    *,
    db_suffix: str,
) -> dict:
    db = Path(tempfile.gettempdir()) / f"pke-i103-{db_suffix}.db"
    if db.exists():
        db.unlink()
    ontology = OntologyRegistry.with_core_seeds()
    service = IngestService(
        interpreter,
        ontology,
        lambda: open_sqlite_uow(db),
        FixedClock(NOW),
    )
    user = UserContext(user_id="diag-a", timezone="America/Fortaleza", now=NOW)
    session = _session()
    report: dict[str, Any] = {"raw": raw, "db": str(db)}
    try:
        ir = interpreter.interpret(raw, _ctx())  # type: ignore[attr-defined]
        report["interpret"] = {
            "ok": True,
            "type": type(ir).__name__,
            "is_ingest_ir": isinstance(ir, IngestIR),
        }
        if isinstance(ir, IngestIR) and ir.event:
            report["interpret"]["relative_day"] = (
                ir.event.time.relative_day.value if ir.event.time.relative_day else None
            )
            report["interpret"]["time_original_text"] = ir.event.time.original_text
        try:
            TemporalResolver().resolve(
                ir.event.time,  # type: ignore[union-attr]
                type("TC", (), {"user": user, "event_status": ir.event.status, "reference_at": NOW})(),  # noqa: E501
            )
            report["temporal_resolve"] = "ok"
        except InsufficientTemporalContextError as exc:
            report["temporal_resolve"] = {"error": "InsufficientTemporalContextError", "msg": str(exc)}
    except InterpretationError as exc:
        report["interpret"] = {
            "ok": False,
            "error": str(exc),
            "cause_type": type(exc.__cause__).__name__ if exc.__cause__ else None,
            "cause": str(exc.__cause__) if exc.__cause__ else None,
            "cause_issues": getattr(exc.__cause__, "issues", None),
        }
        return report
    result = service.ingest(raw, user, session)
    report["ingest"] = {
        "status": result.status.value,
        "issues": [{"code": i.code, "message": i.message, "rule_id": i.rule_id} for i in result.issues],
    }
    return report


def diagnose_d_temporal() -> dict:
    user = UserContext(user_id="diag-d", timezone="America/Fortaleza", now=NOW)
    resolver = TemporalResolver()
    cases = {
        "fake_ir_d1_with_today": ir_d1(),
        "fake_ir_d2_no_time": ir_d2(),
        "fake_ir_no_time": ir_no_time(),
        "deepseek_like_empty_time": ir_a(RAW_D2).model_copy(
            update={
                "event": ir_a(RAW_D2).event.model_copy(  # type: ignore[union-attr]
                    update={"time": ir_no_time().event.time}  # type: ignore[union-attr]
                )
            }
        ),
    }
    out: dict[str, Any] = {}
    for name, ir in cases.items():
        assert ir.event is not None
        try:
            tv = resolver.resolve(
                ir.event.time,
                type(
                    "TC",
                    (),
                    {"user": user, "event_status": ir.event.status, "reference_at": NOW},
                )(),
            )
            out[name] = {
                "resolved": True,
                "date": str(tv.date),
                "instant": tv.instant.isoformat() if tv.instant else None,
                "precision": tv.precision.value if tv.precision else None,
            }
        except Exception as exc:
            out[name] = {"resolved": False, "error": type(exc).__name__, "message": str(exc)}
    return out


def main() -> int:
    load_env()
    if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
        print("ABORT: sem chave", flush=True)
        return 2
    config = DeepSeekConfig.from_env(timeout_seconds=90.0)
    deep = DeepSeekInterpreter(DeepSeekProvider(config), OntologyRegistry.with_core_seeds())
    fake = FakeInterpreter({RAW_A_LIVE: ir_a(RAW_A_LIVE)})

    report: dict[str, Any] = {
        "case_a_interpret_attempts": diagnose_interpret_a(deep, attempts=5),
        "case_a_fake_ingest": diagnose_ingest_path(fake, RAW_A_LIVE, db_suffix="fake"),
        "case_a_deepseek_ingest": None,
        "case_a_structural_diff": None,
        "case_d_temporal": diagnose_d_temporal(),
    }

    # one successful deepseek interpret for diff + ingest
    for attempt in range(1, 8):
        try:
            deep_ir = deep.interpret(RAW_A_LIVE, _ctx())
            if isinstance(deep_ir, IngestIR):
                report["case_a_structural_diff"] = structural_diff(ir_a(RAW_A_LIVE), deep_ir)
                report["case_a_deepseek_ingest"] = diagnose_ingest_path(deep, RAW_A_LIVE, db_suffix="deep")
                break
        except InterpretationError:
            continue
    else:
        report["case_a_deepseek_ingest"] = {"note": "no successful interpret in 7 tries"}

    out = Path(tempfile.gettempdir()) / "pke-i103-e2e-diagnosis.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"saved={out}", flush=True)
    print(
        json.dumps(
            {
                "fake_status": report["case_a_fake_ingest"].get("ingest", {}).get("status"),
                "deep_status": (report.get("case_a_deepseek_ingest") or {}).get("ingest", {}).get("status"),
                "diff_count": len(report.get("case_a_structural_diff") or []),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
