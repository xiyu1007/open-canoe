"""Transport layer — device discovery, serial/USB CDC abstraction, frame I/O."""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from queue import Queue, Empty

from core.protocol import (
    Frame,
    Command,
    decode,
    encode,
    unpack_heartbeat,
    unpack_device_info,
    MAGIC_HEADER,
    END_MAGIC,
)


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


# ── Frame Receiver ───────────────────────────────────────────────────


class FrameReceiver:
    """Buffers raw bytes and extracts complete protocol frames.

    Handles partial frames (waiting for more data) and multiple frames
    arriving in the same read chunk.
    """

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[Frame]:
        """Feed raw bytes, return list of complete frames decoded."""
        self._buf.extend(data)
        frames = decode(bytes(self._buf))

        # Trim consumed bytes: find where the last decoded frame ended
        if frames:
            # Reconstruct the buffer position after last frame
            consumed = 0
            for f in frames:
                payload_len = len(f.payload)
                total = 9 + payload_len  # header(6) + payload + footer(3)
                consumed += total
            self._buf = self._buf[consumed:]
        else:
            # Keep only what might be a partial frame at the end
            # Find last magic header position
            for i in range(len(self._buf) - 1, -1, -1):
                if self._buf[i] == MAGIC_HEADER:
                    self._buf = self._buf[i:]
                    break
            else:
                # Look for possible end magic
                for i in range(len(self._buf)):
                    if self._buf[i] == END_MAGIC and i >= 8:
                        self._buf = self._buf[i + 1 :]
                        break

        return frames

    def reset(self) -> None:
        self._buf.clear()


# ── Abstract Transport ───────────────────────────────────────────────


class AbstractTransport(ABC):
    @abstractmethod
    def connect(self) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def write(self, data: bytes) -> None: ...

    @abstractmethod
    def incoming(self) -> list[Frame]: ...

    @property
    @abstractmethod
    def is_connected(self) -> bool: ...

    @property
    @abstractmethod
    def info(self) -> TransportInfo: ...


# ── Serial Transport ─────────────────────────────────────────────────


class SerialTransport(AbstractTransport):
    """UART or USB CDC transport via pyserial with background frame reader."""

    def __init__(self, port: str, baudrate: int = 115200) -> None:
        self._port = port
        self._baudrate = baudrate
        self._ser = None
        self._rx_thread: threading.Thread | None = None
        self._running = False
        self._receiver = FrameReceiver()
        self._frame_queue: Queue = Queue()

    def connect(self) -> None:
        import serial as _serial

        if self._ser is not None:
            return
        self._ser = _serial.Serial(self._port, self._baudrate, timeout=0.05)
        self._running = True
        self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
        self._rx_thread.start()

    def disconnect(self) -> None:
        self._running = False
        if self._rx_thread and self._rx_thread.is_alive():
            self._rx_thread.join(timeout=1.0)
        self._rx_thread = None
        if self._ser is not None:
            try:
                self._ser.close()
            except Exception:
                pass
            self._ser = None
        self._receiver.reset()
        # Drain queue
        while not self._frame_queue.empty():
            try:
                self._frame_queue.get_nowait()
            except Empty:
                break

    def write(self, data: bytes) -> None:
        if self._ser is None:
            raise TransportError("not connected")
        self._ser.write(data)

    def incoming(self) -> list[Frame]:
        """Non-blocking: return all queued incoming frames."""
        frames: list[Frame] = []
        while True:
            try:
                frames.append(self._frame_queue.get_nowait())
            except Empty:
                break
        return frames

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

    def _rx_loop(self) -> None:
        """Background thread: read serial bytes, decode frames, queue them."""
        while self._running:
            try:
                if self._ser is None or not self._ser.is_open:
                    time.sleep(0.05)
                    continue
                waiting = self._ser.in_waiting
                if waiting > 0:
                    data = self._ser.read(min(waiting, 1024))
                    if data:
                        frames = self._receiver.feed(data)
                        for f in frames:
                            self._frame_queue.put(f)
                else:
                    time.sleep(0.005)
            except Exception:
                time.sleep(0.1)


# ── Serial Port Listing ──────────────────────────────────────────────


def list_serial_ports() -> list[TransportInfo]:
    """List all available serial/CDC ports."""
    from serial.tools.list_ports import comports

    results: list[TransportInfo] = []
    for p in comports():
        if p.vid is not None and p.pid is not None:
            results.append(
                TransportInfo(
                    port=p.device,
                    transport_type="usb_cdc",
                    vid=p.vid,
                    pid=p.pid,
                    description=p.description or "",
                )
            )
        else:
            results.append(
                TransportInfo(
                    port=p.device,
                    transport_type="serial",
                    description=p.description or "",
                )
            )
    return results


# ── Auto-Detect ──────────────────────────────────────────────────────


