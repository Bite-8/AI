"""Collect and validate machine-readable host metadata for Mark2 runs."""

from __future__ import annotations

import importlib.metadata
import json
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PACKAGE_NAMES = ("torch", "transformers", "datasets", "accelerate", "safetensors")
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")


def command(args: list[str], timeout: int = 10) -> dict[str, Any]:
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


def _packages() -> dict[str, str | None]:
    packages = {}
    for name in PACKAGE_NAMES:
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    return packages


def collect(path: Path) -> dict[str, Any]:
    disk = shutil.disk_usage(path)
    return {
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "ram_total_bytes": _memory_bytes(),
        "disk_total_bytes": disk.total,
        "disk_free_bytes": disk.free,
        "nvidia_smi": command(
            ["nvidia-smi", "--query-gpu=index,name,memory.total,driver_version", "--format=csv,noheader,nounits"]
        ),
        "packages": _packages(),
    }


class SystemProbe:
    """Read host state. Tests replace this object; it never downloads assets."""

    def __init__(self, repository_root: Path, filesystem_path: Path):
        self.repository_root = repository_root
        self.filesystem_path = filesystem_path

    def snapshot(self) -> dict[str, Any]:
        commit = command(["git", "-C", str(self.repository_root), "rev-parse", "HEAD"])
        status = command(
            ["git", "-C", str(self.repository_root), "status", "--porcelain", "--untracked-files=no"]
        )
        disk = shutil.disk_usage(self.filesystem_path)
        accelerator: dict[str, Any]
        try:
            import torch

            available = bool(torch.cuda.is_available())
            count = int(torch.cuda.device_count()) if available else 0
            accelerator = {
                "cuda_available": available,
                "bf16_supported": bool(torch.cuda.is_bf16_supported()) if available else False,
                "gpu_count": count,
                "gpus": [
                    {
                        "name": torch.cuda.get_device_name(index),
                        "memory_total_mib": int(torch.cuda.get_device_properties(index).total_memory // (1024**2)),
                    }
                    for index in range(count)
                ],
            }
        except Exception as exc:
            accelerator = {
                "cuda_available": False,
                "bf16_supported": False,
                "gpu_count": 0,
                "gpus": [],
                "error": f"{type(exc).__name__}: {exc}",
            }
        return {
            "git_commit": commit.get("output") if commit.get("status") == "ok" else commit,
            "git_tracked_status": status.get("output") if status.get("status") == "ok" else status,
            "python_version": list(sys.version_info[:3]),
            "packages": _packages(),
            "disk_free_bytes": disk.free,
            "accelerator": accelerator,
        }


def read_profile(path: Path) -> dict[str, Any]:
    profile = json.loads(path.read_text(encoding="utf-8"))
    expected_keys = {"schema_version", "python_minimum", "packages", "accelerator", "disk_free_bytes_minimum"}
    if not isinstance(profile, dict) or set(profile) != expected_keys or profile["schema_version"] != 1:
        raise ValueError("invalid execution profile schema")
    if not isinstance(profile["python_minimum"], list) or len(profile["python_minimum"]) != 2:
        raise ValueError("profile.python_minimum must be [major, minor]")
    if not isinstance(profile["packages"], dict) or set(profile["packages"]) != set(PACKAGE_NAMES):
        raise ValueError("profile.packages must pin every Mark2 dependency")
    expected_accelerator = {"cuda_required", "bf16_required", "gpu_count", "gpu_name", "memory_total_mib_minimum"}
    if not isinstance(profile["accelerator"], dict) or set(profile["accelerator"]) != expected_accelerator:
        raise ValueError("invalid profile.accelerator schema")
    return profile


def _check(name: str, expected: Any, actual: Any, passed: bool, reason: str) -> dict[str, Any]:
    return {"name": name, "expected": expected, "actual": actual, "passed": passed, "reason": reason}


def evaluate_preflight(profile: dict[str, Any], expected_commit: str, probe: SystemProbe) -> dict[str, Any]:
    """Evaluate every host requirement and return a complete diagnostic report."""
    if not FULL_SHA.fullmatch(expected_commit):
        raise ValueError("expected commit must be a full 40-character lowercase commit SHA")
    actual = probe.snapshot()
    checks: list[dict[str, Any]] = []

    commit = actual["git_commit"]
    checks.append(_check("git_commit", expected_commit, commit, commit == expected_commit, "checkout must match approved commit"))
    status = actual["git_tracked_status"]
    checks.append(_check("git_tracked_files_clean", "", status, status == "", "tracked files must have no uncommitted changes"))

    minimum_python = tuple(profile["python_minimum"])
    python_version = tuple(actual["python_version"])
    checks.append(
        _check("python_version", {"minimum": list(minimum_python)}, list(python_version), python_version[:2] >= minimum_python, "Python must meet the execution profile minimum")
    )
    for name, version in profile["packages"].items():
        installed = actual["packages"].get(name)
        checks.append(_check(f"package:{name}", version, installed, installed == version, "dependency must match the exact pin"))

    accelerator = actual["accelerator"]
    cuda_expected = profile["accelerator"]["cuda_required"]
    checks.append(_check("cuda_available", cuda_expected, accelerator.get("cuda_available"), accelerator.get("cuda_available") is cuda_expected, "CUDA availability must match profile"))
    bf16_expected = profile["accelerator"]["bf16_required"]
    checks.append(_check("bf16_supported", bf16_expected, accelerator.get("bf16_supported"), accelerator.get("bf16_supported") is bf16_expected, "GPU must support BF16"))
    count_expected = profile["accelerator"]["gpu_count"]
    count_actual = accelerator.get("gpu_count")
    checks.append(_check("gpu_count", count_expected, count_actual, count_actual == count_expected, "GPU count must match profile"))
    gpus = accelerator.get("gpus", [])
    gpu = gpus[0] if len(gpus) == 1 else {}
    name_expected = profile["accelerator"]["gpu_name"]
    checks.append(_check("gpu_name", name_expected, gpu.get("name"), gpu.get("name") == name_expected, "GPU model must match profile"))
    memory_minimum = profile["accelerator"]["memory_total_mib_minimum"]
    memory_actual = gpu.get("memory_total_mib")
    memory_passed = isinstance(memory_actual, int) and memory_actual >= memory_minimum
    checks.append(_check("gpu_memory_total_mib", {"minimum": memory_minimum}, memory_actual, memory_passed, "GPU VRAM must meet profile minimum"))
    disk_minimum = profile["disk_free_bytes_minimum"]
    disk_actual = actual["disk_free_bytes"]
    checks.append(_check("disk_free_bytes", {"minimum": disk_minimum}, disk_actual, disk_actual >= disk_minimum, "filesystem must have enough free space before download"))

    return {
        "schema_version": 1,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "passed": all(item["passed"] for item in checks),
        "expected_commit": expected_commit,
        "profile": profile,
        "observed": actual,
        "checks": checks,
    }
