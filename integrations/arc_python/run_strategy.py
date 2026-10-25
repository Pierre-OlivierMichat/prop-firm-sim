#!/usr/bin/env python3
"""Execute a user-provided Python strategy on a read-only SCID stream.

Required user module function:
    generate_trades(ticks: Iterable[ScidRecord]) -> Iterable[dict]
Each dict must supply a complete canonical trade CSV row with explicit
initial-risk R. The strategy is responsible for causal signals, fills,
stop/target priority, costs and trade-level P&L; no lookahead guard is inferred.
Only use on a dataset independently admitted for the purpose.
"""
import argparse
import csv
import importlib.util
from pathlib import Path
from scid_ticks import iter_scid

FIELDS = ["open time", "close time", "symbol", "direction", "quantity",
          "entry price", "exit price", "stop loss", "pnl", "fees", "r"]

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input-scid", type=Path, required=True)
    ap.add_argument("--strategy-file", type=Path, required=True)
    ap.add_argument("--output-trades", type=Path, required=True)
    a = ap.parse_args()
    if not a.strategy_file.is_file():
        ap.error(f"Missing Python strategy module: {a.strategy_file}")
    spec = importlib.util.spec_from_file_location("arc_selected_strategy", a.strategy_file)
    if spec is None or spec.loader is None:
        ap.error("Could not import strategy module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fn = getattr(module, "generate_trades", None)
    if not callable(fn):
        ap.error("Strategy module must expose generate_trades(ticks)")
    a.output_trades.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with a.output_trades.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS, extrasaction="ignore")
        writer.writeheader()
        for trade in fn(iter_scid(a.input_scid)):
            if not isinstance(trade, dict) or not all(field in trade for field in FIELDS):
                raise ValueError("Strategy returned incomplete trade (all canonical fields required)")
            if trade["r"] is None or trade["r"] == "":
                raise ValueError("R must reflect actual initial-risk capital; cannot guess")
            writer.writerow(trade)
            count += 1
    print(f"Exported {count} strategy round trips to {a.output_trades}; source NOT certified")

if __name__ == "__main__":
    main()
