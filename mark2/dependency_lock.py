"""Offline validation for the fixed-target Mark2 Python dependency lock."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_LOCK = PACKAGE_DIR / "dependency-lock.json"
DEFAULT_HASHED_REQUIREMENTS = PACKAGE_DIR / "requirements.lock"
DEFAULT_DIRECT_REQUIREMENTS = PACKAGE_DIR / "requirements.txt"
DEFAULT_PROFILE = PACKAGE_DIR / "configs" / "qwen35_9b_l4_profile.json"

SHA256 = re.compile(r"^[0-9a-f]{64}$")
VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+!-]*$")
LOCKED_REQUIREMENT = re.compile(
    r"^([a-z0-9]+(?:-[a-z0-9]+)*)==([^\s;@<>=]+) --hash=sha256:([0-9a-f]{64})$"
)
EXPECTED_TARGET = {
    "operating_system": "linux",
    "platform_system": "Linux",
    "platform_machine": "x86_64",
    "python_version": "3.14",
    "implementation": "cp",
    "abi": "cp314",
    "manylinux_ceiling": "manylinux_2_28_x86_64",
}
EXPECTED_SOURCE = {
    "index_url": "https://pypi.org/simple",
    "artifact_host": "files.pythonhosted.org",
    "only_binary": True,
}


def _exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{label} must contain exactly: {', '.join(sorted(expected))}")
    return value


def canonical_project_name(value: Any, label: str = "project name") -> str:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be a canonical project name")
    canonical = re.sub(r"[-_.]+", "-", value).lower()
    if value != canonical or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value):
        raise ValueError(f"{label} must be a canonical project name")
    return value


def _exact_version(value: Any, label: str) -> str:
    if not isinstance(value, str) or not VERSION.fullmatch(value):
        raise ValueError(f"{label} must be one exact version without a marker, URL, or constraint")
    return value


def parse_direct_requirements(text: str) -> dict[str, str]:
    requirements: dict[str, str] = {}
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.count("==") != 1:
            raise ValueError(f"direct requirements line {number} must be an exact pin")
        name, version = line.split("==")
        name = canonical_project_name(name, f"direct requirements line {number} name")
        version = _exact_version(version, f"direct requirements line {number} version")
        if name in requirements:
            raise ValueError(f"duplicate direct requirement: {name}")
        requirements[name] = version
    if not requirements:
        raise ValueError("direct requirements must not be empty")
    return requirements


def parse_hashed_requirements(text: str) -> dict[str, tuple[str, str]]:
    index_seen = False
    binary_seen = False
    packages: dict[str, tuple[str, str]] = {}
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line == "--index-url https://pypi.org/simple":
            if index_seen:
                raise ValueError("requirements.lock contains duplicate --index-url")
            index_seen = True
            continue
        if line == "--only-binary :all:":
            if binary_seen:
                raise ValueError("requirements.lock contains duplicate --only-binary")
            binary_seen = True
            continue
        match = LOCKED_REQUIREMENT.fullmatch(line)
        if not match:
            raise ValueError(
                f"requirements.lock line {number} must be an exact pin with one SHA-256 hash"
            )
        name = canonical_project_name(match.group(1), f"requirements.lock line {number} name")
        version = _exact_version(match.group(2), f"requirements.lock line {number} version")
        if name in packages:
            raise ValueError(f"requirements.lock contains duplicate project: {name}")
        packages[name] = (version, match.group(3))
    if not index_seen or not binary_seen:
        raise ValueError("requirements.lock must fix the PyPI index and allow wheels only")
    return packages


def validate_dependency_lock(
    lock: Any,
    direct_requirements: dict[str, str],
    profile: Any,
    hashed_requirements_text: str,
) -> dict[str, Any]:
    lock = _exact_keys(
        lock,
        {"schema_version", "target", "source", "generator", "direct_requirements", "resolution", "packages"},
        "dependency lock",
    )
    if lock["schema_version"] != 1:
        raise ValueError("dependency lock schema_version must be 1")
    if lock["target"] != EXPECTED_TARGET:
        raise ValueError(
            "dependency lock target must be Linux x86_64 / CPython 3.14 / manylinux_2_28 ceiling"
        )
    if lock["source"] != EXPECTED_SOURCE:
        raise ValueError("dependency lock source must be the single approved PyPI wheel source")

    generator = _exact_keys(lock["generator"], {"name", "version", "command"}, "generator")
    if generator["name"] != "pip" or generator["version"] != "26.0":
        raise ValueError("dependency lock must record the approved pip 26.0 resolver")
    if not isinstance(generator["command"], list) or not generator["command"] or not all(
        isinstance(item, str) and item for item in generator["command"]
    ):
        raise ValueError("generator.command must be a non-empty string array")
    command_text = " ".join(generator["command"])
    for required in (
        "--dry-run",
        "--only-binary=:all:",
        "--python-version=3.14",
        "--implementation=cp",
        "--abi=cp314",
        "--index-url=https://pypi.org/simple",
        "-r=mark2/requirements.txt",
    ):
        if required not in generator["command"]:
            raise ValueError(f"generator.command is missing {required}")
    if "--extra-index-url" in command_text or "--find-links" in command_text:
        raise ValueError("generator.command must not use additional package sources")

    profile = _exact_keys(
        profile,
        {"schema_version", "python_minimum", "packages", "accelerator", "disk_free_bytes_minimum"},
        "execution profile",
    )
    if not isinstance(profile["packages"], dict):
        raise ValueError("execution profile packages must be an object")
    profile_packages = {
        canonical_project_name(name, "execution profile package name"): _exact_version(
            version, f"execution profile package {name} version"
        )
        for name, version in profile["packages"].items()
    }
    if direct_requirements != profile_packages:
        raise ValueError("requirements.txt and execution profile direct pins differ")

    direct_entries = lock["direct_requirements"]
    if not isinstance(direct_entries, list):
        raise ValueError("direct_requirements must be an array")
    locked_direct: dict[str, str] = {}
    for index, entry in enumerate(direct_entries):
        entry = _exact_keys(entry, {"name", "version"}, f"direct_requirements[{index}]")
        name = canonical_project_name(entry["name"], f"direct_requirements[{index}].name")
        if name in locked_direct:
            raise ValueError(f"duplicate direct requirement in lock: {name}")
        locked_direct[name] = _exact_version(entry["version"], f"direct_requirements[{index}].version")
    if locked_direct != direct_requirements:
        raise ValueError("dependency lock direct pins differ from requirements.txt and execution profile")

    package_entries = lock["packages"]
    if not isinstance(package_entries, list) or not package_entries:
        raise ValueError("packages must be a non-empty array")
    packages: dict[str, tuple[str, str]] = {}
    for index, entry in enumerate(package_entries):
        entry = _exact_keys(entry, {"name", "version", "artifact"}, f"packages[{index}]")
        name = canonical_project_name(entry["name"], f"packages[{index}].name")
        if name in packages:
            raise ValueError(f"dependency lock contains duplicate canonical project name: {name}")
        version = _exact_version(entry["version"], f"packages[{index}].version")
        artifact = _exact_keys(entry["artifact"], {"filename", "url", "sha256"}, f"packages[{index}].artifact")
        filename = artifact["filename"]
        url = artifact["url"]
        digest = artifact["sha256"]
        if not isinstance(filename, str) or not filename.endswith(".whl") or "/" in filename:
            raise ValueError(f"packages[{index}] artifact must be one wheel filename")
        if not isinstance(url, str):
            raise ValueError(f"packages[{index}] artifact URL must be a string")
        parsed = urlparse(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname != EXPECTED_SOURCE["artifact_host"]
            or parsed.query
            or parsed.fragment
            or unquote(parsed.path).rsplit("/", 1)[-1] != filename
        ):
            raise ValueError(f"packages[{index}] artifact must use the approved PyPI file URL")
        if not isinstance(digest, str) or not SHA256.fullmatch(digest):
            raise ValueError(f"packages[{index}] artifact must have one lowercase SHA-256")
        packages[name] = (version, digest)

    resolution = _exact_keys(lock["resolution"], {"package_count", "package_names"}, "resolution")
    names = sorted(packages)
    if resolution["package_count"] != len(names) or resolution["package_names"] != names:
        raise ValueError("resolution package manifest must exactly match the locked dependency closure")
    missing_direct = sorted(set(direct_requirements) - set(packages))
    if missing_direct:
        raise ValueError(f"locked dependency closure is missing direct requirements: {', '.join(missing_direct)}")
    for name, version in direct_requirements.items():
        if packages[name][0] != version:
            raise ValueError(f"locked direct requirement version differs for {name}")

    hashed = parse_hashed_requirements(hashed_requirements_text)
    if hashed != packages:
        raise ValueError("requirements.lock does not exactly match dependency-lock.json")
    return lock


def read_dependency_lock(
    lock_path: Path = DEFAULT_LOCK,
    direct_requirements_path: Path = DEFAULT_DIRECT_REQUIREMENTS,
    profile_path: Path = DEFAULT_PROFILE,
    hashed_requirements_path: Path = DEFAULT_HASHED_REQUIREMENTS,
) -> dict[str, Any]:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    direct = parse_direct_requirements(direct_requirements_path.read_text(encoding="utf-8"))
    hashed = hashed_requirements_path.read_text(encoding="utf-8")
    return validate_dependency_lock(lock, direct, profile, hashed)


def dependency_lock_sha256(lock: Any) -> str:
    payload = json.dumps(lock, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
