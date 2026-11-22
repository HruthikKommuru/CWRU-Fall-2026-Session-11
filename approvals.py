"""Human approval only. The model cannot approve its own refund requests."""
import logging
from decimal import Decimal

# A receipt is an exact (order ID, amount) pair. A set keeps each permission unique.
# This private collection is separate from the tools offered to the model.
_approval_receipts: set[tuple[str, Decimal]] = set()
logger = logging.getLogger(__name__)


def clear_approvals() -> None:
    """Discard unused permissions when a complaint starts or ends."""
    _approval_receipts.clear()


def consume_approval(order_id: str, amount: Decimal) -> bool:
    """Use one matching permission, returning False when the human has not approved it."""
    receipt = (order_id, amount)
    if receipt not in _approval_receipts:
        return False
    _approval_receipts.remove(receipt)
    return True


def review_actions(actions: list[dict]) -> dict:
    """Show proposed actions, read human input, and return ordered approve/reject decisions."""
    decisions = []
    for action in actions:
        print("Pending approval:", action["name"], action["args"])
        choice = input("approve / reject: ").strip().lower()

        # Only a person typing approve grants permission for these exact arguments.
        if choice == "approve" and action["name"] == "issue_refund":
            args = action["args"]
            receipt = (args["order_id"], Decimal(str(args["amount"])))
            _approval_receipts.add(receipt)
            decision = {"type": "approve"}
        else:
            decision = {"type": "reject", "message": "Human rejected this action. Do not retry it."}

        # LangChain expects one decision for each action, in the same order.
        decisions.append(decision)
        logger.info("APPROVAL | %s", decision["type"])
    return {"decisions": decisions}
