#Ask the user wheter a tool call may run

from dataclasses import dataclass

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
