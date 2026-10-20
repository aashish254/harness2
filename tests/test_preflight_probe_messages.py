# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""What a readiness probe says when the command it ran cannot run at all.

`preflight.check` shells out to the vendor tooling (git, gcloud, docker, a benchmark's own
interpreter). When the subprocess itself cannot start or never answers, the issue it recorded
named only the exception class -- "Google Application Default Credentials: FileNotFoundError;
see README.md" -- which leaves the deployer to guess which program is missing. The two cases
below are the ones an unconfigured machine actually produces.
"""

import subprocess
import unittest
from contextlib import ExitStack
from unittest.mock import patch

from harness2 import config, preflight


class _Substrate:
    name = "oc"

    def preflight(self, **_kwargs):
        return None


class _Adapter:
    def __init__(self):
        class _Spec:
            name = "lab"

        self.spec = _Spec()
        self.substrate = _Substrate()

    def tasks(self, split="all"):
        return ["t"]

    def preflight(self):
        return None


def _missing_program(argv, **_kwargs):
    error = FileNotFoundError(2, "No such file or directory")
    error.filename = str(argv[0])
    raise error


def _silent(argv, **_kwargs):
    raise subprocess.TimeoutExpired([str(a) for a in argv], 45)


def _check(raiser):
    """Run the readiness pass with every probe command failing the way `raiser` says."""
    with ExitStack() as stack:
        stack.enter_context(patch.object(preflight, "missing_runners", return_value=""))
        stack.enter_context(patch.object(preflight, "OpencodeSubstrate"))
        stack.enter_context(patch.object(config, "validate_models", lambda **_kw: None))
        # Forces the ADC probe, and names the interpreter the LAB dependency probe invokes.
        stack.enter_context(patch.object(config, "JUDGE_MODEL", "gemini-test"))
        stack.enter_context(patch.object(config, "LAB_PYTHON", "/venv/lab-judge/bin/python"))
        stack.enter_context(patch.object(preflight.shutil, "which", return_value=None))
        stack.enter_context(patch.object(preflight.subprocess, "run", side_effect=raiser))
        stack.enter_context(
            patch.object(preflight.subprocess, "check_output", return_value="0" * 40)
        )
        return preflight.check(_Adapter(), judge=True)


class ProbeFailureMessages(unittest.TestCase):
    def test_every_issue_names_the_path_that_could_not_be_used(self):
        errors = _check(_missing_program)
        self.assertTrue(errors, "the probe pass must record the failed checks")
        for error in errors:
            self.assertNotIn(
                "FileNotFoundError;",
                error,
                f"{error!r} names the exception class but not what is missing",
            )
        joined = "\n".join(errors)
        self.assertIn("Google Application Default Credentials:", joined)
        self.assertIn("No such file or directory (gcloud)", joined)

    def test_a_silent_probe_reports_the_command_and_the_wait_that_expired(self):
        joined = "\n".join(_check(_silent))
        self.assertIn("no response in 45s (git)", joined)
        self.assertIn("no response in 45s (gcloud)", joined)
        self.assertIn("no response in 45s (/venv/lab-judge/bin/python)", joined)


if __name__ == "__main__":
    unittest.main()
