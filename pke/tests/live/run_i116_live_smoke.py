"""I11.6 live smoke — staged metrics (not formal benchmark)."""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from pke.application import FixedClock, IngestService, IngestStatus, SessionContext
from pke.domain import UserContext
from pke.interpretation import DeepSeekInterpreter, InterpretationContext, InterpretationError
from pke.interpretation.prompts import PROMPT_VERSION_V3
from pke.interpretation.semantic.pipeline import envelope_to_canonical_ir
from pke.interpretation.transport.proposal_wire import WireSemanticEnvelope
from pke.llm import DeepSeekConfig, DeepSeekProvider
from pke.ontology import OntologyRegistry
from pke.persist import open_sqlite_uow
from pke.resolution import PersonalContext

from tests.generalization_ingest.fixtures import BENCHMARK_NOW, USER_ID
from tests.live.run_i10_validation import load_env_silent

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "docs" / "reports" / "I11.6-LIVE-SMOKE.json"

CASES = {
    "state": [
        "A geladeira está quebrada.",
        "A porta está aberta.",
        "Acabou detergente.",
    ],
    "relation": [
        "João trabalha na Acme.",
        "O Corolla é meu.",
        "Ana é casada com João.",
    ],
    "event": [
        "Troquei o óleo do Corolla.",
        "A geladeira quebrou.",
        "A porta abriu.",
    ],
}


def _session() -> SessionContext:
    return SessionContext(personal=PersonalContext(user_id=USER_ID))


def _user() -> UserContext:
    return UserContext(user_id=USER_ID, timezone="America/Fortaleza", now=BENCHMARK_NOW)


def main() -> int:
    load_env_silent()
    try:
        cfg = DeepSeekConfig.from_env(timeout_seconds=90.0)
        provider = DeepSeekProvider(cfg)
    except Exception as exc:  # noqa: BLE001
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text(json.dumps({"live_ran": False, "error": str(exc)}, indent=2) + "\n")
        print(f"Live unavailable: {exc}")
        return 0

    ontology = OntologyRegistry.with_core_seeds()
    interpreter = DeepSeekInterpreter(provider, ontology, prompt_version=PROMPT_VERSION_V3)
    runs: list[dict] = []

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        for group, texts in CASES.items():
            for text in texts:
                for run in (1, 2, 3):
                    db = root / f"{group}_r{run}_{abs(hash(text))}.db"
                    row: dict = {
                        "group": group,
                        "text": text,
                        "run": run,
                        "proposal_parse_success": False,
                        "primitive_resolution_success": False,
                        "canonical_resolution_success": False,
                        "knowledge_success": False,
                        "frontier": "PROVIDER",
                    }
                    ctx = InterpretationContext(user=_user())
                    if interpreter.last_raw_content is not None:
                        interpreter.last_raw_content = None
                    try:
                        interpreter.interpret(text, ctx)
                        row["proposal_parse_success"] = True
                        row["primitive_resolution_success"] = True
                        row["canonical_resolution_success"] = True
                        svc = IngestService(
                            interpreter,
                            ontology,
                            lambda p=db: open_sqlite_uow(p),
                            FixedClock(BENCHMARK_NOW),
                        )
                        result = svc.ingest(text, _user(), _session())
                        row["knowledge_success"] = result.status is IngestStatus.COMMITTED
                        row["frontier"] = "PASS" if row["knowledge_success"] else "MATERIALIZATION"
                    except InterpretationError as exc:
                        raw = interpreter.last_raw_content
                        if raw:
                            try:
                                env = WireSemanticEnvelope.parse_json(raw)
                                row["proposal_parse_success"] = True
                                outcome = envelope_to_canonical_ir(env)
                                row["primitive_resolution_success"] = (
                                    outcome.result.primitive.value != "unknown"
                                )
                                row["canonical_resolution_success"] = outcome.ir is not None
                                row["frontier"] = (
                                    "PASS"
                                    if outcome.ir is not None
                                    else (outcome.failure_stage or "CONCEPT_RESOLUTION")
                                )
                            except Exception:
                                row["frontier"] = "PROPOSAL_WIRE"
                        else:
                            row["frontier"] = "PROVIDER"
                        row["error"] = str(exc)[:200]
                    except Exception as exc:  # noqa: BLE001
                        row["frontier"] = "PROVIDER"
                        row["error"] = str(exc)[:200]
                    runs.append(row)

    def rate(key: str) -> float:
        vals = [bool(r[key]) for r in runs]
        return round(sum(vals) / len(vals), 4) if vals else 0.0

    payload = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "prompt": PROMPT_VERSION_V3,
        "cases": sum(len(v) for v in CASES.values()),
        "runs": len(runs),
        "proposal_parse_success": rate("proposal_parse_success"),
        "primitive_resolution_success": rate("primitive_resolution_success"),
        "canonical_resolution_success": rate("canonical_resolution_success"),
        "knowledge_success": rate("knowledge_success"),
        "by_group": {
            g: {
                "knowledge_success": round(
                    sum(1 for r in runs if r["group"] == g and r["knowledge_success"])
                    / max(1, sum(1 for r in runs if r["group"] == g)),
                    4,
                ),
            }
            for g in CASES
        },
        "runs_detail": runs,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    summary = {k: v for k, v in payload.items() if k != "runs_detail"}
    print(json.dumps(summary, indent=2))
    print(f"Wrote {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
