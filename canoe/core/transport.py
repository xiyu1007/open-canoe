"""Transport layer — device discovery and serial/USB CDC abstraction."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import structlog

logger = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class TransportInfo:
    port: str
    transport_type: str
    baudrate: int = 0
    vid: int = 0
    pid: int = 0
    description: str = ""


class TransportError(RuntimeError):
    """Raised when no device is found or connection fails."""


class AbstractTransport(ABC):
    @abstractmethod
    def connect(self) -> None: ...
    @abstractmethod
    def disconnect(self) -> None: ...
    @abstractmethod
    def write(self, data: bytes) -> None: ...
    @abstractmethod
    def read(self, size: int, timeout: float | None = None) -> bytes: ...

    @property
    @abstractmethod
    def is_connected(self) -> bool: ...

    @property
    @abstractmethod
    def info(self) -> TransportInfo: ...


class SerialTransport(AbstractTransport):
    """UART or USB CDC transport via pyserial."""

    def __init__(self, port: str, baudrate: int = 921600) -> None:
        self._port = port
        self._baudrate = baudrate
        self._ser = None

    def connect(self) -> None:
        import serial as _serial

        if self._ser is not None:
            return
        self._ser = _serial.Serial(self._port, self._baudrate, timeout=0.1)

    def disconnect(self) -> None:
        if self._ser is None:
            return
        self._ser.close()
        self._ser = None

    def write(self, data: bytes) -> None:
        if self._ser is None:
            raise TransportError("not connected")
        self._ser.write(data)

    def read(self, size: int, timeout: float | None = None) -> bytes:
        if self._ser is None:
            raise TransportError("not connected")
        if timeout is not None:
            orig = self._ser.timeout
            self._ser.timeout = timeout
            try:
                return self._ser.read(size)
            finally:
                self._ser.timeout = orig
        return self._ser.read(size)

    @property
    def is_connected(self) -> bool:
        return self._ser is not None and self._ser.is_open

    @property
    def info(self) -> TransportInfo:
        return TransportInfo(
            port=self._port,
            transport_type="serial",
            baudrate=self._baudrate,
        )


def list_serial_ports() -> list[TransportInfo]:
    """List all available serial/CDC ports."""
    from serial.tools.list_ports import comports

    results: list[TransportInfo] = []
    for p in comports():
        if p.vid is not None and p.pid is not None:
            results.append(TransportInfo(
                port=p.device,
                transport_type="usb_cdc",
                vid=p.vid,
                pid=p.pid,
                description=p.description or "",
            ))
        else:
            results.append(TransportInfo(
                port=p.device,
                transport_type="serial",
                description=p.description or "",
            ))
    return results


def auto_detect(baudrate: int = 921600) -> AbstractTransport:
    """Auto-detect and return the best available CAN probe transport."""
    ports = list_serial_ports()
    if not ports:
        raise TransportError(
            "No CAN probe detected.\nConnect a device via USB and retry."
        )
    # Prefer USB CDC devices
    for p in ports:
        if p.transport_type == "usb_cdc":
            return SerialTransport(port=p.port, baudrate=baudrate)
    return SerialTransport(port=ports[0].port, baudrate=baudrate)
