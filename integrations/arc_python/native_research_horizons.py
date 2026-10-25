#!/usr/bin/env python3
"""ARC-native prop campaign by horizon, behind the LuxAlgo fork.

This is the *mark-aware research backend*, not LuxAlgo's approximate
closed-trade R bootstrap. Only the ARC native source-admission gateway is
allowed to open hash-bound historical mark streams. No tick or trade series
are emitted into the fork output, and no source is published on GitHub.

The outputs are fast-research conditional Monte Carlo estimates, not firm
certification or payouts received. Horizons measure OPEN TRADING SESSIONS,
converted to dated calendar offsets. Re-running different horizons is independent Monte Carlo
and therefore their *estimated* curves can have sampling non-monotonicity.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from math import sqrt

def wilson(k: int, n: int) -> list[float]:
    if n <= 0 or k < 0 or k > n:
        raise ValueError("Invalid count for 95% Wilson confidence interval")
    z = 1.959963984540054
    x = k / n
    d = 1 + z * z / n
    m = (x + z * z / (2 * n)) / d
    w = z * sqrt((x * (1 - x) + z * z / (4 * n)) / n) / d
    return [0.0 if k == 0 else max(0.0, m - w),
            1.0 if k == n else min(1.0, m + w)]

def trading_horizon_calendar_offsets(clock: list[dict], horizons: list[int]) -> dict[int, int]:
    """Translate nth PRESENT open exchange session to inclusive calendar-day count."""
    seen = 0
    offsets = {}
    for ordinal, session in enumerate(clock, 1):
        if session["market_open"] and session["status"] == "PRESENT":
            seen += 1
        if seen in horizons and seen not in offsets:
            offsets[seen] = ordinal
    if set(offsets) != set(horizons):
        raise ValueError("Target calendar cannot cover all trading horizons")
    return offsets


def main() -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--arc-repo", required=True, type=Path)
    cli.add_argument("--output", required=True, type=Path)
    cli.add_argument("--strategy", choices=["NQ_PRECISION", "ES_PRECISION_PORT"], default="NQ_PRECISION")
    cli.add_argument("--programme", choices=["LucidDaily", "LucidPro", "LucidFlex"], default="LucidDaily")
    cli.add_argument("--size-k", choices=[25, 50, 100, 150], type=int, default=25)
    cli.add_argument("--ids", default="", help="Comma-separated exact source-product IDs; empty selects all chosen programme and size")
    cli.add_argument("--horizons", default="3,4,5,10,20,40", help="TRADING days, must be <=40")
    cli.add_argument("--paths", type=int, default=200)
    cli.add_argument("--seed", type=int, default=20261025)
    cli.add_argument("--execution", choices=[0, 1], type=int, default=1)
    cli.add_argument("--side-fee-cents", choices=[175, 189], type=int, default=189)
    cli.add_argument("--sizing", choices=["FIRST_TIER_FIXED", "ONE_MINI_FIXED"], default="ONE_MINI_FIXED")
    cli.add_argument("--payout", choices=["MINIMUM", "MAX_AVAILABLE"], default="MINIMUM")
    args = cli.parse_args()

    if args.arc_repo.resolve().is_relative_to(Path(__file__).resolve().parents[2]):
        cli.error("ARC canonical repository must be independent of LuxAlgo fork")
    if not (100 <= args.paths <= 20000):
        cli.error("100..20000 Monte Carlo paths required")
    if not (0 <= args.seed < 2**32):
        cli.error("Seed outside UINT32")
    try:
        horizons = sorted(set(map(int, args.horizons.split(","))))
    except ValueError:
        cli.error("Invalid list of horizon integers")
    if not horizons or horizons[0] < 1 or horizons[-1] > 40:
        cli.error("All horizons must be between 1 and 40 TRADING days")
    ids = tuple(x.strip() for x in args.ids.split(",") if x.strip())
    if len(ids) != len(set(ids)):
        cli.error("Duplicate account IDs")

    sys.path.insert(0, str(args.arc_repo.resolve()))
    from research_ops.prop_agent_gateway_v1.service import prepare
    from research_ops.engine_truth.native_bridge import execute, identity
    from research_ops.engine_truth.contracts import canonical
    from research_ops.prop_factory_v1.registry import digest

    plan = prepare(strategy=args.strategy, programme=args.programme,
                   size_k=args.size_k, ids=ids, execution=args.execution,
                   fee_side_cents=args.side_fee_cents, horizon=90,
                   paths=args.paths, seed=args.seed, sizing=args.sizing, payout=args.payout)
    # Official LucidPro 25K DLL help page says None, while the ARC 2026-10-23
    # catalogue contains an optional DLL-ON variant with a conflicting offer card.
    # Neither may be treated as firm-exact until that discrepancy is adjudicated.
    for cell in plan["cells"]:
        if any("25K_PRO_DLL_CONFLICT" in x
               for x in cell["unimplemented_compliance_constraints"]):
            raise ValueError("UNRESOLVED_OFFICIAL_25K_PRO_DLL_CONFLICT: block affected variant")
    source = plan["native_request"]
    base_jobs = source["jobs"]
    if not base_jobs or len(base_jobs) * len(horizons) * args.paths > 500000:
        raise ValueError("No accounts or excessive paths/account/horizon cells")
    # Resolve horizon h into the calendar length containing h open sessions.
    clock = base_jobs[0]["request"]["target_calendar"]
    day_counts = trading_horizon_calendar_offsets(clock, horizons)
    jobs = []
    for h in horizons:
        for cell in base_jobs:
            r = dict(cell["request"])
            r["experiment"] = {**r["experiment"], "horizon_days": day_counts[h], "audit_paths": 0}
            jobs.append({"cell_id": cell["cell_id"] + f"|H{h}", "request": r})
    native_request = {
        "schema": "ARC_ENGINE_TRUTH_LOCAL_BATCH_V2",
        "calendar": source["calendar"],
        "jobs": jobs,
    }
    source_request_bytes = canonical(native_request)
    if len(source_request_bytes) > 64000000:
        raise ValueError("Native batch input size exceeds bounded 64 MB")
    source_sha = plan["settings"]["source_calendar_sha256"]
    result = execute(native_request, timeout=240)
    if result.get("schema") != "ARC_ENGINE_TRUTH_LOCAL_BATCH_RESULT_V2":
        raise ValueError("Unexpected native output schema")
    rows = result.get("rows", [])
    expected = {j["cell_id"] for j in jobs}
    if len(rows) != len(expected) or {r["cell_id"] for r in rows} != expected:
        raise ValueError("Native returned incomplete account/horizon grid")
    vals = []
    for row in rows:
        if row.get("status") != "COMPLETED":
            raise ValueError("Native refused " + str(row["cell_id"]) + ": " + str(row.get("error")))
        summary = row["result"]["summary"]
        if summary.get("paths") != args.paths:
            raise ValueError("Wrong Monte Carlo denominator")
        if any(summary.get(k) not in (0, None) for k in
               ("pass_unresolved", "request_unresolved", "censored_paths")):
            raise ValueError("Nonzero censoring or unresolved pass / request")
        if summary.get("p_pass") is None or summary.get("p_first_request") is None:
            raise ValueError("Unknown modeled pass/request probabilities")
        ps = summary["p_pass"]
        pr = summary["p_first_request"]
        if not (0 <= pr <= ps <= 1):
            raise ValueError("Impossible joint event ordering")
        passed = round(ps * args.paths)
        requested = round(pr * args.paths)
        if abs(ps - passed / args.paths) > 1e-9 or abs(pr - requested / args.paths) > 1e-9:
            raise ValueError("Probabilities not exact path frequencies")
        vals.append({
            "cell_id": row["cell_id"].rsplit("|H", 1)[0],
            "horizon_trading_days": int(row["cell_id"].rsplit("|H", 1)[1]),
            "horizon_calendar_days_actual": day_counts[int(row["cell_id"].rsplit("|H", 1)[1])],
            "p_pass_eval": ps,
            "p_pass_eval_wilson95": wilson(passed, args.paths),
            "p_first_request": pr,
            "p_first_request_wilson95": wilson(requested, args.paths),
            "paths": args.paths, "passes": passed, "requests": requested,
            "soft_stop_count": summary["soft_stops"],
            "failed_paths": summary["failures"],
            "request_unknown": False,
            "request_not_bank_cash": True,
        })
    vals.sort(key=lambda x: (x["cell_id"], x["horizon_trading_days"]))
    account_map = {x["cell_id"]: x for x in plan["cells"]}
    receipt = {
        "schema": "ARC_LUXALGO_NATIVE_VERIFIED_HORIZONS_V1",
        "status": "FAST_RESEARCH_SOURCE_ADMITTED_RULES_NOT_CERTIFIED",
        "source": args.strategy,
        "programme": args.programme,
        "size_k": args.size_k,
        "horizons_are": "OPEN_TRADING_SESSIONS_FROM_FIRST_EVALUATION",
        "horizon_calendar_conversion": {str(k): day_counts[k] for k in sorted(day_counts)},
        "engine": "ARC_CANONICAL_NATIVE_ORDERED_MARK_EVENT_SIMULATOR",
        "backend": "research_ops.engine_truth.native_bridge.execute",
        "source_calendar_sha256": source_sha,
        "risk_certificate_sha256": plan["settings"]["source_risk_certificate_sha256"],
        "native_engine_exe_sha256": identity()["executable_sha256"],
        "native_request_sha256": sha256(source_request_bytes).hexdigest(),
        "seed": args.seed,
        "market_side_fee_cents": args.side_fee_cents,
        "sizing": args.sizing,
        "payout_request_policy": args.payout,
        "account_rules": [{
            "cell_id": k,
            "product_id": v["product_id"],
            "source_rule_sha256": v["original_native_rule_sha256"],
            "unimplemented_compliance_constraints": v["unimplemented_compliance_constraints"],
        } for k, v in account_map.items()],
        "results": vals,
        "limitations": [
            "Historical admitted, exposed strategy source; not independent out-of-sample validation",
            "Firm rule options are versioned and source-bound, not exhaustively externally certified",
            "Intraday funding in 5-30m is approximated by next-session activation in ARC current native rules",
            "Known news blackout and trading constraints are not all enforced by source stream",
            "Fixed 5-session resampling and 200-or-more paths quantify MC error, not historical model error",
            "Official purchase and processing fees unknown; net bank cash probability not claimed",
            "Never claim payout approved or received. Event is first modeled eligible request",
        ],
        "immutable_input_account_plan_run_id": plan["run_id"],
    }
    serial = json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists() and args.output.read_text(encoding="utf-8") != serial:
        raise ValueError("Immutable prior result differs: select new output identity")
    if not args.output.exists():
        args.output.write_text(serial, encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "output": str(args.output),
                      "cells": len(account_map), "horizons": horizons, "paths": args.paths,
                      "results": vals[:12], "limitations": receipt["limitations"]}, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
