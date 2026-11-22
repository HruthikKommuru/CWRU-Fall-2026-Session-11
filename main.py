"""Run the TrailMix support agent for one complaint or the six supplied tickets."""
import argparse
import logging

from agent import build_agent, run_agent
from config import EMPTY_HANDBOOK, configure_logging, load_config
from tickets import run_tickets
from tools import get_store


def main() -> int:
    """Read the command, check setup, and run the support agent."""
    # 1. Choose one complaint or the supplied ticket list.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("message", nargs="?", help="A customer complaint in quotes")
    parser.add_argument("--tickets", action="store_true", help="Run the six supplied complaints")
    args = parser.parse_args()
    if args.message and args.tickets:
        parser.error("Use a quoted complaint or --tickets, one at a time.")
    if not args.message and not args.tickets:
        parser.error("Supply a quoted complaint or --tickets.")

    # 2. Load private keys and check the existing handbook before running.
    configure_logging()
    if not load_config():
        return 1
    try:
        get_store()
        agent = build_agent()

        # 3. Run the chosen input. Each proposed refund still needs human approval.
        if args.tickets:
            return run_tickets(agent)
        result = run_agent(agent, args.message)
        if result["stopped"]:
            return 1
        return 0
    except Exception as error:
        if isinstance(error, RuntimeError) and str(error) == EMPTY_HANDBOOK:
            logging.error("%s", EMPTY_HANDBOOK)
        else:
            logging.error("Setup failed. Check keys/index; for 429/500, wait and retry.")
        return 1


# Start the application when this file is run from the terminal.
if __name__ == "__main__":
    raise SystemExit(main())
