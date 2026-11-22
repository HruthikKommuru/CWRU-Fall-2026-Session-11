"""The four functions Gemini may call. Every tool returns text, including failures."""
import json
import os
from decimal import Decimal
from threading import Lock

import pandas as pd
from langchain.chat_models import init_chat_model
from langchain.embeddings import init_embeddings
from langchain.tools import tool
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone

from approvals import consume_approval
from config import (
    CHAT_MODEL, DRAFT_REPLY_PROMPT, EMBEDDING_MODEL, EMPTY_HANDBOOK,
    INDEX_NAME, K, NAMESPACE, ORDER_FIELDS, ORDERS_PATH, REFUNDS_PATH,
)

# One writer at a time prevents parallel tool calls from recording duplicate refunds.
_refund_lock = Lock()


def read_order(order_id: str) -> dict | None:
    """Read the support fields for one order without loading identity columns."""
    # Load only the support columns, then check one order at a time.
    orders = pd.read_csv(ORDERS_PATH, usecols=ORDER_FIELDS, keep_default_na=False)
    for order in orders.to_dict("records"):
        if order["order_id"] == order_id:
            return order
    return None


def get_store() -> PineconeVectorStore:
    """Read the existing Session 10 index and check that its namespace contains records."""
    # Connect to the index that Session 10 already created.
    pinecone = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    description = pinecone.describe_index(INDEX_NAME)
    index = pinecone.Index(host=description.host)

    # A namespace is a named group of saved handbook pieces inside that index.
    statistics = index.describe_index_stats()
    namespace = statistics.namespaces.get(NAMESPACE)
    if namespace is None or namespace.vector_count == 0:
        raise RuntimeError(EMPTY_HANDBOOK)
    # Embeddings turn the search question into numbers that Pinecone can compare.
    embeddings = init_embeddings(EMBEDDING_MODEL)
    return PineconeVectorStore(index=index, embedding=embeddings, namespace=NAMESPACE)


# TOOL 1: The model uses an exact order ID to obtain verified purchase details.
@tool
def lookup_order(order_id: str) -> str:
    """Find an order before acting on it; use an exact T- order ID. Return order details or a missing-order/error message."""
    try:
        order = read_order(order_id)
        if order is None:
            return f"No order {order_id} found."
        # JSON is dictionary-shaped text that the model can read.
        return json.dumps(order)
    except Exception:
        return "Order lookup unavailable. Check data/orders.csv."


# TOOL 2: Only query operations are allowed. Nothing here creates or writes vectors.
@tool
def search_handbook(query: str) -> str:
    """Check handbook policy before stating a rule. Return up to four cited excerpts, or a friendly search/setup error."""
    try:
        store = get_store()
        pieces = store.similarity_search(query, k=K, namespace=NAMESPACE)

        # Put a heading citation above each matching handbook piece.
        excerpts = []
        for piece in pieces:
            label = piece.metadata.get("section", "Front matter")
            if piece.metadata.get("topic"):
                label += " > " + piece.metadata["topic"]
            excerpts.append(f"[{label}]\n{piece.page_content}")
        if not excerpts:
            return EMPTY_HANDBOOK
        return "\n\n".join(excerpts)
    except Exception:
        return "Handbook search unavailable. Check keys (auth), wait and retry (429/500), or " + EMPTY_HANDBOOK


# TOOL 3: This creates a text draft; it does not send a message or authorize a refund.
@tool
def draft_reply(situation: str) -> str:
    """Draft a short polite reply after collecting verified facts and cited policy. Return a draft, or an error; never send it."""
    try:
        # Step 1: combine the writing rules with the verified support facts.
        prompt = ChatPromptTemplate.from_messages([
            ("system", DRAFT_REPLY_PROMPT), ("human", "{situation}")
        ])
        # Step 2: let Gemini draft a reply, retrying temporary failures up to 3 times.
        model = init_chat_model(CHAT_MODEL)
        model = model.with_retry(stop_after_attempt=3)

        # Step 3: turn the model's message into plain text. | means "pass to the next step".
        parser = StrOutputParser()
        chain = prompt | model | parser
        return chain.invoke({"situation": situation})
    except Exception:
        return "Reply drafting unavailable. Check your Google key; for 429/500, wait and retry."


# TOOL 4: Approval is enforced by middleware AND checked here before a local write.
@tool
def issue_refund(order_id: str, amount: float) -> str:
    """Record a fake refund only for an eligible delivered order after human approval. Return confirmation or a refusal; never move real money."""
    with _refund_lock:
        try:
            # First check the order. Missing or undelivered orders cannot be refunded.
            order = read_order(order_id)
            if order is None:
                return f"No order {order_id} found."
            if order["status"] != "delivered":
                return "Refund refused: order must be delivered."

            # Decimal compares money accurately; invalid values and fractions of a cent are refused.
            value = Decimal(str(amount))
            price = Decimal(str(order["price"]))
            valid_amount = value.is_finite() and value > 0 and value <= price
            if not valid_amount:
                return "Refund refused: amount must be positive and no greater than the order price."
            if value != value.quantize(Decimal("0.01")):
                return "Refund refused: use whole cents."

            # An order can appear only once in the refund ledger, even after restarting Python.
            if REFUNDS_PATH.exists():
                refunded_ids = pd.read_csv(REFUNDS_PATH)["order_id"].values
                if order_id in refunded_ids:
                    return "Already refunded. No action taken."

            # This uses up the exact permission created by the person's approval.
            if not consume_approval(order_id, value):
                return "Human approval required. No action taken."

            # All checks passed. Append a fake record; there is no payment API.
            REFUNDS_PATH.parent.mkdir(parents=True, exist_ok=True)
            record = pd.DataFrame([{"order_id": order_id, "amount": f"{value:.2f}"}])
            record.to_csv(REFUNDS_PATH, mode="a", index=False, header=not REFUNDS_PATH.exists())
            return f"Fake refund recorded: {order_id}, {value:.2f} dollars. No real money moved."
        except Exception:
            return "Refund unavailable. Check the amount and local CSV files; no retry is automatic."


# These are the four tools available to the support agent.
TOOLS = [search_handbook, lookup_order, draft_reply, issue_refund]
for current_tool in TOOLS:
    current_tool.handle_validation_error = "Invalid tool arguments. Check the order ID, amount, or query."
