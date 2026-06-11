"""
Build protocol command frames. Each method returns bytes ready to send.
"""
import struct
from .protocol_defs import (
    Command, CANMode, CommInterface, CANFilterMode, CANFilterScale,
    PROTOCOL_MAGIC_HEADER, PROTOCOL_END_MAGIC, PROTOCOL_FRAME_OVERHEAD,
)
from .frame_codec import FrameCodec


class CommandBuilder:
    """Builds and parses protocol frames."""

    _seq = 0

    @classmethod
    def _next_seq(cls) -> int:
        cls._seq = (cls._seq + 1) & 0xFFFF
        return cls._seq

    # ---- Info Query ----

    @classmethod
    def get_info(cls) -> bytes:
        return FrameCodec.encode(Command.GET_INFO, cls._next_seq())

    @classmethod
    def get_capabilities(cls) -> bytes:
        return FrameCodec.encode(Command.GET_CAPABILITIES, cls._next_seq())

    @classmethod
    def get_status(cls) -> bytes:
        return FrameCodec.encode(Command.GET_STATUS, cls._next_seq())

    @classmethod
    def get_adc_status(cls) -> bytes:
        return FrameCodec.encode(Command.GET_ADC_STATUS, cls._next_seq())

    # ---- Parameter Config ----

    @classmethod
    def can_set_baudrate(cls, baudrate: int, channel: int = 0) -> bytes:
        data = struct.pack("<I B", baudrate, channel)
        return FrameCodec.encode(Command.CAN_SET_BAUDRATE, cls._next_seq(), data)

    @classmethod
    def can_set_mode(cls, mode: int, channel: int = 0) -> bytes:
        data = struct.pack("<B B", channel, mode)
        return FrameCodec.encode(Command.CAN_SET_MODE, cls._next_seq(), data)

    @classmethod
    def can_set_filter(cls, channel: int = 0, filter_index: int = 0,
                       filter_mode: int = CANFilterMode.ID_MASK,
                       filter_scale: int = CANFilterScale.S_32BIT,
                       id_high: int = 0, id_low: int = 0,
                       mask_high: int = 0xFFFFFFFF, mask_low: int = 0xFFFFFFFF) -> bytes:
        data = struct.pack("<B B B B I I I I",
                           channel, filter_index, filter_mode, filter_scale,
                           id_high, id_low, mask_high, mask_low)
        return FrameCodec.encode(Command.CAN_SET_FILTER, cls._next_seq(), data)

    @classmethod
    def adc_set_sampling(cls, sample_rate: int, resolution: int = 12,
                         channel: int = 0) -> bytes:
        data = struct.pack("<I B B", sample_rate, resolution, channel)
        return FrameCodec.encode(Command.ADC_SET_SAMPLING, cls._next_seq(), data)

    @classmethod
    def comm_set_interface(cls, interface: int) -> bytes:
        data = struct.pack("<B", interface)
        return FrameCodec.encode(Command.COMM_SET_INTERFACE, cls._next_seq(), data)

    # ---- Control ----

    @classmethod
    def can_start_listen(cls) -> bytes:
        return FrameCodec.encode(Command.CAN_START_LISTEN, cls._next_seq())

    @classmethod
    def can_stop_listen(cls) -> bytes:
        return FrameCodec.encode(Command.CAN_STOP_LISTEN, cls._next_seq())

    @classmethod
    def adc_start_sample(cls) -> bytes:
        return FrameCodec.encode(Command.ADC_START_SAMPLE, cls._next_seq())

    @classmethod
    def adc_stop_sample(cls) -> bytes:
        return FrameCodec.encode(Command.ADC_STOP_SAMPLE, cls._next_seq())

    @classmethod
    def can_send_frame(cls, can_id: int, dlc: int, data: bytes,
                       ide: bool = False, rtr: bool = False,
                       channel: int = 0) -> bytes:
        flags = 0
        if ide:
            flags |= 1  # bit0: IDE
        if rtr:
            flags |= 2  # bit1: RTR
        # can_send_frame_t: can_id(4) + dlc(1) + flags(1) + channel(1) + data[8] = 15 bytes
        payload = struct.pack("<I B B B 8s", can_id, dlc, flags, channel,
                              data.ljust(8, b'\x00')[:8])
        return FrameCodec.encode(Command.CAN_SEND_FRAME, cls._next_seq(), payload)

    @classmethod
    def system_reset(cls) -> bytes:
        return FrameCodec.encode(Command.SYSTEM_RESET, cls._next_seq())

    # ---- Response Parsers ----

    @classmethod
    def parse_device_info(cls, data: bytes) -> dict:
        """Parse MSG_INFO_RESPONSE payload into dict."""
        if len(data) < 72:
            return {}
        fw_major, fw_minor, fw_patch, _reserved = struct.unpack_from("<B B B B", data, 0)
        proto_ver = struct.unpack_from("<H", data, 4)[0]
        mcu_model = data[6:38].split(b'\x00')[0].decode('ascii', errors='replace')
        fw_desc = data[38:70].split(b'\x00')[0].decode('ascii', errors='replace')
        serial = struct.unpack_from("<I", data, 70)[0]
        return {
            "fw_version": f"{fw_major}.{fw_minor}.{fw_patch}",
            "fw_major": fw_major, "fw_minor": fw_minor, "fw_patch": fw_patch,
            "protocol_version": f"{(proto_ver >> 8) & 0xFF}.{proto_ver & 0xFF}",
            "mcu_model": mcu_model,
            "fw_description": fw_desc,
            "device_serial": f"0x{serial:08X}",
        }

    @classmethod
    def parse_capabilities(cls, data: bytes) -> dict:
        """Parse MSG_CAPABILITIES_RESP payload into dict."""
        if len(data) < 12:
            return {}
        bits, can_count, max_adc_rate, adc_res, max_can_baud = \
            struct.unpack_from("<I B I B H", data, 0)
        return {
            "capability_bits": bits,
            "has_adc": bool(bits & 1),
            "has_usb_cdc": bool(bits & 2),
            "has_multi_can": bool(bits & 4),
            "has_timestamp_us": bool(bits & 8),
            "can_channel_count": can_count,
            "max_adc_sample_rate": max_adc_rate,
            "adc_resolution": adc_res,
            "max_can_baudrate": max_can_baud,
        }

    @classmethod
    def parse_status(cls, data: bytes) -> dict:
        """Parse MSG_STATUS_RESPONSE payload into dict."""
        if len(data) < 8:
            return {}
        can_listen, adc_sampling, comm_if, can_active, uptime = \
            struct.unpack_from("<B B B B I", data, 0)
        return {
            "can_listening": bool(can_listen),
            "adc_sampling": bool(adc_sampling),
            "comm_interface": "USART" if comm_if == 0 else "USB_CDC",
            "can_channels_active": can_active,
            "uptime_ms": uptime,
        }

    @classmethod
    def parse_can_frame(cls, data: bytes) -> dict:
        """Parse MSG_CAN_FRAME_UP payload into dict.
        can_frame_up_t: timestamp(4)+can_id(4)+dlc(1)+flags(1)+data[8]+channel(1)=19 bytes
        """
        if len(data) < 19:
            return {}
        ts, can_id, dlc, flags = struct.unpack_from("<I I B B", data, 0)
        payload = data[10:18]
        channel = data[18]
        return {
            "timestamp": ts,
            "can_id": can_id,
            "dlc": dlc,
            "flags": flags,
            "is_extended": bool(flags & 1),
            "is_rtr": bool(flags & 2),
            "is_error": bool(flags & 4),
            "data": payload[:dlc],
            "channel": channel,
        }

    @classmethod
    def parse_adc_data(cls, data: bytes) -> dict:
        """Parse MSG_ADC_DATA_UP payload into dict."""
        if len(data) < 14:
            return {}
        ts, sample_rate, sample_count, resolution, ch, mode = \
            struct.unpack_from("<I I H H B B", data, 0)
        samples = []
        for i in range(min(sample_count, (len(data) - 14) // 2)):
            samples.append(struct.unpack_from("<H", data, 14 + i * 2)[0])
        return {
            "timestamp": ts,
            "sample_rate": sample_rate,
            "sample_count": sample_count,
            "resolution": resolution,
            "channel": ch,
            "mode": "ADC" if mode == 0 else "Logic",
            "samples": samples,
        }

    @classmethod
    def parse_error(cls, data: bytes) -> dict:
        """Parse MSG_ERROR_NOTIFY payload into dict."""
        if len(data) < 8:
            return {}
        err_code, src, flags, ts = struct.unpack_from("<B B H I", data, 0)
        src_names = {0: "CAN", 1: "ADC", 2: "COMM", 3: "SYSTEM"}
        return {
            "error_code": err_code,
            "source": src_names.get(src, f"Unknown({src})"),
            "error_flags": flags,
            "timestamp": ts,
        }

    @classmethod
    def parse_heartbeat(cls, data: bytes) -> dict:
        """Parse MSG_DEVICE_HEARTBEAT payload into dict."""
        if len(data) < 36:
            return {}
        mcu_model = data[0:32].split(b'\x00')[0].decode('ascii', errors='replace')
        fw_major, fw_minor, fw_patch, comm_if = struct.unpack_from("<B B B B", data, 32)
        return {
            "mcu_model": mcu_model,
            "fw_version": f"{fw_major}.{fw_minor}.{fw_patch}",
            "comm_interface": "USART" if comm_if == 0 else "USB_CDC",
        }

    @classmethod
    def parse_ack(cls, data: bytes) -> dict:
        """Parse MSG_ACK/MSG_NACK payload into dict."""
        if len(data) < 2:
            return {}
        ack_cmd, err_code = struct.unpack_from("<B B", data, 0)
        return {"ack_cmd": ack_cmd, "error_code": err_code, "is_ok": err_code == 0}
