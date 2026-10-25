import { describe, expect, it } from "vitest";
import { simulate, type TraderProfileInput } from "../src/index.js";
import { baseSpec } from "./helpers.js";

const profile: TraderProfileInput = {
  kind: "bootstrap",
  rSeries: [2, 2, 1, -1, 2, 1, 2, -1, 1, 2, 2, -1],
  blockMeanLength: 3,
  tradesPerDay: 2,
  risk: { mode: "fixed-amount", value: 100 },
};
const spec = baseSpec({
  accountSize: 25000,
  steps: [{ profitTargetAmount: 300, minTradingDays: 0 }],
  dailyLoss: null,
  maxLoss: { mode: "static-initial", amount: 1500 },
  funded: {
    profitSplitPct: 80,
    payoutFrequency: "on-demand",
    firstPayoutMinDays: 0,
    payoutRules: { bufferAmount: 0 },
  },
});

describe("ARC cumulative campaign horizons", () => {
  it("makes funded payouts joint, monotone and reproducible", () => {
    const options = { paths: 200, seed: 33, attemptCap: 1,
      fundedHorizonDays: 40, campaignHorizons: [40, 3, 5, 5, 10] };
    const first = simulate(spec, profile, options);
    expect(first).toEqual(simulate(spec, profile, options));
    const rows = first.campaign!.horizons;
    expect(rows.map((x) => x.days)).toEqual([3, 5, 10, 40]);
    for (const [i, row] of rows.entries()) {
      expect(row.pFirstRequest).toBeLessThanOrEqual(row.pPassEval);
      expect(row.pPassEval).toBe(row.evalPassedPaths / 200);
      expect(row.pFirstRequest).toBe(row.modeledFirstRequestPaths / 200);
      if (i > 0) {
        expect(row.pPassEval).toBeGreaterThanOrEqual(rows[i - 1]!.pPassEval);
        expect(row.pFirstRequest).toBeGreaterThanOrEqual(rows[i - 1]!.pFirstRequest);
      }
    }
  });
  it("preserves legacy results when no horizon requested", () => {
    const result = simulate(spec, profile, { paths: 100, seed: 1 });
    expect(result.campaign).toBeUndefined();
  });
  it("fails closed when horizon is censored or funded disabled", () => {
    expect(() => simulate(spec, profile, {
      paths: 100, fundedHorizonDays: 5, campaignHorizons: [10],
    })).toThrow(/fundedHorizonDays/);
    expect(() => simulate(spec, profile, {
      paths: 100, simulateFunded: false, campaignHorizons: [3],
    })).toThrow(/simulateFunded/);
  });
  it("does not award a payout before a minimum evaluation duration", () => {
    const slowSpec = baseSpec({
      steps: [{ profitTargetAmount: 300, minTradingDays: 5 }],
      dailyLoss: null,
      maxLoss: { mode: "static-initial", amount: 1500 },
      funded: {
        profitSplitPct: 80,
        payoutFrequency: "on-demand",
        firstPayoutMinDays: 0,
      },
    });
    const result = simulate(slowSpec, profile, {
      paths: 100, seed: 2, attemptCap: 1,
      fundedHorizonDays: 10, campaignHorizons: [3, 5, 10],
    });
    expect(result.campaign!.horizons[0]!.pPassEval).toBe(0);
    expect(result.campaign!.horizons[0]!.pFirstRequest).toBe(0);
  });
});
