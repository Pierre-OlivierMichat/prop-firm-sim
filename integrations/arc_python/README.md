# ARC / LuxAlgo Python bridge (research prototype)

This branch was cloned from LuxAlgo dev, upstream commit 05e443250f1294c03fe65120727666feeb353e32. Public GitHub fork: https://github.com/Pierre-OlivierMichat/prop-firm-sim/tree/arc/first-payout-python-bridge. The upstream dev branch remains unmodified.

After corepack pnpm install and corepack pnpm build:

    python integrations/arc_python/run_campaign.py --trades PATH/strategy.csv --spec PATH/rules.json --paths 2000 --seed 42 --attempt-cap 1 --horizons 3,4,5,10,20,40 --funded-horizon 90 --risk 100 --risk-mode fixed-amount --output PATH/result.json

Input CSV is a causal Python-backtest completed trade ledger, not tick data. Header:
    open time,close time,symbol,direction,quantity,entry price,exit price,stop loss,pnl,fees,r

Provide explicit realised-R based on actual initial risk, not an inferred moved stop. Feed a full versioned LuxAlgo ChallengeSpec including all evaluation, funded, loss, fee and payout rules. Firm rules must be source-verified separately; never fill unknown costs with zero.

The engine accepts --campaign-horizons DAYS; JSON output campaign.horizons contains pPassEval, pFirstRequest and Wilson 95% intervals (all paths denominator, cumulative elapsed simulated days from first evaluation). pFirstRequest is a first modeled eligible withdrawal event, NOT a compliant payout request actually approved, and NOT received cash. Failed retries cost elapsed days.

IMPORTANT LIMITATIONS: It uses block-resampled trade R values and fixed/Poisson trade counts, so original no-trade days, temporal day clustering, intratrade equity marks and granular trailing-drawdown breaches are not reproduced. The existing LuxAlgo min-trading-days and funded calendar approximation may inflate speed probabilities; see assumptions.flags. This bridge does NOT supersede ARC's native Prop Campaign OS or its existing eligibility firewall. No Sierra file is read or exported here.

Next technical extension: add session-preserving and mark-aware TradeSource, parity-test with ARC native, then introduce authorized source ingestion for Python tick replay. No proprietary data, protected partitions or live fees are authorized by this prototype.


## Direct SCID-to-Python hook (synthetic tested; real data not inspected)

The read-only scid_ticks.iter_scid(path) streams 56-byte-header / 40-byte-record
Sierra intraday files as Python ScidRecord values (timestamp UTC, OHLC,
number of trades, volume, bid volume, ask volume). It does not assert all
records are single exchange trades: test the recording interval and vendor
metadata first. It does not infer quotes or aggressor flags from OHLC fields.

Provide a Python strategy module implementing:

    def generate_trades(ticks):
        for tick in ticks:
            ... # causal execution and separate risk, fees, slippage
            yield {"open time": ..., "close time": ..., "symbol": ..., "direction": ...,
                   "quantity": ..., "entry price": ..., "exit price": ...,
                   "stop loss": ..., "pnl": ..., "fees": ..., "r": ...}

Then produce the complete trade ledger:

    python integrations/arc_python/run_strategy.py --input-scid PATH/contract.scid --strategy-file PATH/strategy.py --output-trades PATH/ledger.csv

And calculate prop economics via run_campaign.py above.

For reproducible proof without real market data:

    python -m unittest discover -s integrations/arc_python -p test_*.py -v
    python integrations/arc_python/run_campaign.py --trades integrations/arc_python/synthetic_demo_trades.csv --spec integrations/arc_python/synthetic_demo_spec.json --paths 200 --seed 42 --attempt-cap 1 --horizons 3,4,5,10,20,40 --funded-horizon 90 --risk 100 --risk-mode fixed-amount --output integrations/arc_python/synthetic_demo_result.json

The synthetic spec and trades demonstrate software integration, not real strategy
or Lucid account performance. Do not import Sierra archives without separately
resolving vendor rights and ARC evidence eligibility. Official Sierra SCID format
documentation has been removed; decoder layout was cross-checked against the
publicly documented legacy 56/40-byte record structure, not every historical
file/version variant. Live/protected data and broker permissions remain gated.

## LucidDaily / LucidPro / LucidFlex account catalogue

The generator reads only the source-bound 2026-10-23 ARC Python account catalogue;
it does not inspect historical market files. It reproduces the 56 unique ARC
variant IDs/hashes and exports the requested size subset into **versioned
LuxAlgo ChallengeSpec JSON** plus a SHA256 source/translation manifest.

Example, from the fork root:

    python integrations/arc_python/export_lucid_specs.py --arc-repo PATH/TO/vp_edge_backtest --output-dir integrations/arc_python/lucid_specs_20261023_v1 --sizes 25,50 --fee 25=60 --fee 50=90

The supplied evaluation fees of 60/90 USD are **explicit hypothetical research
inputs**, not verified Lucid checkout prices. By default the export includes
16 LucidDaily, 4 LucidPro and 8 LucidFlex 25K/50K variants.

Run one simulated, provisional account using an admitted strategy CSV:

    python integrations/arc_python/run_campaign.py --trades PATH/strategy.csv --spec integrations/arc_python/lucid_specs_20261023_v1/lucid-daily-25k-dll-off-evaldd-eod-evalcons-50-20261023-v1.json --paths 2000 --attempt-cap 1 --horizons 3,4,5,10,20,40 --risk 100 --risk-mode fixed-amount --output PATH/result.json

Every generated account has explicit flagsNotSimulated and a manifest
status of PROJECTION_ONLY_NOT_RULE_PARITY_CERTIFIED. The firm source
linkage is in the manifest, not in the ChallengeSpec sources property,
which requires a human-verified date. The bridge never claims such
human verification. All 28 inputs pass the LuxAlgo Zod challenge schema.

### Current rule coverage / blocking gaps

Modeled: evaluation target, one-step evaluation, min trading days,
best-day evaluation consistency (Daily/Flex), evaluation/funded drawdown
types, funded payout buffer, minimum first-request amount (USD 500),
first cycle profit threshold, funded Pro 40% consistency, Flex five
qualifying days and minimum winning-day amount, first payout cap,
first-request share, and provisional fees.

NOT modeled with exact parity: intratrade equity marks, soft DLL trade
halts and scaling, DLL-triggered profit caps, LucidDaily's news
blackout and live-transfer threshold, Flex dynamic mini scaling,
full calendar-accurate funding activation, actual payout approval
and bank-cash receipt. Strict full-account certification remains
blocked until these are addressed in the event engine and tested
against ARC native rules. Never treat a modeled payout event as
approved or received money.

No market data was included in this public fork, and the generated
synthetic sample is not a real Lucid performance estimate.
