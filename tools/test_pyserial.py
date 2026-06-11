"""Open-Canoe protocol test using pyserial."""
import serial
import struct
import time
import sys

PORT = sys.argv[1] if len(sys.argv) > 1 else 'COM7'
BAUD = 115200

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
    seq = (int(time.time() * 1000) & 0xFFFF)
    hdr = struct.pack('<BHBH', 0xA5, tl, cmd, seq)
    c = crc16(hdr + payload)
    return hdr + payload + struct.pack('<HB', c, 0x5A)

def parse_frames(data):
    frames = []
    while len(data) >= 9:
        idx = data.find(b'\xA5')
        if idx < 0: break
        remaining = data[idx:]
        if len(remaining) < 9: break
        tl = struct.unpack('<H', remaining[1:3])[0]
        if tl < 9 or tl > 265:
            data = data[idx+1:]
            continue
        if len(remaining) < tl: break
        if remaining[tl-1] != 0x5A:
            data = data[idx+1:]
            continue
        cmd = remaining[3]
        hdr = remaining[:6]
        pl = remaining[6:tl-3]
        calc = crc16(hdr + pl)
        rcv = struct.unpack('<H', remaining[tl-3:tl-1])[0]
        if calc == rcv:
            frames.append((cmd, pl, remaining[idx:idx+tl]))
        data = remaining[tl:]
    return frames

print(f"Opening {PORT} at {BAUD} baud...")
sp = serial.Serial(PORT, BAUD, timeout=0.5)
sp.reset_input_buffer()

# Wait for data (heartbeat should arrive within 3s of MCU boot)
print("Waiting for heartbeat...")
start = time.time()
all_data = b''
while time.time() - start < 3:
    if sp.in_waiting:
        chunk = sp.read(sp.in_waiting)
        all_data += chunk
        frames = parse_frames(all_data)
        for cmd, pl, raw in frames:
            if cmd == 0x93:
                mcu = pl[:32].split(b'\x00')[0].decode('ascii', errors='replace')
                print(f"  HEARTBEAT: MCU={mcu} FW=v{pl[32]}.{pl[33]}.{pl[34]}")
    time.sleep(0.05)

# Now test each command
tests = [
    (0x01, "GET_INFO"),
    (0x02, "GET_CAPABILITIES"),
    (0x03, "GET_STATUS"),
    (0x04, "GET_ADC_STATUS"),
]

for cmd, name in tests:
    frame = build_frame(cmd)
    print(f"\n>>> Sending {name}: {frame.hex()}")
    sp.write(frame)
    sp.flush()
    time.sleep(0.3)

    # Read response
    if sp.in_waiting:
        resp = sp.read(sp.in_waiting)
        print(f"  Raw response ({len(resp)}B): {resp.hex()}")
        frames = parse_frames(resp)
        for rcmd, pl, raw in frames:
            if rcmd == 0x81:
                mcu = pl[6:38].split(b'\x00')[0].decode('ascii', errors='replace')
                print(f"  -> INFO: FW=v{pl[0]}.{pl[1]}.{pl[2]} MCU={mcu}")
            elif rcmd == 0x82:
                caps = struct.unpack_from('<I', pl)[0]
                feats = []
                if caps & 1: feats.append('ADC')
                if caps & 2: feats.append('USB-CDC')
                if caps & 4: feats.append('MULTI-CAN')
                if caps & 8: feats.append('TIMESTAMP_US')
                print(f"  -> CAPS: CAN_CH={pl[4]} features={feats}")
            elif rcmd == 0x83:
                uptime = struct.unpack_from('<I', pl, 4)[0]
                print(f"  -> STATUS: CAN={pl[0]} ADC={pl[1]} IF={pl[2]} uptime={uptime}ms")
            elif rcmd == 0x84:
                print(f"  -> ADC: avail={pl[0]} sampling={pl[1]} res={pl[2]}")
            elif rcmd == 0xA0:
                print(f"  -> ACK: err={pl[1]}")
            elif rcmd == 0xA1:
                print(f"  -> NACK")
            else:
                print(f"  -> 0x{rcmd:02X}: {pl.hex()[:40]}")
    else:
        print(f"  No response!")

sp.close()
print("\nDone.")
