"""Step 3a: agent.log must never contain tool arguments or tool output.

Captures every log record from every module while call_llm runs real tool
calls, then checks that no secret text appears anywhere in the log, while the
event log (the right place for content) still has it.

Run from the repo root: venv/bin/python -m tests.test_logging
"""
import json
import logging
import re
import types
import unittest

import llm

SECRET_FILE = "OLLAMA_API_KEY=sk-FAKE-OLLAMA-111\nGROQ_API_KEY=gsk_FAKE_GROQ_222\n"
SECRETS = ["sk-FAKE-OLLAMA-111", "gsk_FAKE_GROQ_222", "WRITE_TEXT_333",
           "EDIT_OLD_444", "EDIT_NEW_555", "Bearer CMD_666", "SHELL_OUT_777"]

TOOL_LINE = re.compile(
    r"TOOL name=(\w+) call_id=(\S+) ok=(True|False) result_chars?=(\d+) ms=(\d+)")


class Msg:
    """Just enough of the SDK's ChatCompletionMessage for call_llm."""
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self, exclude_none=True):
        d = {"role": "assistant"}
        if self.content:
            d["content"] = self.content
        if self.tool_calls:
            d["tool_calls"] = [
                {"id": c.id, "type": "function",
                 "function": {"name": c.function.name,
                              "arguments": c.function.arguments}}
                for c in self.tool_calls]
        return d


def call(cid, name, arguments):
    raw = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return types.SimpleNamespace(
        id=cid, function=types.SimpleNamespace(name=name, arguments=raw))


def response(msg):
    return types.SimpleNamespace(
        choices=[types.SimpleNamespace(message=msg)],
        usage=types.SimpleNamespace(prompt_tokens=1, completion_tokens=1))


class ScriptedClient:
    """First reply: the given tool calls. Second reply: a plain answer."""
    def __init__(self, tool_calls):
        self.replies = [response(Msg(tool_calls=tool_calls)),
                        response(Msg(content="done"))]
        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(create=lambda **kw: self.replies.pop(0)))


class FakeLog:
    def __init__(self):
        self.events = []

    def append(self, event, **kw):
        self.events.append(event)
        return event


class Gate:
    def __init__(self, deny=()):
        self.deny = set(deny)

    def check(self, tool, args):
        if tool in self.deny:
            return types.SimpleNamespace(allowed=False, message="error: user denied this call")
        return types.SimpleNamespace(allowed=True, message="")


TOOLS = {
    "read_file": lambda **a: SECRET_FILE,
    "write_file": lambda **a: "wrote the file\n",
    "edit_file": lambda **a: "ok",
    "run_shell": lambda **a: "exit=0\nstdout:\nSHELL_OUT_777\nstderr:\n",
}


class CaptureAll(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.lines = []

    def emit(self, record):
        text = record.getMessage()
        if record.exc_info:
            text += "\n" + logging.Formatter().formatException(record.exc_info)
        self.lines.append(text)


class LoggingTests(unittest.TestCase):
    def setUp(self):
        self.root = logging.getLogger()
        self.old_level = self.root.level
        self.root.setLevel(logging.DEBUG)
        self.cap = CaptureAll()
        self.root.addHandler(self.cap)

    def tearDown(self):
        self.root.removeHandler(self.cap)
        self.root.setLevel(self.old_level)

    def run_calls(self, tool_calls, profile="development", deny=()):
        log = FakeLog()
        llm.call_llm(ScriptedClient(tool_calls), [{"role": "user", "content": "go"}],
                     dict(TOOLS), event_log=log, session_id="s",
                     tool_profile=profile, gate=Gate(deny))
        return log

    def assert_no_secrets(self):
        everything = "\n".join(self.cap.lines)
        for s in SECRETS:
            self.assertNotIn(s, everything, f"{s!r} leaked into the log")

    def tool_lines(self):
        return [m for m in (TOOL_LINE.search(l) for l in self.cap.lines) if m]

    def test_1_file_contents_never_logged(self):
        log = self.run_calls([call("c1", "read_file", {"file_name": ".env"})])
        self.assert_no_secrets()
        # ...but the event log still holds the content (the right place for it)
        obs = [e for e in log.events if e.type == "observation"]
        self.assertIn("gsk_FAKE_GROQ_222", obs[0].content)

    def test_2_arguments_never_logged(self):
        self.run_calls([
            call("c1", "write_file", {"file_name": "a.py", "text": "WRITE_TEXT_333"}),
            call("c2", "edit_file", {"file_name": "a.py", "old": "EDIT_OLD_444",
                                     "new": "EDIT_NEW_555"}),
            call("c3", "run_shell", {"command": "curl -H 'Authorization: Bearer CMD_666'"}),
        ])
        self.assert_no_secrets()

    def test_3_useful_fields_logged(self):
        self.run_calls([call("call_abc", "read_file", {"file_name": ".env"})])
        lines = self.tool_lines()
        self.assertEqual(len(lines), 1)
        name, cid, ok, chars, ms = lines[0].groups()
        self.assertEqual((name, cid, ok), ("read_file", "call_abc", "True"))
        self.assertEqual(int(chars), len(SECRET_FILE))
        self.assertGreaterEqual(int(ms), 0)

    def test_4_failures_log_one_clean_line_each(self):
        self.run_calls([
            call("bad_json", "read_file", "{not json SECRET_ARG"),
            call("bad_profile", "write_file", {"file_name": "a", "text": "WRITE_TEXT_333"}),
        ], profile="readonly")
        self.run_calls([call("denied", "run_shell", {"command": "echo Bearer CMD_666"})],
                       deny={"run_shell"})
        lines = {m.group(2): m.group(3) for m in self.tool_lines()}
        self.assertEqual(lines, {"bad_json": "False", "bad_profile": "False",
                                 "denied": "False"})
        self.assert_no_secrets()
        self.assertNotIn("SECRET_ARG", "\n".join(self.cap.lines))


if __name__ == "__main__":
    unittest.main(verbosity=2)
