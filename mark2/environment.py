"""Collect machine-readable host, dependency, and accelerator metadata."""

from __future__ import annotations

import importlib.metadata
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def command(args: list[str], timeout: int = 10) -> dict:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "unavailable", "reason": type(exc).__name__}
    if result.returncode:
        return {"status": "error", "returncode": result.returncode}
    return {"status": "ok", "output": result.stdout.strip()}


def _memory_bytes() -> int | None:
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError, IndexError):
        pass
    return None


def collect(path: Path) -> dict:
    disk = shutil.disk_usage(path)
    packages = {}
    for name in ("torch", "transformers", "datasets", "accelerate", "safetensors"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return {
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "ram_total_bytes": _memory_bytes(),
        "disk_total_bytes": disk.total,
        "disk_free_bytes": disk.free,
        "nvidia_smi": command(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total,driver_version",
                "--format=csv,noheader,nounits",
            ]
        ),
        "packages": packages,
    }
