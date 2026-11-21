import unittest

from permissions.approver import Answer
from permissions.gate import Gate
from permissions.policy import Policy


class Fake:
    def __init__(self, allowed):
        self.allowed = allowed
        self.calls = 0

    def ask(self, tool, args, reason):
        self.calls += 1
        return Answer(self.allowed, "" if self.allowed else "no")


class Boom:
    def ask(self, tool, args, reason):
        raise RuntimeError("approver crashed")


class GateTests(unittest.TestCase):
    def test_allowed_calls_never_ask(self):
        a = Fake(False)
        v = Gate(Policy(), a).check("read_file", {"file_name": "x"})
        self.assertTrue(v.allowed)
        self.assertEqual(a.calls, 0)

    def test_user_says_yes(self):
        a = Fake(True)
        v = Gate(Policy(), a).check("run_shell", {"command": "ls"})
        self.assertTrue(v.allowed)
        self.assertEqual((a.calls, v.source), (1, "user"))

    def test_user_says_no(self):
        v = Gate(Policy(), Fake(False)).check("run_shell", {"command": "ls"})
        self.assertFalse(v.allowed)
        self.assertTrue(v.message.startswith("error:"))
        self.assertIn("denied", v.message)

    def test_deny_rule_never_asks(self):
        a = Fake(True)
        g = Gate(Policy(deny=["run_shell(rm*)"]), a)
        v = g.check("run_shell", {"command": "rm x"})
        self.assertFalse(v.allowed)
        self.assertEqual(a.calls, 0)
        self.assertTrue(v.message.startswith("error:"))

    def test_dont_ask_refuses_without_asking(self):
        a = Fake(True)
        v = Gate(Policy(mode="dont_ask"), a).check("write_file", {"file_name": "x"})
        self.assertFalse(v.allowed)
        self.assertEqual(a.calls, 0)

    def test_plan_mode_refuses_edits(self):
        v = Gate(Policy(mode="plan"), Fake(True)).check("write_file", {"file_name": "x"})
        self.assertFalse(v.allowed)

    def test_crash_fails_closed(self):
        v = Gate(Policy(), Boom()).check("run_shell", {"command": "ls"})
        self.assertFalse(v.allowed)
        self.assertEqual(v.source, "error")


if __name__ == "__main__":
    unittest.main()