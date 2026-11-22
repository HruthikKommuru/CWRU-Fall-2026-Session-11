"""Build and run the agent loop. Start the application with main.py."""
import logging
from typing import Any
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
from tools import ALL_TOOLS, READ_ONLY_TOOLS

logger = logging.getLogger(__name__)


def build_agent(read_only: bool = False, model: Any = None) -> Any:
    """Give Gemini its tools, instructions, and approval gate."""
    # A test can supply a local scripted model; normal runs always create Gemini.
    if model is None:
        model = init_chat_model(CHAT_MODEL)

    # Read-only mode cannot refund because that tool is not available to the model.
    active_tools = READ_ONLY_TOOLS
    middleware = []
    if not read_only:
        active_tools = ALL_TOOLS
        approval = HumanInTheLoopMiddleware(interrupt_on={"issue_refund": True})
        middleware.append(approval)

    # The checkpointer remembers a paused run until the person reviews its action.
    return create_agent(
        model=model, tools=active_tools, system_prompt=SYSTEM_PROMPT,
        middleware=middleware, checkpointer=InMemorySaver(),
    )


def log_message(message: Any) -> None:
    """Show observable tool choices and returned results, not hidden reasoning."""
    if isinstance(message, AIMessage) and message.tool_calls:
        choices = []
        for call in message.tool_calls:
            choices.append(call["name"])
        logger.info("REASON | model selected %s", choices)
        for call in message.tool_calls:
            logger.info("ACT (proposed) | %s %s", call["name"], call["args"])
    elif isinstance(message, ToolMessage):
        logger.info("OBSERVE | %s", str(message.content)[:150])


def run_agent(agent: Any, message: str, thread_id: str | None = None) -> dict:
    """Run one complaint, review pending refunds, and return its messages and status."""
    if thread_id is None:
        thread_id = str(uuid4())
    run_config = {"recursion_limit": MAX_STEPS, "configurable": {"thread_id": thread_id}}
    request = {"messages": [{"role": "user", "content": message}]}
    result = {"messages": []}
    seen_messages = 0
    steps = 0
    stopped = False
    clear_approvals()

    try:
        while True:
            pending = []
            run_config["recursion_limit"] = max(1, MAX_STEPS - steps)

            # Each event contains the current conversation; inspect only new messages.
            for event in agent.stream(request, config=run_config, stream_mode="values"):
                if "__interrupt__" in event:
                    pending = event["__interrupt__"]
                    continue
                result = event
                new_messages = result["messages"][seen_messages:]
                seen_messages = len(result["messages"])
                model_or_tool_updated = False
                for current_message in new_messages:
                    if isinstance(current_message, (AIMessage, ToolMessage)):
                        model_or_tool_updated = True
                    log_message(current_message)
                if model_or_tool_updated:
                    steps += 1

                # A completed final answer is allowed at the limit; another action is not.
                last_message = result["messages"][-1]
                finished = isinstance(last_message, AIMessage) and not last_message.tool_calls
                if steps >= MAX_STEPS and not finished:
                    raise GraphRecursionError("Local step budget exhausted.")

            if not pending:
                break

            # The model has stopped. A person decides, then the same run resumes.
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
        # A failed or cancelled run must not leave unused permissions for another run.
        clear_approvals()

    result["steps"] = steps
    result["stopped"] = stopped
    final_text = "No answer."
    if result["messages"]:
        final_text = result["messages"][-1].content
    logger.info("DONE | %s | %d steps", final_text, steps)
    for current_message in result["messages"]:
        current_message.pretty_print()
    return result
