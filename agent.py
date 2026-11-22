"""Create the agent, run a complaint, and pause when a person must approve a refund."""
import logging
from uuid import uuid4

from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphRecursionError
from langgraph.types import Command

from approvals import clear_approvals, review_actions
from config import CHAT_MODEL, MAX_STEPS, SYSTEM_PROMPT
from tools import TOOLS

logger = logging.getLogger(__name__)


def build_agent():
    """Give Gemini its instructions, available tools, and refund approval rule."""
    # Give Gemini all four tools, with a pause BEFORE issue_refund can run.
    model = init_chat_model(CHAT_MODEL)
    approval_rule = HumanInTheLoopMiddleware(interrupt_on={"issue_refund": True})

    # Memory saves the conversation while the person makes a decision.
    return create_agent(
        model=model,
        tools=TOOLS,
        system_prompt=SYSTEM_PROMPT,
        middleware=[approval_rule],
        checkpointer=InMemorySaver(),
    )


def count_steps(messages: list) -> int:
    """Count model turns and tool-result groups in the conversation."""
    steps = 0
    previous_was_tool = False
    for message in messages:
        # Several tools may run together. Their consecutive replies form one tool step.
        is_tool = isinstance(message, ToolMessage)
        if isinstance(message, AIMessage):
            steps += 1
        elif is_tool and not previous_was_tool:
            steps += 1
        previous_was_tool = is_tool
    return steps


def log_message(message) -> None:
    """Show the model's proposed tools or a tool's returned result."""
    if isinstance(message, AIMessage):
        for call in message.tool_calls:
            logger.info("REASON | model selected %s", call["name"])
            logger.info("ACT (proposed) | %s %s", call["name"], call["args"])
    elif isinstance(message, ToolMessage):
        logger.info("OBSERVE | %s", str(message.content)[:150])


def run_agent(agent, message: str) -> dict:
    """Run, check for approval, and resume until the complaint is finished."""
    # 1. Give each complaint its own ID. Keep that ID when resuming after approval.
    thread_id = str(uuid4())
    settings = {"recursion_limit": MAX_STEPS, "configurable": {"thread_id": thread_id}}
    request = {"messages": [{"role": "user", "content": message}]}
    result = {"messages": []}
    steps = 0
    stopped = False
    clear_approvals()

    try:
        while True:
            # 2. invoke() runs until the agent finishes OR pauses for human approval.
            settings["recursion_limit"] = max(1, MAX_STEPS - steps)
            result = agent.invoke(request, config=settings)
            steps = count_steps(result["messages"])

            # 3. No interrupt means the agent has finished this complaint.
            pending = result.get("__interrupt__", [])
            if not pending:
                break
            # Resuming needs room for the tool result and the model's next message.
            if MAX_STEPS - steps < 2:
                raise GraphRecursionError("No steps left for another action.")

            # 4. Show the proposed refund and resume with the person's decision.
            actions = pending[0].value["action_requests"]
            decisions = review_actions(actions)
            request = Command(resume=decisions)

    except GraphRecursionError:
        logger.warning("Agent stopped: step limit reached.")
        stopped = True
    except (EOFError, KeyboardInterrupt):
        logger.warning("Agent stopped: approval cancelled.")
        stopped = True
    except Exception:
        logger.error("Agent request failed. Check your keys; for 429/500, wait and retry.")
        stopped = True
    finally:
        # An approval from this complaint cannot be used by a later complaint.
        clear_approvals()
        if stopped:
            # Keep the partial trace even if a limit, cancelled input, or API error stopped us.
            result = agent.get_state(settings).values

    # 5. Print the recorded steps and full conversation after the run ends.
    messages = result.get("messages", [])
    for saved_message in messages:
        log_message(saved_message)
    steps = count_steps(messages)
    final_text = "No answer."
    if messages:
        final_text = messages[-1].content
    logger.info("DONE | %s | %d steps", final_text, steps)
    for saved_message in messages:
        saved_message.pretty_print()
    return {"messages": messages, "steps": steps, "stopped": stopped}
