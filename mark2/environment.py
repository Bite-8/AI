"""Collect experiment resource information without ML dependencies.

Usage: python -m mark2.environment --output logs/mark2/environment.json
"""

from __future__ import annotations

import argparse
import ctypes
import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def run_command(args: list[str]) -> dict:
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=10, check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "unavailable", "reason": type(exc).__name__}
    if result.returncode:
        return {"status": "error", "returncode": result.returncode}
    return {"status": "ok", "output": result.stdout.strip()}


def total_memory_bytes() -> int | None:
    if sys.platform.startswith("linux"):
        try:
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
        except (OSError, ValueError, IndexError):
            return None
    elif sys.platform == "darwin":
        result = run_command(["sysctl", "-n", "hw.memsize"])
        if result["status"] == "ok":
            try:
                return int(result["output"])
            except ValueError:
                return None
    elif sys.platform == "win32":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("load", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong),
                ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return status.total_physical
    return None


def cgroup_memory_limit() -> dict:
    """Read common Linux container limits; missing is not proof of no limit."""
    paths = [
        Path("/sys/fs/cgroup/memory.max"),
        Path("/sys/fs/cgroup/memory/memory.limit_in_bytes"),
    ]
    for path in paths:
        try:
            value = path.read_text().strip()
            return {"status": "read", "source": str(path), "value": value}
        except OSError:
            continue
    return {"status": "unknown"}


def collect(disk_path: Path) -> dict:
    disk = shutil.disk_usage(disk_path)
    packages = {}
    for name in ("numpy", "torch", "transformers", "huggingface-hub", "safetensors"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {
        "schema_version": 1,
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "os": platform.system(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "ram_total_bytes": total_memory_bytes(),
        "cgroup_memory_limit": cgroup_memory_limit(),
        "disk": {"total_bytes": disk.total, "free_bytes": disk.free},
        "nvidia_smi": run_command([
            "nvidia-smi",
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader,nounits",
        ]),
        "packages": packages,
        "notes": [
            "NVIDIA query columns: name, total VRAM (MiB), driver version.",
            "Unavailable NVIDIA query does not prove absence of a GPU.",
            "AMD/Apple accelerators and framework usability require separate checks.",
            "RAM may describe the host; container limits may be lower.",
            "Installed package metadata does not prove imports or model execution work.",
            "Disk values describe the filesystem containing --disk-path.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Save JSON (refuses overwrite)")
    parser.add_argument("--disk-path", type=Path, default=Path.cwd())
    args = parser.parse_args()
    try:
        report = collect(args.disk_path)
        payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("x", encoding="utf-8") as handle:
                handle.write(payload)
    except OSError as exc:
        parser.exit(1, f"Environment report failed: {exc}\n")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
