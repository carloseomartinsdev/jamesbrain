"""Diagnóstico live de rejects wire — salva JSON sanitizado em temp. Sem API key."""

from __future__ import annotations

import datetime as dt
import json
import os
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from pke.domain import UserContext
from pke.interpretation import DeepSeekInterpreter, InterpretationContext
from pke.interpretation.transport.wire import WireEnvelope
from pke.llm import DeepSeekConfig, DeepSeekProvider
from pke.llm.errors import LlmError
from pke.llm.validation import format_validation_issues
from pke.ontology import OntologyRegistry

FORTALEZA = ZoneInfo("America/Fortaleza")
NOW = dt.datetime(2026, 9, 1, 15, 0, tzinfo=FORTALEZA)

TARGETS = {
    "A": "Troquei o óleo do Corolla hoje por 320 reais.",
    "B": "Tenho dentista quinta às 15h com a Dra. Ana.",
    "D": "Acho que a revisão ficou em uns 180 reais.",
}

GOALS = {"rejects": 3, "accepts": 3}


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


def _ctx() -> InterpretationContext:
    return InterpretationContext(
        user=UserContext(user_id="diag", timezone="America/Fortaleza", now=NOW)
    )


def _validate_raw(content: str) -> dict:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        return {"stage": "json_parse", "error": str(exc), "raw_preview": content[:800]}
    try:
        WireEnvelope.model_validate(payload)
        return {"stage": "wire_ok"}
    except ValidationError as exc:
        return {
            "stage": "wire_reject",
            "issues": format_validation_issues(exc),
        }


def probe_case(code: str, raw: str, provider: DeepSeekProvider, registry: OntologyRegistry) -> dict:
    interpreter = DeepSeekInterpreter(provider, registry)
    ctx = _ctx()
    row: dict = {"case": code, "raw": raw}
    try:
        ir = interpreter.interpret(raw, ctx)
        row["outcome"] = "accepted"
        row["ir_intent"] = getattr(ir, "intent", None)
        if hasattr(ir, "event") and ir.event is not None:
            row["event_type"] = ir.event.type.key
        meta = interpreter.last_metadata
        if meta:
            row["tokens"] = meta.total_tokens
        return row
    except Exception as exc:
        row["outcome"] = "rejected"
        row["error_class"] = type(exc).__name__
        row["error"] = str(exc)
        if isinstance(exc.__cause__, ValidationError):
            row["validation"] = format_validation_issues(exc.__cause__)
        # capture last provider content if provider succeeded but wire failed
        from pke.interpretation.prompts import build_messages
        from pke.llm.models import LlmStructuredRequest

        messages = build_messages(raw, ctx, interpreter._view, prompt_version=interpreter.prompt_version)
        try:
            resp = provider.generate_structured(
                LlmStructuredRequest(messages=messages, json_schema=interpreter._wire_schema)
            )
            row["provider_content"] = resp.content
            row["wire_diagnosis"] = _validate_raw(resp.content)
        except LlmError as prov_exc:
            row["provider_error"] = str(prov_exc)
        return row


def run_focus(case: str, max_calls: int = 20) -> dict:
    load_env_silent()
    if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
        raise SystemExit("DEEPSEEK_API_KEY ausente")
    provider = DeepSeekProvider(DeepSeekConfig.from_env(timeout_seconds=90.0))
    registry = OntologyRegistry.with_core_seeds()
    raw = TARGETS[case]
    rejects: list[dict] = []
    accepts: list[dict] = []
    for attempt in range(1, max_calls + 1):
        row = probe_case(case, raw, provider, registry)
        row["attempt"] = attempt
        if row["outcome"] == "accepted":
            accepts.append(row)
        else:
            rejects.append(row)
        print(
            f"{case}#{attempt} {row['outcome']} "
            f"{row.get('error') or row.get('event_type') or row.get('provider_error')}",
            flush=True,
        )
        if len(rejects) >= GOALS["rejects"] and len(accepts) >= GOALS["accepts"]:
            break
    return {"case": case, "rejects": rejects, "accepts": accepts}


def main() -> int:
    out_dir = Path(tempfile.gettempdir()) / "pke-i102-diagnosis"
    out_dir.mkdir(exist_ok=True)
    report: dict = {"cases": {}}
    for code in ("D", "A", "B"):
        report["cases"][code] = run_focus(code)
    path = out_dir / "wire-rejects.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"saved={path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
