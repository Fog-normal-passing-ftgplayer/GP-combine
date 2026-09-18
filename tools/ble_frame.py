#!/usr/bin/env python3
"""GP-Combine 手机 App 协议：造帧工具（BLE 控制面）

手机 App 还没写完之前，用 nRF Connect 手敲帧要自己算 CRC，容易敲错还很难查
（错了设备只会回 ERR_BAD_CRC，或者干脆没反应）。这个脚本按固件的协议格式
吐出可直接粘贴的十六进制。

注意：本工具只负责「造字节」，不负责发。Android 不会把 BLE 的 GATT 能力交给
Termux 里的普通进程，所以真正的发送还是在手机上的 nRF Connect（或以后自己的
App）里粘贴。好在 Termux 能调系统剪贴板，配合起来就没手感问题了：

    python3 ble_frame.py --clip        # 生成完自动塞进手机剪贴板

然后在 nRF Connect 的写框里长按 → 粘贴。

帧格式（和 esp32_170x320/src/net/proto.h 一致）：
    A5 5A | ver=1 | cmd | seq(LE) | len(LE) | payload | CRC16-CCITT(LE, 覆盖 ver..载荷)

用法：
    python3 ble_frame.py                       # 不带参数 = 手机友好的菜单模式
    python3 ble_frame.py ping
    python3 ble_frame.py auth 123456
    python3 ble_frame.py cfg_get
    python3 ble_frame.py script 123456         # 一次吐出整套自测顺序
    python3 ble_frame.py script 123456 --hex-only
    python3 ble_frame.py cfg_set 01 01 00 01 64 00 00 00 01 3C 00 01 01 00 00 00 00

任何命令都能加 --clip：把结果丢进手机剪贴板（termux-clipboard-set，没有就只打印）。
seq 默认 0，要连着发多帧用 --seq N 区分（回包会把 seq 原样带回来）。
"""

import argparse
import shutil
import subprocess
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

# cfg_set 的 17 字节默认值（和固件里 espCfgPack / espCfgDefaults 对得上）：
# [0]帧版本 [1]镜像格式 [2]输入历史 [3]按键布局 [4]背景透明度 [5]背光
# [6]水平翻转 [7]垂直翻转 [8]反色 [9]屏保模式 [10-11]屏保分钟(小端)
# [12]关屏 [13]无线开关 [14]主题 [15]风格 [16]保留
CFG_DEFAULT = "01 01 00 01 64 00 00 00 01 3C 00 01 01 00 00 00 00"


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


def to_clipboard(text: str) -> bool:
    """Termux 里把结果丢进系统剪贴板；没装 termux-api 就返回 False。"""
    exe = shutil.which("termux-clipboard-set")
    if not exe:
        return False
    try:
        subprocess.run([exe], input=text.encode("utf-8"), check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def emit(text: str, clip: bool) -> None:
    print(text)
    if clip and to_clipboard(text):
        print("# 已复制到剪贴板（去 nRF Connect 写框长按粘贴）", file=sys.stderr)


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


def print_script(code: str, hex_only: bool = False) -> str:
    if len(code) != 6 or not code.isdigit():
        raise SystemExit("配对码必须是 6 位数字，例如：script 123456")
    lines = []
    for i, (name, payload, note, expect) in enumerate(SCRIPT, 1):
        if payload is None:
            payload = code.encode("ascii")
        frame = build(CMDS[name], payload, seq=0)
        if hex_only:
            lines.append(hexs(frame))
            continue
        lines += [
            f"# ---- {i}. {name.upper()} ----",
            f"# 说明：{note}",
            f"# 期望：{expect}",
            hexs(frame),
            "",
        ]
    if not hex_only:
        err = build(CMDS["err"], bytes([0x04]) + b"auth first", seq=0)
        lines += [
            "# AUTH 没过之前，除了 ping / auth，其它命令都会回这帧（ERR 0x04 auth first）：",
            hexs(err),
        ]
    return "\n".join(lines)


def ask(prompt: str, default: str = "") -> str:
    try:
        v = input(prompt).strip()
    except EOFError:
        raise SystemExit(0)
    return v or default


def menu(clip: bool) -> int:
    items = [
        ("ping", "探活（不用认证，先确认链路）"),
        ("auth", "认证（要输屏幕上的 6 位配对码）"),
        ("info", "固件 / 存储 / 内存"),
        ("pair_info", "设备名 / 配对码 / 已连接手机数"),
        ("cfg_get", "读 17 字节设置"),
        ("cfg_set", "写 17 字节设置（默认填当前默认值）"),
        ("cfg_reset", "恢复出厂（会写盘并同步 Pico）"),
        ("script", "整套自测顺序（要输配对码）"),
    ]
    while True:
        print()
        for i, (name, desc) in enumerate(items, 1):
            print(f"  {i}. {name:<9} {desc}")
        print("  q. 退出")
        choice = ask("选哪个: ").lower()
        if choice in ("q", "quit", "exit", ""):
            return 0
        if not choice.isdigit() or not 1 <= int(choice) <= len(items):
            print("没这个选项")
            continue
        name = items[int(choice) - 1][0]

        if name == "script":
            code = ask("6 位配对码: ")
            emit(print_script(code), clip)
            continue

        payload = b""
        if name == "auth":
            code = ask("6 位配对码: ")
            if len(code) != 6:
                print("配对码要 6 位")
                continue
            payload = code.encode("ascii")
        elif name == "cfg_set":
            raw = ask(f"17 个十六进制字节（回车用默认）: ", CFG_DEFAULT)
            try:
                payload = bytes(int(x, 16) for x in raw.replace(",", " ").split())
            except ValueError:
                print("有不是十六进制的东西，重来")
                continue
            if len(payload) != 17:
                print(f"要 17 字节，你给了 {len(payload)}")
                continue

        emit(hexs(build(CMDS[name], payload)), clip)


def main() -> int:
    ap = argparse.ArgumentParser(description="造 GP-Combine 协议帧（十六进制）")
    ap.add_argument("cmd", nargs="?", choices=sorted(CMDS) + ["script"])
    ap.add_argument("payload", nargs="*", help="十六进制字节；auth 可以直接写 6 位配对码")
    ap.add_argument("--seq", type=int, default=0)
    ap.add_argument("--hex-only", action="store_true", help="script 模式：只打印十六进制行")
    ap.add_argument("--clip", action="store_true", help="结果丢进手机剪贴板（Termux）")
    a = ap.parse_args()

    if a.cmd is None:
        return menu(a.clip)

    if a.cmd == "script":
        emit(print_script("".join(a.payload), a.hex_only), a.clip)
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
    emit(hexs(frame), a.clip)
    print(f"# {len(frame)} 字节  cmd=0x{cmd:02X}  len={len(payload)}  seq={a.seq}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
