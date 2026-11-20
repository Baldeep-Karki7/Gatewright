"""What a permission rule looks like

This is the vocabulary of the permission system. It ise used to match the tool call against a rule"""

import fnmatch
import os
import re
from dataclasses import dataclass
from typing import Optional

#tools that take file in their arguments
FILE_TOOLS = {"read_file", "write_file", "edit_file"}

# Characters that let one shell string do more than one thing.
_SHELL_SYNTAX = re.compile(r"[;&|`<>\n]|\$\(")

# Where to cut a compound command into its simple commands.
_SPLIT = re.compile(r"\|\||&&|[;&|\n`()]")

# A leading "NAME=value" assignment, e.g. FOO=1
_ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

# Wrapper commands that run another command after them.
_WRAPPERS = {"sudo", "env", "command", "nohup", "time", "exec"}

@dataclass(frozen=True)
class Rule:
    """A Rule = tool name, a glob the subject must macth"""

    #immutable
    tool :str
    pattern :Optional[str] = None

    def __str__(self):
        return f"{self.tool}({self.pattern})" if self.pattern else self.tool


def parse_rule(text:str):
    """Turn a rule string into a Rule
    
    'run_shell(git push * )' -> Rule('run_shell','git push *')
    """

    text = text.strip()
    if "(" in text and text.endswith(")"):
        tool, pattern = text[:-1].split("(",1)
        tool, pattern = tool.strip(), pattern.strip()
        if not tool or not pattern:
            raise ValueError(f"bad rule: {text!r}")
        return Rule(tool, pattern)

    if not text:
        raise ValueError("empty rule")

    #no parenthesis, then tool wide rule
    return Rule(text)


def subject(tool:str, args)->str:
    """The part of a call that patterns are matched against"""

    if not isinstance(args, dict):
        return ""

    if tool in FILE_TOOLS:
        return os.path.normpath(str(args.get("file_name","")))

    if tool == "list_dir":
        return os.path.normpath(str(args.get("path", ".")))

    if tool == "run_shell":
        return " ".join(str(args.get("command", "")).split())

    #unknown tool
    return ""

def has_shell_syntax(command:str)->bool:
    """True if the command chains, pipes, redirects or substitutes
    
    Cheap version of "is it a compound command??"
    """
    return bool(_SHELL_SYNTAX.search(command))

def command_parts(command: str) -> list[str]:
    """Split a compound command into simple commands, without leading VAR=x or sudo.

    It may split too much (for example inside quotes). That only makes matching
    stricter, which is the safe direction: an over-split can cause a false
    match on a deny rule or an extra prompt, never a false pass.
    """
    parts = []
    for piece in _SPLIT.split(command):
        words = piece.split()

        # Strip leading assignments and wrappers so that "FOO=1 sudo git push"
        # is judged as "git push".
        while words and (_ASSIGNMENT.match(words[0]) or words[0] in _WRAPPERS):
            words = words[1:]

        if words:
            parts.append(" ".join(words))

    return parts


def rule_matches(rule: Rule, tool:str, candidates: list[str])->bool:
    """Does this rule cover a call to 'tool' whose matchable strings are 'candidates'?"""

    if rule.tool != tool:
        return False

    if rule.pattern is None:
        return True

    return any(fnmatch.fnmatchcase(c, rule.pattern)for c in candidates)