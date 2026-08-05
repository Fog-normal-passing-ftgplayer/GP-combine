"""ESP32-S3 串口检测。"""
from __future__ import annotations

from serial.tools import list_ports

# Espressif 官方 VID（内置 USB-JTAG/串口）；CP210x 是常见的外置转串口芯片
ESP_VIDS = {0x303A}
CP210X_VIDS = {0x10C4}


def list_esp32_ports() -> list[str]:
    ports: list[str] = []
    try:
        comports = list_ports.comports()
    except Exception:
        return ports
    for p in comports:
        name = p.device or ""
        desc = ((p.description or "") + " " + (p.hwid or "")).lower()
        if p.vid in ESP_VIDS or p.vid in CP210X_VIDS:
            ports.append(name)
        elif "esp32" in desc or "esp32s3" in desc or "usb jtag" in desc:
            ports.append(name)
    return sorted(set(ports))


def first_esp32_port() -> str:
    ports = list_esp32_ports()
    return ports[0] if ports else ""
