import unittest

from permissions.approver import Answer
from permissions.gate import Gate
from permissions.policy import Policy


class FakeApprover:
    """Stands in for TerminalApprover: fixed answer, counts how often it's asked."""

    def __init__(self, allowed):
        self.allowed = allowed
        self.calls = 0
        self.last = None

    def ask(self, tool, args, reason):
        self.calls += 1
        self.last = (tool, args, reason)
        return Answer(self.allowed, "" if self.allowed else "user said no")


class AgentGateTests(unittest.TestCase):
    """End-to-end checks: policy -> gate -> approver, with no real terminal."""

    def test_reads_run_without_asking(self):
        approver = FakeApprover(False)
        verdict = Gate(Policy(mode="accept_edits"), approver).check(
            "read_file", {"file_name": "README.md"},
        )

        self.assertTrue(verdict.allowed)
        self.assertEqual(verdict.action, "allow")
        self.assertEqual(verdict.source, "mode")
        self.assertEqual(approver.calls, 0, "read tools must never prompt")

    def test_edits_run_without_asking_in_accept_edits(self):
        approver = FakeApprover(False)
        verdict = Gate(Policy(mode="accept_edits"), approver).check(
            "write_file", {"file_name": "x.txt"},
        )

        self.assertTrue(verdict.allowed)
        self.assertEqual(verdict.source, "mode")
        self.assertEqual(approver.calls, 0)

    def test_shell_prompts_and_user_approves(self):
        approver = FakeApprover(True)
        verdict = Gate(Policy(mode="accept_edits"), approver).check(
            "run_shell", {"command": "ls"},
        )

        self.assertTrue(verdict.allowed)
        self.assertEqual(verdict.action, "ask")
        self.assertEqual(verdict.source, "user")
        self.assertEqual(verdict.reason, "user approved")
        self.assertEqual(approver.calls, 1)

        # The approver must receive the policy's reason, so it can display it.
        tool, args, reason = approver.last
        self.assertEqual(tool, "run_shell")
        self.assertEqual(args, {"command": "ls"})
        self.assertEqual(reason, "no rule matched")

    def test_shell_user_refuses_gets_unverified_message(self):
        approver = FakeApprover(False)
        verdict = Gate(Policy(mode="accept_edits"), approver).check(
            "run_shell", {"command": "rm -rf x"},
        )

        self.assertFalse(verdict.allowed)
        self.assertEqual(verdict.action, "ask")
        self.assertEqual(verdict.source, "user")
        self.assertIn("denied", verdict.message)
        self.assertIn("unverified", verdict.message)
        self.assertEqual(verdict.reason, "user said no")
        self.assertEqual(approver.calls, 1)

    def test_deny_rule_wins_without_asking(self):
        approver = FakeApprover(True)
        verdict = Gate(
            Policy(mode="default", deny=["run_shell(git push*)"]), approver,
        ).check("run_shell", {"command": "sudo git push"})

        self.assertFalse(verdict.allowed)
        self.assertEqual(verdict.action, "deny")
        self.assertEqual(verdict.source, "rule")
        self.assertTrue(verdict.message.startswith("error:"))
        self.assertEqual(approver.calls, 0, "a deny rule must not prompt")


if __name__ == "__main__":
    unittest.main()