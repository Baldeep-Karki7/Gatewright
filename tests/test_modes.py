from permissions.modes import category, fallback, plan_shell_ok, plan_block_reason

assert category("read_file") == "read"
assert category("write_file") == "edit"
assert category("run_shell") == "shell"
assert category("todo_write") == "internal"
assert category("mystery_tool") == "other"


assert category("read_file") == "read"
assert category("write_file") == "edit"
assert category("run_shell") == "shell"
assert category("todo_write") == "internal"
assert category("mystery_tool") == "other"


#checking if the tools work in modes
assert fallback("default", "read_file")[0] == "allow"
assert fallback("default", "todo_write")[0] == "allow"
assert fallback("default", "write_file")[0] == "ask"
assert fallback("default", "run_shell")[0] == "ask"
assert fallback("default", "mystery_tool")[0] == "ask"
assert fallback("accept_edits", "write_file")[0] == "allow"
assert fallback("accept_edits", "run_shell")[0] == "ask"
assert fallback("bypass", "run_shell")[0] == "allow"
assert fallback("plan", "write_file")[0] == "deny"
assert fallback("plan", "mystery_tool")[0] == "deny"

#plan_shell_ok checks if the shell command is allowed to run in plan mode
assert plan_shell_ok("ls") is True
assert plan_shell_ok("ls -la") is True
assert plan_shell_ok("cat notes.txt") is True
assert plan_shell_ok("git diff HEAD") is True
assert plan_shell_ok("ls && pwd") is False
assert plan_shell_ok("cat /etc/passwd") is False
assert plan_shell_ok("cat ../x") is False
assert plan_shell_ok("cat ~/x") is False
assert plan_shell_ok("git diff --output=x") is False
assert plan_shell_ok("python3 -m unittest") is False

#plan_block_reason gives the allow/deny and reason the tool is not allowed to run
assert plan_block_reason("read_file", "") is None
assert plan_block_reason("todo_write", "") is None
assert plan_block_reason("run_shell", "ls") is None
assert plan_block_reason("run_shell", "rm -rf /") is not None
assert plan_block_reason("write_file", "") is not None
assert plan_block_reason("mystery_tool", "") is not None

print("ok!")