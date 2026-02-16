"""Planner node for multi-step task breakdown."""

import weave
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from agent.state import AgentState
from agent.prompts import PLANNER_PROMPT, SYSTEM_PROMPT


@weave.op()
def planner_node(state: AgentState) -> dict:
    """
    Break down complex requests into actionable steps.

    Returns updated state with a plan.
    """
    messages = state.get("messages", [])
    intent = state.get("intent", "general")
    event_details = state.get("event_details")

    # Get the last user message
    last_message = ""
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "user":
            last_message = msg.get("content", "")
            break
        elif hasattr(msg, "type") and msg.type == "human":
            last_message = msg.content
            break

    # Build context for planning
    event_context = ""
    if event_details:
        event_context = f"""
Event: {event_details.get('name', 'Unnamed')}
Date: {event_details.get('date', 'TBD')}
Headcount: {event_details.get('headcount', 'TBD')}
Budget: ${event_details.get('budget', 'TBD')}
Dietary: {', '.join(event_details.get('dietary_restrictions', [])) or 'None specified'}
"""

    planning_prompt = PLANNER_PROMPT.format(
        request=last_message,
        event_details=event_context or "No event details provided yet.",
    )

    llm = ChatGroq(
        model="openai/gpt-oss-120b",
        temperature=0.3,
        max_tokens=500,
    )

    response = llm.invoke([
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=planning_prompt),
    ])

    plan = response.content

    return {
        "current_plan": plan,
        "messages": [AIMessage(content=f"Here's my plan:\n\n{plan}")],
    }
