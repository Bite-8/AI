import json
import subprocess
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from mark2 import instance


def config():
    return instance.read_instance_config()


class FakeBackend:
    def __init__(self, ec2_state="running", ping_status="Online"):
        self.ec2_state = ec2_state
        self.ping_status = ping_status
        self.calls = []
        self.command_status = "Success"

    def describe_ec2(self, instance_id):
        self.calls.append(("describe_ec2", instance_id))
        return {"instance_id": instance_id, "state": self.ec2_state}

    def describe_ssm(self, instance_id):
        self.calls.append(("describe_ssm", instance_id))
        return {"instance_id": instance_id, "ping_status": self.ping_status}

    def start(self, instance_id):
        self.calls.append(("start", instance_id))
        self.ec2_state = "running"
        self.ping_status = "Online"

    def stop(self, instance_id):
        self.calls.append(("stop", instance_id))
        self.ec2_state = "stopped"
        self.ping_status = "ConnectionLost"

    def send_command(self, instance_id, commands, timeout):
        self.calls.append(("send_command", instance_id, commands, timeout))
        return "command-1"

    def command_result(self, instance_id, command_id):
        self.calls.append(("command_result", instance_id, command_id))
        return {
            "command_id": command_id,
            "status": self.command_status,
            "response_code": 0 if self.command_status == "Success" else 1,
            "stdout": "ok",
            "stderr": "",
        }

    def session(self, instance_id):
        self.calls.append(("session", instance_id))


class ConfigTests(unittest.TestCase):
    def test_fixed_target_and_commands_are_valid(self):
        value = config()
        self.assertEqual(value["region"], "ap-northeast-1")
        self.assertEqual(value["instance_id"], "i-0fb8c2572680019af")
        self.assertEqual(set(value["run_commands"]), {"inventory"})

    def test_target_override_is_rejected(self):
        for field, replacement, message in (
            ("instance_id", "i-00000000000000000", "approved target"),
            ("region", "us-east-1", "must be ap-northeast-1"),
        ):
            value = config()
            value[field] = replacement
            with self.subTest(field=field), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "config.json"
                path.write_text(json.dumps(value), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, message):
                    instance.read_instance_config(path)


