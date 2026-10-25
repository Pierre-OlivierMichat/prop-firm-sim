# ARC / LuxAlgo Python bridge (research prototype)

This is a local development branch cloned from LuxAlgo dev, commit 05e443250f1294c03fe65120727666feeb353e32. The GitHub-hosted fork has not been created.

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
