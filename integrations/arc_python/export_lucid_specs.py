#!/usr/bin/env python3
"""Versioned, research-only projection of ARC Lucid rules into LuxAlgo JSON.

Does NOT read any market-data archive. Does NOT certify Lucid contracts or
pricing. Unknown semantics are flagged; do not interpret as executable parity.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

CATALOG_REL = Path("research_ops/prop_os_extension_v4/lucid_catalogue.py")
ALL_SIZES = (25, 50, 100, 150)
ALL_PROGRAMMES = ("LucidDaily", "LucidPro", "LucidFlex")
STATUS = "PROJECTION_ONLY_NOT_RULE_PARITY_CERTIFIED"


def load_catalogue(arc_repo: Path):
    file = arc_repo / CATALOG_REL
    if not file.is_file():
        raise ValueError(f"ARC current Lucid catalogue missing: {file}")
    module_spec = importlib.util.spec_from_file_location("arc_source_bound_lucid_catalogue", file)
    if module_spec is None or module_spec.loader is None:
        raise ValueError("Invalid ARC source catalogue module")
    mod = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(mod)
    if mod.SCHEMA != "ARC_LUCID_PROGRAMMES_CURRENT_V1" or mod.REVIEWED_AS_OF != "2026-10-23":
        raise ValueError("Unknown ARC catalogue schema/version: review source before projecting")
    profiles = mod.products()
    if len(profiles) != 56:
        raise ValueError("Current ARC Lucid matrix not exactly 56")
    for profile in profiles:
        without_hash = {k: v for k, v in profile.items() if k != "product_sha256"}
        if mod.digest(without_hash) != profile["product_sha256"]:
            raise ValueError("ARC product content hash mismatch")
        if mod.digest(profile["native"]) != profile["native_sha256"]:
            raise ValueError("ARC native rules hash mismatch")
    return file, profiles


def max_loss(profile: dict, *, funded: bool) -> dict:
    n = profile["native"]
    mode = n["funded_drawdown_mode" if funded else "drawdown_mode"]
    if mode not in ("EOD", "INTRADAY"):
        raise ValueError(f"Unmapped drawdown: {mode}")
    amount_cents = n["funded_drawdown_cents" if funded else "drawdown_cents"]
    initial_cents = n["funded_initial_cents" if funded else "initial_cents"]
    lock_cents = n["funded_floor_lock_cents" if funded else "floor_lock_cents"]
    return {
        "amount": amount_cents / 100,
        "mode": "trailing-realized-eod" if mode == "EOD" else "trailing-locks-at-initial",
        "locksAtInitial": True,
        "lockOffsetAmount": (lock_cents - initial_cents) / 100,
    }


def project(profile: dict, fee: float) -> dict:
    n = profile["native"]
    size = profile["nominal_size_usd"]
    programme = profile["program"]
    cfg = profile["configuration"]
    if fee <= 0:
        raise ValueError("Explicit positive hypothetical evaluation fee required")
    if cfg["eval_drawdown_mode"] not in ("EOD", "INTRADAY"):
        raise ValueError("Unsupported evaluation drawdown")
    if programme not in ALL_PROGRAMMES:
        raise ValueError("Unsupported Lucid programme")
    if n["daily_action"] != "SOFT":
        raise ValueError("Daily action changed: projection needs review")
    if n["split_ppm"] != 900000:
        raise ValueError("Split changed")
    if n["min_trading_days"] != 1:
        raise ValueError("Evaluation minimum days changed")
    if n["payout_min_cents"] != 50000:
        raise ValueError("Payout minimum changed")
    if n["funded_enabled"] is not True:
        raise ValueError("Funded phase must be enabled")
    if n["max_simulated_payouts"] != 1:
        raise ValueError("Only first-payout account profiles supported")
    eval_step = {
        "profitTargetAmount": n["eval_target_cents"] / 100,
        "minTradingDays": n["min_trading_days"],
    }
    if n["eval_consistency_ppm"] < 1000000:
        eval_step["consistency"] = {
            "maxBestDayProfitPct": n["eval_consistency_ppm"] / 10000
        }
    payout = {
        "bufferAmount": n["payout_buffer_cents"] / 100,
        "minPayoutAmount": n["payout_min_cents"] / 100,
        "minCycleProfitAmount": n["cycle_profit_min_cents"] / 100,
        "minWinningDays": n["qualifying_days"],
        "winningDayMinProfit": n["qualifying_day_cents"] / 100,
    }
    if n.get("payout_cap_cents"):
        # This catalogue records first-request caps; later payouts may differ.
        payout["maxPayoutAmount"] = n["payout_cap_cents"][0] / 100
    if n["payout_fraction_basis"] == "CYCLE_PROFIT":
        if n["payout_fraction_ppm"] != 500000:
            raise ValueError("Unknown profit fraction")
        payout["maxPayoutPctOfProfit"] = 50
    elif n["payout_fraction_basis"] != "PROFIT_ABOVE_BUFFER":
        raise ValueError("Unsupported payout fraction basis")
    if n["consistency_ppm"] < 1000000:
        payout["consistencyMaxBestDayPct"] = n["consistency_ppm"] / 10000

    gaps = list(profile["native_semantic_gaps"])
    gaps.extend([
        "SIMULATOR_BOOTSTRAP_OMITS_DAILY_TIMES_AND_INTRATRADE_MARKS",
        "TRADING_CAPS_NOT_ENFORCED: requires causal Python strategy sizing",
        "EVALUATION_INTRADAY_ACTIVATION_NOT_MODELED: assumes next session",
        "PAYOUT_MINIMUM_ENFORCED_FIRST_REQUEST_ONLY",
        "PAYOUT_APPROVAL_IS_NOT_REQUEST_OR_BANK_RECEIPT",
        "RESET_FEE_UNKNOWN: restrict interpretation to one attempt",
        "PURCHASE_FEE_HYPOTHETICAL_NOT_CHECKOUT_VERIFIED",
    ])
    if n["daily_limit_cents"] is not None or n["funded_daily_limit_cents"] is not None:
        gaps.append("SOFT_DLL_NOT_ENFORCED: LuxAlgo models breach/fail, not soft trade halt")
    if programme == "LucidFlex":
        gaps.append("FUNDED_SCALING_TIERS_NOT_ENFORCED")
    spec = {
        "challengeId": n["id"],
        "name": f"{programme} {size // 1000}K | DLL {'on' if cfg['dll_enabled'] else 'off'}"
                f" | evalDD {cfg['eval_drawdown_mode']}"
                f" | consistency {cfg['eval_consistency_percent'] or 'none'}",
        "productType": "futures",
        "accountSize": size,
        "currency": "USD",
        "steps": [eval_step],
        "dailyLoss": None,  # Soft cap does not mean punitive failure; must not fake it.
        "maxLoss": max_loss(profile, funded=False),
        "fees": {
            "price": fee,
            "billing": "one-time",
            "resetFee": None,
            "activationFee": n["activation_fee_cents"] / 100,
            "refundableOnPass": False,
        },
        "funded": {
            "profitSplitPct": n["split_ppm"] / 10000,
            "payoutFrequency": "on-demand",  # Official articles: no fixed payout window.
            "firstPayoutMinDays": 0,
            "dailyLoss": None,
            "maxLoss": max_loss(profile, funded=True),
            "payoutRules": payout,
        },
        "constraints": {
            "maxContractSize": n["eval_cap"],
        },
        "flagsNotSimulated": sorted(set(gaps)),
    }
    return spec


def write_new_or_identical(path: Path, payload: dict) -> None:
    data = (json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    if path.exists() and path.read_bytes() != data:
        raise ValueError(f"Refuse to overwrite differing generated evidence: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(data)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--arc-repo", type=Path, required=True)
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--sizes", default="25,50")
    ap.add_argument("--programmes", default="LucidDaily,LucidPro,LucidFlex")
    ap.add_argument("--fee", action="append", default=[], help="EXPLICIT hypothetical evaluation price, e.g. 25=60")
    args = ap.parse_args()
    try:
        sizes = [int(x.strip()) for x in args.sizes.split(",")]
        programmes = [x.strip() for x in args.programmes.split(",")]
        if len(set(sizes)) != len(sizes) or any(x not in ALL_SIZES for x in sizes):
            raise ValueError("Invalid or duplicate nominal sizes")
        if len(set(programmes)) != len(programmes) or any(x not in ALL_PROGRAMMES for x in programmes):
            raise ValueError("Invalid or duplicate programmes")
        fees = {}
        for assignment in args.fee:
            size_text, price_text = assignment.split("=", 1)
            size, price = int(size_text), float(price_text)
            if size in fees or size not in ALL_SIZES or price <= 0:
                raise ValueError("Fee must be unique positive price for supported size")
            fees[size] = price
        if set(sizes) - set(fees):
            raise ValueError(f"Missing explicit fees for sizes {sorted(set(sizes)-set(fees))}")
        source, all_profiles = load_catalogue(args.arc_repo)
        selected = [x for x in all_profiles
                    if x["nominal_size_usd"] // 1000 in sizes and x["program"] in programmes]
        expected = sum(14 for _ in sizes) if set(programmes) == set(ALL_PROGRAMMES) else None
        if expected is not None and len(selected) != expected:
            raise ValueError("Unexpected selected Lucid account matrix")
        entries = []
        for profile in selected:
            size = profile["nominal_size_usd"] // 1000
            output = args.output_dir / f"{profile['product_id']}.json"
            spec = project(profile, fees[size])
            write_new_or_identical(output, spec)
            entries.append({
                "product_id": profile["product_id"],
                "programme": profile["program"],
                "size_k": size,
                "configuration": profile["configuration"],
                "source_product_sha256": profile["product_sha256"],
                "source_native_sha256": profile["native_sha256"],
                "output": output.name,
                "output_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
                "flags_not_simulated": spec["flagsNotSimulated"],
                "source_urls": profile["source_urls"],
                "status": STATUS,
            })
        manifest = {
            "schema": "ARC_LUCID_LUXALGO_PROJECTION_V1",
            "reviewed_as_of": "2026-10-23",
            "source_relpath": str(CATALOG_REL).replace("\\", "/"),
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "fee_assumption_usd_by_size": {str(k): fees[k] for k in sorted(fees)},
            "fee_source": "USER_PROVISIONAL_SCENARIO_NOT_LUCID_CHECKOUT",
            "status": STATUS,
            "count": len(entries),
            "accounts": entries,
            "warnings": [
                "No exact account is certified: soft DLL, session timing, data marks and restrictions remain missing",
                "Evaluation fees are user-provided hypothetical scenarios, not current checkout quotes",
                "The modeled first payout is an eligible request proxy, not bank cash",
            ],
        }
        write_new_or_identical(args.output_dir / "manifest.json", manifest)
    except (ValueError, OSError) as exc:
        ap.error(str(exc))
    print(json.dumps({"manifest": str(args.output_dir / "manifest.json"),
                      "count": len(selected), "status": STATUS}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