class ControllerTests(unittest.TestCase):
    def test_status_returns_verified_target(self):
        result = instance.InstanceController(config(), FakeBackend()).status()
        self.assertEqual(result["region"], "ap-northeast-1")
        self.assertEqual(result["ec2"]["state"], "running")
        self.assertEqual(result["ssm"]["ping_status"], "Online")

    def test_mismatched_instance_id_stops_before_action(self):
        backend = FakeBackend()
        backend.describe_ec2 = lambda unused: {"instance_id": "i-wrong", "state": "running"}
        with self.assertRaisesRegex(instance.InstanceError, "does not match"):
            instance.InstanceController(config(), backend).stop()
        self.assertNotIn("stop", [call[0] for call in backend.calls])

    def test_unexpected_state_and_ssm_offline_stop_before_action(self):
        for backend, message in (
            (FakeBackend("pending", "Online"), "refuses EC2 state"),
            (FakeBackend("running", "ConnectionLost"), "not SSM Online"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(instance.InstanceError, message):
                instance.InstanceController(config(), backend).stop()
            self.assertNotIn("stop", [call[0] for call in backend.calls])

    def test_start_requires_exact_confirmation(self):
        backend = FakeBackend("stopped", "ConnectionLost")
        with self.assertRaisesRegex(instance.InstanceError, "requires --confirm-start"):
            instance.InstanceController(config(), backend).start(None)
        self.assertEqual(backend.calls, [])

    def test_start_and_stop_normal_paths(self):
        backend = FakeBackend("stopped", "ConnectionLost")
        controller = instance.InstanceController(config(), backend, sleep=lambda unused: None)
        observed = []
        started = controller.start(config()["instance_id"], before_start=observed.append)
        self.assertEqual(started["ec2"]["state"], "running")
        self.assertEqual(observed[0]["ec2"]["state"], "stopped")
        stopped = controller.stop()
        self.assertEqual(stopped["ec2"]["state"], "stopped")
        self.assertEqual([call[0] for call in backend.calls].count("start"), 1)
        self.assertEqual([call[0] for call in backend.calls].count("stop"), 1)

    def test_timeout_is_finite(self):
        value = deepcopy(config())
        value["timeouts"].update(start_seconds=1, poll_seconds=1)
        backend = FakeBackend("stopped", "ConnectionLost")
        backend.start = lambda instance_id: backend.calls.append(("start", instance_id))
        ticks = iter((0, 0, 1))
        controller = instance.InstanceController(value, backend, monotonic=lambda: next(ticks), sleep=lambda unused: None)
        with self.assertRaisesRegex(instance.InstanceError, "timed out"):
            controller.start(value["instance_id"])

    def test_run_command_uses_only_repository_allowlist(self):
        backend = FakeBackend()
        controller = instance.InstanceController(config(), backend)
        result = controller.run_command("inventory")
        self.assertEqual(result["status"], "Success")
        call = next(call for call in backend.calls if call[0] == "send_command")
        self.assertEqual(call[2], config()["run_commands"]["inventory"])
        with self.assertRaisesRegex(instance.InstanceError, "unknown repository command"):
            controller.run_command("echo-secret")

    def test_run_command_failure_is_reported(self):
        backend = FakeBackend()
        backend.command_status = "Failed"
        with self.assertRaisesRegex(instance.InstanceError, "status Failed and response code 1"):
            instance.InstanceController(config(), backend).run_command("inventory")

    def test_session_requires_running_online_target(self):
        backend = FakeBackend()
        instance.InstanceController(config(), backend).session()
        self.assertIn(("session", config()["instance_id"]), backend.calls)
        offline = FakeBackend("running", "ConnectionLost")
        with self.assertRaisesRegex(instance.InstanceError, "not SSM Online"):
            instance.InstanceController(config(), offline).session()


class AwsCliBackendTests(unittest.TestCase):
    def test_ec2_lookup_requires_exactly_one_result(self):
        responses = (
            {"Reservations": []},
            {"Reservations": [{"Instances": [{}, {}]}]},
        )
        for payload in responses:
            with self.subTest(count=len(payload["Reservations"])):
                def runner(args, **kwargs):
                    return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")

                backend = instance.AwsCliBackend("ap-northeast-1", "i-fixed", runner=runner)
                with self.assertRaisesRegex(instance.InstanceError, "expected exactly one"):
                    backend.describe_ec2("i-fixed")

    def test_send_command_passes_json_as_one_argument_without_shell(self):
        calls = []

        def runner(args, **kwargs):
            calls.append((args, kwargs))
            return subprocess.CompletedProcess(args, 0, json.dumps({"Command": {"CommandId": "abc"}}), "")

        backend = instance.AwsCliBackend("ap-northeast-1", "i-fixed", runner=runner)
        self.assertEqual(backend.send_command("i-fixed", ["uname -r", "python3 --version"], 30), "abc")
        args, kwargs = calls[0]
        parameter = args[args.index("--parameters") + 1]
        self.assertEqual(json.loads(parameter), {"commands": ["uname -r", "python3 --version"]})
        self.assertNotIn("shell", kwargs)

    def test_permission_error_is_sanitized(self):
        def runner(args, **kwargs):
            return subprocess.CompletedProcess(args, 255, "", "AccessDenied for arn:aws:iam::123456789012:role/test")

        backend = instance.AwsCliBackend("ap-northeast-1", "i-fixed", runner=runner)
        with self.assertRaisesRegex(instance.InstanceError, r"\[redacted-arn\]"):
            backend.describe_ssm("i-fixed")


if __name__ == "__main__":
    unittest.main()
