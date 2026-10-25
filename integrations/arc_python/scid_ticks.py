"""Read-only streaming Sierra Intraday SCID record decoder for a Python strategy.

Based on the published 56-byte header and 40-byte record layout.
Times are UTC microseconds since 1899-12-30. Reading a file says nothing
about that file's eligibility, source ownership, tick completeness or roll map.
The caller must resolve those questions before opening a real market file.

This module does not make trades or fabricate a bid/ask book: OHLC fields
may carry special Sierra meanings in tick-by-tick/BidAsk modes.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import struct
from typing import Iterator

HEADER = struct.Struct("<4sIIHHI36s")
RECORD = struct.Struct("<q4f4I")
EPOCH = datetime(1899, 12, 30, tzinfo=timezone.utc)


@dataclass(frozen=True)
class ScidRecord:
    timestamp_utc: datetime
    open: float
    high: float
    low: float
    last: float
    number_of_trades: int
    volume: int
    bid_volume: int
    ask_volume: int

    @property
    def single_trade_record(self) -> bool:
        return self.number_of_trades == 1


def iter_scid(path: Path | str) -> Iterator[ScidRecord]:
    """Stream records without materializing multi-GB source files."""
    with Path(path).open("rb") as handle:
        raw_header = handle.read(HEADER.size)
        if len(raw_header) != HEADER.size:
            raise ValueError("Truncated SCID header")
        magic, header_size, record_size, _version, _unused, _utc_index, _ = HEADER.unpack(raw_header)
        if magic != b"SCID" or header_size != HEADER.size or record_size != RECORD.size:
            raise ValueError("Unsupported SCID file or record layout")
        previous_us = None
        while True:
            raw = handle.read(RECORD.size)
            if not raw:
                return
            if len(raw) != RECORD.size:
                raise ValueError("Partial trailing SCID record")
            t, op, high, low, last, n, vol, bid, ask = RECORD.unpack(raw)
            if t < 0 or (previous_us is not None and t < previous_us):
                raise ValueError("Invalid or nonmonotonic SCID timestamp")
            previous_us = t
            yield ScidRecord(EPOCH + timedelta(microseconds=t), op, high, low, last, n, vol, bid, ask)
