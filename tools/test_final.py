"""Full protocol test for Open-Canoe firmware."""
import ctypes, struct, time

k32 = ctypes.windll.kernel32
h = k32.CreateFileW(r'\\.\COM7', 0x80000000|0x40000000, 0, None, 3, 0, None)
if h == -1 or h == ctypes.c_void_p(-1).value:
    print('Cannot open COM7')
    exit()

class DCB(ctypes.Structure):
    _fields_ = [('DCBlength',ctypes.c_uint32),('BaudRate',ctypes.c_uint32),
        ('fBinary',ctypes.c_uint32),('fParity',ctypes.c_uint32),
        ('fOutxCtsFlow',ctypes.c_uint32),('fOutxDsrFlow',ctypes.c_uint32),
        ('fDtrControl',ctypes.c_uint32),('fDsrSensitivity',ctypes.c_uint32),
        ('fTXContinueOnXoff',ctypes.c_uint32),('fOutX',ctypes.c_uint32),
        ('fInX',ctypes.c_uint32),('fErrorChar',ctypes.c_uint32),
        ('fNull',ctypes.c_uint32),('fRtsControl',ctypes.c_uint32),
        ('fAbortOnError',ctypes.c_uint32),('fDummy2',ctypes.c_uint32*17),
        ('wReserved',ctypes.c_uint16),('XonLim',ctypes.c_uint16),
        ('XoffLim',ctypes.c_uint16),('ByteSize',ctypes.c_uint8),
        ('Parity',ctypes.c_uint8),('StopBits',ctypes.c_uint8),
        ('XonChar',ctypes.c_int8),('XoffChar',ctypes.c_int8),
        ('ErrorChar',ctypes.c_int8),('EofChar',ctypes.c_int8),
        ('EvtChar',ctypes.c_int8),('wReserved1',ctypes.c_uint16)]
dcb = DCB(); dcb.DCblength = ctypes.sizeof(DCB); k32.GetCommState(h, ctypes.byref(dcb))
dcb.BaudRate = 115200; dcb.ByteSize = 8; dcb.Parity = 0; dcb.StopBits = 0; k32.SetCommState(h, ctypes.byref(dcb))

class TO(ctypes.Structure):
    _fields_ = [('a',ctypes.c_uint32),('b',ctypes.c_uint32),('c',ctypes.c_uint32),('d',ctypes.c_uint32),('e',ctypes.c_uint32)]
to = TO(); to.a = 50; to.c = 1000; k32.SetCommTimeouts(h, ctypes.byref(to))
k32.PurgeComm(h, 0x000F)

CMD_NAMES = {
    0x01:'GET_INFO', 0x02:'GET_CAPS', 0x03:'GET_STATUS', 0x04:'GET_ADC_STATUS',
    0x10:'SET_BAUD', 0x11:'SET_MODE', 0x12:'SET_FILTER', 0x20:'SET_ADC',
    0x28:'SET_IF', 0x30:'START_LISTEN', 0x31:'STOP_LISTEN',
    0x32:'ADC_START', 0x33:'ADC_STOP', 0x34:'SEND_FRAME', 0x3F:'RESET',
    0x81:'INFO_RESP', 0x82:'CAPS_RESP', 0x83:'STATUS_RESP', 0x84:'ADC_STATUS_RESP',
    0x90:'CAN_FRAME', 0x91:'ADC_DATA', 0x92:'ERROR', 0x93:'HEARTBEAT',
    0xA0:'ACK', 0xA1:'NACK',
}

def crc16(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8): crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else (crc << 1)
        crc &= 0xFFFF
    return crc

def build_frame(cmd, payload=b''):
    tl = 9 + len(payload)
    hdr = struct.pack('<BHBH', 0xA5, tl, cmd, 0x5555)
    c = crc16(hdr + payload)
    return hdr + payload + struct.pack('<HB', c, 0x5A)

def send_cmd(cmd, payload=b''):
    frame = build_frame(cmd, payload)
    written = ctypes.c_uint32(0)
    k32.WriteFile(h, frame, len(frame), ctypes.byref(written), None)

def read_all():
    buf = (ctypes.c_uint8*4096)(); read = ctypes.c_uint32(0)
    k32.ReadFile(h, buf, 4096, ctypes.byref(read), None)
    return bytes(buf[:read.value])

print("=" * 60)
print("Open-Canoe Protocol Test")
print("=" * 60)

all_data = b''

# Wait for first heartbeat to confirm firmware is alive
print("\nWaiting for heartbeat...")
for i in range(30):
    time.sleep(0.1)
    all_data += read_all()

