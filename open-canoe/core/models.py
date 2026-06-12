"""CAN domain data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import deque
import time


@dataclass(frozen=True, slots=True)
class CANMessage:
    arbitration_id: int
    data: bytes
    is_extended: bool = False
    is_error: bool = False
    is_remote: bool = False
    timestamp_us: int = 0
    channel: int = 0

    @property
    def dlc(self) -> int:
        return len(self.data)

    @property
    def id_str(self) -> str:
        w = 8 if self.is_extended else 3
        return f"0x{self.arbitration_id:0{w}X}"

    @property
    def data_str(self) -> str:
        return " ".join(f"{b:02X}" for b in self.data)


@dataclass
class BusStatistics:
    window_s: float = 5.0
    _rx_timestamps: deque[float] = field(default_factory=deque)
    _tx_count: int = 0
    _error_count: int = 0

    def record_rx(self) -> None:
        now = time.monotonic()
        self._rx_timestamps.append(now)
        self._prune(now)

    def record_tx(self) -> None:
        self._tx_count += 1

    def record_error(self) -> None:
        self._error_count += 1

    @property
    def msg_rate(self) -> float:
        now = time.monotonic()
        self._prune(now)
        if not self._rx_timestamps:
            return 0.0
        elapsed = now - self._rx_timestamps[0]
        return len(self._rx_timestamps) / elapsed if elapsed > 0 else 0.0

    @property
    def bus_load_pct(self) -> float:
        return (self.msg_rate * 128) / 500_000 * 100

    @property
    def error_count(self) -> int:
        return self._error_count

    @property
    def tx_count(self) -> int:
        return self._tx_count

    def reset(self) -> None:
        self._rx_timestamps.clear()
        self._tx_count = 0
        self._error_count = 0

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_s
        while self._rx_timestamps and self._rx_timestamps[0] < cutoff:
            self._rx_timestamps.popleft()
