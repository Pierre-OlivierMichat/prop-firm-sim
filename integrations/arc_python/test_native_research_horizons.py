"""Deterministic tests for the native research backend wrappers (no market files)."""
import unittest

from native_research_horizons import trading_horizon_calendar_offsets, wilson


class NativeHorizonTests(unittest.TestCase):
    def test_exchange_session_clock_counts_only_market_open_dates(self):
        clock = [
            {"market_open": True, "status": "PRESENT"},
            {"market_open": True, "status": "PRESENT"},
            {"market_open": False, "status": "CLOSED"},
            {"market_open": False, "status": "CLOSED"},
            {"market_open": True, "status": "PRESENT"},
            {"market_open": True, "status": "PRESENT"},
            {"market_open": False, "status": "CLOSED"},
            {"market_open": True, "status": "PRESENT"},
        ]
        self.assertEqual(trading_horizon_calendar_offsets(clock, [1, 2, 3, 4, 5]),
                         {1: 1, 2: 2, 3: 5, 4: 6, 5: 8})

    def test_refuse_missing_sessions_not_silently_calendar_days(self):
        with self.assertRaisesRegex(ValueError, "cannot cover"):
            trading_horizon_calendar_offsets(
                [{"market_open": True, "status": "PRESENT"}], [3])

    def test_wilson_rare_event_uncertainty_and_input_guards(self):
        self.assertEqual(wilson(0, 1000)[0], 0)
        self.assertAlmostEqual(wilson(0, 1000)[1], 0.00382675848555, places=10)
        self.assertEqual(wilson(1000, 1000)[1], 1)
        l, h = wilson(1, 1000)
        self.assertLess(l, 0.001)
        self.assertGreater(h, 0.001)
        for cases in [(-1, 1000), (1001, 1000), (0, 0)]:
            with self.assertRaises(ValueError):
                wilson(*cases)


if __name__ == "__main__":
    unittest.main()
