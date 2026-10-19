#!/usr/bin/env python3
"""把接收端诊断固件的 USB 串口输出抓到文件。

用法: python3 tools/receiver_diag/read_acm.py [--port /dev/ttyACM0] [--seconds 30] [--out /tmp/rxdiag.log]
会在端口出现前一直等（刷完机板子重启时正好接上），然后连续读指定秒数。
"""

import argparse
import sys
import time

import serial


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyACM0")
    ap.add_argument("--seconds", type=float, default=30.0)
    ap.add_argument("--wait", type=float, default=60.0)
    ap.add_argument("--out", default="/tmp/rxdiag.log")
    args = ap.parse_args()

    port = None
    deadline = time.time() + args.wait
    while time.time() < deadline:
        try:
            port = serial.Serial(args.port, 115200, timeout=0.5)
            break
        except Exception:
            time.sleep(0.2)
    if port is None:
        print(f"NO PORT {args.port} within {args.wait}s", file=sys.stderr)
        return 1

    print(f"capturing {args.port} for {args.seconds}s -> {args.out}", flush=True)
    end = time.time() + args.seconds
    with open(args.out, "wb") as fh:
        while time.time() < end:
            data = port.read(4096)
            if data:
                fh.write(data)
                fh.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
