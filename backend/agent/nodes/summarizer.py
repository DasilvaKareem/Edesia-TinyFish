"""Summarizer node for clean response formatting."""

import weave
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from agent.state import AgentState
from agent.prompts import SYSTEM_PROMPT


SUMMARIZER_SYSTEM = """You are a helpful assistant summarizing the results of actions.
Be concise, friendly, and professional. Format your response clearly.
If there are pending actions requiring approval, make that clear.
Include relevant details like prices, times, and next steps."""


@weave.op()
def summarizer_node(state: AgentState) -> dict:
    """
    Summarize results and format the final response.

    In most cases, the executor already provides a good response,
    so this node just passes through without adding another message.
    """
    # Always pass through - the executor's response is sufficient
    # This node exists for future use cases where we need post-processing
    return {}
