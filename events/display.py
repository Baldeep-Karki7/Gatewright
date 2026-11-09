import logging

logger = logging.getLogger(__name__)


class ConsoleDisplay:
    def __init__(self):
        # ActionEvent.id -> (tool_name, target)
        self.pending = {}
        self.VERBS = {
                "read_file":  ("Reading", "Read"),
                "write_file": ("Writing", "Wrote"),
                "edit_file":  ("Editing", "Modified"),
                "list_dir":   ("Listing", "Listed"),
                "run_shell":  ("Running", "Ran"),
            }

    def _target(self, tool, args):
        if not isinstance(args, dict):
            return ""
        if tool in ("read_file", "write_file", "edit_file"):
            return args.get("file_name", "")
        if tool == "run_shell":
            return args.get("command", "")
        if tool == "list_dir":
            return "workspace"
        return ""

    def __call__(self, event):
        if event.type == "action":
            target = self._target(event.tool_name, event.arguments)
            self.pending[event.id] = (event.tool_name, target)
            ing, _ = self.VERBS.get(event.tool_name, ("Calling", "Called"))
            print(f"  {ing} {target or event.tool_name}...")

        elif event.type == "observation":
            entry = self.pending.pop(event.action_id, None)
            if entry is None:
                logger.warning("observation %s has no matching action", event.action_id)
                entry = ("tool", "")
            tool, target = entry

            _, done = self.VERBS.get(tool, ("Calling", "Called"))
            text = str(event.content)
            failed = text.startswith("error") or (
                tool == "run_shell" and not text.startswith("exit=0"))

            if failed:
                first = text.splitlines()[0][:100] if text else ""
                print(f"  Failed: {tool} {target} ({first})")
            elif tool == "edit_file":
                print(f"  {done} {target or tool}")