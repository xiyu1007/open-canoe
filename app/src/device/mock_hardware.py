"""
Mock hardware simulator for testing without real STM32 hardware.
Simulates F103 and F407 behavior, supports loopback mode,
waveform data generation, and flash simulation.
"""
import time
import struct
import math
import random
import threading
from collections import deque
from ..protocol.frame_codec import FrameCodec, crc16
from ..protocol.protocol_defs import (
    Command, CANMode, CommInterface,
    CAN_ERR_CRC, CAN_ERR_BIT_STUFFING, CAN_ERR_BUS_OFF,
    PROTOCOL_MAGIC_HEADER, PROTOCOL_END_MAGIC,
)


class MockHardware:
    """Simulates an STM32 Open-Canoe device."""

    def __init__(self, mcu_model: str = "STM32F103C8T6"):
        self._mcu_model = mcu_model
        self._fw_major = 1
        self._fw_minor = 0
        self._fw_patch = 0
        self._serial_no = random.randint(0x10000000, 0xFFFFFFFF)
        self._start_time = time.time()
        self._running = False

        # CAN state
        self._can_listening = False
        self._can_mode = CANMode.NORMAL
        self._can_baudrate = 500000
        self._can_loopback = False
        self._can_error_state = 0  # bitmask
        self._tx_count = 0
        self._rx_count = 0
        self._error_count = 0

        # ADC state
        self._adc_sampling = False
        self._adc_sample_rate = 100000
        self._adc_resolution = 12
        self._adc_channel = 0
        self._adc_phase = 0.0

        # Comm
        self._comm_interface = CommInterface.USART

        # Response queue (thread-safe)
        self._response_queue: deque = deque()
        self._queue_lock = threading.Lock()

        # Device-specific configs
        if "F103" in mcu_model:
            self._has_adc = True
            self._has_usb_cdc = False
            self._can_channels = 1
            self._max_adc_rate = 1000000
            self._max_can_baud = 1000
        else:  # F407
            self._has_adc = True
            self._has_usb_cdc = True
            self._can_channels = 2
            self._max_adc_rate = 2700000
            self._max_can_baud = 1000

        # Periodic tasks
        self._wave_thread: threading.Thread | None = None

    # ---- Lifecycle ----

    def start(self):
        self._running = True
        self._start_time = time.time()
        self._send_heartbeat()

    def stop(self):
        self._running = False
        if self._wave_thread and self._wave_thread.is_alive():
            self._wave_thread.join(timeout=1.0)

    def set_device_manager(self, dm):
        """Weak ref to MockDeviceManager for ADC data push."""
        self._dm = dm

    # ---- Frame Feed ----

    def feed_frame(self, raw: bytes):
        """Process an incoming frame and push response(s) to queue."""
        # Parse header
        if len(raw) < 6:
            return
        cmd = raw[3]
        seq = struct.unpack_from("<H", raw, 4)[0]
        data_len = len(raw) - 9  # total - header(6) - footer(3)
        data = raw[6:6 + data_len] if data_len > 0 else b""

        if cmd in _COMMAND_HANDLERS:
            resp_cmd, resp_data = _COMMAND_HANDLERS[cmd](self, data, seq)
            if resp_cmd is not None:
                self._enqueue_response(resp_cmd, seq, resp_data)
        else:
            self._enqueue_response(Command.NACK, seq,
                                   struct.pack("<B B", cmd, 0x01))  # INVALID_CMD

    def get_response_frame(self, timeout: float = 0.0) -> bytes | None:
        """Get the next response frame from the queue (non-blocking or with timeout)."""
        deadline = time.time() + timeout
        while True:
            with self._queue_lock:
                if self._response_queue:
                    return self._response_queue.popleft()
            if time.time() >= deadline:
                return None
            time.sleep(0.001)

    def _enqueue_response(self, cmd: int, seq: int, payload: bytes = b""):
        """Enqueue a response frame."""
        frame = FrameCodec.encode(cmd, seq, payload)
        with self._queue_lock:
            self._response_queue.append(frame)

    # ---- Heartbeat ----

    def _send_heartbeat(self):
        model_bytes = self._mcu_model.encode('ascii').ljust(32, b'\x00')
        payload = struct.pack("<32s B B B B", model_bytes,
                              self._fw_major, self._fw_minor,
                              self._fw_patch, self._comm_interface)
        self._enqueue_response(Command.DEVICE_HEARTBEAT, 0, payload)

    # ---- CAN Loopback ----

    def _handle_loopback(self, data: bytes):
        """If in loopback mode, echo the CAN frame back as MSG_CAN_FRAME_UP.
        Incoming payload is can_send_frame_t: can_id(4)+dlc(1)+flags(1)+channel(1)+data[8]=15 bytes
        Outgoing payload is can_frame_up_t: timestamp(4)+can_id(4)+dlc(1)+flags(1)+data[8]+channel(1)=19 bytes
        """
        if self._can_loopback and self._can_listening:
            if len(data) >= 15:
                can_id, dlc, flags, channel = struct.unpack_from("<I B B B", data, 0)
                can_data = data[7:15]
                ts = int((time.time() - self._start_time) * 1_000_000) & 0xFFFFFFFF
                payload = struct.pack("<I I B B 8s B",
                                     ts, can_id, dlc, flags, can_data, channel)
                self._rx_count += 1
                self._enqueue_response(Command.CAN_FRAME_UP, 0, payload)

    # ---- ADC Waveform ----

    def _generate_waveform_data(self, count: int = 64) -> bytes:
        """Generate simulated ADC waveform samples."""
        ts = int((time.time() - self._start_time) * 1_000_000) & 0xFFFFFFFF
        samples = []
        for i in range(count):
            self._adc_phase += 0.05
            # Composite: sine + noise + sawtooth
            val = (math.sin(self._adc_phase) * 1500 +
                   math.sin(self._adc_phase * 7.3) * 300 +
                   ((self._adc_phase * 200) % 800) +
                   random.gauss(0, 30) +
                   2048)
            val = max(0, min(4095, int(val)))
            samples.append(val)
        # Build ADC_DATA_UP: timestamp(4) + sample_rate(4) + sample_count(2) +
        #                   resolution(2) + channel(1) + mode(1) + samples[](2*N)
        header = struct.pack("<I I H H B B", ts, self._adc_sample_rate,
                             count, self._adc_resolution, self._adc_channel, 0)
        samples_bytes = b"".join(struct.pack("<H", s) for s in samples)
        return header + samples_bytes

    def _start_waveform(self):
        if not self._wave_thread or not self._wave_thread.is_alive():
            self._wave_thread = threading.Thread(
                target=self._wave_loop, daemon=True)
            self._wave_thread.start()

    def _wave_loop(self):
        """Generate ADC data packets at ~30fps."""
        while self._running and self._adc_sampling:
            payload = self._generate_waveform_data(64)
            self._enqueue_response(Command.ADC_DATA_UP, 0, payload)
            time.sleep(0.033)  # ~30fps

    # ---- Flash Simulation ----

    def simulate_flash(self, progress_callback=None) -> bool:
        """Simulate firmware flash with progress. Takes ~3 seconds."""
        stages = [
            (0.0, 0.5, "Erasing flash..."),
            (0.5, 1.5, "Writing firmware..."),
            (1.5, 2.5, "Verifying..."),
            (2.5, 3.0, "Resetting..."),
        ]
        for (start_t, end_t, msg) in stages:
            while time.time() - self._start_time_for_flash < end_t:
                elapsed = time.time() - self._start_time_for_flash
                pct = int((elapsed / 3.0) * 100)
                if progress_callback:
                    progress_callback(pct, msg)
                time.sleep(0.05)
        self._serial_no = random.randint(0x10000000, 0xFFFFFFFF)
        return True


