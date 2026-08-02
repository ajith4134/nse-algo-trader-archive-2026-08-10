"""Tests for the verification cockpit's outcome classifier.

The cockpit's verdict is only trustworthy if it distinguishes a genuine engine defect (FAIL, blocks
approval) from an environment gap it could not run through (SKIPPED, surfaced but non-blocking). This
locks that boundary down against the exact output shapes the real 63-check sweep produces, so a future
edit cannot silently start crying wolf (skips as fails) or hiding real breakage (fails as skips).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from verification_cockpit import _classify  # noqa: E402


class TestClassifyPass:
    def test_exit_zero_is_pass(self) -> None:
        assert _classify(0, "RESULT: PASS\n") == ("PASS", "")


class TestClassifyFail:
    """Only genuine Python errors with no environment gate block approval."""

    def test_plain_assertion_error_is_fail(self) -> None:
        status, _ = _classify(1, "AssertionError: bound 1.2 > 1.0 expected")
        assert status == "FAIL"

    def test_real_traceback_bug_is_fail_even_with_teardown_abort(self) -> None:
        # cross_modal_binding: a genuine AttributeError, then a native abort on the way out. The
        # traceback must win — a real bug is not excused by the C-library abort that follows it.
        out = (
            "Traceback (most recent call last):\n"
            "  AttributeError: 'NoneType' object has no attribute 'summary'\n"
            "terminate called without an active exception"
        )
        status, _ = _classify(-6, out)
        assert status == "FAIL"


class TestClassifySkip:
    """Environment gaps are unverified, not broken — surfaced but never blocking (Rule J)."""

    def test_native_teardown_abort_without_traceback_is_skip(self) -> None:
        # global_workspace: logic printed PASS, then torch/HF aborted on interpreter teardown.
        out = "Loading weights 201/201\nRESULT: PASS\nterminate called without an active exception"
        status, reason = _classify(-6, out)
        assert status == "SKIPPED"
        assert "teardown" in reason

    def test_broker_http_auth_error_is_skip(self) -> None:
        out = "requests.exceptions.HTTPError: 403 Client Error for url loginByPassword\n raise_for_status"
        status, _ = _classify(1, out)
        assert status == "SKIPPED"

    def test_manual_broker_login_is_skip(self) -> None:
        status, _ = _classify(2, "only a manual browser login (with TOTP) can produce; no headless login")
        assert status == "SKIPPED"

    def test_timeout_is_skip(self) -> None:
        status, _ = _classify(124, "TIMED OUT after 180s")
        assert status == "SKIPPED"

    def test_missing_database_is_skip(self) -> None:
        status, _ = _classify(1, "sqlite3.OperationalError: no such table: experience_nodes")
        assert status == "SKIPPED"

    def test_missing_dependency_is_skip(self) -> None:
        status, _ = _classify(1, "ModuleNotFoundError: No module named foo")
        assert status == "SKIPPED"
