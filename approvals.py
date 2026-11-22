"""Ask a person before allowing a fake refund. Start reading at review_actions()."""
import logging
from decimal import Decimal

# An empty list means that no refunds have been approved yet.
# Each item will be a dictionary, for example: {"order_id": "T-1042", "amount": Decimal("89")}.
# Only the human-input code below adds items. This list is never a model tool.
_approved_refunds = []
logger = logging.getLogger(__name__)


def clear_approvals() -> None:
    """Start or finish a complaint with an empty approval list."""
    _approved_refunds.clear()


def consume_approval(order_id: str, amount: Decimal) -> bool:
    """Find an exact approval and remove it so it can only be used once."""
    for refund in _approved_refunds:
        same_order = refund["order_id"] == order_id
        same_amount = refund["amount"] == amount
        if same_order and same_amount:
            _approved_refunds.remove(refund)
            return True
    return False


def review_actions(actions: list) -> dict:
    """Ask about each proposed action and give LangChain the person's decisions."""
    decisions = []
    for action in actions:
        # 1. Show exactly what the model wants to do, then wait for keyboard input.
        print("Pending approval:", action["name"], action["args"])
        choice = input("approve / reject: ").strip().lower()

        # 2. Typing approve allows this order and amount, not any other refund.
        if choice == "approve" and action["name"] == "issue_refund":
            details = action["args"]
            _approved_refunds.append({
                "order_id": details["order_id"],
                "amount": Decimal(str(details["amount"])),
            })
            decision = {"type": "approve"}
        else:
            decision = {"type": "reject", "message": "Human rejected this action. Do not retry it."}

        # 3. Keep the decisions in the same order as the proposed actions.
        decisions.append(decision)
        logger.info("APPROVAL | %s", decision["type"])
    return {"decisions": decisions}
