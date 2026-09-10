"""One-shot extraction for I12.3-R formal closure (no live calls)."""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from tests.engine_v1_baseline.corpus import CORPUS

ROOT = Path(__file__).resolve().parents[2]
r = json.loads((ROOT / "docs/reports/I12.3-LIVE-CHARACTERIZATION.json").read_text(encoding="utf-8"))
by = {c.id: c for c in CORPUS}
cv = r["case_variance"]
unsafe = [cid for cid, v in cv.items() if v == "UNSAFE_VARIANCE"]
runs_by: dict[str, list] = defaultdict(list)
for x in r["runs"]:
    runs_by[x["case_id"]].append(x)

out: dict = {"unsafe_ledger": [], "s4_ledger": [], "mp_detail": {}, "repeat_stats": {}}

sys = rep = spo = 0
for cid in unsafe:
    c = by.get(cid)
    rs = runs_by[cid]
    n_u = sum(
        1
        for x in rs
        if x.get("severity") in {"S3", "S4"} or x.get("verdict") == "UNSAFE"
    )
    if n_u == len(rs):
        repeatability = "ALL_RUNS"
        sys += 1
    elif n_u >= 2:
        repeatability = "REPEATED"
        rep += 1
    else:
        repeatability = "SPORADIC"
        spo += 1
    fail = []
    for x in rs:
        if x.get("severity") in {"S3", "S4"} or x.get("verdict") in {
            "UNSAFE",
            "WRONG_PRIMITIVE",
            "WRONG_INTENT",
        }:
            fail.append(
                {
                    "run": x["run"],
                    "verdict": x["verdict"],
                    "severity": x["severity"],
                    "observed_intent": x.get("observed_intent"),
                    "observed_primitive": x.get("observed_primitive"),
                    "notes": x.get("notes"),
                    "primary_root": x.get("primary_root"),
                }
            )
    roots = Counter(
        x.get("primary_root")
        for x in rs
        if x.get("severity") in {"S3", "S4"} or x.get("verdict") == "UNSAFE"
    )
    primary = roots.most_common(1)[0][0] if roots else "NONE"
    out["unsafe_ledger"].append(
        {
            "case": cid,
            "family": c.category if c else "?",
            "utterance": c.utterance if c else "",
            "runs": len(rs),
            "unsafe_runs": n_u,
            "failure": Counter(f["verdict"] for f in fail).most_common(1)[0][0] if fail else "?",
            "severity_mix": dict(Counter(x["severity"] for x in rs)),
            "primary_root": primary,
            "repeatability": repeatability,
            "expected_intent": c.expected_intent if c else None,
            "expected_primitive": c.expected_primitive if c else None,
            "fail_runs": fail,
        }
    )

for x in r["runs"]:
    if x["severity"] != "S4":
        continue
    c = by[x["case_id"]]
    out["s4_ledger"].append(
        {
            "case": x["case_id"],
            "run": x["run"],
            "input": c.utterance,
            "category": c.category,
            "expected_intent": c.expected_intent,
            "expected_primitive": c.expected_primitive,
            "observed_intent": x.get("observed_intent"),
            "observed_primitive": x.get("observed_primitive"),
            "verdict": x["verdict"],
            "notes": x.get("notes"),
            "primary_root": x.get("primary_root"),
            "canonicalization": x.get("canonicalization"),
            "why_s4": "FALSE_CORRECTION_ROUTING"
            if "FALSE_CORRECTION" in str(x.get("notes"))
            else str(x.get("notes")),
            "propose_only": True,
            "commit_path_class": "POTENTIALLY_COMMITTABLE"
            if x.get("observed_intent") == "correct"
            else "BLOCKED_DOWNSTREAM",
        }
    )

for cid, rows in (r.get("mp_anchors") or {}).items():
    c = by.get(cid)
    out["mp_detail"][cid] = {
        "utterance": c.utterance if c else "",
        "expected_primitive": c.expected_primitive if c else None,
        "notes": c.notes if c else "",
        "runs": rows,
        "correct": sum(1 for row in rows if row["verdict"] == "CORRECT"),
        "safe_miss": sum(1 for row in rows if row["verdict"] in {"COVERAGE_MISS", "SAFE_ABSTENTION"}),
        "wrong_primitive": sum(1 for row in rows if row["verdict"] == "WRONG_PRIMITIVE"),
        "severities": dict(Counter(row["severity"] for row in rows)),
    }

out["repeat_stats"] = {"all_runs_unsafe": sys, "repeated": rep, "sporadic": spo}
out["s3_verdicts"] = {
    f"{v}/{s}": n
    for (v, s), n in Counter(
        (x["verdict"], x["severity"]) for x in r["runs"] if x["severity"] in {"S3", "S4"}
    ).items()
}
path = ROOT / "docs/reports/I12.3-R-CLOSURE-EXTRACT.json"
path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"wrote {path}")
print("unsafe", len(out["unsafe_ledger"]), "s4", len(out["s4_ledger"]))
print("repeat", out["repeat_stats"])
print("mp keys", list(out["mp_detail"]))