# ---- Command Handlers ----

def _cmd_get_info(hw: MockHardware, data: bytes, seq: int):
    model_bytes = hw._mcu_model.encode('ascii').ljust(32, b'\x00')
    desc = f"Open-Canoe {hw._mcu_model}".encode('ascii').ljust(32, b'\x00')
    proto_ver = (1 << 8) | 0
    payload = struct.pack("<B B B B H 32s 32s I",
                          hw._fw_major, hw._fw_minor, hw._fw_patch, 0,
                          proto_ver, model_bytes, desc, hw._serial_no)
    return (Command.INFO_RESPONSE, payload)


def _cmd_get_capabilities(hw: MockHardware, data: bytes, seq: int):
    bits = 0
    if hw._has_adc:
        bits |= 1  # CAP_ADC
    if hw._has_usb_cdc:
        bits |= 2  # CAP_USB_CDC
    if hw._can_channels >= 2:
        bits |= 4  # CAP_MULTI_CAN
    bits |= 8  # CAP_TIMESTAMP_US
    payload = struct.pack("<I B I B H",
                          bits, hw._can_channels,
                          hw._max_adc_rate if hw._has_adc else 0,
                          hw._adc_resolution if hw._has_adc else 0,
                          hw._max_can_baud)
    return (Command.CAPABILITIES_RESPONSE, payload)


def _cmd_get_status(hw: MockHardware, data: bytes, seq: int):
    can_active_map = 1 if hw._can_listening else 0
    uptime = int((time.time() - hw._start_time) * 1000) & 0xFFFFFFFF
    payload = struct.pack("<B B B B I",
                          1 if hw._can_listening else 0,
                          1 if hw._adc_sampling else 0,
                          hw._comm_interface,
                          can_active_map,
                          uptime)
    return (Command.STATUS_RESPONSE, payload)


