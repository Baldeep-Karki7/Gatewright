#When no rule matches then what does this mode do

"""Operating modes, and what each does with a call that no rule covers.

This module is the fallback table. It knows nothing about user-authored rules
and nothing about the gate or the approver. Its one question is:

    "if nothing else matched, what should this mode do with this tool?"

The plan-mode allowlist (plan_shell_ok) is the exception: it inspects the
actual command, because "shell" in plan mode is only allowed for a short list
of read-only commands.
"""

import fnmatch
from typing import Optional
from permissions.rules import has_shell_syntax

#The only shell commands plan mode will run
PLAN_SHELL = (
    "ls", "ls *", "cat *", "head *", "tail *", "wc *", "grep *",
    "git status", "git status *", "git diff", "git diff *", "git log", "git log *",
)


# Flags that make an otherwise read-only command write or run something.
RISKY_FLAGS = ("--output", "--ext-diff", "--textconv")

PLAN = "plan"
DEFAULT = "default"
ACCEPT_EDITS = "accept_edits"
DONT_ASK = "dont_ask"
BYPASS = "bypass"
MODES  = (PLAN, DEFAULT, ACCEPT_EDITS, DONT_ASK, BYPASS)

READ_TOOLS = {"read_file", "list_dir"}
EDIT_TOOLS = {"edit_file", "write_file"}
SHELL_TOOLS = {"run_shell"}
INTERNAL_TOOLS = {"todo_write"}

def category(tool: str) -> str:
    """'read', 'edit', 'shell', 'internal', or 'other' (anything unknown)."""
    if tool in READ_TOOLS:
        return "read"
    if tool in EDIT_TOOLS:
        return "edit"
    if tool in SHELL_TOOLS:
        return "shell"
    if tool in INTERNAL_TOOLS:
        return "internal"
    return "other"


def fallback(mode:str, tool)->tuple[str, str]:
    #(action, reason) for a call that no rule matched
    #dont_ask turns every 'ask' into a denial 

    cat = category(tool)

    #reading and upadtong the todo change nothing outside the agent
    if cat in ("read", "internal"):
        return "allow", f"{cat} tools are always allowed"

    if mode == PLAN:
        if cat == "shell":
            return "allow", "read-only command in plan mode"
        return "deny", "plan mode is read-only"

    if mode == BYPASS:
        return "allow", "bypass mode"

    if mode == ACCEPT_EDITS and cat == "edit":
        return "allow", "edits are accepted in this mode"

    return "ask", "no rule matched"

def plan_shell_ok(command:str) -> bool:
    """True for one plain read-only command that stays within workspace"""
    if has_shell_syntax(command):
        return False

    words = command.split()
    if not words:
        return False

    for word in words[1:]:
        if word.startswith(("/", "~")) or ".." in word:
            return False

        if word.split("=", 1)[0] in RISKY_FLAGS:
            return False

    #if the command matches any plan_shell command
    return any(fnmatch.fnmatchcase(command, p) for p in PLAN_SHELL)

def plan_block_reason(tool:str, command:str)->Optional[str]:
    """if plan mode refuses the call then why, and None if it allows the call"""

    cat = category(tool)
    if cat in ("read", "internal"):
        return None

    if cat == "shell":
        if plan_shell_ok(command):
            return None
        return "plan mode only allows a short list of read-only comands"

    return "plan mode is read-only"


"""Two decisions worth understanding
1. fallback("plan", "run_shell") returns "allow", not "ask". This looks unsafe until you see the contract in the docstring: policy.py will call plan_block_reason() before the fallback, so an unsafe command is denied before this line is ever reached. fallback only sees tools that already passed. The trade-off is that fallback is not safe to call on a raw plan-mode command by itself — which is why the contract is written down.

2. Unknown tools are "other" and get "ask" in normal modes, "deny" in plan. A tool you don't recognise should never be silently allowed. ask in default/accept_edits, deny in plan, allow only under bypass."""