"""ESP32-S3 串口检测。"""
from __future__ import annotations

from serial.tools import list_ports

# 常见 ESP32 开发板的 USB 串口桥 VID：
# 0x303A Espressif 原生 USB-JTAG/CDC
# 0x10C4 CP210x
# 0x1A86 CH340/CH341/CH9102（QinHeng/WCH）
# 0x0403 FTDI
ESP_VIDS = {0x303A, 0x10C4, 0x1A86, 0x0403}
DESC_KEYWORDS = (
    "esp32", "usb jtag", "usb serial", "usb-serial",
    "ch340", "ch341", "ch9102", "cp210", "ftdi",
    "qinheng", "wch",
)


def list_esp32_ports() -> list[str]:
    ports: list[str] = []
    usb_ports: list[str] = []
    try:
        comports = list_ports.comports()
    except Exception:
        return ports
    for p in comports:
        name = p.device or ""
        desc = ((p.description or "") + " " + (p.hwid or "")).lower()
        if p.vid in ESP_VIDS:
            ports.append(name)
        elif any(k in desc for k in DESC_KEYWORDS):
            ports.append(name)
        if p.vid is not None:
            usb_ports.append(name)
    if not ports:
        ports = usb_ports   # 兜底：识别不到型号时任何 USB 串口都算候选
    return sorted(set(ports))


def first_esp32_port() -> str:
    ports = list_esp32_ports()
    return ports[0] if ports else ""