def _cmd_get_adc_status(hw: MockHardware, data: bytes, seq: int):
    payload = struct.pack("<B B I B",
                          1 if hw._has_adc else 0,
                          1 if hw._adc_sampling else 0,
                          hw._adc_sample_rate if hw._adc_sampling else 0,
                          hw._adc_resolution)
    return (Command.ADC_STATUS_RESP, payload)


def _cmd_can_set_baudrate(hw: MockHardware, data: bytes, seq: int):
    if len(data) >= 5:
        baudrate, _ = struct.unpack_from("<I B", data, 0)
        hw._can_baudrate = baudrate
    return (Command.ACK, struct.pack("<B B", Command.CAN_SET_BAUDRATE, 0))


def _cmd_can_set_mode(hw: MockHardware, data: bytes, seq: int):
    if len(data) >= 2:
        _, mode = struct.unpack_from("<B B", data, 0)
        hw._can_mode = mode
        hw._can_loopback = mode in (CANMode.LOOPBACK, CANMode.LOOPBACK_SILENT)
    return (Command.ACK, struct.pack("<B B", Command.CAN_SET_MODE, 0))


def _cmd_can_set_filter(hw: MockHardware, data: bytes, seq: int):
    return (Command.ACK, struct.pack("<B B", Command.CAN_SET_FILTER, 0))


def _cmd_adc_set_sampling(hw: MockHardware, data: bytes, seq: int):
    if len(data) >= 6:
        rate, res, ch = struct.unpack_from("<I B B", data, 0)
        hw._adc_sample_rate = rate
        hw._adc_resolution = res
        hw._adc_channel = ch
    return (Command.ACK, struct.pack("<B B", Command.ADC_SET_SAMPLING, 0))


def _cmd_comm_set_interface(hw: MockHardware, data: bytes, seq: int):
    if len(data) >= 1:
        iface = data[0]
        if iface == CommInterface.USB_CDC and not hw._has_usb_cdc:
            return (Command.NACK, struct.pack("<B B", Command.COMM_SET_INTERFACE, 0x02))
        hw._comm_interface = iface
    return (Command.ACK, struct.pack("<B B", Command.COMM_SET_INTERFACE, 0))


def _cmd_can_start_listen(hw: MockHardware, data: bytes, seq: int):
    hw._can_listening = True
    return (Command.ACK, struct.pack("<B B", Command.CAN_START_LISTEN, 0))


def _cmd_can_stop_listen(hw: MockHardware, data: bytes, seq: int):
    hw._can_listening = False
    return (Command.ACK, struct.pack("<B B", Command.CAN_STOP_LISTEN, 0))


def _cmd_adc_start_sample(hw: MockHardware, data: bytes, seq: int):
    if not hw._has_adc:
        return (Command.NACK, struct.pack("<B B", Command.ADC_START_SAMPLE, 0x20))
    hw._adc_sampling = True
    hw._start_waveform()
    return (Command.ACK, struct.pack("<B B", Command.ADC_START_SAMPLE, 0))


def _cmd_adc_stop_sample(hw: MockHardware, data: bytes, seq: int):
    hw._adc_sampling = False
    return (Command.ACK, struct.pack("<B B", Command.ADC_STOP_SAMPLE, 0))


def _cmd_can_send_frame(hw: MockHardware, data: bytes, seq: int):
    hw._tx_count += 1
    # If loopback mode, echo back
    hw._handle_loopback(data)
    return (Command.ACK, struct.pack("<B B", Command.CAN_SEND_FRAME, 0))


def _cmd_system_reset(hw: MockHardware, data: bytes, seq: int):
    hw._can_listening = False
    hw._adc_sampling = False
    hw._start_time = time.time()
    # Re-send heartbeat to simulate post-reset identification
    hw._send_heartbeat()
    return (Command.ACK, struct.pack("<B B", Command.SYSTEM_RESET, 0))


_COMMAND_HANDLERS = {
    Command.GET_INFO: _cmd_get_info,
    Command.GET_CAPABILITIES: _cmd_get_capabilities,
    Command.GET_STATUS: _cmd_get_status,
    Command.GET_ADC_STATUS: _cmd_get_adc_status,
    Command.CAN_SET_BAUDRATE: _cmd_can_set_baudrate,
    Command.CAN_SET_MODE: _cmd_can_set_mode,
    Command.CAN_SET_FILTER: _cmd_can_set_filter,
    Command.ADC_SET_SAMPLING: _cmd_adc_set_sampling,
    Command.COMM_SET_INTERFACE: _cmd_comm_set_interface,
    Command.CAN_START_LISTEN: _cmd_can_start_listen,
    Command.CAN_STOP_LISTEN: _cmd_can_stop_listen,
    Command.ADC_START_SAMPLE: _cmd_adc_start_sample,
    Command.ADC_STOP_SAMPLE: _cmd_adc_stop_sample,
    Command.CAN_SEND_FRAME: _cmd_can_send_frame,
    Command.SYSTEM_RESET: _cmd_system_reset,
}
