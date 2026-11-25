"""Step 2c: fit the history into a token budget before each API call.

Run from the repo root: venv/bin/python -m tests.test_context
"""
import copy
import types
import unittest

import agent
import llm
from context import CLEARED, estimate_tokens, fit_to_budget

SYS = {"role": "system", "content": "system prompt"}
TOOLS = [{"type": "function", "function": {"name": "read_file"}}]


def turn(n, tool_results=(), answer=True, size=10):
    """One user turn: user msg, then per tool result an assistant tool_calls msg
    followed by its tool msg, then optionally a final assistant answer."""
    msgs = [{"role": "user", "content": f"question {n}"}]
    for k, text in enumerate(tool_results):
        cid = f"call_{n}_{k}"
        msgs.append({"role": "assistant", "content": "",
                     "tool_calls": [{"id": cid, "type": "function",
                                     "function": {"name": "read_file", "arguments": "{}"}}]})
        msgs.append({"role": "tool", "tool_call_id": cid, "content": text})
    if answer:
        msgs.append({"role": "assistant", "content": "a" * size})
    return msgs


def assert_pairs_intact(tc, msgs):
    """Every tool message must answer a tool_call made earlier in the list."""
    seen = set()
    for m in msgs:
        for c in m.get("tool_calls", []) or []:
            seen.add(c["id"])
        if m["role"] == "tool":
            tc.assertIn(m["tool_call_id"], seen, "tool result without its tool call")


class FitToBudgetTests(unittest.TestCase):
    def test_1_short_history_sent_unchanged(self):
        msgs = [SYS] + turn(1) + turn(2)
        to_send, est = fit_to_budget(msgs, TOOLS, 6000)
        self.assertEqual(to_send, msgs)
        self.assertLessEqual(est, 6000)

    def test_2_old_turns_dropped_system_kept(self):
        msgs = [SYS] + turn(1, size=3000) + turn(2, size=3000) + turn(3, size=300)
        to_send, est = fit_to_budget(msgs, TOOLS, 1500)
        self.assertEqual(to_send[0], SYS, "system prompt must always be first")
        contents = [m["content"] for m in to_send]
        self.assertNotIn("question 1", contents, "oldest turn dropped first")
        self.assertIn("question 2", contents, "stops dropping once it fits")
        self.assertIn("question 3", contents, "latest turn always kept")
        self.assertLessEqual(est, 1500)

    def test_3_tool_call_and_result_never_split(self):
        msgs = ([SYS] + turn(1, ["x" * 3000, "y" * 3000])
                + turn(2, ["z" * 600]) + turn(3, ["w" * 300], answer=False))
        for budget in (400, 800, 1500, 3000, 6000):
            to_send, _ = fit_to_budget(msgs, TOOLS, budget)
            assert_pairs_intact(self, to_send)

    def test_4_old_tool_outputs_cleared_newest_kept(self):
        # One turn (in progress) with three big tool results.
        msgs = [SYS] + turn(1, ["A" * 6000, "B" * 6000, "C" * 600], answer=False)
        to_send, est = fit_to_budget(msgs, TOOLS, 1500)
        tools = [m["content"] for m in to_send if m["role"] == "tool"]
        self.assertEqual(tools[:2], [CLEARED, CLEARED])
        self.assertEqual(tools[2], "C" * 600, "newest tool output must be kept")
        self.assertLessEqual(est, 1500)
        assert_pairs_intact(self, to_send)

    def test_5a_reports_over_budget_when_nothing_fits(self):
        # The newest tool output alone is too big: estimate must exceed budget.
        msgs = [SYS] + turn(1, ["Z" * 30000], answer=False)
        _, est = fit_to_budget(msgs, TOOLS, 2000)
        self.assertGreater(est, 2000)

    def test_6_original_messages_never_modified(self):
        msgs = ([SYS] + turn(1, size=3000)
                + turn(2, ["A" * 6000, "B" * 6000, "C" * 100], answer=False))
        before = copy.deepcopy(msgs)
        fit_to_budget(msgs, TOOLS, 1500)      # drops turn 1 and clears tool outputs
        self.assertEqual(msgs, before)

    def test_estimate_counts_tools(self):
        msgs = [SYS] + turn(1)
        _, without = fit_to_budget(msgs, [], 6000)
        _, with_tools = fit_to_budget(msgs, TOOLS, 6000)
        self.assertEqual(with_tools - without, estimate_tokens(TOOLS) - estimate_tokens([]))


# ---- call_llm integration -------------------------------------------------

def ok_response(text="done"):
    msg = types.SimpleNamespace(content=text, tool_calls=None)
    return types.SimpleNamespace(
        choices=[types.SimpleNamespace(message=msg)],
        usage=types.SimpleNamespace(prompt_tokens=1, completion_tokens=1))


class RecordingClient:
    def __init__(self):
        self.sent = []
        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.sent.append(copy.deepcopy(kw["messages"]))
        return ok_response()


class FakeLog:
    def __init__(self):
        self.events = []

    def append(self, event, **kw):
        self.events.append(event)
        return event


class CallLlmTests(unittest.TestCase):
    def setUp(self):
        self._budget = llm.CONTEXT_BUDGET

    def tearDown(self):
        llm.CONTEXT_BUDGET = self._budget

    def call(self, client, msgs):
        return llm.call_llm(client, msgs, {}, event_log=FakeLog(), session_id="s",
                            tool_profile="development", gate=None)

    def test_7_sends_trimmed_copy_keeps_full_history(self):
        llm.CONTEXT_BUDGET = 3000
        msgs = [SYS] + turn(1, size=9000) + [{"role": "user", "content": "now"}]
        n_before = len(msgs)
        client = RecordingClient()
        self.call(client, msgs)
        sent = client.sent[0]
        self.assertLess(len(sent), n_before, "old turn should not be sent")
        self.assertEqual(sent[0], SYS)
        self.assertEqual(len(msgs), n_before, "full history kept (no new msg on plain reply)")
        self.assertEqual(msgs[1]["content"], "question 1", "old turn still in memory")

    def test_5b_nothing_fits_raises_context_length_without_api_call(self):
        llm.CONTEXT_BUDGET = 2000
        msgs = [SYS, {"role": "user", "content": "Z" * 30000}]
        client = RecordingClient()
        with self.assertRaises(llm.RequestTooLarge) as cm:
            self.call(client, msgs)
        self.assertEqual(cm.exception.kind, "context_length")
        self.assertEqual(client.sent, [], "no API call should be made")


class RunTurnTests(unittest.TestCase):
    def test_5c_over_budget_rolls_back_turn(self):
        saved = (agent.snapshot, llm.CONTEXT_BUDGET, agent.client)
        agent.snapshot = lambda: None
        llm.CONTEXT_BUDGET = 2000
        try:
            agent.client = RecordingClient()
            msgs = [SYS, {"role": "user", "content": "Z" * 30000}]
            log = FakeLog()
            todo = types.SimpleNamespace(items=[], active=False)
            agent.run_turn(msgs, "start-id", 1, log, "/tmp", "s", todo,
                           "development", gate=None)
            self.assertEqual(msgs, [SYS])
            self.assertEqual([e.type for e in log.events], ["turn_aborted"])
        finally:
            agent.snapshot, llm.CONTEXT_BUDGET, agent.client = saved

    def test_8_old_trim_messages_removed(self):
        import utils
        self.assertFalse(hasattr(utils, "trim_messages"))
        self.assertFalse(hasattr(agent, "trim_messages"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
