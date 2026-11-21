#The checkpoint every tool call passes through passes through before it runs

import logging
from dataclasses import dataclass
from permissions.policy import Policy
from permissions.approver import TerminalApprover


logger = logging.getLogger(__name__)



USER_DENIED = (
    "error: user denied this call. Do not retry it, and do not mark any "
    "verification step completed. Tell the user the work is unverified, or ask "
    "how they want to verify it."
)

def refusal(reason):
    return (f"error: this call was refused ({reason}). Do not retry it. "
            "Use a different approach, or tell the user what you could not do.")

@dataclass(frozen=True)
class Verdict:
    allowed :bool
    message : str
    action : str #what the policy said 
    source : str #rule/mode/user/error
    reason : str


class Gate:
    def __init__(self, policy: Policy, approver:TerminalApprover):
        self.policy = policy
        self.approver = approver

    def check(self, tool, args):
        #returns a verdict
        try:
            d = self.policy.decide(tool, args)

            if d.action == "allow":
                verdict = Verdict(True, "", "allow", d.source, d.reason)

            elif d.action == "deny":
                verdict = Verdict(False, refusal(d.reason), "deny", d.source, d.reason)

            elif d.action == "ask":
                answer = self.approver.ask(tool, args, d.reason)

                if answer.allowed:
                    verdict = Verdict(True, "", "ask", "user", "user approved")
                else:
                    verdict = Verdict(False, USER_DENIED, "ask", "user",
                                      answer.note or "user said no")
            else:
                raise ValueError(f"unknown policy action: {d.action!r}")

        except Exception:
            logger.exception("permission check failed for %s", tool)
            verdict = Verdict(False, "error: the permission check failed, so the call was refused", "deny", "error", "check failed")

        logger.info("PERMISSION tool=%s action=%s source=%s allowed=%s reason=%s",
                    tool, verdict.action, verdict.source, verdict.allowed, verdict.reason)
        return verdict
