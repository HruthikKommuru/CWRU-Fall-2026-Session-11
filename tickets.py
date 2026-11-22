"""Run the six supplied complaints and compare proposed tools with expected tools."""
import pandas as pd
from langchain_core.messages import AIMessage

from agent import run_agent
from config import MAX_STEPS, TICKETS_PATH


def requested_tools(messages: list) -> set:
    """Read tool names from model requests; a request does not prove a refund executed."""
    # A set keeps each tool name once, even if the model requested it several times.
    names = set()
    for message in messages:
        if isinstance(message, AIMessage):
            for call in message.tool_calls:
                names.add(call["name"])
    return names


def run_tickets(agent) -> int:
    """Print one routing check per ticket and return zero only when all pass."""
    # 1. Read the complaints. Each dictionary below represents one CSV row.
    if not TICKETS_PATH.is_file():
        print("Missing data/test_tickets.csv. Restore the supplied test complaints.")
        return 1
    rows = pd.read_csv(TICKETS_PATH, keep_default_na=False)
    passed = 0
    for ticket in rows.to_dict("records"):
        # 2. Send this complaint through the same agent used by main.py.
        print("\nTicket", ticket["ticket_id"], ":", ticket["message"])
        result = run_agent(agent, ticket["message"])
        requested = requested_tools(result["messages"])
        expected = set(ticket["expected_tools"].split(";"))

        # 3. Check the chosen tools. A failed or over-budget run cannot pass.
        ok = requested == expected
        if result["stopped"] or result["steps"] > MAX_STEPS:
            ok = False
        mark = "✗"
        if ok:
            passed += 1
            mark = "✓"
        print(mark, "Ticket", ticket["ticket_id"], "requested:", sorted(requested))
        if not ok:
            print("Expected:", sorted(expected))

    # 4. Show the total. A zero return code tells the terminal that all checks passed.
    print(f"Tool checks: {passed}/{len(rows)}")
    if passed == len(rows):
        return 0
    return 1
