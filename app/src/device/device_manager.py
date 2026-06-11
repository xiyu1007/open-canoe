"""
Device connection manager. Handles serial port lifecycle, frame sending,
async receive loop, and response dispatch.
"""
import time
import threading
import struct
import serial
from ..protocol.frame_codec import FrameCodec
from ..protocol.command_builder import CommandBuilder
from ..protocol.protocol_defs import (
    Command, PROTOCOL_MAGIC_HEADER, PROTOCOL_END_MAGIC,
)


class DeviceManager:
    """Manages connection to Open-Canoe hardware device."""

    def __init__(self):
        self._serial: serial.Serial | None = None
        self._connected = False
        self._port = ""
        self._baudrate = 115200
        self._rx_thread: threading.Thread | None = None
        self._rx_buffer = bytearray()
        self._lock = threading.Lock()
        self._callbacks: dict[int, list] = {}  # cmd -> list of callbacks
        self._general_callback = None  # called for every frame
        self._running = False

        # Device state (populated after connection)
        self.device_info: dict = {}
        self.capabilities: dict = {}
        self.status: dict = {}
        self.mcu_model = "Unknown"
        self.fw_version = "?"

    # ---- Connection ----

    def connect(self, port: str, baudrate: int = 115200) -> bool:
        """Open serial port and start receive thread."""
        if self._connected:
            self.disconnect()
        try:
            self._serial = serial.Serial(
                port=port, baudrate=baudrate,
                bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE, timeout=0.05,
            )
            self._port = port
            self._baudrate = baudrate
            self._connected = True
            self._running = True
            self._rx_buffer.clear()
            self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
            self._rx_thread.start()
            return True
        except serial.SerialException as e:
            self._connected = False
            return False

    def disconnect(self):
        """Close serial port and stop receive thread."""
        self._running = False
        if self._rx_thread and self._rx_thread.is_alive():
            self._rx_thread.join(timeout=1.0)
        self._rx_thread = None
        if self._serial and self._serial.is_open:
            try:
                self._serial.close()
            except Exception:
                pass
        self._serial = None
        self._connected = False
        self._port = ""

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def port(self) -> str:
        return self._port

    @property
    def baudrate(self) -> int:
        return self._baudrate

    # ---- Send ----

    def send_raw(self, frame: bytes) -> bool:
        """Send a raw frame over serial. Thread-safe."""
        if not self._serial or not self._serial.is_open:
            return False
        with self._lock:
            try:
                self._serial.write(frame)
                self._serial.flush()
                return True
            except serial.SerialException:
                return False

    def send_command(self, cmd: int, seq: int, data: bytes = b"") -> bool:
        """Encode and send a command frame."""
        frame = FrameCodec.encode(cmd, seq, data)
        return self.send_raw(frame)

    # ---- Receive ----

    def _rx_loop(self):
        """Background receive thread. Feeds bytes to frame decoder, dispatches results."""
        while self._running:
            if not self._serial or not self._serial.is_open:
                time.sleep(0.1)
                continue
            try:
                waiting = self._serial.in_waiting
                if waiting > 0:
                    raw = self._serial.read(min(waiting, 4096))
                    for result in FrameCodec.feed_and_decode(self._rx_buffer, raw):
                        if result.ok:
                            self._dispatch(result.cmd, result.seq, result.data)
                else:
                    time.sleep(0.005)
            except (serial.SerialException, OSError):
                time.sleep(0.1)

    def _dispatch(self, cmd: int, seq: int, data: bytes):
        """Dispatch a successfully decoded frame."""
        # General callback
        if self._general_callback:
            try:
                self._general_callback(cmd, seq, data)
            except Exception:
                pass
        # Command-specific callbacks
        if cmd in self._callbacks:
            for cb in self._callbacks[cmd]:
                try:
                    cb(cmd, seq, data)
                except Exception:
                    pass

    # ---- Callbacks ----

    def set_general_callback(self, callback):
        """Set callback for ALL received frames: callback(cmd, seq, data)."""
        self._general_callback = callback

    def register_callback(self, cmd: int, callback):
        """Register a callback for a specific command code."""
        if cmd not in self._callbacks:
            self._callbacks[cmd] = []
        self._callbacks[cmd].append(callback)

    def clear_callbacks(self):
        self._callbacks.clear()

    # ---- High-Level Commands ----

    def query_info(self) -> bool:
        return self.send_raw(CommandBuilder.get_info())

    def query_capabilities(self) -> bool:
        return self.send_raw(CommandBuilder.get_capabilities())

    def query_status(self) -> bool:
        return self.send_raw(CommandBuilder.get_status())

    def query_adc_status(self) -> bool:
        return self.send_raw(CommandBuilder.get_adc_status())

    def start_can_listen(self) -> bool:
        return self.send_raw(CommandBuilder.can_start_listen())

    def stop_can_listen(self) -> bool:
        return self.send_raw(CommandBuilder.can_stop_listen())

    def send_can_frame(self, can_id: int, dlc: int, data: bytes,
                       ide: bool = False, rtr: bool = False,
                       channel: int = 0) -> bool:
        return self.send_raw(CommandBuilder.can_send_frame(
            can_id, dlc, data, ide=ide, rtr=rtr, channel=channel))

    def set_can_mode(self, mode: int, channel: int = 0) -> bool:
        return self.send_raw(CommandBuilder.can_set_mode(mode, channel))

    def set_can_baudrate(self, baudrate: int, channel: int = 0) -> bool:
        return self.send_raw(CommandBuilder.can_set_baudrate(baudrate, channel))

    def start_adc(self) -> bool:
        return self.send_raw(CommandBuilder.adc_start_sample())

    def stop_adc(self) -> bool:
        return self.send_raw(CommandBuilder.adc_stop_sample())

    def reset_device(self) -> bool:
        return self.send_raw(CommandBuilder.system_reset())


class MockDeviceManager(DeviceManager):
    """DeviceManager backed by MockHardware instead of a real serial port."""

    def __init__(self, mock_hw):
        super().__init__()
        self._mock = mock_hw
        self._mock.set_device_manager(self)
        self._running = True
        self._rx_buffer = bytearray()
        self._rx_thread = threading.Thread(target=self._mock_rx_loop, daemon=True)
        self._rx_thread.start()

    def connect(self, port: str = "", baudrate: int = 115200) -> bool:
        self._connected = True
        self._port = port or "MOCK"
        self._baudrate = baudrate
        if not self._rx_thread or not self._rx_thread.is_alive():
            self._running = True
            self._rx_thread = threading.Thread(target=self._mock_rx_loop, daemon=True)
            self._rx_thread.start()
        self._mock.start()
        return True

    def disconnect(self):
        self._running = False
        if self._rx_thread and self._rx_thread.is_alive():
            self._rx_thread.join(timeout=1.0)
        self._mock.stop()
        self._connected = False

    def send_raw(self, frame: bytes) -> bool:
        if not self._connected:
            return False
        self._mock.feed_frame(frame)
        return True

    def _mock_rx_loop(self):
        while self._running:
            frame = self._mock.get_response_frame(timeout=0.05)
            if frame:
                for result in FrameCodec.feed_and_decode(self._rx_buffer, frame):
                    if result.ok:
                        self._dispatch(result.cmd, result.seq, result.data)
            else:
                time.sleep(0.01)
