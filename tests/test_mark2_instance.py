import json
import subprocess
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

from mark2 import instance


def config():
    return instance.read_instance_config()


class FakeBackend:
    def __init__(
        self,
        ec2_state="running",
        ping_status="Online",
        ssm_present=True,
        agent_version="3.3.1957.0",
    ):
        self.ec2_state = ec2_state
        self.ping_status = ping_status
        self.ssm_present = ssm_present
        self.agent_version = agent_version
        self.calls = []
        self.command_status = "Success"

    def describe_ec2(self, instance_id):
        self.calls.append(("describe_ec2", instance_id))
        return {"instance_id": instance_id, "state": self.ec2_state}

    def describe_ssm(self, instance_id):
        self.calls.append(("describe_ssm", instance_id))
        if not self.ssm_present:
            raise instance.SsmTargetNotFound("no managed-instance record")
        return {
            "instance_id": instance_id,
            "ping_status": self.ping_status,
            "agent_version": self.agent_version,
            "platform_type": "Linux",
            "platform_name": "Ubuntu",
            "platform_version": "22.04",
        }

    def start(self, instance_id):
        self.calls.append(("start", instance_id))
        self.ec2_state = "running"
        self.ping_status = "Online"
        self.ssm_present = True

    def stop(self, instance_id):
        self.calls.append(("stop", instance_id))
        self.ec2_state = "stopped"
        self.ssm_present = False

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

    def check_run_command(self, instance_id, commands, timeout):
        self.calls.append(("check_run_command", instance_id, commands, timeout))
        return {"transport": "fake", "api_mutation": False}

    def check_session_client(self):
        self.calls.append(("check_session_client",))
        return {
            "api_mutation": False,
            "executable": "/usr/local/bin/session-manager-plugin",
            "minimum_version": "1.2.764.0",
            "standalone_verification": "passed",
            "version": "1.2.764.0",
        }

    def session(self, instance_id):
        self.calls.append(("session", instance_id))


class TransitionBackend(FakeBackend):
    """Return one EC2/SSM observation per inspect call without real waiting."""

    def __init__(self, observations):
        super().__init__("stopped", ssm_present=False)
        self.observations = list(observations)
        self.current = None

    def describe_ec2(self, instance_id):
        self.calls.append(("describe_ec2", instance_id))
        if not self.observations:
            raise AssertionError("unexpected extra transition observation")
        self.current = self.observations[0]
        return {"instance_id": instance_id, "state": self.current[0]}

    def describe_ssm(self, instance_id):
        self.calls.append(("describe_ssm", instance_id))
        _, ssm = self.observations.pop(0)
        if isinstance(ssm, Exception):
            raise ssm
        if ssm is None:
            raise instance.SsmTargetNotFound("no managed-instance record")
        if isinstance(ssm, dict):
            return ssm
        return {"instance_id": instance_id, "ping_status": ssm}

    def start(self, instance_id):
        self.calls.append(("start", instance_id))


