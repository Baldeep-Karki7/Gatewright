"""Step 3b: every agent.log line carries session= and turn= ids.

Runs a real one-shot session (run_agent) in a temporary project folder with a
fake API client, captures log lines through agent.py's own filter and format,
and checks the ids on lines from our modules and from httpx/openai.

Run from the repo root: venv/bin/python -m tests.test_log_context
"""
import io
import logging
import re
import shutil
import tempfile
import types
import unittest

import agent
import llm
from events.replay import load_events
from events.sessions import create_session
from log_context import ContextFilter, set_session

LINE = re.compile(r"session=(\S+) turn=(\S+) (\S+) (.*)")


def tool_call_msg():
    call = types.SimpleNamespace(
        id="call_1", function=types.SimpleNamespace(name="list_dir", arguments='{"path": "."}'))
    msg = types.SimpleNamespace(content=None, tool_calls=[call])
    msg.model_dump = lambda exclude_none=True: {
        "role": "assistant",
        "tool_calls": [{"id": "call_1", "type": "function",
                        "function": {"name": "list_dir", "arguments": '{"path": "."}'}}]}
    return msg


class FakeClient:
    """Logs like the real SDK does, then replies: tool call, then answer."""
    def __init__(self, fail=False):
        self.fail = fail
        self.replies = [tool_call_msg(), types.SimpleNamespace(content="done", tool_calls=None)]
        self.chat = types.SimpleNamespace(completions=types.SimpleNamespace(create=self.create))

    def create(self, **kw):
        logging.getLogger("httpx").info('HTTP Request: POST /chat/completions "HTTP/1.1 200 OK"')
        logging.getLogger("openai._base_client").info("Retrying request in 2.0 seconds")
        if self.fail:
            raise RuntimeError("boom")
        return types.SimpleNamespace(
            choices=[types.SimpleNamespace(message=self.replies.pop(0))],
            usage=types.SimpleNamespace(prompt_tokens=1, completion_tokens=1))


class Gate:
    def check(self, tool, args):
        return types.SimpleNamespace(allowed=True, message="")


class LogContextTests(unittest.TestCase):
    def setUp(self):
        self.root = logging.getLogger()
        # Detach the real agent.log handler so tests don't write to it.
        self.real_handlers = list(self.root.handlers)
        for h in self.real_handlers:
            self.root.removeHandler(h)
        # Same filter and format as agent.py, writing to memory.
        self.buf = io.StringIO()
        self.cap = logging.StreamHandler(self.buf)
        for f in agent.handler.filters:
            self.cap.addFilter(f)
        self.cap.setFormatter(agent.handler.formatter)
        self.root.addHandler(self.cap)
        self.old_level = self.root.level
        self.root.setLevel(logging.INFO)

        self.tmp = tempfile.mkdtemp()
        self.saved = (agent.DATA_DIR, llm.DATA_DIR, agent.snapshot, agent.client)
        agent.DATA_DIR = llm.DATA_DIR = self.tmp
        agent.snapshot = lambda: None

    def tearDown(self):
        agent.DATA_DIR, llm.DATA_DIR, agent.snapshot, agent.client = self.saved
        self.root.removeHandler(self.cap)
        for h in self.real_handlers:
            self.root.addHandler(h)
        self.root.setLevel(self.old_level)
        set_session("-")
        shutil.rmtree(self.tmp)

    def lines(self):
        return [LINE.search(l).groups() for l in self.buf.getvalue().splitlines() if LINE.search(l)]

    def run_session(self, fail=False):
        session_id, events_path = create_session(self.tmp)
        set_session(session_id)                        # what __main__ does after get_session
        agent.client = FakeClient(fail=fail)
        agent.run_agent(session_id, events_path=events_path, project_dir=self.tmp,
                        gate=Gate(), tool_profile="development", one_shot_prompt="hi")
        return session_id, events_path

    def test_1_before_session_shows_dashes(self):
        set_session("-")
        logging.getLogger("utils").info("startup line")
        self.assertEqual(self.lines()[-1][:2], ("-", "-"))

    def test_2_and_4_every_turn_line_tagged_and_matches_transcript(self):
        session_id, events_path = self.run_session()
        user_id = next(e.id for e in load_events(events_path)
                       if e.type == "message" and e.source == "user")
        turn_lines = [l for l in self.lines() if l[1] != "-"]
        self.assertTrue(turn_lines)
        for session, turn, name, msg in turn_lines:
            self.assertEqual(session, session_id)
            self.assertEqual(turn, user_id, f"{name}: {msg}")
        names = {l[2] for l in turn_lines}
        for expected in ("httpx", "openai._base_client", "llm", "agent"):
            self.assertIn(expected, names, f"no tagged line from {expected}")
        self.assertTrue(any("TOOL name=list_dir" in l[3] for l in turn_lines))

    def test_3_turn_cleared_after_turn(self):
        session_id, _ = self.run_session()
        logging.getLogger("agent").info("after the turn")
        self.assertEqual(self.lines()[-1][:2], (session_id, "-"))

    def test_3b_turn_cleared_after_failed_turn(self):
        session_id, events_path = self.run_session(fail=True)
        kinds = [e.type for e in load_events(events_path)]
        self.assertIn("turn_aborted", kinds)
        logging.getLogger("agent").info("after the failed turn")
        self.assertEqual(self.lines()[-1][:2], (session_id, "-"))

    def test_5_filter_never_drops(self):
        f = ContextFilter()
        for level in (logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR):
            rec = logging.LogRecord("x", level, __file__, 1, "m", None, None)
            self.assertTrue(f.filter(rec))
            self.assertTrue(hasattr(rec, "session") and hasattr(rec, "turn"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
