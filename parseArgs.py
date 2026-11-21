import argparse
from permissions.modes import MODES

def parse_args():
    parser = argparse.ArgumentParser(description="Coding agent harness")

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--continue", dest="continue_session", action="store_true",
        help="Continue the most recently active session",
    )
    
    group.add_argument(
        "--resume", nargs="?", const="interactive", default=None,
        help="Select a previous session or provide a session ID",
    )

    parser.add_argument(
        "prompt", nargs="?",
        help="Run one prompt and exit (non-interactive)",
    )
    parser.add_argument(
        "--allow-shell", action="store_true",
        help="Auto-approve shell commands (batch mode only)",
    )
    parser.add_argument(
        "--yes", action="store_true",
        help="Answer yes to confirmation prompts (batch mode only)",
    )

    parser.add_argument(
        "--mode", choices=MODES, default="accept_edits",
        help="Permission mode (default: accept_edits)"
    )

    return parser.parse_args()
