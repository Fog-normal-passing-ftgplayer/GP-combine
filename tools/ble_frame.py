#!/usr/bin/env python3
"""GP-Combine 手机 App 协议：造帧工具（BLE 控制面）

用途：手机 App 还没写完之前，用 nRF Connect 手敲帧验证太痛苦（CRC 得手算）。
这个脚本按固件的协议格式吐出可直接粘贴的十六进制字节。

帧格式（和 esp32_170x320/src/net/proto.h 一致）：
    A5 5A | ver=1 | cmd | seq(LE) | len(LE) | payload | CRC16-CCITT(LE, 覆盖 ver..载荷)

用法：
    python3 tools/ble_frame.py ping
    python3 tools/ble_frame.py auth 123456
    python3 tools/ble_frame.py info
    python3 tools/ble_frame.py pair_info
    python3 tools/ble_frame.py cfg_get
    python3 tools/ble_frame.py cfg_set 01 01 00 01 64 00 00 00 01 3C 00 01 01 00 00 00 00
    python3 tools/ble_frame.py cfg_reset
    python3 tools/ble_frame.py script 123456      # 一次吐整套自测顺序（含期望回包）

seq 默认 0；要连着发多帧可以 --seq N（回包会把 seq 原样带回来，方便对号）。
"""

import argparse
import sys

MAGIC = (0xA5, 0x5A)
VER = 1

CMDS = {
    "ping": 0x01,
    "auth": 0x02,
    "info": 0x03,
    "pair_info": 0x04,
    "cfg_get": 0x10,
    "cfg_set": 0x11,
    "cfg_reset": 0x12,
    "err": 0x7F,
}


def crc16(data: bytes) -> int:
    """CRC16-CCITT（多项式 0x1021，初值 0xFFFF）—— 必须和 proto.h 的 protoCrc16 一致。"""
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def build(cmd: int, payload: bytes = b"", seq: int = 0) -> bytes:
    if len(payload) > 256:
        raise SystemExit("载荷超过 PROTO_MAX_PAYLOAD(256)")
    body = bytes([VER, cmd]) + seq.to_bytes(2, "little") + len(payload).to_bytes(2, "little") + payload
    crc = crc16(body)
    return bytes(MAGIC) + body + crc.to_bytes(2, "little")


def hexs(frame: bytes) -> str:
    return " ".join(f"{b:02X}" for b in frame)


# 手测顺序：(命令, 载荷, 说明, 期望回包)
# 断连会清 authed，所以每次重连都要从头走一遍。
SCRIPT = [
    ("ping", b"", "探活：不需要认证。回包应该和发过去的这帧一模一样", "同一帧原样回来"),
    ("auth", None, "认证：把配对码换成屏幕上那 6 位", "1 字节 01 = 过，00 = 码错"),
    ("info", b"", "固件/存储/内存信息（这条开始必须先过 AUTH）", "ASCII 文本，ver=... / fs=... / ram=..."),
    ("pair_info", b"", "设备名、配对码、蓝牙开关、已连手机数", "ASCII 文本，name=... / pair=... / clients=..."),
    ("cfg_get", b"", "读 17 字节设置镜像", "17 字节设置数据"),
    ("cfg_reset", b"", "恢复出厂（会写 LittleFS 并同步给 Pico）", "1 字节 00 = OK；发之前想清楚"),
]


def print_script(code: str, hex_only: bool = False) -> None:
    if len(code) != 6 or not code.isdigit():
        raise SystemExit("配对码必须是 6 位数字，例如：script 123456")
    for i, (name, payload, note, expect) in enumerate(SCRIPT, 1):
        if payload is None:
            payload = code.encode("ascii")
        assert name in CMDS
        frame = build(CMDS[name], payload, seq=0)
        if hex_only:
            print(hexs(frame))
            continue
        print(f"# ---- {i}. {name.upper()} ----")
        print(f"# 说明：{note}")
        print(f"# 期望：{expect}")
        print(hexs(frame))
        print()
    if not hex_only:
        err = build(CMDS["err"], bytes([0x04]) + b"auth first", seq=0)
        print("# AUTH 没过之前，除了 ping / auth，其它命令都会回这帧（ERR 0x04 auth first）：")
        print(hexs(err))


def main() -> int:
    ap = argparse.ArgumentParser(description="造 GP-Combine 协议帧（十六进制）")
    ap.add_argument("cmd", choices=sorted(CMDS) + ["script"])
    ap.add_argument("payload", nargs="*", help="十六进制字节；auth 可以直接写 6 位配对码")
    ap.add_argument("--seq", type=int, default=0)
    ap.add_argument("--hex-only", action="store_true", help="script 模式：只打印十六进制行")
    a = ap.parse_args()

    if a.cmd == "script":
        code = "".join(a.payload)
        print_script(code, a.hex_only)
        return 0

    cmd = CMDS[a.cmd]
    payload = b""
    if a.cmd == "auth":
        code = "".join(a.payload)
        if len(code) != 6:
            raise SystemExit("配对码必须是 6 位，例如：auth 123456")
        payload = code.encode("ascii")
    elif a.payload:
        try:
            payload = bytes(int(x, 16) for x in a.payload)
        except ValueError:
            raise SystemExit("载荷要写成十六进制字节，例如：cfg_set 01 01 00 ...")

    if a.cmd == "cfg_set" and len(payload) != 17:
        raise SystemExit(f"cfg_set 载荷必须是 17 字节，现在给了 {len(payload)}")

    frame = build(cmd, payload, a.seq)
    print(hexs(frame))
    print(f"# {len(frame)} 字节  cmd=0x{cmd:02X}  len={len(payload)}  seq={a.seq}",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
