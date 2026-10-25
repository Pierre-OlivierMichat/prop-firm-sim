#!/usr/bin/env python3
"""Python ARC trade-ledger -> LuxAlgo campaign simulation bridge (research only).

Input must be an admitted causal backtest's executed trade log; this program does
not read raw ticks or certify the firm's live rules, execution or data license.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while data := f.read(1 << 20):
            h.update(data)
    return h.hexdigest()

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trades", type=Path, required=True)
    ap.add_argument("--spec", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--paths", type=int, default=2000)
    ap.add_argument("--attempt-cap", type=int, default=1)
    ap.add_argument("--seed", default="42")
    ap.add_argument("--horizons", default="3,4,5,10,20,40")
    ap.add_argument("--funded-horizon", type=int, default=90)
    ap.add_argument("--risk", default="0.5%")
    ap.add_argument("--risk-mode", choices=["fixed-amount", "percent-of-balance", "percent-of-initial"],
                    default="percent-of-initial")
    ap.add_argument("--node-cli", type=Path,
                    default=Path(__file__).resolve().parents[2] / "packages/cli/dist/index.js")
    a = ap.parse_args()
    for path in (a.trades, a.spec, a.node_cli):
        if not path.is_file():
            ap.error(f"Required file does not exist: {path}")
    try:
        horizons = [int(x.strip()) for x in a.horizons.split(",")]
    except ValueError:
        ap.error("Comma-separated integer horizons required")
    if not horizons or min(horizons) < 1 or max(horizons) > a.funded_horizon:
        ap.error("All horizons must lie in 1..funded-horizon")
    if a.paths < 100 or a.attempt_cap < 1:
        ap.error("paths >= 100 and attempt-cap >= 1 required")
    with a.trades.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = {s.lower().strip() for s in (reader.fieldnames or [])}
        if not {"open time", "r"} <= fields:
            ap.error("CSV requires open time and explicit initial-risk R column")
        rows = list(reader)
    if len(rows) < 10:
        ap.error("Need at least 10 historical closed trades")
    with a.spec.open(encoding="utf-8") as f:
        spec = json.load(f)
    if not isinstance(spec, dict) or not all(k in spec for k in ("steps", "funded", "fees", "maxLoss")):
        ap.error("Full versioned ChallengeSpec required; no guessed missing rules")
    cmd = ["node", str(a.node_cli), "simulate", "--spec", str(a.spec),
           "--trade-log", str(a.trades), "--risk", a.risk,
           "--risk-mode", a.risk_mode, "--paths", str(a.paths),
           "--seed", a.seed, "--attempt-cap", str(a.attempt_cap),
           "--funded-horizon", str(a.funded_horizon),
           "--campaign-horizons", a.horizons, "--json"]
    run = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=False)
    if run.returncode:
        print(run.stderr or run.stdout, file=sys.stderr)
        return run.returncode
    result = json.loads(run.stdout)
    if "campaign" not in result:
        raise RuntimeError("ARC campaign metrics missing from fork")
    receipt = {
        "schema": "ARC_LUXALGO_CAMPAIGN_BRIDGE_V1",
        "trades_source": str(a.trades.resolve()),
        "trades_sha256": digest(a.trades),
        "trade_count": len(rows),
        "spec_source": str(a.spec.resolve()),
        "spec_sha256": digest(a.spec),
        "result": result,
        "limitations": [
            "First request is modeled eligible withdrawal, not approval or received cash",
            "Bootstrap R series omits session-wise frequency, no-trade days and intratrade marks",
            "No source eligibility, prop-rule correctness or executable fill certification here",
        ],
    }
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"receipt": str(a.output.resolve()), "campaign": result["campaign"]}, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
