from permissions.policy import Policy

PY_RULE = "run_shell(python3 -m unittest*)"
PUSH = "run_shell(git push*)"
cases = []  # (group, mode, options, tool, args, expected_action)

def case(group, mode, options, tool, args, expected):
    cases.append((group, mode, options, tool, args, expected))

# ---------------- Pass 1: mode fallbacks, no rules involved ----------------
case("pass1", "default",      {}, "read_file",   {"file_name": "a.py"}, "allow")
case("pass1", "default",      {}, "todo_write",  {"todos": []},         "allow")
case("pass1", "default",      {}, "write_file",  {"file_name": "a.py"}, "ask")
case("pass1", "default",      {}, "run_shell",   {"command": "ls"},     "ask")
case("pass1", "default",      {}, "mystery_tool", {},                   "ask")
case("pass1", "accept_edits", {}, "write_file",  {"file_name": "a.py"}, "allow")
case("pass1", "accept_edits", {}, "run_shell",   {"command": "ls"},     "ask")
case("pass1", "bypass",       {}, "write_file",  {"file_name": "a.py"}, "allow")
case("pass1", "bypass",       {}, "run_shell",   {"command": "ls"},     "allow")
case("pass1", "default",      {}, "run_shell",   None,                  "ask")
case("pass1", "default",      {}, "run_shell",   {},                    "ask")

# ---------------- Pass 2: rules, precedence, anti-bypass ----------------
case("pass2", "default", {"allow": [PY_RULE]}, "run_shell", {"command": "python3 -m unittest -v"}, "allow")
case("pass2", "default", {"allow": [PY_RULE]}, "run_shell", {"command": "python3 -m unittest; rm -rf x"}, "ask")
case("pass2", "default", {"allow": [PY_RULE]}, "run_shell", {"command": "python3 -m unittest && ls"}, "ask")
case("pass2", "default", {"allow": [PY_RULE]}, "run_shell", {"command": "sudo python3 -m unittest"}, "ask")

case("pass2", "default", {"deny": [PUSH]}, "run_shell", {"command": "git push origin main"}, "deny")
case("pass2", "default", {"deny": [PUSH]}, "run_shell", {"command": "ls && git push"}, "deny")
case("pass2", "default", {"deny": [PUSH]}, "run_shell", {"command": "FOO=1 git push"}, "deny")
case("pass2", "default", {"deny": [PUSH]}, "run_shell", {"command": "sudo git push"}, "deny")
case("pass2", "default", {"deny": [PUSH]}, "run_shell", {"command": "echo $(git push)"}, "deny")
# known gap: a different spelling is not matched
case("pass2", "default", {"deny": [PUSH]}, "run_shell", {"command": "git -C . push"}, "ask")

case("pass2", "default", {"allow": [PUSH], "deny": ["run_shell"]}, "run_shell", {"command": "git push"}, "deny")
case("pass2", "default", {"allow": ["run_shell(python3*)"], "ask": ["run_shell"]}, "run_shell", {"command": "python3 x.py"}, "ask")

case("pass2", "default", {"deny": ["write_file(.env)"]}, "write_file", {"file_name": ".env"}, "deny")
case("pass2", "default", {"deny": ["write_file(.env)"]}, "write_file", {"file_name": "./.env"}, "deny")
case("pass2", "default", {"deny": ["write_file(.env)"]}, "write_file", {"file_name": "a/../.env"}, "deny")
case("pass2", "default", {"allow": ["write_file(docs/*)"]}, "write_file", {"file_name": "docs/a.md"}, "allow")

case("pass2", "bypass", {"deny": [PUSH]}, "run_shell", {"command": "git push"}, "deny")

# ---------------- Pass 3: plan override and dont_ask ----------------
case("pass3", "plan", {}, "read_file",  {"file_name": "a.py"}, "allow")
case("pass3", "plan", {}, "todo_write", {"todos": []},         "allow")
case("pass3", "plan", {}, "write_file", {"file_name": "a.py"}, "deny")
case("pass3", "plan", {"allow": [PY_RULE]}, "run_shell", {"command": "python3 -m unittest"}, "deny")
case("pass3", "plan", {}, "mystery_tool", {}, "deny")

case("pass3", "dont_ask", {}, "write_file", {"file_name": "a.py"}, "deny")
case("pass3", "dont_ask", {}, "run_shell",  {"command": "ls"},     "deny")
case("pass3", "dont_ask", {"allow": [PY_RULE]}, "run_shell", {"command": "python3 -m unittest"}, "allow")

failures = []
for group, mode, options, tool, args, expected in cases:
    got = Policy(mode=mode, **options).decide(tool, args)
    if got.action != expected:
        failures.append((group, mode, options, tool, args, expected, got))

for f in failures:
    print("FAIL", f)
print(f"{len(cases) - len(failures)}/{len(cases)} decision cases passed")
assert not failures

# Hidden tools (pass 1)
assert Policy(deny=["run_shell"]).is_hidden("run_shell")
assert not Policy(deny=[PUSH]).is_hidden("run_shell")
assert Policy(mode="plan").is_hidden("write_file")
assert not Policy(mode="plan").is_hidden("read_file")
assert not Policy(mode="plan").is_hidden("todo_write")
assert not Policy().is_hidden("write_file")

# Bad input (pass 1 construction / rules parsing)
from permissions.rules import parse_rule

for bad in ("", "run_shell()", "(x)"):
    try:
        parse_rule(bad)
        raise AssertionError(f"accepted bad rule {bad!r}")
    except ValueError:
        pass
try:
    Policy(mode="nonsense")
    raise AssertionError("accepted bad mode")
except ValueError:
    pass

print("ok")