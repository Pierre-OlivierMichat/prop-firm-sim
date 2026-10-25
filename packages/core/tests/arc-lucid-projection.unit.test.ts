import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { join, dirname } from "node:path";
import { ChallengeSpecSchema, simulate, type TraderProfileInput } from "../src/index.js";
import { baseSpec } from "./helpers.js";

const folder = fileURLToPath(new URL("../../../integrations/arc_python/lucid_specs_20261023_v1/", import.meta.url));
const manifest = JSON.parse(readFileSync(join(folder, "manifest.json"), "utf8")) as {
  count: number; status: string;
  accounts: { product_id: string; output: string; programme: string; size_k: number }[];
};
const alwaysWins: TraderProfileInput = {
  kind: "bootstrap",
  rSeries: Array(12).fill(1),
  blockMeanLength: 1,
  tradesPerDay: 1,
  risk: { mode: "fixed-amount", value: 100 },
};

describe("ARC source-bound Lucid account projections", () => {
  it("validates all 28 generated size/option configurations against LuxAlgo's actual spec schema", () => {
    expect(manifest.status).toBe("PROJECTION_ONLY_NOT_RULE_PARITY_CERTIFIED");
    expect(manifest.count).toBe(28);
    const ids = new Set<string>();
    for (const entry of manifest.accounts) {
      const source = JSON.parse(readFileSync(join(folder, entry.output), "utf8"));
      const parsed = ChallengeSpecSchema.parse(source);
      expect(parsed.challengeId).toBe(entry.product_id);
      expect(parsed.accountSize).toBe(entry.size_k * 1000);
      expect(parsed.funded.payoutRules?.minPayoutAmount).toBe(500);
      expect(parsed.funded.profitSplitPct).toBe(90);
      expect(parsed.flagsNotSimulated.length).toBeGreaterThan(0);
      expect(parsed.dailyLoss).toBe(null); // Never transform a SOFT stop into a hard breach.
      expect(ids.has(parsed.challengeId)).toBe(false);
      ids.add(parsed.challengeId);
    }
    expect(ids.size).toBe(28);
  });

  it("cannot count a first request below the minimum payout amount", () => {
    const spec = baseSpec({
      accountSize: 25000,
      steps: [{ profitTargetAmount: 100, minTradingDays: 1 }],
      maxLoss: { mode: "static-initial", amount: 1000 },
      dailyLoss: null,
      funded: {
        profitSplitPct: 90,
        payoutFrequency: "on-demand",
        firstPayoutMinDays: 0,
        payoutRules: { bufferAmount: 0, minPayoutAmount: 500 },
      },
    });
    const x = simulate(spec, alwaysWins, {
      paths: 100, seed: 5, attemptCap: 1,
      campaignHorizons: [3, 5, 6, 10], fundedHorizonDays: 10,
    });
    expect(x.campaign!.horizons.map((h) => [h.days, h.pPassEval, h.pFirstRequest]))
      .toEqual([[3, 1, 0], [5, 1, 0], [6, 1, 1], [10, 1, 1]]);
  });

  it("cannot count first request before funded cycle minimum is reached", () => {
    const spec = baseSpec({
      accountSize: 25000,
      steps: [{ profitTargetAmount: 100, minTradingDays: 1 }],
      maxLoss: { mode: "static-initial", amount: 1000 },
      dailyLoss: null,
      funded: {
        profitSplitPct: 90,
        payoutFrequency: "on-demand",
        firstPayoutMinDays: 0,
        payoutRules: { bufferAmount: 0, minPayoutAmount: 500, minCycleProfitAmount: 700 },
      },
    });
    const x = simulate(spec, alwaysWins, {
      paths: 100, seed: 5, attemptCap: 1,
      campaignHorizons: [6, 7, 8], fundedHorizonDays: 10,
    });
    expect(x.campaign!.horizons.map((h) => [h.days, h.pFirstRequest]))
      .toEqual([[6, 0], [7, 0], [8, 1]]);
  });
});
