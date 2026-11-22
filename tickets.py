"""Run the six supplied complaints and compare proposed tools with expected tools."""
from typing import Any
import pandas as pd
from langchain_core.messages import AIMessage

from agent import run_agent
from config import MAX_STEPS, TICKETS_PATH


def requested_tools(messages: list) -> set[str]:
    """Read tool names from model requests; a request does not prove a refund executed."""
    names = set()
    for message in messages:
        if isinstance(message, AIMessage):
            for call in message.tool_calls:
                names.add(call["name"])
    return names


def run_tickets(agent: Any) -> int:
    """Print one routing check per ticket and return zero only when all pass."""
    rows = pd.read_csv(TICKETS_PATH, keep_default_na=False)
    passed = 0
    for row in rows.itertuples():
        print("\nTicket", row.ticket_id, ":", row.message)
        result = run_agent(agent, row.message)
        requested = requested_tools(result["messages"])
        expected = set(row.expected_tools.split(";"))

        # Compare sets of tool names and reject runs that stopped early or exceeded the budget.
        ok = requested == expected
        if result["stopped"] or result["steps"] > MAX_STEPS:
            ok = False
        mark = "✗"
        if ok:
            passed += 1
            mark = "✓"
        print(mark, "Ticket", row.ticket_id, "requested:", sorted(requested))
        if not ok:
            print("Expected:", sorted(expected))

    print(f"Tool checks: {passed}/{len(rows)}")
    if passed == len(rows):
        return 0
    return 1