def _try_heartbeat(port: str, baudrate: int, timeout: float = 0.8) -> dict | None:
    """Quick single-port probe. Returns device info dict or None."""
    tr = SerialTransport(port=port, baudrate=baudrate)
    try:
        tr.connect()
    except Exception:
        return None
    deadline = time.monotonic() + timeout
    hb = None
    sent_getinfo = False
    while time.monotonic() < deadline:
        frames = tr.incoming()
        for f in frames:
            if f.command == Command.DEVICE_HEARTBEAT:
                try:
                    hb = unpack_heartbeat(f.payload)
                except Exception:
                    pass
                break
            elif f.command == Command.INFO_RESPONSE:
                try:
                    info = unpack_device_info(f.payload)
                    hb = {"mcu_model": info.get("mcu_model", "?"),
                          "fw_version": info.get("fw_version", "?"),
                          "comm_interface": "USART"}
                except Exception:
                    pass
                break
        if hb:
            break
        if not sent_getinfo and time.monotonic() > deadline - 0.5:
            try:
                tr.write(encode(Command.GET_INFO))
                sent_getinfo = True
            except Exception:
                break
        time.sleep(0.02)
    tr.disconnect()
    if hb:
        hb["port"] = port
        hb["baudrate"] = baudrate
    return hb


def auto_detect(baudrates: list[int] | None = None) -> tuple[AbstractTransport, dict]:
    """Auto-detect CAN probe by scanning ports.

    Opens each port, tries heartbeat then GET_INFO. Returns a CONNECTED
    transport + device info dict. Raises TransportError if no device found.
    """
    if baudrates is None:
        baudrates = [115200, 921600]

    ports = list_serial_ports()
    if not ports:
        raise TransportError(
            "No serial ports found.\nConnect a CAN probe via USB and retry."
        )

    # Prefer USB CDC devices, skip Bluetooth virtual ports
    cdc_ports = [p for p in ports if p.transport_type == "usb_cdc"]
    other_ports = [p for p in ports if p.transport_type != "usb_cdc"
                   and "bluetooth" not in p.description.lower()
                   and "蓝牙" not in p.description]
    ordered = cdc_ports + other_ports

    for p in ordered:
        for br in baudrates:
            tr = SerialTransport(port=p.port, baudrate=br)
            try:
                tr.connect()
            except Exception:
                continue
            time.sleep(0.3)

            # Wait for heartbeat or probe with GET_INFO
            hb = None
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                frames = tr.incoming()
                for f in frames:
                    if f.command == Command.DEVICE_HEARTBEAT:
                        try:
                            hb = unpack_heartbeat(f.payload)
                        except Exception:
                            pass
                        break
                    elif f.command == Command.INFO_RESPONSE:
                        try:
                            info = unpack_device_info(f.payload)
                            hb = {
                                "mcu_model": info.get("mcu_model", "Unknown"),
                                "fw_version": info.get("fw_version", "?"),
                                "comm_interface": "USART",
                            }
                        except Exception:
                            pass
                        break
                if hb:
                    break
                # If no passive response, actively probe with GET_INFO
                if time.monotonic() > deadline - 1.5 and hb is None:
                    try:
                        tr.write(encode(Command.GET_INFO))
                    except Exception:
                        break
                time.sleep(0.05)

            if hb is not None:
                return tr, hb
            tr.disconnect()

    raise TransportError(
        "No CAN probe detected.\n"
        "Connect a device via USB and retry.\n\n"
        f"Scanned {len(ordered)} port(s) at {len(baudrates)} baudrate(s)."
    )


def detect_and_connect(
    port: str | None = None,
    baudrate: int = 115200,
) -> tuple[AbstractTransport, dict]:
    """Connect to a device and verify presence. Returns (transport, device_info).

    If port is None or 'auto', auto-detects. Otherwise uses the specified port.
    """
    if port and port != "auto":
        tr = SerialTransport(port=port, baudrate=baudrate)
        try:
            tr.connect()
        except Exception as e:
            raise TransportError(f"Could not open {port}: {e}")
        time.sleep(0.3)
    else:
        return auto_detect(baudrates=[baudrate, 921600])

    # Wait for heartbeat or probe with GET_INFO
    hb = None
    deadline = time.monotonic() + 3.0
    sent_getinfo = False
    while time.monotonic() < deadline:
        frames = tr.incoming()
        for f in frames:
            if f.command == Command.DEVICE_HEARTBEAT:
                try:
                    hb = unpack_heartbeat(f.payload)
                except Exception:
                    pass
                break
            elif f.command == Command.INFO_RESPONSE:
                try:
                    info = unpack_device_info(f.payload)
                    hb = {
                        "mcu_model": info.get("mcu_model", "Unknown"),
                        "fw_version": info.get("fw_version", "?"),
                        "comm_interface": "USART",
                    }
                except Exception:
                    pass
                break
        if hb:
            break
        # Active probe after 1s of no heartbeat
        if not sent_getinfo and time.monotonic() > deadline - 2.0:
            try:
                tr.write(encode(Command.GET_INFO))
                sent_getinfo = True
            except Exception:
                break
        time.sleep(0.05)

    if hb is None:
        tr.disconnect()
        raise TransportError(
            "No response from device.\n"
            "Verify the CAN probe is connected and firmware is flashed.\n"
            f"Port: {tr.info.port}  Baudrate: {tr.info.baudrate}"
        )

    return tr, hb