class ConfigTests(unittest.TestCase):
    def test_fixed_target_and_commands_are_valid(self):
        value = config()
        self.assertEqual(value["region"], "ap-northeast-1")
        self.assertEqual(value["instance_id"], "i-0fb8c2572680019af")
        self.assertEqual(set(value["run_commands"]), {"inventory"})
        self.assertNotIn("amazon-ssm-agent -version", value["run_commands"]["inventory"])
        self.assertEqual(
            value["run_commands"]["inventory"],
            [
                "cat /etc/os-release",
                "uname -r",
                "python3 --version",
                "nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader",
                "nvidia-smi",
            ],
        )

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
        self.assertIs(result["ssm"]["record_present"], True)
        self.assertEqual(result["ssm"]["ping_status"], "Online")

    def test_stopped_status_accepts_explicit_ssm_absence(self):
        result = instance.InstanceController(config(), FakeBackend("stopped", ssm_present=False)).status()
        self.assertEqual(result["ec2"]["state"], "stopped")
        self.assertEqual(result["ssm"], {"record_present": False})

    def test_ssm_absence_is_rejected_unless_ec2_is_stopped(self):
        for state in ("pending", "running", "stopping"):
            with self.subTest(state=state), self.assertRaisesRegex(
                instance.InstanceError, f"no managed-instance record while EC2 state is '{state}'"
            ):
                instance.InstanceController(config(), FakeBackend(state, ssm_present=False)).status()

    def test_stopped_status_does_not_hide_other_ssm_failures(self):
        backend = FakeBackend("stopped")
        backend.describe_ssm = lambda unused: (_ for _ in ()).throw(instance.InstanceError("AccessDenied"))
        with self.assertRaisesRegex(instance.InstanceError, "AccessDenied"):
            instance.InstanceController(config(), backend).status()

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

    def test_start_client_failure_precedes_aws_inspection(self):
        backend = FakeBackend("stopped", ssm_present=False)
        backend.check_session_client = lambda: (_ for _ in ()).throw(
            instance.InstanceError("local client unavailable")
        )
        with self.assertRaisesRegex(instance.InstanceError, "local client unavailable"):
            instance.InstanceController(config(), backend).start(config()["instance_id"])
        self.assertEqual(backend.calls, [])

    def test_start_and_stop_normal_paths(self):
        backend = FakeBackend("stopped", ssm_present=False)
        controller = instance.InstanceController(config(), backend, sleep=lambda unused: None)
        observed = []
        started = controller.start(config()["instance_id"], before_start=observed.append)
        self.assertEqual(started["ec2"]["state"], "running")
        self.assertEqual(observed[0]["ec2"]["state"], "stopped")
        self.assertEqual(observed[0]["ssm"], {"record_present": False})
        stopped = controller.stop()
        self.assertEqual(stopped["ec2"]["state"], "stopped")
        self.assertEqual(stopped["ssm"], {"record_present": False})
        self.assertEqual([call[0] for call in backend.calls].count("start"), 1)
        self.assertEqual([call[0] for call in backend.calls].count("stop"), 1)
        self.assertEqual(backend.calls[0], ("check_session_client",))

    def test_start_waits_for_ssm_record_through_observed_startup_sequence(self):
        target = config()["instance_id"]
        backend = TransitionBackend(
            [
                ("stopped", None),
                ("pending", None),
                ("running", None),
                ("running", "Online"),
            ]
        )
        sleeps = []
        result = instance.InstanceController(config(), backend, sleep=sleeps.append).start(target)
        self.assertEqual(result["ec2"]["state"], "running")
        self.assertEqual(result["ssm"]["ping_status"], "Online")
        self.assertEqual(sleeps, [config()["timeouts"]["poll_seconds"]] * 2)
        self.assertEqual([call[0] for call in backend.calls].count("start"), 1)

    def test_start_waits_for_existing_offline_record_to_become_online(self):
        target = config()["instance_id"]
        backend = TransitionBackend(
            [("stopped", None), ("running", "ConnectionLost"), ("running", "Online")]
        )
        result = instance.InstanceController(config(), backend, sleep=lambda unused: None).start(target)
        self.assertEqual(result["ssm"]["ping_status"], "Online")

    def test_start_absent_record_timeout_reports_last_incomplete_state(self):
        value = deepcopy(config())
        value["timeouts"].update(start_seconds=1, poll_seconds=1)
        backend = TransitionBackend([("stopped", None), ("running", None)])
        ticks = iter((0, 1))
        controller = instance.InstanceController(
            value, backend, monotonic=lambda: next(ticks), sleep=lambda unused: None
        )
        with self.assertRaisesRegex(
            instance.InstanceError,
            "last incomplete state: EC2 'running', SSM record absent",
        ):
            controller.start(value["instance_id"])

    def test_start_wait_does_not_retry_ssm_api_or_validation_failures(self):
        target = config()["instance_id"]
        failures = (
            instance.InstanceError("AccessDenied"),
            instance.InstanceError("invalid managed-instance list"),
            instance.InstanceError("expected exactly one managed instance"),
        )
        for failure in failures:
            with self.subTest(failure=str(failure)):
                backend = TransitionBackend([("stopped", None), ("running", failure)])
                sleeps = []
                with self.assertRaisesRegex(instance.InstanceError, str(failure)):
                    instance.InstanceController(config(), backend, sleep=sleeps.append).start(target)
                self.assertEqual(sleeps, [])

    def test_start_wait_rejects_mismatched_ssm_target_without_retry(self):
        target = config()["instance_id"]
        backend = TransitionBackend(
            [
                ("stopped", None),
                ("running", {"instance_id": "i-wrong", "ping_status": "Online"}),
            ]
        )
        with self.assertRaisesRegex(instance.InstanceError, "SSM response instance ID does not match"):
            instance.InstanceController(config(), backend, sleep=lambda unused: self.fail("must not retry")).start(
                target
            )

    def test_start_wait_rejects_forbidden_ec2_state_before_ssm_lookup(self):
        target = config()["instance_id"]
        for state in ("shutting-down", "future-state"):
            with self.subTest(state=state):
                backend = TransitionBackend([("stopped", None), (state, None)])
                with self.assertRaisesRegex(instance.InstanceError, "forbidden or unknown state"):
                    instance.InstanceController(
                        config(), backend, sleep=lambda unused: self.fail("must not retry")
                    ).start(target)
                self.assertEqual([call[0] for call in backend.calls].count("describe_ssm"), 1)

    def test_stop_is_idempotent_without_ssm_record(self):
        backend = FakeBackend("stopped", ssm_present=False)
        result = instance.InstanceController(config(), backend).stop()
        self.assertEqual(result["ssm"], {"record_present": False})
        self.assertNotIn("stop", [call[0] for call in backend.calls])

    def test_timeout_is_finite(self):
        value = deepcopy(config())
        value["timeouts"].update(start_seconds=1, poll_seconds=1)
        backend = FakeBackend("stopped", "ConnectionLost")
        backend.start = lambda instance_id: backend.calls.append(("start", instance_id))
        ticks = iter((0, 0, 1))
        controller = instance.InstanceController(value, backend, monotonic=lambda: next(ticks), sleep=lambda unused: None)
        with self.assertRaisesRegex(
            instance.InstanceError,
            "last incomplete state: EC2 'stopped', SSM ping status 'ConnectionLost'",
        ):
            controller.start(value["instance_id"])

    def test_run_command_uses_only_repository_allowlist(self):
        backend = FakeBackend()
        controller = instance.InstanceController(config(), backend)
        result = controller.run_command("inventory")
        self.assertEqual(result["command_result"]["status"], "Success")
        self.assertEqual(
            result["managed_instance_provenance"],
            {
                "instance_id": config()["instance_id"],
                "agent_version": "3.3.1957.0",
                "platform_type": "Linux",
                "platform_name": "Ubuntu",
                "platform_version": "22.04",
            },
        )
        call = next(call for call in backend.calls if call[0] == "send_command")
        self.assertEqual(call[2], config()["run_commands"]["inventory"])
        with self.assertRaisesRegex(instance.InstanceError, "unknown repository command"):
            controller.run_command("echo-secret")

    def test_run_command_rejects_invalid_agent_version_before_send(self):
        missing_backend = FakeBackend()
        missing_backend.describe_ssm = lambda instance_id: {
            "instance_id": instance_id,
            "ping_status": "Online",
            "platform_type": "Linux",
            "platform_name": "Ubuntu",
            "platform_version": "22.04",
        }
        with self.assertRaisesRegex(instance.InstanceError, "invalid agent version"):
            instance.InstanceController(config(), missing_backend).run_command("inventory")
        self.assertNotIn("send_command", [call[0] for call in missing_backend.calls])

        for agent_version in (None, "", "   ", [], 123, "3.3.1957.0 invalid"):
            with self.subTest(agent_version=agent_version):
                backend = FakeBackend(agent_version=agent_version)
                with self.assertRaisesRegex(instance.InstanceError, "invalid agent version"):
                    instance.InstanceController(config(), backend).run_command("inventory")
                self.assertNotIn("send_command", [call[0] for call in backend.calls])

    def test_run_command_requires_running_online_snapshot_before_send(self):
        for backend, message in (
            (FakeBackend(ec2_state="stopped", ssm_present=False), "requires the fixed target to be running"),
            (FakeBackend(ping_status="ConnectionLost"), "not SSM Online"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(instance.InstanceError, message):
                instance.InstanceController(config(), backend).run_command("inventory")
            self.assertNotIn("send_command", [call[0] for call in backend.calls])

    def test_run_command_failure_is_reported(self):
        backend = FakeBackend()
        backend.command_status = "Failed"
        with self.assertRaisesRegex(instance.InstanceError, "status Failed and response code 1"):
            instance.InstanceController(config(), backend).run_command("inventory")

    def test_run_command_retries_eventual_consistency(self):
        backend = FakeBackend()
        original_command_result = backend.command_result
        attempts = 0

        def command_result(instance_id, command_id):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise instance.CommandInvocationNotReady("not visible yet")
            return original_command_result(instance_id, command_id)

        backend.command_result = command_result
        sleeps = []
        result = instance.InstanceController(config(), backend, sleep=sleeps.append).run_command("inventory")
        self.assertEqual(result["command_result"]["status"], "Success")
        self.assertEqual(attempts, 2)
        self.assertEqual(sleeps, [config()["timeouts"]["poll_seconds"]])

    def test_run_command_eventual_consistency_respects_timeout(self):
        value = deepcopy(config())
        value["timeouts"].update(command_seconds=1, poll_seconds=1)
        backend = FakeBackend()
        backend.command_result = lambda unused_instance_id, unused_command_id: (_ for _ in ()).throw(
            instance.CommandInvocationNotReady("not visible yet")
        )
        ticks = iter((0, 0, 1))
        controller = instance.InstanceController(
            value,
            backend,
            monotonic=lambda: next(ticks),
            sleep=lambda unused: None,
        )
        with self.assertRaisesRegex(instance.InstanceError, "timed out after 1 seconds"):
            controller.run_command("inventory")

    def test_run_command_rejects_unknown_status_without_polling(self):
        backend = FakeBackend()
        backend.command_status = "FutureStatus"
        with self.assertRaisesRegex(instance.InstanceError, "unknown status"):
            instance.InstanceController(config(), backend).run_command("inventory")

    def test_check_run_command_does_not_inspect_or_mutate_the_target(self):
        backend = FakeBackend()
        result = instance.InstanceController(config(), backend).check_run_command()
        self.assertEqual(result, {"transport": "fake", "api_mutation": False})
        self.assertEqual(
            backend.calls,
            [
                (
                    "check_run_command",
                    config()["instance_id"],
                    config()["run_commands"],
                    config()["timeouts"]["command_seconds"],
                )
            ],
        )

    def test_check_session_client_does_not_inspect_or_mutate_the_target(self):
        backend = FakeBackend()
        result = instance.InstanceController(config(), backend).check_session_client()
        self.assertEqual(result["api_mutation"], False)
        self.assertEqual(backend.calls, [("check_session_client",)])

    def test_non_session_actions_do_not_require_session_client(self):
        for action in ("status", "stop", "run_command", "check_run_command"):
            with self.subTest(action=action):
                backend = FakeBackend()
                backend.check_session_client = lambda: self.fail("must not check plugin")
                controller = instance.InstanceController(config(), backend)
                if action == "run_command":
                    controller.run_command("inventory")
                else:
                    getattr(controller, action)()

    def test_session_requires_running_online_target(self):
        backend = FakeBackend()
        instance.InstanceController(config(), backend).session()
        self.assertIn(("session", config()["instance_id"]), backend.calls)
        self.assertEqual(backend.calls[0], ("check_session_client",))
        offline = FakeBackend("running", "ConnectionLost")
        with self.assertRaisesRegex(instance.InstanceError, "not SSM Online"):
            instance.InstanceController(config(), offline).session()

    def test_session_client_failure_precedes_aws_inspection_and_session(self):
        backend = FakeBackend()
        backend.check_session_client = lambda: (_ for _ in ()).throw(
            instance.InstanceError("local client unavailable")
        )
        with self.assertRaisesRegex(instance.InstanceError, "local client unavailable"):
            instance.InstanceController(config(), backend).session()
        self.assertEqual(backend.calls, [])


class SessionManagerClientCheckTests(unittest.TestCase):
    @staticmethod
    def result(args, returncode=0, stdout="", stderr=""):
        return subprocess.CompletedProcess(args, returncode, stdout, stderr)

    def test_success_uses_bounded_shell_free_checks_and_returns_evidence(self):
        calls = []

        def runner(args, **kwargs):
            calls.append((args, kwargs))
            if args[-1:] == ["--version"]:
                return self.result(args, stdout="1.2.764.0\n")
            return self.result(args, stdout=instance.SESSION_MANAGER_PLUGIN_SUCCESS_MESSAGE + "\n")

        check = instance.SessionManagerClientCheck(
            finder=lambda name: "/opt/session-manager-plugin",
            runner=runner,
        )
        result = check.check()
        self.assertEqual(
            result,
            {
                "api_mutation": False,
                "executable": "/opt/session-manager-plugin",
                "minimum_version": "1.2.764.0",
                "standalone_verification": "passed",
                "version": "1.2.764.0",
            },
        )
        self.assertEqual(
            [call[0] for call in calls],
            [
                ["/opt/session-manager-plugin", "--version"],
                ["/opt/session-manager-plugin"],
            ],
        )
        for _, kwargs in calls:
            self.assertEqual(kwargs["timeout"], instance.SESSION_MANAGER_PLUGIN_TIMEOUT_SECONDS)
            self.assertIs(kwargs["capture_output"], True)
            self.assertNotIn("shell", kwargs)

    def test_missing_plugin_fails_without_starting_a_process(self):
        check = instance.SessionManagerClientCheck(
            finder=lambda name: None,
            runner=lambda *args, **kwargs: self.fail("runner must not be called"),
        )
        with self.assertRaisesRegex(instance.InstanceError, "not found on PATH"):
            check.check()

    def test_timeout_and_launch_failure_expose_only_exception_type(self):
        failures = (
            subprocess.TimeoutExpired(["secret-command"], 5, output="credential=secret"),
            OSError("credential=secret"),
        )
        for failure in failures:
            with self.subTest(failure=type(failure).__name__):
                check = instance.SessionManagerClientCheck(
                    finder=lambda name: "/opt/session-manager-plugin",
                    runner=lambda *args, **kwargs: (_ for _ in ()).throw(failure),
                )
                with self.assertRaisesRegex(instance.InstanceError, type(failure).__name__) as raised:
                    check.check()
                self.assertNotIn("secret", str(raised.exception))
                self.assertNotIn("credential", str(raised.exception))

    def test_nonzero_output_is_not_exposed(self):
        check = instance.SessionManagerClientCheck(
            finder=lambda name: "/opt/session-manager-plugin",
            runner=lambda args, **kwargs: self.result(
                args, returncode=1, stderr="credential=https://private.invalid/token"
            ),
        )
        with self.assertRaisesRegex(instance.InstanceError, "exited non-zero") as raised:
            check.check()
        self.assertNotIn("private.invalid", str(raised.exception))
        self.assertNotIn("credential", str(raised.exception))

    def test_invalid_and_old_versions_fail_closed(self):
        for version, message in (
            ("1.2.764", "invalid version"),
            ("version 1.2.764.0", "invalid version"),
            ("1.2.763.0", "below the required minimum"),
        ):
            with self.subTest(version=version):
                check = instance.SessionManagerClientCheck(
                    finder=lambda name: "/opt/session-manager-plugin",
                    runner=lambda args, **kwargs: self.result(args, stdout=version),
                )
                with self.assertRaisesRegex(instance.InstanceError, message):
                    check.check()

    def test_standalone_message_mismatch_fails_without_exposing_output(self):
        def runner(args, **kwargs):
            if args[-1:] == ["--version"]:
                return self.result(args, stdout="1.2.764.0")
            return self.result(args, stdout="credential=https://private.invalid/token")

        check = instance.SessionManagerClientCheck(
            finder=lambda name: "/opt/session-manager-plugin",
            runner=runner,
        )
        with self.assertRaisesRegex(instance.InstanceError, "expected message") as raised:
            check.check()
        self.assertNotIn("private.invalid", str(raised.exception))
        self.assertNotIn("credential", str(raised.exception))


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

    def test_run_command_delegates_to_sdk_without_aws_cli(self):
        class Transport:
            def send_command(self, instance_id, commands, timeout):
                self.request = (instance_id, commands, timeout)
                return "abc"

            def command_result(self, instance_id, command_id):
                self.result_request = (instance_id, command_id)
                return {"command_id": command_id, "status": "Success", "response_code": 0}

        transport = Transport()
        backend = instance.AwsCliBackend(
            "ap-northeast-1",
            "i-fixed",
            runner=lambda *args, **kwargs: self.fail("AWS CLI must not run"),
            run_command_transport=transport,
        )
        self.assertEqual(backend.send_command("i-fixed", ["uname -r"], 30), "abc")
        self.assertEqual(backend.command_result("i-fixed", "abc")["status"], "Success")
        self.assertEqual(transport.request, ("i-fixed", ["uname -r"], 30))
        self.assertEqual(transport.result_request, ("i-fixed", "abc"))

    def test_ssm_lookup_distinguishes_absence_from_invalid_or_multiple_results(self):
        cases = (
            ({"InstanceInformationList": []}, instance.SsmTargetNotFound, "no managed-instance record"),
            ({"InstanceInformationList": [{}, {}]}, instance.InstanceError, "expected exactly one"),
            ({}, instance.InstanceError, "invalid response"),
            ({"InstanceInformationList": None}, instance.InstanceError, "invalid managed-instance list"),
        )
        for payload, error_type, message in cases:
            with self.subTest(payload=payload):
                def runner(args, **kwargs):
                    return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")

                backend = instance.AwsCliBackend("ap-northeast-1", "i-fixed", runner=runner)
                with self.assertRaisesRegex(error_type, message):
                    backend.describe_ssm("i-fixed")

    def test_permission_error_is_sanitized(self):
        def runner(args, **kwargs):
            return subprocess.CompletedProcess(args, 255, "", "AccessDenied for arn:aws:iam::123456789012:role/test")

        backend = instance.AwsCliBackend("ap-northeast-1", "i-fixed", runner=runner)
        with self.assertRaisesRegex(instance.InstanceError, r"\[redacted-arn\]"):
            backend.describe_ssm("i-fixed")


class FakeSsmClient:
    def __init__(self, region="ap-northeast-1"):
        self.meta = SimpleNamespace(region_name=region)
        self.calls = []
        self.send_response = {"Command": {"CommandId": "command-1"}}
        self.result_response = {
            "CommandId": "command-1",
            "InstanceId": "i-fixed",
            "Status": "Success",
            "ResponseCode": 0,
            "StandardOutputContent": "ok",
            "StandardErrorContent": "",
        }

    def send_command(self, **request):
        self.calls.append(("send_command", request))
        if isinstance(self.send_response, Exception):
            raise self.send_response
        return self.send_response

    def get_command_invocation(self, **request):
        self.calls.append(("get_command_invocation", request))
        if isinstance(self.result_response, Exception):
            raise self.result_response
        return self.result_response


class FakeSdkError(Exception):
    def __init__(self, code):
        super().__init__("sensitive SDK detail must never be displayed")
        self.response = {"Error": {"Code": code}}


class SsmRunCommandTransportTests(unittest.TestCase):
    def transport(self, client):
        return instance.SsmRunCommandTransport(
            "ap-northeast-1",
            "i-fixed",
            {"inventory": ["uname -r", "python3 --version"]},
            30,
            client_factory=lambda region: client,
        )

    def test_send_command_uses_exact_fixed_request(self):
        client = FakeSsmClient()
        transport = self.transport(client)
        self.assertEqual(transport.send_command("i-fixed", ["uname -r", "python3 --version"], 30), "command-1")
        self.assertEqual(
            client.calls,
            [
                (
                    "send_command",
                    {
                        "InstanceIds": ["i-fixed"],
                        "DocumentName": "AWS-RunShellScript",
                        "Parameters": {"commands": ["uname -r", "python3 --version"]},
                        "TimeoutSeconds": 30,
                    },
                )
            ],
        )

    def test_result_preserves_validated_fields(self):
        client = FakeSsmClient()
        result = self.transport(client).command_result("i-fixed", "command-1")
        self.assertEqual(
            result,
            {
                "command_id": "command-1",
                "status": "Success",
                "response_code": 0,
                "stdout": "ok",
                "stderr": "",
            },
        )
        self.assertEqual(
            client.calls,
            [("get_command_invocation", {"InstanceId": "i-fixed", "CommandId": "command-1"})],
        )

    def test_eventual_consistency_is_the_only_retryable_sdk_error(self):
        for code, expected in (
            ("InvocationDoesNotExist", instance.CommandInvocationNotReady),
            ("AccessDeniedException", instance.InstanceError),
            ("InvalidInstanceId", instance.InstanceError),
            ("ThrottlingException", instance.InstanceError),
        ):
            with self.subTest(code=code):
                client = FakeSsmClient()
                client.result_response = FakeSdkError(code)
                with self.assertRaises(expected) as raised:
                    self.transport(client).command_result("i-fixed", "command-1")
                if code != "InvocationDoesNotExist":
                    self.assertNotIsInstance(raised.exception, instance.CommandInvocationNotReady)
                    self.assertIn(code, str(raised.exception))
                self.assertNotIn("sensitive SDK detail", str(raised.exception))

    def test_non_service_sdk_failures_expose_only_exception_type(self):
        client = FakeSsmClient()
        client.send_response = TimeoutError("credential=https://private.invalid/token")
        with self.assertRaisesRegex(instance.InstanceError, "TimeoutError") as raised:
            self.transport(client).send_command(
                "i-fixed", ["uname -r", "python3 --version"], 30
            )
        self.assertNotIn("private.invalid", str(raised.exception))
        self.assertNotIn("credential", str(raised.exception))

    def test_invalid_or_mismatched_responses_fail_closed(self):
        cases = (
            ({}, "mismatched target"),
            ({
                "CommandId": "command-1",
                "InstanceId": "i-fixed",
                "Status": "FutureStatus",
                "ResponseCode": 0,
                "StandardOutputContent": "",
                "StandardErrorContent": "",
            }, "unknown status"),
            ({
                "CommandId": "command-1",
                "InstanceId": "i-fixed",
                "Status": "Success",
                "ResponseCode": "0",
                "StandardOutputContent": "",
                "StandardErrorContent": "",
            }, "invalid response code"),
        )
        for payload, message in cases:
            with self.subTest(message=message):
                client = FakeSsmClient()
                client.result_response = payload
                with self.assertRaisesRegex(instance.InstanceError, message):
                    self.transport(client).command_result("i-fixed", "command-1")

    def test_precheck_builds_client_without_api_call_and_rejects_wrong_region(self):
        client = FakeSsmClient()
        result = self.transport(client).check(
            "i-fixed", {"inventory": ["uname -r", "python3 --version"]}, 30
        )
        self.assertEqual(result["api_mutation"], False)
        self.assertEqual(result["document_name"], "AWS-RunShellScript")
        self.assertEqual(client.calls, [])

        wrong_region = FakeSsmClient("us-east-1")
        with self.assertRaisesRegex(instance.InstanceError, "region does not match"):
            self.transport(wrong_region).check(
                "i-fixed", {"inventory": ["uname -r", "python3 --version"]}, 30
            )

    def test_fixed_target_allowlist_and_timeout_boundaries_are_rejected(self):
        transport = self.transport(FakeSsmClient())
        with self.assertRaisesRegex(instance.InstanceError, "fixed target"):
            transport.send_command("i-other", ["uname -r"], 30)
        with self.assertRaisesRegex(instance.InstanceError, "allowlist"):
            transport.check("i-fixed", {}, 30)
        with self.assertRaisesRegex(instance.InstanceError, "allowlist"):
            transport.send_command("i-fixed", ["uname -r"], 30)
        with self.assertRaisesRegex(instance.InstanceError, "fixed timeout"):
            transport.check(
                "i-fixed", {"inventory": ["uname -r", "python3 --version"]}, True
            )
        with self.assertRaisesRegex(instance.InstanceError, "fixed timeout"):
            transport.send_command("i-fixed", ["uname -r", "python3 --version"], 31)


if __name__ == "__main__":
    unittest.main()
