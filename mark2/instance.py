"""Safely inspect and operate the fixed Mark2 GPU instance through EC2 and SSM."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable


PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG = PACKAGE_DIR / "configs" / "gpu_instance.json"
EC2_STATES = {"pending", "running", "shutting-down", "terminated", "stopping", "stopped"}
TERMINAL_COMMAND_STATES = {"Success", "Cancelled", "TimedOut", "Failed", "Cancelling"}


class InstanceError(RuntimeError):
    """A safe, user-facing failure that must stop the requested operation."""


class CommandInvocationNotReady(InstanceError):
    """The newly sent SSM command is not visible to GetCommandInvocation yet."""


def _exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError(f"{label} must contain exactly: {', '.join(sorted(expected))}")
    return value


def read_instance_config(path: Path = DEFAULT_CONFIG) -> dict[str, Any]:
    config = _exact_keys(
        json.loads(path.read_text(encoding="utf-8")),
        {"schema_version", "region", "instance_id", "timeouts", "run_commands"},
        "instance config",
    )
    if config["schema_version"] != 1:
        raise ValueError("instance config schema_version must be 1")
    if config["region"] != "ap-northeast-1":
        raise ValueError("instance config region must be ap-northeast-1")
    if config["instance_id"] != "i-0fb8c2572680019af":
        raise ValueError("instance config instance_id does not match the approved target")
    timeouts = _exact_keys(
        config["timeouts"],
        {"start_seconds", "stop_seconds", "command_seconds", "poll_seconds"},
        "timeouts",
    )
    for name, value in timeouts.items():
        if type(value) is not int or value <= 0:
            raise ValueError(f"timeouts.{name} must be a positive integer")
    if timeouts["poll_seconds"] > min(timeouts["start_seconds"], timeouts["stop_seconds"]):
        raise ValueError("poll_seconds must not exceed a transition timeout")
    commands = config["run_commands"]
    if not isinstance(commands, dict) or not commands:
        raise ValueError("run_commands must define at least one repository command")
    for name, lines in commands.items():
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", name):
            raise ValueError("run command names must be lowercase stable identifiers")
        if not isinstance(lines, list) or not lines or not all(isinstance(line, str) and line for line in lines):
            raise ValueError(f"run_commands.{name} must be a non-empty list of command strings")
    return config


def _redact(message: str) -> str:
    message = re.sub(r"arn:aws(?:-[a-z]+)?:[^\s]+", "[redacted-arn]", message)
    message = re.sub(r"(?<!\d)\d{12}(?!\d)", "[redacted-account]", message)
    message = re.sub(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b", "[redacted-access-key]", message)
    return message.strip()


class AwsCliBackend:
    """AWS process boundary; tests replace this class or its runner."""

    def __init__(
        self,
        region: str,
        instance_id: str,
        runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.region = region
        self.instance_id = instance_id
        self.runner = runner

    def _target(self, instance_id: str) -> None:
        if instance_id != self.instance_id:
            raise InstanceError("AWS backend refused an instance ID other than the fixed target")

    def _run(self, service_args: list[str], timeout: int = 30, interactive: bool = False) -> Any:
        args = ["aws", *service_args, "--region", self.region]
        try:
            result = self.runner(
                args,
                text=True,
                capture_output=not interactive,
                timeout=None if interactive else timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise InstanceError(
                f"AWS CLI failed during {service_args[0]} {service_args[1]} "
                f"for fixed target {self.instance_id}: {type(exc).__name__}"
            ) from exc
        if result.returncode:
            detail = _redact(getattr(result, "stderr", "") or "")
            if len(detail) > 500:
                detail = detail[:500] + "..."
            error_type = (
                CommandInvocationNotReady
                if service_args[:2] == ["ssm", "get-command-invocation"]
                and re.search(r"\bInvocationDoesNotExist\b", detail)
                else InstanceError
            )
            raise error_type(
                f"AWS CLI failed during {service_args[0]} {service_args[1]} for fixed target {self.instance_id}"
                + (f": {detail}" if detail else "")
            )
        if interactive:
            return None
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise InstanceError(f"AWS CLI returned invalid JSON during {service_args[0]} {service_args[1]}") from exc

    def describe_ec2(self, instance_id: str) -> dict[str, Any]:
        self._target(instance_id)
        payload = self._run(
            ["ec2", "describe-instances", "--instance-ids", instance_id, "--output", "json"]
        )
        reservations = payload.get("Reservations", []) if isinstance(payload, dict) else []
        instances = [item for reservation in reservations for item in reservation.get("Instances", [])]
        if len(instances) != 1:
            raise InstanceError(f"EC2 target lookup returned {len(instances)} instances; expected exactly one")
        item = instances[0]
        return {
            "instance_id": item.get("InstanceId"),
            "state": (item.get("State") or {}).get("Name"),
            "image_id": item.get("ImageId"),
            "instance_type": item.get("InstanceType"),
            "architecture": item.get("Architecture"),
            "root_device_name": item.get("RootDeviceName"),
            "block_devices": [
                {
                    "device_name": device.get("DeviceName"),
                    "delete_on_termination": (device.get("Ebs") or {}).get("DeleteOnTermination"),
                }
                for device in item.get("BlockDeviceMappings", [])
            ],
        }

    def describe_ssm(self, instance_id: str) -> dict[str, Any]:
        self._target(instance_id)
        payload = self._run(
            [
                "ssm",
                "describe-instance-information",
                "--filters",
                f"Key=InstanceIds,Values={instance_id}",
                "--output",
                "json",
            ]
        )
        items = payload.get("InstanceInformationList", []) if isinstance(payload, dict) else []
        if len(items) != 1:
            raise InstanceError(f"SSM target lookup returned {len(items)} managed instances; expected exactly one")
        item = items[0]
        return {
            "instance_id": item.get("InstanceId"),
            "ping_status": item.get("PingStatus"),
            "agent_version": item.get("AgentVersion"),
            "platform_type": item.get("PlatformType"),
            "platform_name": item.get("PlatformName"),
            "platform_version": item.get("PlatformVersion"),
        }

    def start(self, instance_id: str) -> None:
        self._target(instance_id)
        self._run(["ec2", "start-instances", "--instance-ids", instance_id, "--output", "json"])

    def stop(self, instance_id: str) -> None:
        self._target(instance_id)
        self._run(["ec2", "stop-instances", "--instance-ids", instance_id, "--output", "json"])

    def send_command(self, instance_id: str, commands: list[str], timeout: int) -> str:
        self._target(instance_id)
        payload = self._run(
            [
                "ssm",
                "send-command",
                "--instance-ids",
                instance_id,
                "--document-name",
                "AWS-RunShellScript",
                "--parameters",
                json.dumps({"commands": commands}, separators=(",", ":")),
                "--timeout-seconds",
                str(timeout),
                "--output",
                "json",
            ]
        )
        command_id = (payload.get("Command") or {}).get("CommandId") if isinstance(payload, dict) else None
        if not isinstance(command_id, str) or not command_id:
            raise InstanceError("SSM send-command did not return a command ID")
        return command_id

    def command_result(self, instance_id: str, command_id: str) -> dict[str, Any]:
        self._target(instance_id)
        payload = self._run(
            [
                "ssm",
                "get-command-invocation",
                "--instance-id",
                instance_id,
                "--command-id",
                command_id,
                "--output",
                "json",
            ]
        )
        return {
            "command_id": command_id,
            "status": payload.get("Status"),
            "response_code": payload.get("ResponseCode"),
            "stdout": payload.get("StandardOutputContent", ""),
            "stderr": payload.get("StandardErrorContent", ""),
        }

    def session(self, instance_id: str) -> None:
        self._target(instance_id)
        self._run(["ssm", "start-session", "--target", instance_id], interactive=True)


class InstanceController:
    def __init__(
        self,
        config: dict[str, Any],
        backend: Any,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config
        self.backend = backend
        self.monotonic = monotonic
        self.sleep = sleep
        self.instance_id = config["instance_id"]

    def inspect(self) -> dict[str, Any]:
        ec2 = self.backend.describe_ec2(self.instance_id)
        if ec2.get("instance_id") != self.instance_id:
            raise InstanceError("EC2 response instance ID does not match the fixed target")
        state = ec2.get("state")
        if state not in EC2_STATES or state in {"terminated", "shutting-down"}:
            raise InstanceError(f"EC2 target has forbidden or unknown state: {state!r}")
        ssm = self.backend.describe_ssm(self.instance_id)
        if ssm.get("instance_id") != self.instance_id:
            raise InstanceError("SSM response instance ID does not match the fixed target")
        return {"region": self.config["region"], "ec2": ec2, "ssm": ssm}

    @staticmethod
    def _require_online(snapshot: dict[str, Any]) -> None:
        if snapshot["ssm"].get("ping_status") != "Online":
            raise InstanceError("fixed target is not SSM Online")

    def status(self) -> dict[str, Any]:
        return self.inspect()

    def _wait(self, action: str, timeout: int) -> dict[str, Any]:
        deadline = self.monotonic() + timeout
        while True:
            snapshot = self.inspect()
            state = snapshot["ec2"]["state"]
            if action == "start" and state == "running" and snapshot["ssm"].get("ping_status") == "Online":
                return snapshot
            if action == "stop" and state == "stopped":
                return snapshot
            if self.monotonic() >= deadline:
                raise InstanceError(f"{action} timed out after {timeout} seconds for fixed target {self.instance_id}")
            self.sleep(self.config["timeouts"]["poll_seconds"])

    def start(
        self,
        confirmation: str | None,
        before_start: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        if confirmation != self.instance_id:
            raise InstanceError(f"start requires --confirm-start {self.instance_id}")
        snapshot = self.inspect()
        if before_start is not None:
            before_start(snapshot)
        state = snapshot["ec2"]["state"]
        if state == "running":
            self._require_online(snapshot)
            return snapshot
        if state != "stopped":
            raise InstanceError(f"start refuses EC2 state {state!r}")
        self.backend.start(self.instance_id)
        return self._wait("start", self.config["timeouts"]["start_seconds"])

    def stop(self) -> dict[str, Any]:
        snapshot = self.inspect()
        state = snapshot["ec2"]["state"]
        if state == "stopped":
            return snapshot
        if state != "running":
            raise InstanceError(f"stop refuses EC2 state {state!r}")
        self._require_online(snapshot)
        self.backend.stop(self.instance_id)
        return self._wait("stop", self.config["timeouts"]["stop_seconds"])

    def run_command(self, name: str) -> dict[str, Any]:
        snapshot = self.inspect()
        if snapshot["ec2"]["state"] != "running":
            raise InstanceError("run-command requires the fixed target to be running")
        self._require_online(snapshot)
        commands = self.config["run_commands"].get(name)
        if commands is None:
            raise InstanceError(f"unknown repository command: {name}")
        timeout = self.config["timeouts"]["command_seconds"]
        command_id = self.backend.send_command(self.instance_id, list(commands), timeout)
        deadline = self.monotonic() + timeout
        while True:
            try:
                result = self.backend.command_result(self.instance_id, command_id)
            except CommandInvocationNotReady:
                if self.monotonic() >= deadline:
                    raise InstanceError(f"SSM Run Command {command_id} timed out after {timeout} seconds")
                self.sleep(self.config["timeouts"]["poll_seconds"])
                continue
            status = result.get("status")
            if status in TERMINAL_COMMAND_STATES:
                if status != "Success" or result.get("response_code") != 0:
                    raise InstanceError(
                        f"SSM Run Command {command_id} finished with status {status} "
                        f"and response code {result.get('response_code')!r}"
                    )
                return result
            if self.monotonic() >= deadline:
                raise InstanceError(f"SSM Run Command {command_id} timed out after {timeout} seconds")
            self.sleep(self.config["timeouts"]["poll_seconds"])

    def session(self) -> None:
        snapshot = self.inspect()
        if snapshot["ec2"]["state"] != "running":
            raise InstanceError("session requires the fixed target to be running")
        self._require_online(snapshot)
        self.backend.session(self.instance_id)


def build_parser(config: dict[str, Any]) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("status", help="inspect the fixed EC2 and SSM target")
    start = actions.add_parser("start", help="start the stopped fixed target and wait for SSM")
    start.add_argument("--confirm-start", help="must exactly equal the fixed instance ID")
    actions.add_parser("stop", help="normally stop the running fixed target")
    command = actions.add_parser("run-command", help="run one repository-defined SSM command")
    command.add_argument("name", choices=sorted(config["run_commands"]))
    actions.add_parser("session", help="open an SSM Session Manager session (no SSH fallback)")
    return parser


def main() -> int:
    try:
        config = read_instance_config()
        args = build_parser(config).parse_args()
        controller = InstanceController(config, AwsCliBackend(config["region"], config["instance_id"]))
        if args.action == "status":
            result = controller.status()
        elif args.action == "start":
            result = controller.start(
                args.confirm_start,
                before_start=lambda snapshot: print(
                    "WARNING: start begins paid usage for "
                    f"{config['region']} / {config['instance_id']}; "
                    f"current EC2 state={snapshot['ec2']['state']}",
                    file=sys.stderr,
                ),
            )
        elif args.action == "stop":
            result = controller.stop()
        elif args.action == "run-command":
            result = controller.run_command(args.name)
        else:
            controller.session()
            result = {"region": config["region"], "instance_id": config["instance_id"], "session": "ended"}
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (InstanceError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {_redact(str(exc))}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
