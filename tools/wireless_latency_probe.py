#!/usr/bin/env python3
"""GP-Combine 无线延迟后台实测（只用标准库，Linux）。

能测两件事：

1) 只插无线接收器时 —— 报点间隔统计（仅 HID 模式设备有 hidraw 时可用）
   XInput 模式走内核 xpad 驱动，没有 hidraw 节点，只能看按键边沿。

2) 同时插上本体（有线 USB）时 —— 真·端到端差值
   同一颗按键的两条链路会同时产生边沿：有线那条（Pico 直连 USB）几乎就是
   人按键的时刻，无线那条（nRF24 -> 接收器 -> USB）晚多少就是无线多出来的延迟。
   两个设备的时间戳都来自内核，同一时钟，不需要对表。
   测的时候只按同一个键（比如 A）反复按，配对最干净。

用法（读 /dev/hidraw* 要 root）：
    sudo python3 tools/wireless_latency_probe.py --list
    sudo python3 tools/wireless_latency_probe.py --seconds 40
"""

import argparse
import fcntl
import glob
import os
import re
import select
import statistics
import struct
import sys
import time

EV_SYN = 0x00
EV_KEY = 0x01
EV_ABS = 0x03

CODE_NAMES = {
    0x00: "ABS_X", 0x01: "ABS_Y", 0x02: "ABS_Z", 0x03: "ABS_RX",
    0x04: "ABS_RY", 0x05: "ABS_RZ",
    0x10: "HAT0X", 0x11: "HAT0Y",
    0x130: "BTN_A", 0x131: "BTN_B", 0x132: "BTN_C", 0x133: "BTN_X",
    0x134: "BTN_Y", 0x135: "BTN_Z", 0x136: "BTN_TL", 0x137: "BTN_TR",
    0x138: "BTN_TL2", 0x139: "BTN_TR2", 0x13A: "BTN_MODE",
    0x13B: "BTN_THUMBL", 0x13C: "BTN_THUMBR",
    0x220: "DPAD_UP", 0x221: "DPAD_DOWN", 0x222: "DPAD_LEFT", 0x223: "DPAD_RIGHT",
}


def code_name(code):
    return CODE_NAMES.get(code, "0x%x" % code)

EVENT_STRUCT = struct.Struct("<qqHHi")  # sec, usec, type, code, value


def _read(path):
    try:
        with open(path) as fh:
            return fh.read().strip()
    except OSError:
        return ""


def _usb_port(sysfs):
    m = re.search(r"/usb\d+/(\d+-\d+(?:\.\d+)*)", sysfs or "")
    return m.group(1) if m else "?"


def _event_index(path):
    try:
        return int(path.rsplit("event", 1)[-1])
    except ValueError:
        return 0


def discover(pattern):
    """按名字找手柄类设备（evdev 为主，HID 模式的顺带捡上 hidraw）。"""
    rx = re.compile(pattern, re.I)
    devices = []
    seen = set()
    for ev in sorted(glob.glob("/sys/class/input/event*"), key=_event_index):
        base = os.path.join(ev, "device")
        name = _read(os.path.join(base, "name"))
        if not name or not rx.search(name):
            continue
        # 只收真正的输入设备（有按键能力位图）
        if not _read(os.path.join(base, "capabilities", "key")):
            continue
        phys = _read(os.path.join(base, "phys"))
        if (name, phys) in seen:
            continue
        seen.add((name, phys))
        hidraw = None
        for node in glob.glob(os.path.join(base, "hidraw", "hidraw*")):
            hidraw = "/dev/" + os.path.basename(node)
            break
        devices.append({
            "name": name,
            "phys": phys,
            "port": _usb_port(os.path.realpath(ev)),
            "hidraw": hidraw,
            "event": "/dev/input/" + os.path.basename(ev),
            "evfd": None,
            "reports": [],   # 原始报文到达时刻（monotonic，仅 hidraw 模式）
            "times": [],     # 每个 evdev 事件的内核时间戳（含 ABS/SYN，用来量报文节奏）
            "edges": [],     # (内核时间戳, code, value)
        })
    return devices


def describe(dev, idx):
    print("  [%d] %s" % (idx, dev["name"]))
    print("      evdev=%s  usb口=%s  hidraw=%s" % (
        dev["event"], dev["port"], dev["hidraw"] or "无(XInput)"))


ABS_CODES = (0x00, 0x01, 0x02, 0x03, 0x04, 0x05)
ABSINFO = struct.Struct("<6i")


def _eviocgabs(code):
    return 0x80000000 | (ABSINFO.size << 16) | (ord("E") << 8) | (0x40 + code)


def read_abs(fd):
    """直接 ioctl 读当前轴值（不依赖变化事件，值稳定时也能读到）。"""
    out = {}
    if fd is None:
        return out
    buf = bytearray(ABSINFO.size)
    for code in ABS_CODES:
        try:
            fcntl.ioctl(fd, _eviocgabs(code), buf, True)
        except OSError:
            continue
        out[code] = ABSINFO.unpack(bytes(buf))[0]
    return out


