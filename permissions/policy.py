#Decides whether a tool call is allowed, needs approval or is denied

#This module has access to both rules and modes and is the only module that can decide

from dataclasses import dataclass

from permissions.modes import DEFAULT, MODES, PLAN, DONT_ASK, fallback, category, plan_block_reason
from permissions.rules import Rule, parse_rule, rule_matches, subject, command_parts, has_shell_syntax

@dataclass(frozen=True)
class Decision:
    action : str #allow, ask, deny
    reason : str
    source : str #rule | mode

class Policy:
    def __init__(self, mode=DEFAULT, allow = (), ask = (), deny = ()): 
        if mode not in MODES:
            raise ValueError(f"Unknown mode : {mode!r}")
        self.mode = mode

        self.allow: list[Rule] = [parse_rule(r) for r in allow]
        self.ask: list[Rule] = [parse_rule(r) for r in ask]
        self.deny: list[Rule] = [parse_rule(r) for r in deny]

    @staticmethod
    def _first(rules, tool, candidates):
        """The first rule in 'rules' that covers this call or None"""
        for rule in rules:
            if rule_matches(rule, tool, candidates):
                return rule
        return None

    def _record(self, action:str, reason:str, source:str)->Decision:
        """Build a Decision, converting ask to deny in dont_ask mode"""

        if self.mode == DONT_ASK and action == "ask":
            return Decision("deny", f"{reason}; dont_ask refuses instead of asking", source)
        return Decision(action, reason, source)


    def decide(self, tool:str, args)->Decision:
        #Decide whether a tool call is denied, asked or allowed
        """
        Precedence, highest first:
          1. deny rules      -- a user restriction always wins
          2. plan mode       -- the mode's own safety override (can beat allow)
          3. ask rules       -- an explicit "ask" outranks an explicit "allow"
          4. allow rules     -- a grant, matched conservatively
          5. the mode        -- fallback when no rule matched
        """
        
        whole = subject(tool, args)

        checked = [whole]
        if tool == "run_shell":
            checked += command_parts(whole)

        #check deny first
        rule = self._first(self.deny, tool, checked)
        if rule is not None:
            return Decision("deny", f"denied by rule {rule}", "rule")

        #check if mode is plan
        if self.mode == PLAN:
            blocked = plan_block_reason(tool, whole)
            if blocked is not None:
                return self._record("deny", blocked, "mode")

        #check ask then
        rule = self._first(self.ask, tool, checked)
        if rule is not None:
            return self._record("ask", f"ask rule matched {rule}", "rule")

        if not(tool == "run_shell" and has_shell_syntax(whole)):
            rule = self._first(self.allow, tool, [whole])

            if rule is not None:
               return Decision("allow", f"allowed by rule {rule}", "rule")

        action, reason = fallback(self.mode, tool)
        return self._record(action, reason, source="mode")

    def is_hidden(self, tool)->bool:
        #True if the model shouldnt be told about this tool at all
        if any(r.tool == tool and r.pattern is None for r in self.deny):
            return True
        return self.mode == PLAN and category(tool) not in ("read", "internal")
    