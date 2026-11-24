#!/usr/bin/env python3
"""Convert a pip 26.0 dry-run report into the reviewed Mark2 lock pair."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlparse

try:
    from packaging.markers import default_environment
    from packaging.requirements import Requirement
except ModuleNotFoundError:  # pip vendors packaging in the approved generation environment.
    from pip._vendor.packaging.markers import default_environment
    from pip._vendor.packaging.requirements import Requirement


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIR = ROOT / "mark2"


def canonical_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()


def target_environment() -> dict[str, str]:
    environment = default_environment()
    environment.update(
        {
            "implementation_name": "cpython",
            "platform_machine": "x86_64",
            "platform_python_implementation": "CPython",
            "platform_system": "Linux",
            "python_full_version": "3.14.0",
            "python_version": "3.14",
            "sys_platform": "linux",
            "extra": "",
        }
    )
    return environment


def dependency_graph(items: list[dict], direct_names: set[str]) -> dict[str, list[str]]:
    metadata = {canonical_name(item["metadata"]["name"]): item["metadata"] for item in items}
    dependencies: dict[str, set[str]] = {name: set() for name in metadata}
    requested_extras: dict[str, set[str]] = {name: set() for name in metadata}
    expanded: dict[str, frozenset[str]] = {}
    pending = list(direct_names)
    while pending:
        name = pending.pop()
        if name not in metadata:
            raise ValueError(f"resolver report is missing dependency metadata for {name}")
        extras = frozenset(requested_extras[name])
        if expanded.get(name) == extras:
            continue
        expanded[name] = extras
        for raw in metadata[name].get("requires_dist") or []:
            requirement = Requirement(raw)
            environments = []
            for extra in {"", *extras}:
                environment = target_environment()
                environment["extra"] = extra
                environments.append(environment)
            if requirement.marker and not any(
                requirement.marker.evaluate(environment=environment) for environment in environments
            ):
                continue
            dependency = canonical_name(requirement.name)
            if dependency not in metadata:
                raise ValueError(f"resolver report is missing selected dependency {dependency}")
            dependencies[name].add(dependency)
            new_extras = set(requirement.extras) - requested_extras[dependency]
            if dependency not in expanded or new_extras:
                requested_extras[dependency].update(new_extras)
                pending.append(dependency)
    return {name: sorted(values) for name, values in dependencies.items()}


def resolver_command() -> list[str]:
    platforms = [f"--platform=manylinux_2_{version}_x86_64" for version in range(28, 4, -1)]
    return [
        "python3",
        "-m",
        "pip",
        "install",
        "--dry-run",
        "--ignore-installed",
        "--report=/tmp/mark2-pip-report.json",
        "--only-binary=:all:",
        "--implementation=cp",
        "--python-version=3.14",
        "--abi=cp314",
        *platforms,
        "--platform=manylinux2014_x86_64",
        "--platform=manylinux2010_x86_64",
        "--platform=manylinux1_x86_64",
        "--platform=linux_x86_64",
        "--index-url=https://pypi.org/simple",
        "--requirement=mark2/requirements.txt",
    ]


def build_lock(report: dict) -> dict:
    if report.get("version") != "1" or report.get("pip_version") != "26.0":
        raise ValueError("report must be a pip 26.0 installation report version 1")
    direct = []
    for raw in (PACKAGE_DIR / "requirements.txt").read_text(encoding="utf-8").splitlines():
        if raw and not raw.startswith("#"):
            name, version = raw.split("==")
            direct.append({"name": canonical_name(name), "version": version})
    direct.sort(key=lambda item: item["name"])
    report_items = report.get("install", [])
    dependency_edges = dependency_graph(report_items, {item["name"] for item in direct})
    packages = []
    for item in report_items:
        download = item["download_info"]
        url = download["url"]
        hashes = download["archive_info"].get("hashes", {})
        name = canonical_name(item["metadata"]["name"])
        packages.append(
            {
                "name": name,
                "version": item["metadata"]["version"],
                "dependencies": dependency_edges[name],
                "artifact": {
                    "filename": PurePosixPath(unquote(urlparse(url).path)).name,
                    "url": url,
                    "sha256": hashes["sha256"],
                },
            }
        )
    packages.sort(key=lambda item: item["name"])
    return {
        "schema_version": 1,
        "target": {
            "operating_system": "linux",
            "platform_system": "Linux",
            "platform_machine": "x86_64",
            "python_version": "3.14",
            "implementation": "cp",
            "abi": "cp314",
            "manylinux_ceiling": "manylinux_2_28_x86_64",
        },
        "source": {
            "index_url": "https://pypi.org/simple",
            "artifact_host": "files.pythonhosted.org",
            "only_binary": True,
        },
        "generator": {"name": "pip", "version": "26.0", "command": resolver_command()},
        "direct_requirements": direct,
        "resolution": {
            "package_count": len(packages),
            "package_names": [item["name"] for item in packages],
        },
        "packages": packages,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="pip 26.0 --report JSON from the recorded resolver command")
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    lock = build_lock(report)
    (PACKAGE_DIR / "dependency-lock.json").write_text(
        json.dumps(lock, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Generated from dependency-lock.json for Linux x86_64 / CPython 3.14.",
        "# Regenerate and review both files together; do not edit this file alone.",
        "--index-url https://pypi.org/simple",
        "--only-binary :all:",
    ]
    lines.extend(
        f"{item['name']}=={item['version']} --hash=sha256:{item['artifact']['sha256']}"
        for item in lock["packages"]
    )
    (PACKAGE_DIR / "requirements.lock").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
