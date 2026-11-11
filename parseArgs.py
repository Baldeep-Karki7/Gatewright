import argparse

def parse_args():
    parser = argparse.ArgumentParser(
        description="Coding agent harness"
    )

    group = parser.add_mutually_exclusive_group()

    group.add_argument(
        "--continue",
        dest="continue_session",
        action="store_true",
        help="Continue the most recently active session"
    )

    group.add_argument(
        "--resume",
        nargs="?",
        const="interactive",
        default=None,
        help="Select a previous session or provide a session ID"
    )

    return parser.parse_args()