"""Step 2b: API error classification in llm.py and handling in agent.py.

Run from the repo root: venv/bin/python -m tests.test_errors

Fakes the API client so every error path runs without a network call.
"""
import types
import unittest

import httpx
import openai

import agent
import llm

REQ = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")

# Body shapes taken from the real 413 in agent.log; the 400 one follows
# OpenAI's documented context_length_exceeded error.
BODY_413 = {"error": {
    "message": "Request too large for model `openai/gpt-oss-20b` ... on tokens per "
               "minute (TPM): Limit 8000, Requested 15513",
    "type": "tokens", "code": "rate_limit_exceeded"}}
BODY_400_CTX = {"error": {
    "message": "This model's maximum context length is 131072 tokens. However, your "
               "messages resulted in 140000 tokens.",
    "type": "invalid_request_error", "code": "context_length_exceeded"}}
BODY_400_TOOL = {"error": {
    "message": "tool call validation failed: missing required argument 'file_name'",
    "type": "invalid_request_error", "code": "tool_use_failed"}}
BODY_429 = {"error": {"message": "Rate limit reached", "type": "tokens",
                      "code": "rate_limit_exceeded"}}


def api_error(status, body):
    """Build the exception the SDK itself would raise for this response."""
    client = openai.OpenAI(api_key="x", base_url="https://example.invalid")
    resp = httpx.Response(status, request=REQ, json=body)
    return client._make_status_error(body["error"]["message"], body=body, response=resp)


def ok_response(text="done"):
    msg = types.SimpleNamespace(content=text, tool_calls=None)
    return types.SimpleNamespace(
        choices=[types.SimpleNamespace(message=msg)],
        usage=types.SimpleNamespace(prompt_tokens=1, completion_tokens=1))


class FakeClient:
    """create() raises/returns the scripted items in order."""
    def __init__(self, *script):
        self.script = list(script)
        self.calls = 0
        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls += 1
        item = self.script.pop(0) if self.script else self.last
        self.last = item
        if isinstance(item, Exception):
            raise item
        return item


class FakeLog:
    def __init__(self):
        self.events = []

    def append(self, event, **kw):
        self.events.append(event)
        return event


def run_call_llm(client, messages):
    return llm.call_llm(client, messages, {}, event_log=FakeLog(),
                        session_id="s", tool_profile="development", gate=None)


class ClassifyTests(unittest.TestCase):
    def test_413_is_rate_limit_tokens(self):
        self.assertEqual(llm.too_large_kind(api_error(413, BODY_413)), "rate_limit_tokens")

    def test_400_context_length(self):
        self.assertEqual(llm.too_large_kind(api_error(400, BODY_400_CTX)), "context_length")

    def test_400_context_length_by_code_only(self):
        body = {"error": {"message": "Request rejected.",
                          "type": "invalid_request_error",
                          "code": "context_length_exceeded"}}
        self.assertEqual(llm.too_large_kind(api_error(400, body)), "context_length")

    def test_400_tool_error_is_not_too_large(self):
        self.assertIsNone(llm.too_large_kind(api_error(400, BODY_400_TOOL)))


class CallLlmTests(unittest.TestCase):
    def test_413_raises_request_too_large_without_retry(self):
        client = FakeClient(api_error(413, BODY_413))
        with self.assertRaises(llm.RequestTooLarge) as cm:
            run_call_llm(client, [{"role": "user", "content": "hi"}])
        self.assertEqual(cm.exception.kind, "rate_limit_tokens")
        self.assertEqual(client.calls, 1)

    def test_400_context_raises_request_too_large_without_retry(self):
        client = FakeClient(api_error(400, BODY_400_CTX))
        messages = [{"role": "user", "content": "hi"}]
        with self.assertRaises(llm.RequestTooLarge) as cm:
            run_call_llm(client, messages)
        self.assertEqual(cm.exception.kind, "context_length")
        self.assertEqual(client.calls, 1)
        self.assertEqual(len(messages), 1, "nothing should be fed back to the model")

    def test_400_tool_error_is_fed_back_then_succeeds(self):
        client = FakeClient(api_error(400, BODY_400_TOOL), ok_response("fixed"))
        messages = [{"role": "user", "content": "hi"}]
        self.assertEqual(run_call_llm(client, messages), "fixed")
        self.assertEqual(client.calls, 2)
        self.assertIn("rejected before any tool ran", messages[-1]["content"])

    def test_429_is_re_raised_unchanged(self):
        client = FakeClient(api_error(429, BODY_429))
        with self.assertRaises(openai.RateLimitError):
            run_call_llm(client, [{"role": "user", "content": "hi"}])
        self.assertEqual(client.calls, 1)


class RunTurnTests(unittest.TestCase):
    def setUp(self):
        self._snapshot = agent.snapshot
        self._call_llm = agent.call_llm
        agent.snapshot = lambda: None          # no git in this test

    def tearDown(self):
        agent.snapshot = self._snapshot
        agent.call_llm = self._call_llm

    def run_with_error(self, exc):
        def boom(*a, **kw):
            raise exc
        agent.call_llm = boom
        log = FakeLog()
        messages = [{"role": "system", "content": "sys"},
                    {"role": "user", "content": "read big.txt"},
                    {"role": "tool", "content": "x" * 50}]
        todo = types.SimpleNamespace(items=[], active=False)
        agent.run_turn(messages, "start-id", 1, log, "/tmp", "s", todo,
                       "development", gate=None)
        return messages, log

    def test_rate_limit_tokens_rolls_back_turn(self):
        messages, log = self.run_with_error(llm.RequestTooLarge("rate_limit_tokens", "too big"))
        self.assertEqual(messages, [{"role": "system", "content": "sys"}])
        self.assertEqual([e.type for e in log.events], ["turn_aborted"])
        self.assertEqual(log.events[0].error_type, "RequestTooLarge")

    def test_context_length_rolls_back_turn(self):
        messages, log = self.run_with_error(llm.RequestTooLarge("context_length", "too long"))
        self.assertEqual(len(messages), 1)
        self.assertEqual([e.type for e in log.events], ["turn_aborted"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
