import argparse
import struct
import time
from typing import Optional

import os
import sys
import ctypes.util

import usb.core
import usb.util
import usb.backend.libusb1  # 确保 PyInstaller 收集 libusb1 backend
import usb.backend.libusb0  # noqa: F401 - 兼容部分环境（仅用于打包收集与回退）


VID = 0x10C4
PID = 0xEA61
EP_OUT = 0x02
EP_IN = 0x82


def _backend_debug_info() -> str:
    """用于在 GUI 弹窗里定位 backend/DLL 问题。"""
    lines: list[str] = []
    lines.append(f"python: {sys.executable}")
    lines.append(f"frozen: {getattr(sys, 'frozen', False)}")
    if getattr(sys, "frozen", False):
        lines.append(f"_MEIPASS: {getattr(sys, '_MEIPASS', '')}")
    # 是否能定位到 libusb-1.0.dll（不保证一定加载成功，但能提供线索）
    try:
        found = ctypes.util.find_library("libusb-1.0")
    except Exception as e:
        found = f"error: {e}"
    lines.append(f"ctypes.find_library('libusb-1.0'): {found}")
    # PATH 可能很长，截断展示
    p = os.environ.get("PATH", "")
    lines.append(f"PATH(head): {p[:300]}")
    return "\n".join(lines)


def build_reset() -> bytes:
    # 冷启动/切换前的 reset 包
    return bytes.fromhex("f0000000000000000000000000")


def build_exec(current_mA: float, duration: int) -> bytes:
    # 强度单位：0.01 mA
    current_units = int(round(current_mA * 100))
    return (
        bytes([0xFF, 0x03, 0x01])
        + struct.pack("<H", current_units)
        + struct.pack("<H", duration)
        + bytes.fromhex("0000dc050000")
    )


def find_device():
    # 优先尝试 libusb1；若不可用则回退到 PyUSB 默认 backend（与直接 python 运行保持一致）
    backend = usb.backend.libusb1.get_backend()
    if backend is not None:
        dev = usb.core.find(idVendor=VID, idProduct=PID, backend=backend)
    else:
        dev = usb.core.find(idVendor=VID, idProduct=PID)
    if dev is None:
        raise RuntimeError("找不到设备：10C4:EA61\n\n" + _backend_debug_info())
    dev.set_configuration()
    return dev


def clear_endpoints(dev) -> None:
    for ep in (EP_OUT, EP_IN):
        try:
            dev.clear_halt(ep)
            print(f"clear_halt({hex(ep)}): ok")
        except Exception as e:
            print(f"clear_halt({hex(ep)}): {e} -> continue")


def drain_in(dev) -> None:
    while True:
        try:
            data = bytes(dev.read(EP_IN, 64, timeout=50))
            print("drain in:", data.hex())
        except usb.core.USBTimeoutError:
            break
        except usb.core.USBError as e:
            print("drain stopped:", e)
            break


def safe_ctrl(dev, bm_request_type: int, b_request: int, w_value: int, w_index: int, label: str) -> None:
    try:
        dev.ctrl_transfer(
            bm_request_type,
            b_request,
            w_value,
            w_index,
            None,
            timeout=1000,
        )
        print(f"{label}: ok")
    except usb.core.USBError as e:
        # 第一条在你的设备上可能会报 Pipe error，但后续仍可成功
        print(f"{label}: {e} -> continue")


def read_ack(dev, label: str, timeout_ms: int) -> Optional[bytes]:
    try:
        data = bytes(dev.read(EP_IN, 64, timeout=timeout_ms))
        print(f"{label}: {data.hex()}")
        return data
    except usb.core.USBTimeoutError:
        print(f"{label}: timeout")
        return None
    except usb.core.USBError as e:
        print(f"{label}: usb error: {e}")
        return None


def validate_args(current_mA: float, duration: int) -> None:
    if not (0.0 <= current_mA <= 4.0):
        raise ValueError("current 必须在 0.0 到 4.0 mA 之间")
    if not (0 <= duration <= 65535):
        raise ValueError("duration 必须在 0 到 65535 之间")
    # 协议按 0.01 mA 编码
    units = current_mA * 100
    if abs(units - round(units)) > 1e-9:
        raise ValueError("current 必须精确到 0.01 mA，例如 0.40 / 0.80 / 1.60")


def run_sequence(current_mA: float, duration: int, settle_s: float = 0.05) -> None:
    validate_args(current_mA, duration)

    dev = find_device()
    try:
        clear_endpoints(dev)
        drain_in(dev)

        print("step 1: ctrl 40 00 ffff 0000")
        safe_ctrl(dev, 0x40, 0x00, 0xFFFF, 0x0000, "ctrl1")
        time.sleep(settle_s)

        print("step 2: ctrl 40 02 0002 0000")
        safe_ctrl(dev, 0x40, 0x02, 0x0002, 0x0000, "ctrl2")
        time.sleep(settle_s)

        print("step 3: ctrl 40 02 0001 0000")
        safe_ctrl(dev, 0x40, 0x02, 0x0001, 0x0000, "ctrl3")
        time.sleep(settle_s)

        reset_cmd = build_reset()
        exec_cmd = build_exec(current_mA, duration)

        print("reset =", reset_cmd.hex(), "len =", len(reset_cmd))
        print("exec  =", exec_cmd.hex(), "len =", len(exec_cmd))

        n = dev.write(EP_OUT, reset_cmd, timeout=2000)
        print("wrote reset:", n)
        read_ack(dev, "ack1", 500)

        time.sleep(settle_s)

        n = dev.write(EP_OUT, exec_cmd, timeout=2000)
        print("wrote exec:", n)
        read_ack(dev, "ack2", 300)

        print("命令已发送。")
    finally:
        usb.util.dispose_resources(dev)


def main() -> None:
    parser = argparse.ArgumentParser(description="Control Xeye SH shocker")
    parser.add_argument("--current", type=float, required=True, help="刺激强度，单位 mA，例如 0.40")
    parser.add_argument("--duration", type=int, required=True, help="持续时间字段整数，例如 2 / 50 / 100")
    parser.add_argument("--repeat", type=int, default=1, help="重复次数，默认 1")
    parser.add_argument("--interval", type=float, default=1.0, help="重复之间间隔秒数，默认 1.0")
    args = parser.parse_args()

    for i in range(args.repeat):
        print(f"\n=== run {i + 1}/{args.repeat} ===")
        run_sequence(args.current, args.duration)
        if i < args.repeat - 1:
            time.sleep(args.interval)


if __name__ == "__main__":
    main()