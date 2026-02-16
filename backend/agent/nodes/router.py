"""Router node for intent classification."""

import weave
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

from agent.state import AgentState
from agent.prompts import ROUTER_PROMPT

VALID_INTENTS = {"reservation", "catering", "poll", "budget", "browser", "general", "food_order", "delivery"}


@weave.op()
def router_node(state: AgentState) -> dict:
    """
    Classify the user's intent to route to appropriate handler.

    Returns updated state with intent classification.
    """
    messages = state.get("messages", [])
    if not messages:
        return {"intent": "general"}

    # Get the last user message
    last_message = None
    for msg in reversed(messages):
        if isinstance(msg, dict) and msg.get("role") == "user":
            last_message = msg.get("content", "")
            break
        elif hasattr(msg, "type") and msg.type == "human":
            last_message = msg.content
            break

    if not last_message:
        return {"intent": "general"}

    # Use Groq for fast classification
    llm = ChatGroq(
        model="openai/gpt-oss-120b",
        temperature=0,
        max_tokens=20,
    )

    response = llm.invoke([
        SystemMessage(content=ROUTER_PROMPT),
        HumanMessage(content=last_message),
    ])

    intent = response.content.strip().lower()

    # Validate intent
    if intent not in VALID_INTENTS:
        intent = "general"

    # Map delivery to food_order for unified workflow
    if intent == "delivery":
        intent = "food_order"

    return {"intent": intent}