# 探针编码：报告值 = 1000 + (us/10)*20；Y 轴 xpad 会取反（PC 值 = -(报告值+1)）
def _probe_us(v, invert=False):
    r = (-v - 1) if invert else v
    if r is None or r < 1000:
        return float("nan")
    return (r - 1000) / 20.0 * 10.0


def abs_line(dev):
    vals = read_abs(dev.get("evfd"))
    if not vals:
        return ""
    return "  ".join("%s=%d" % (code_name(c), vals[c]) for c in sorted(vals))


def decode_line(dev):
    """接收器仪表盘固件专用：把编码进轴里的耗时解出来。"""
    v = read_abs(dev.get("evfd"))
    if not v or not all(v.get(c, -1) >= 0 for c in ABS_CODES):
        return ""
    parts = [
        "主循环 %.2fms" % (_probe_us(v[0x00]) / 1e3),
        "平均包间隔 %.2fms" % (_probe_us(v[0x01], True) / 1e3),
        "收包耗时 %.3fms" % (_probe_us(v[0x03]) / 1e3),
        "钩子+process %.3fms" % (_probe_us(v[0x04], True) / 1e3),
    ]
    return "  ".join(parts)


def stats(values, unit="ms", scale=1e3):
    values = sorted(values)
    n = len(values)
    if n == 0:
        return None
    return {
        "n": n,
        "mean": sum(values) / n * scale,
        "min": values[0] * scale,
        "p50": values[n // 2] * scale,
        "p95": values[min(n - 1, int(n * 0.95))] * scale,
        "max": values[-1] * scale,
        "unit": unit,
    }


def fmt(s):
    if s is None:
        return "-"
    return "n=%d 平均%.2f 中位%.2f p95 %.2f 最大%.2f %s" % (
        s["n"], s["mean"], s["p50"], s["p95"], s["max"], s["unit"])


class _Tee:
    """把 stdout/stderr 同时写进日志文件，边跑边落盘，管道被 Ctrl-C 掐掉也不丢结果。"""

    def __init__(self, stream, path):
        self.stream = stream
        self.fh = open(path, "w")

    def write(self, text):
        self.stream.write(text)
        self.fh.write(text)
        self.fh.flush()
        return len(text)

    def flush(self):
        self.stream.flush()
        self.fh.flush()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=40.0, help="采样时长（秒）")
    ap.add_argument("--list", action="store_true", help="只列设备")
    ap.add_argument("--log", default=None, help="同时把结果写进这个文件")
    ap.add_argument("--name", default=r"GP2040|Open Stick|Gamepad|Controller|Xbox|X-Box|PS4|Switch|HID gamepad",
                    help="设备名匹配正则")
    ap.add_argument("--pair-window", type=float, default=0.25,
                    help="跨设备配对的边沿最大间隔（秒）")
    args = ap.parse_args()

    if args.log:
        sys.stdout = sys.stderr = _Tee(sys.stdout, args.log)

    devices = discover(args.name)
    if not devices:
        print("没找到手柄类设备。先把接收器/本体插上再跑。")
        return 1

    print("发现 %d 个设备：" % len(devices))
    for i, dev in enumerate(devices):
        describe(dev, i)
    if args.list:
        return 0
    if len(devices) == 1:
        print("\n只有一个设备：只能量报点节奏。要做「无线比有线慢多少」的对比，")
        print("把本体用 USB 线也插到这台电脑上（两条链路同时在线）再跑一次。")
    print("测的时候只按同一个键（比如 A）反复按，配对方便。开始采样 %.0f 秒…\n"
          % args.seconds)

    fds = {}
    for dev in devices:
        for kind in ("hidraw", "event"):
            node = dev[kind]
            if not node:
                continue
            try:
                fd = os.open(node, os.O_RDONLY | os.O_NONBLOCK)
            except OSError as exc:
                print("打不开 %s: %s" % (node, exc))
                return 1
            fds[fd] = (dev, kind)
            if kind == "event":
                dev["evfd"] = fd

    t0 = time.monotonic()
    last_report_log = t0
    try:
        while True:
            now = time.monotonic()
            if now - t0 >= args.seconds:
                break
            timeout = min(0.5, max(0.02, args.seconds - (now - t0)))
            ready, _, _ = select.select(list(fds), [], [], timeout)
            for fd in ready:
                dev, kind = fds[fd]
                try:
                    data = os.read(fd, 4096)
                except BlockingIOError:
                    continue
                except OSError:
                    continue
                if not data:
                    continue
                stamp = time.monotonic()
                if kind == "hidraw":
                    dev["reports"].append(stamp)
                else:
                    for off in range(0, len(data) - EVENT_STRUCT.size + 1, EVENT_STRUCT.size):
                        sec, usec, etype, code, value = EVENT_STRUCT.unpack_from(data, off)
                        stamp = sec + usec / 1e6
                        dev["times"].append(stamp)
                        # 按键(EV_KEY 0/1) 和 方向键/摇杆(EV_ABS) 都算"边沿"
                        if (etype == EV_KEY and value in (0, 1)) or etype == EV_ABS:
                            dev["edges"].append((stamp, code, value))
            if now - last_report_log >= 2.0:
                last_report_log = now
                print("  进行中 %4.0fs：%s" % (now - t0, "  ".join(
                    "%s口 边沿%d" % (d["port"], len(d["edges"])) for d in devices)))
                for d in devices:
                    line = decode_line(d) or abs_line(d)
                    if line:
                        print("      %s口 实时: %s" % (d["port"], line))
                sys.stdout.flush()
    except KeyboardInterrupt:
        print("\n手动结束。")

    print("\n================ 结果 ================")
    for dev in devices:
        gaps = [b - a for a, b in zip(dev["reports"], dev["reports"][1:])]
        tag = "%s (usb %s)" % (dev["name"], dev["port"])
        if gaps:
            s = stats(gaps)
            over = {ms: sum(1 for g in gaps if g * 1e3 > ms) for ms in (4, 8, 20, 50)}
            print("%s 报文 %d 条，平均 %.2fms/条" % (tag, len(dev["reports"]) + 1, s["mean"]))
            print("   间隔: 中位%.2f p95 %.2f 最大%.2f ms | >4ms %d 次, >8ms %d 次, >20ms %d 次, >50ms %d 次"
                  % (s["p50"], s["p95"], s["max"], over[4], over[8], over[20], over[50]))
        # evdev 侧节奏（含摇杆 ABS）：同一次报文里的所有事件时间戳相同，去重后就是报文节奏
        slots = sorted(set(dev["times"]))
        if len(slots) > 1:
            sg = [b - a for a, b in zip(slots, slots[1:])]
            s = stats(sg)
            over = {ms: sum(1 for g in sg if g * 1e3 > ms) for ms in (2, 4, 8, 20)}
            print("%s evdev 报文 %d 条（去重后）: 平均 %.2fms 中位 %.2f p95 %.2f 最大 %.2f"
                  % (tag, len(slots), s["mean"], s["p50"], s["p95"], s["max"]))
            print("   间隔分布: >2ms %d 次, >4ms %d 次, >8ms %d 次, >20ms %d 次"
                  % (over[2], over[4], over[8], over[20]))
        live = abs_line(dev)
        if live:
            print("   当前轴值(实时读): " + live)
            dec = decode_line(dev)
            if dec:
                print("   >>> 仪表盘解码: " + dec)
        print("%s 按键边沿 %d 个" % (tag, len(dev["edges"])))
        kinds = {}
        last = {}
        for _ts, code, value in dev["edges"]:
            kinds[(code, value)] = kinds.get((code, value), 0) + 1
            last[code] = value
        if kinds:
            top = sorted(kinds.items(), key=lambda kv: -kv[1])[:6]
            print("   边沿种类: " + "  ".join(
                "%s=%d ×%d" % (code_name(code), value, n) for (code, value), n in top))
            print("   各轴最后值: " + "  ".join(
                "%s=%d(n=%d)" % (code_name(c), v, sum(n for (cc, _), n in kinds.items() if cc == c))
                for c, v in sorted(last.items())))

    if len(devices) >= 2:
        a, b = devices[0], devices[1]
        used = set()
        deltas = []
        last_pair = 0.0
        for ta, ca, va in a["edges"]:
            if ta - last_pair < 0.06:      # 同一颗键的重复边沿别连着配
                continue
            best = None
            for i, (tb, cb, vb) in enumerate(b["edges"]):
                if i in used or vb != va:
                    continue
                dt = tb - ta
                if abs(dt) > args.pair_window:
                    continue
                if best is None or abs(dt) < abs(best[1]):
                    best = (i, dt)
            if best is None:
                continue
            used.add(best[0])
            deltas.append(best[1])
            last_pair = ta
        if deltas:
            s = stats(deltas)
            print("\n跨设备配对 %d 对（正=1号更早）" % s["n"])
            print("   1号 usb%s  vs  2号 usb%s" % (a["port"], b["port"]))
            print("   差值: 平均 %+.2fms 中位 %+.2f p95 %+.2f 最大 %+.2f 最小 %+.2f"
                  % (s["mean"], s["p50"], s["p95"], s["max"], s["min"]))
            print("   每次: " + " ".join("%+.1f" % (d * 1e3) for d in deltas[:60]))
            print("   正=usb%s 先到（它就是有线直连的本体），负=usb%s 先到。" % (
                a["port"] if s["mean"] > 0 else b["port"],
                b["port"] if s["mean"] > 0 else a["port"]))
            print("   两条链路的净差值就是这个数；两端各自还有 1ms 的 USB 轮询相位抖动。")
        else:
            print("\n没有配对到边沿：确认两个设备都在动（比如本体是有线手柄模式），再跑一次。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
