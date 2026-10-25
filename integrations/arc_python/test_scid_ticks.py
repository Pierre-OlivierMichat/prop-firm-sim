"""Synthetic byte fixtures only: never reads local Sierra market history."""
from datetime import datetime, timezone
import csv
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from scid_ticks import HEADER, RECORD, iter_scid

class ScidDecoderTests(unittest.TestCase):
    def test_synthetic_scid_with_microsecond_timestamps(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "synthetic.scid"
            micros = 3_978_979_200_123_456
            f.write_bytes(
                HEADER.pack(b"SCID", 56, 40, 1, 0, 0, bytes(36)) +
                RECORD.pack(micros, 10., 11., 9., 10.5, 1, 4, 3, 1) +
                RECORD.pack(micros + 10, 10., 11., 9., 10.75, 1, 2, 0, 2)
            )
            ticks = list(iter_scid(f))
            self.assertEqual(len(ticks), 2)
            self.assertEqual(ticks[0].volume, 4)
            self.assertEqual(ticks[0].bid_volume, 3)
            self.assertEqual(ticks[1].ask_volume, 2)
            self.assertEqual(ticks[1].timestamp_utc - ticks[0].timestamp_utc,
                             __import__("datetime").timedelta(microseconds=10))
            self.assertEqual(ticks[0].timestamp_utc.tzinfo, timezone.utc)
            self.assertTrue(ticks[0].single_trade_record)

    def test_bad_header_and_truncated_record_refused(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / "bad.scid"
            f.write_bytes(b"bad" * 40)
            with self.assertRaises(ValueError):
                list(iter_scid(f))
            f.write_bytes(HEADER.pack(b"SCID", 56, 40, 1, 0, 0, bytes(36)) + b"\x00" * 3)
            with self.assertRaises(ValueError):
                list(iter_scid(f))

    def test_strategy_plugin_reads_synthetic_ticks(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            f = root / "synthetic.scid"
            f.write_bytes(
                HEADER.pack(b"SCID", 56, 40, 1, 0, 0, bytes(36)) +
                RECORD.pack(3_978_979_200_123_456, 10., 11., 9., 10.5, 1, 4, 3, 1)
            )
            strategy = root / "strat.py"
            strategy.write_text(
                "def generate_trades(ticks):\n"
                "  for t in ticks:\n"
                "    yield {'open time':'2026-01-05 14:00','close time':'2026-01-05 14:01',"
                "'symbol':'NQ','direction':'long','quantity':1,'entry price':10,"
                "'exit price':11,'stop loss':9,'pnl':20,'fees':0,'r':1}\n",
                encoding="utf-8")
            output = root / "trades.csv"
            child = subprocess.run(
                [sys.executable, str(Path(__file__).with_name("run_strategy.py")),
                 "--input-scid", str(f), "--strategy-file", str(strategy),
                 "--output-trades", str(output)],
                capture_output=True, text=True)
            self.assertEqual(child.returncode, 0, child.stderr)
            with output.open(newline="") as h:
                rows = list(csv.DictReader(h))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["r"], "1")

if __name__ == "__main__":
    unittest.main()
