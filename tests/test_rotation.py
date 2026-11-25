"""Step 3c: agent.log is size-capped with rotation.

Checks agent.py's real handler settings, then imports agent.py in a fresh
process inside a throwaway workspace with a tiny size limit and writes enough
lines to force several rotations.

Run from the repo root: venv/bin/python -m tests.test_rotation
"""
import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from logging.handlers import RotatingFileHandler

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable


def run_in_workspace(env_extra, code):
    """Run `code` in a fresh python started inside a temporary workspace."""
    ws = tempfile.mkdtemp(prefix="rot-ws-")
    env = {**os.environ, **env_extra, "PYTHONPATH": REPO}
    r = subprocess.run([PY, "-c", code], cwd=ws, env=env,
                       capture_output=True, text=True, timeout=60)
    return ws, r


WRITE_LINES = r"""
import logging, agent
from agent_config import DATA_DIR
from log_context import set_session, set_turn
set_session("sess-123"); set_turn("turn-456")
log = logging.getLogger("llm")
for i in range(2000):
    log.info("line %05d %s", i, "x" * 60)
print(DATA_DIR)
"""


class RotationTests(unittest.TestCase):
    def tearDown(self):
        for d in getattr(self, "cleanup", []):
            shutil.rmtree(d, ignore_errors=True)
        # agent_config creates ~/.harness/projects/<workspace>-<hash> on import
        for d in glob.glob(os.path.expanduser("~/.harness/projects/rot-ws-*")):
            shutil.rmtree(d, ignore_errors=True)

    def track(self, ws, data_dir=None):
        self.cleanup = getattr(self, "cleanup", []) + [ws] + ([data_dir] if data_dir else [])

    def test_0_agent_uses_rotating_handler_with_config(self):
        import agent
        from agent_config import LOG_BACKUPS, LOG_MAX_BYTES
        self.assertIsInstance(agent.handler, RotatingFileHandler)
        self.assertEqual(agent.handler.maxBytes, LOG_MAX_BYTES)
        self.assertEqual(agent.handler.backupCount, LOG_BACKUPS)
        self.assertEqual(agent.handler.encoding.lower(), "utf-8")
        self.assertGreaterEqual(LOG_BACKUPS, 1, "backupCount 0 disables rotation")

    def test_1_2_3_rotates_caps_files_keeps_ids(self):
        limit, backups = 10 * 1024, 3
        ws, r = run_in_workspace({"HARNESS_LOG_MAX_BYTES": str(limit),
                                  "HARNESS_LOG_BACKUPS": str(backups)}, WRITE_LINES)
        self.assertEqual(r.returncode, 0, r.stderr)
        data_dir = r.stdout.strip().splitlines()[-1]
        self.track(ws, data_dir)

        files = sorted(glob.glob(os.path.join(data_dir, "agent.log*")))
        names = {os.path.basename(f) for f in files}
        # 1. it rotated, 2. never more than backups + 1 files
        self.assertEqual(names, {"agent.log", "agent.log.1", "agent.log.2", "agent.log.3"})
        for f in files:
            self.assertLessEqual(os.path.getsize(f), limit, f)

        # 3. ids survive rotation, in every file
        for f in files:
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    self.assertIn("session=sess-123 turn=turn-456", line)

        # newest lines in agent.log, older ones in .1 (nothing out of order)
        def numbers(path):
            with open(path, encoding="utf-8") as fh:
                return [int(m.group(1)) for m in re.finditer(r"line (\d{5})", fh.read())]
        newest, older = numbers(files[0]), numbers(files[1])
        self.assertEqual(newest[-1], 1999)
        self.assertLess(older[-1], newest[0])

    def test_4_invalid_settings(self):
        probe = "from agent_config import LOG_BACKUPS, LOG_MAX_BYTES; print(LOG_BACKUPS, LOG_MAX_BYTES)"
        ws, r = run_in_workspace({"HARNESS_LOG_BACKUPS": "0", "HARNESS_LOG_MAX_BYTES": "5"}, probe)
        self.track(ws)
        self.assertEqual(r.returncode, 0, r.stderr)
        backups, max_bytes = map(int, r.stdout.split())
        self.assertEqual(backups, 1, "0 must be raised to the minimum")
        self.assertEqual(max_bytes, 10 * 1024)

        ws, r = run_in_workspace({"HARNESS_LOG_BACKUPS": "abc"}, probe)
        self.track(ws)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("HARNESS_LOG_BACKUPS must be a whole number", r.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
