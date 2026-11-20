from permissions.rules import Rule, parse_rule, subject, has_shell_syntax, command_parts, rule_matches

assert parse_rule('run_shell(git push -u main)') == Rule('run_shell', 'git push -u main')

assert parse_rule("read_file") == Rule("read_file")

for bad in ["", "run_shell()", "(x)"]:
    try:
        parse_rule(bad)
    except Exception as e:
        print(e)

assert subject("read_file", {"file_name": "./a/../.env"}) == ".env"
assert subject("list_dir", {}) == "."
assert subject("list_dir", {"path": "a/./b"}) == "a/b"
assert subject("run_shell", {"command": "git   push\n origin"}) == "git push origin"
assert subject("run_shell", None) == ""


#check the has_shell_syntax 
assert has_shell_syntax("ls -la") is False
assert has_shell_syntax("ls && pwd") is True
assert has_shell_syntax("echo $(date)") is True

assert command_parts("ls && git push") == ["ls", "git push"]
assert command_parts("git status && git add . && git commit -m 'none' && git commit -m 'none' ") == ["git status", "git add .", "git commit -m 'none'", "git commit -m 'none'"]
assert command_parts("python3 -m unittest; rm -rf x") == ["python3 -m unittest", "rm -rf x"]


PUSH = parse_rule("run_shell(git push *)")
assert rule_matches(PUSH, "run_shell", ["git push origin main"]) is True
assert rule_matches(PUSH, "run_shell", ["git push origin main", "ls"]) is True
assert rule_matches(PUSH, "read_file", ["git push"]) is False
assert rule_matches(parse_rule("run_shell"), "run_shell", []) is True

print("ok")
