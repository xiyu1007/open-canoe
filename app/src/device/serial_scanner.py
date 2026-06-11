"""Serial port scanner for device discovery."""
import serial.tools.list_ports


def scan_ports() -> list[dict]:
    """Scan all available serial ports. Returns list of {port, description, hwid, vid, pid}."""
    ports = []
    for p in serial.tools.list_ports.comports():
        info = {
            "port": p.device,
            "description": p.description,
            "hwid": p.hwid,
            "vid": None,
            "pid": None,
        }
        if p.vid is not None:
            info["vid"] = f"0x{p.vid:04X}"
        if p.pid is not None:
            info["pid"] = f"0x{p.pid:04X}"
        ports.append(info)
    return ports


def find_stlink_serial() -> str | None:
    """Find the ST-Link VCP serial port if present."""
    for p in serial.tools.list_ports.comports():
        if p.vid == 0x0483 and p.pid == 0x3748:
            return p.device
    return None


def find_any_serial() -> str | None:
    """Find any available serial port."""
    ports = list(serial.tools.list_ports.comports())
    if ports:
        return ports[0].device
    return None
