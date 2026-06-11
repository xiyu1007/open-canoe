"""Open-Canoe command sender — send HEX commands and see responses."""
import serial
import struct
import sys

PORT = sys.argv[1] if len(sys.argv) > 1 else 'COM7'
CMD = sys.argv[2] if len(sys.argv) > 2 else '01'  # default: GET_INFO

def crc16(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
        crc &= 0xFFFF
    return crc

def build_frame(cmd, payload=b''):
    tl = 9 + len(payload)
    hdr = struct.pack('<BHBH', 0xA5, tl, cmd, 0)
    c = crc16(hdr + payload)
    return hdr + payload + struct.pack('<HB', c, 0x5A)

# Commands
cmds = {
    '01': ('GET_INFO', b''),
    '02': ('GET_CAPABILITIES', b''),
    '03': ('GET_STATUS', b''),
    '04': ('GET_ADC_STATUS', b''),
    '30': ('START_CAN_LISTEN', b''),
    'info': ('GET_INFO', b''),
    'caps': ('GET_CAPABILITIES', b''),
    'status': ('GET_STATUS', b''),
    'adc': ('GET_ADC_STATUS', b''),
    'start': ('START_CAN_LISTEN', b''),
}

if CMD not in cmds:
    print(f"Unknown command: {CMD}")
    print(f"Available: {list(cmds.keys())}")
    exit(1)

name, payload = cmds[CMD]
# Extract hex command code from key
cmd_code = int(CMD, 16) if CMD.isdigit() or all(c in '0123456789ABCDEFabcdef' for c in CMD) else {'info': 0x01, 'caps': 0x02, 'status': 0x03, 'adc': 0x04, 'start': 0x30}[CMD]
frame = build_frame(cmd_code, payload)

sp = serial.Serial(PORT, 115200, timeout=0.5)
sp.reset_input_buffer()

# Drain any stale data
sp.read(1024)

print(f">>> {name}: {frame.hex()}")
sp.write(frame)
sp.flush()

# Read response
import time
time.sleep(0.3)
resp = sp.read(512)

if resp:
    print(f"<<< {len(resp)} bytes")
    while len(resp) >= 9:
        idx = resp.find(b'\xA5')
        if idx < 0 or idx + 9 > len(resp):
            break
        tl = struct.unpack('<H', resp[idx+1:idx+3])[0]
        if tl < 9 or idx + tl > len(resp):
            resp = resp[idx+1:]
            continue
        if resp[idx+tl-1] != 0x5A:
            resp = resp[idx+1:]
            continue
        rcmd = resp[idx+3]
        hdr = resp[idx:idx+6]
        pl = resp[idx+6:idx+tl-3]
        calc = crc16(hdr + pl)
        rcv = struct.unpack('<H', resp[idx+tl-3:idx+tl-1])[0]
        if calc != rcv:
            resp = resp[idx+tl:]
            continue

        if rcmd == 0x81:    # INFO
            mcu = pl[6:38].split(b'\x00')[0].decode()
            print(f"  MCU: {mcu}, FW: v{pl[0]}.{pl[1]}.{pl[2]}")
        elif rcmd == 0x82:  # CAPS
            caps = struct.unpack_from('<I', pl)[0]
            feats = []
            if caps & 1: feats.append('ADC')
            if caps & 2: feats.append('USB-CDC')
            if caps & 4: feats.append('MULTI-CAN')
            if caps & 8: feats.append('TIMESTAMP_US')
            print(f"  CAN channels: {pl[4]}, Features: {feats}")
        elif rcmd == 0x83:  # STATUS
            uptime = struct.unpack_from('<I', pl, 4)[0]
            print(f"  CAN: {pl[0]}, ADC: {pl[1]}, IF: {'USART' if pl[2]==0 else 'USB'}, uptime: {uptime}ms")
        elif rcmd == 0x84:  # ADC
            print(f"  ADC avail: {pl[0]}, sampling: {pl[1]}, resolution: {pl[2]}")
        elif rcmd == 0xA0:  # ACK
            print(f"  ACK: err={pl[1]}")
        elif rcmd == 0x93:  # Heartbeat
            mcu = pl[:32].split(b'\x00')[0].decode()
            print(f"  HEARTBEAT: {mcu} v{pl[32]}.{pl[33]}.{pl[34]}")
        else:
            print(f"  0x{rcmd:02X}: {pl.hex()[:40]}")
        resp = resp[idx+tl:]
else:
    print("  No response")
sp.close()