# Parse all frames received so far
hb_count = 0
while len(all_data) >= 9:
    idx = all_data.find(b'\xA5')
    if idx < 0: break
    remaining = all_data[idx:]
    if len(remaining) < 9: break
    tl = struct.unpack('<H', remaining[1:3])[0]
    if tl < 9 or tl > 265: all_data = all_data[idx+1:]; continue
    if len(remaining) < tl: break
    if remaining[tl-1] != 0x5A: all_data = all_data[idx+1:]; continue
    cmd = remaining[3]
    hdr = remaining[:6]
    pl = remaining[6:tl-3]
    calc_crc = crc16(hdr + pl)
    rcv_crc = struct.unpack('<H', remaining[tl-3:tl-1])[0]
    if calc_crc == rcv_crc:
        name = CMD_NAMES.get(cmd, f'0x{cmd:02X}')
        if cmd == 0x93:
            hb_count += 1
            mcu = pl[:32].split(b'\x00')[0].decode('ascii','replace')
            fw = f"v{pl[32]}.{pl[33]}.{pl[34]}"
            iface = "USART" if pl[35]==0 else "USB-CDC"
            if hb_count == 1:
                print(f"Heartbeat: MCU={mcu}, FW={fw}, IF={iface}")
        else:
            print(f"[{name}] payload={pl.hex()[:40]}")
    all_data = remaining[tl:]

# Test queries
tests = [
    ("CMD_GET_INFO", 0x01, None),
    ("CMD_GET_CAPABILITIES", 0x02, None),
    ("CMD_GET_STATUS", 0x03, None),
    ("CMD_GET_ADC_STATUS", 0x04, None),
]

for test_name, cmd, payload in tests:
    print(f"\n>>> Sending {test_name}...")
    send_cmd(cmd, payload or b'')
    time.sleep(0.3)
    all_data += read_all()

    # Parse responses
    while len(all_data) >= 9:
        idx = all_data.find(b'\xA5')
        if idx < 0: break
        remaining = all_data[idx:]
        if len(remaining) < 9: break
        tl = struct.unpack('<H', remaining[1:3])[0]
        if tl < 9 or tl > 265: all_data = all_data[idx+1:]; continue
        if len(remaining) < tl: break
        if remaining[tl-1] != 0x5A: all_data = all_data[idx+1:]; continue
        cmd_r = remaining[3]
        hdr = remaining[:6]
        pl = remaining[6:tl-3]
        calc_crc = crc16(hdr + pl)
        rcv_crc = struct.unpack('<H', remaining[tl-3:tl-1])[0]
        if calc_crc != rcv_crc:
            all_data = remaining[tl:]
            continue
        name = CMD_NAMES.get(cmd_r, f'0x{cmd_r:02X}')
        if cmd_r == 0x81:  # INFO_RESP
            fw = f"v{pl[0]}.{pl[1]}.{pl[2]}"
            proto = (pl[4]<<8)|pl[5]
            mcu = pl[8:40].split(b'\x00')[0].decode('ascii','replace')
            desc = pl[40:72].split(b'\x00')[0].decode('ascii','replace')
            serial = struct.unpack_from('<I', pl, 4)[0]
            print(f"  INFO_RESP: FW={fw}, MCU={mcu}, Desc={desc}")
        elif cmd_r == 0x82:  # CAPS_RESP
            caps, can_ch, adc_rate, adc_res, can_baud = struct.unpack_from('<IBIBH', pl)
            feats = []
            if caps & 1: feats.append('ADC')
            if caps & 2: feats.append('USB-CDC')
            if caps & 4: feats.append('MULTI-CAN')
            if caps & 8: feats.append('TIMESTAMP_US')
            print(f"  CAPS_RESP: features={feats}, CAN_CH={can_ch}, ADC={adc_rate}Hz/{adc_res}bit")
        elif cmd_r == 0x83:  # STATUS_RESP
            can_listen, adc_samp, comm_if, can_ch, uptime = struct.unpack_from('<BBBB I', pl)
            print(f"  STATUS_RESP: CAN_listen={can_listen}, ADC_samp={adc_samp}, IF={'USART'if comm_if==0 else 'USB'}, uptime={uptime}ms")
        elif cmd_r == 0x84:  # ADC_STATUS_RESP
            avail, sampling, res = pl[0], pl[1], pl[2]
            print(f"  ADC_STATUS_RESP: available={avail}, sampling={sampling}, resolution={res}")
        elif cmd_r == 0xA0:  # ACK
            if len(pl) >= 2: print(f"  ACK: cmd=0x{pl[0]:02X}, err={pl[1]}")
            else: print(f"  ACK: {pl.hex()}")
        elif cmd_r == 0xA1:  # NACK
            print(f"  NACK: {pl.hex()}")
        elif cmd_r == 0x93:  # heartbeat (ignore)
            pass
        else:
            print(f"  {name}: {pl.hex()[:40]}")
        all_data = remaining[tl:]

print("\n" + "=" * 60)
print("Test Complete!")
print("=" * 60)
k32.CloseHandle(h)
