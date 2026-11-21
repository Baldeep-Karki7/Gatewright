#Ask the user wheter a tool call may run
from dataclasses import dataclass
from agent_config import INTERACTIVE


@dataclass(frozen=True)
class Answer:
    allowed : bool
    note: str = "" #the reason shown/logged for a refusal


def describe(tool, args):
    if not isinstance(args, dict):
        return f"{tool} arguments unreadable"

    if tool == "run_shell":
        return str(args.get("command", ""))

    if tool in ("read_file", "write_file", "edit_file"):
        return str(args.get("file_name", ""))

    if tool == "list_dir":
        return str(args.get("path") or ".")

    #unknown toold
    return f"{str(args)[:200]}"


class TerminalApprover:
    """asks in a terminal. anything other than yes counts as no"""

    def ask(self, tool, args, reason):
        print(f"Permission needed : {tool}")
        print(describe(tool, args))
        print(f"({reason})")

        try:
            reply = input("Allow? (y/n) ")
        except (EOFError, KeyboardInterrupt):
            # No human at the keyboard (pipe closed, Ctrl-C): refuse, don't crash.
            return Answer(False, "no input")

        if reply.strip().lower() in ("y", "yes"):
            return Answer(True)
        return Answer(False, "user said no")


class AutoYesApprover:
    """Approves some or all 'ask' decisiuons without a terminal."""

    #--yes (tools=None)
    #--allow-shell(tools = {"run_shell"})

    def __init__(self, tools=None):
        self.tools = tools

    def ask(self, tools, args, reason):
        if self.tools is not None and tools not in self.tools:
            return Answer(False, "not auto-approved")
        return Answer(True, "auto-approved")

class DenyApprover:
    "Refuse every ask: no human is available in this run"

    def ask(self, tools, args, reason):
        return Answer(False, "no approval available (non-interactive)")


def build_gate(args):
    #Create permission gate for the run
    from permissions.gate import Gate
    from permissions.policy import Policy

    if INTERACTIVE:
        approver = TerminalApprover()
    elif args.yes:
        approver = AutoYesApprover()
    elif args.allow_shell:
        approver = AutoYesApprover(tools = {"run_shell"})
    else:
        approver = DenyApprover()
    return Gate(Policy(mode = args.mode), approver)
