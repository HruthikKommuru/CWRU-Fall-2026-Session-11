"""Start here: choose a tool exercise, a read-only agent, the full agent, or ticket tests."""
import argparse
import logging
import os

# Each import names the function AND the file that owns it. No lab alias is used.
from config import EMPTY_HANDBOOK, TICKETS_PATH, configure_logging, load_config
from approvals import clear_approvals, review_actions
from tools import draft_reply, get_store, issue_refund, lookup_order, search_handbook
from agent import build_agent, run_agent
from tickets import run_tickets


def run_tool_demo() -> int:
    """Call the four tools directly so students can see each input and output."""
    # Start a fresh exercise with no unused permission from an earlier direct call.
    clear_approvals()

    # Local lookups and guardrail checks work without any API credentials.
    print("\nORDER LOOKUP")
    print(lookup_order.invoke({"order_id": "T-1042"}))
    print(lookup_order.invoke({"order_id": "T-9999"}))
    print("\nREFUND GUARDRAILS")
    print(issue_refund.invoke({"order_id": "T-1015", "amount": 10}))
    print(issue_refund.invoke({"order_id": "T-1042", "amount": 90}))
    print(issue_refund.invoke({"order_id": "T-1001", "amount": 10}))

    # Search and drafting are the two tools that require live service access.
    if os.getenv("GOOGLE_API_KEY") and os.getenv("PINECONE_API_KEY"):
        print("\nHANDBOOK SEARCH")
        evidence = search_handbook.invoke({"query": "Customer smells gas from a Summit Stove"})
        print(evidence)
        print("\nREPLY DRAFT")
        facts = evidence + "\n" + lookup_order.invoke({"order_id": "T-1042"})
        print(draft_reply.invoke({"situation": facts}))
    else:
        print("\nAdd both keys to .env to also run handbook search and reply drafting.")

    # Even a direct tool call needs a person's exact, one-use approval.
    print("\nPRACTICE REFUND: T-1001, 10 dollars (fictional)")
    request = {"name": "issue_refund", "args": {"order_id": "T-1001", "amount": 10}}
    try:
        decisions = review_actions([request])
        if decisions["decisions"][0]["type"] == "approve":
            print(issue_refund.invoke(request["args"]))
            print(issue_refund.invoke(request["args"]))
        else:
            print("Rejected: no practice refund was written.")
    except (EOFError, KeyboardInterrupt):
        print("Practice demo stopped. Inspect output/refunds.csv before retrying.")
    finally:
        clear_approvals()
    return 0


def main() -> int:
    """Read command-line options, validate setup, and start the selected exercise."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("message", nargs="?", help="A customer complaint, enclosed in quotes")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--demo-tools", action="store_true", help="Try each tool without an agent")
    modes.add_argument("--read-only", action="store_true", help="Run without the refund tool")
    modes.add_argument("--tickets", action="store_true", help="Run the six supplied test complaints")
    parser.add_argument("--verbose", action="store_true", help="Show DEBUG logs")
    args = parser.parse_args()
    configure_logging(args.verbose)

    # Make invalid command combinations clear before loading keys or connecting to services.
    if args.message and (args.demo_tools or args.tickets):
        parser.error("Use a message, --demo-tools, or --tickets as separate exercises.")
    if not (args.message or args.demo_tools or args.tickets):
        parser.error("Supply a quoted complaint, --demo-tools, or --tickets.")
    if not load_config(require_keys=not args.demo_tools):
        return 1
    if args.tickets and not TICKETS_PATH.is_file():
        logging.error("Missing data/test_tickets.csv. Restore the supplied test fixture.")
        return 1
    if args.demo_tools:
        return run_tool_demo()

    try:
        # This checks an existing namespace only. The lab never ingests or modifies Pinecone.
        get_store()
        support_agent = build_agent(read_only=args.read_only)
        if args.tickets:
            return run_tickets(support_agent)
        result = run_agent(support_agent, args.message)
        if result["stopped"]:
            return 1
        return 0
    except Exception as error:
        if isinstance(error, RuntimeError) and str(error) == EMPTY_HANDBOOK:
            logging.error("%s", EMPTY_HANDBOOK)
        else:
            logging.error("Setup failed. Check keys/index; for 429/500, wait and retry.")
        return 1


# Python runs this block only when main.py is started directly from the terminal.
if __name__ == "__main__":
    raise SystemExit(main())
