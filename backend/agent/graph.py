"""LangGraph definition for the Edesia agent."""

from typing import Literal, Optional
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.base import BaseCheckpointSaver

from agent.state import AgentState
from agent.nodes import (
    router_node,
    planner_node,
    executor_node,
    approval_node,
    summarizer_node,
    preferences_node,
)
from agent.nodes.vendor_search import vendor_search_node
from agent.nodes.order_builder import order_builder_node
from agent.nodes.order_validator import order_validator_node
from agent.nodes.order_submit import order_submit_node


def should_plan(state: AgentState) -> Literal["executor"]:
    """Route all requests to executor for simplicity.

    The executor handles tool calls and generates responses.
    Complex routing was causing duplicate LLM calls.
    """
    # Simplified: all requests go to executor
    return "executor"


def route_food_order(state: AgentState) -> Literal["vendor_search", "order_builder", "order_validator", "order_submit", "executor"]:
    """Route within food order workflow based on current step."""
    food_order = state.get("food_order")

    if not food_order:
        return "vendor_search"

    current_step = food_order.get("current_step", "gather_requirements") if isinstance(food_order, dict) else food_order.current_step
    requested_step = state.get("requested_step")

    # Handle jump requests - user can skip to specific steps
    if requested_step:
        step_mapping = {
            "search_vendors": "vendor_search",
            "build_order": "order_builder",
            "review_order": "order_validator",
            "confirm_order": "order_submit",
        }
        if requested_step in step_mapping:
            return step_mapping[requested_step]

    # Normal workflow routing
    step_routing = {
        "gather_requirements": "executor",  # Use executor to gather info
        "search_vendors": "vendor_search",
        "select_vendor": "executor",  # Use executor for conversation
        "build_order": "order_builder",
        "review_order": "order_validator",
        "confirm_order": "order_submit",
        "submit_order": "order_submit",
        "track_order": "executor",
    }

    return step_routing.get(current_step, "executor")


def after_validation(state: AgentState) -> Literal["approval", "order_builder"]:
    """After validation, route based on errors."""
    food_order = state.get("food_order")

    if not food_order:
        return "order_builder"

    errors = food_order.get("validation_errors", []) if isinstance(food_order, dict) else food_order.validation_errors

    if errors:
        return "order_builder"  # Go back to fix issues

    return "approval"  # Proceed to confirmation


def needs_approval_check(state: AgentState) -> Literal["approval", "summarizer"]:
    """Check if we need human approval."""
    pending_actions = state.get("pending_actions", [])

    if pending_actions:
        return "approval"

    return "summarizer"


def create_agent_graph(checkpointer: Optional[BaseCheckpointSaver] = None) -> StateGraph:
    """Create and compile the agent graph.

    Args:
        checkpointer: Optional LangGraph checkpointer for persistent memory.
                     Pass a RedisSaver for production use.

    Graph Structure:
        preferences (entry) ---> router
           |
           +---> planner ---> executor ---> approval/summarizer ---> END
           |
           +---> executor ---> approval/summarizer ---> END
           |
           +---> food_order workflow:
                    |
                    +---> vendor_search ---> executor (selection)
                    |
                    +---> order_builder ---> order_validator
                    |                              |
                    |                       +------+------+
                    |                       |             |
                    |                   [errors]      [pass]
                    |                       |             |
                    |                       v             v
                    +<---------------- order_builder  order_submit ---> approval ---> END

    The preferences node runs first to:
    - Load user food preferences from Redis
    - Detect and save new preferences mentioned in the message
    """

    # Create the graph with our state schema
    graph = StateGraph(AgentState)

    # Add preferences node (runs first to load/detect preferences)
    graph.add_node("preferences", preferences_node)

    # Add core nodes
    graph.add_node("router", router_node)
    graph.add_node("planner", planner_node)
    graph.add_node("executor", executor_node)
    graph.add_node("approval", approval_node)
    graph.add_node("summarizer", summarizer_node)

    # Add food order workflow nodes
    graph.add_node("vendor_search", vendor_search_node)
    graph.add_node("order_builder", order_builder_node)
    graph.add_node("order_validator", order_validator_node)
    graph.add_node("order_submit", order_submit_node)

    # Set entry point to preferences node
    graph.set_entry_point("preferences")

    # Preferences always goes to router
    graph.add_edge("preferences", "router")

    # All requests go to executor (simplified routing)
    graph.add_edge("router", "executor")

    # Executor goes directly to END (simplified - no summarizer needed)
    graph.add_edge("executor", END)

    # Order builder goes to validator
    graph.add_edge("order_builder", "order_validator")

    # Validator routes based on errors
    graph.add_conditional_edges(
        "order_validator",
        after_validation,
        {
            "order_builder": "order_builder",
            "approval": "approval",
        }
    )

    # Order submit goes to approval (for confirmation)
    graph.add_edge("order_submit", "approval")

    # Approval and summarizer both end
    graph.add_edge("approval", END)
    graph.add_edge("summarizer", END)

    # Compile the graph with optional checkpointer for persistent memory
    return graph.compile(checkpointer=checkpointer)
