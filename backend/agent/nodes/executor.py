"""Executor node for running tools."""

import weave
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage
from langgraph.config import get_stream_writer

from agent.state import AgentState
from agent.prompts import get_system_prompt
from tools import ALL_TOOLS
from models.orders import FoodOrderContext


@weave.op()
async def executor_node(state: AgentState) -> dict:
    """
    Execute tools based on the conversation context.

    Streams status updates via get_stream_writer() for real-time UI feedback.

    Returns updated state with tool results.
    """
    # Get stream writer for custom status updates
    try:
        writer = get_stream_writer()
    except Exception:
        writer = None  # Fallback if streaming not available

    def emit_status(status: str, details: dict = None):
        """Emit a status update to the stream."""
        if writer:
            writer({
                "type": "status",
                "status": status,
                **(details or {}),
            })

    messages = state.get("messages", [])
    intent = state.get("intent", "general")
    current_plan = state.get("current_plan")
    user_preferences = state.get("user_preferences")
    timezone = state.get("timezone")
    user_profile = state.get("user_profile")
    user_id = state.get("user_id")
    has_images = state.get("has_images", False)

    emit_status("thinking", {"message": "Processing your request..."})

    # Log profile for debugging
    print(f"[EXECUTOR] user_profile from state: {user_profile}")
    print(f"[EXECUTOR] user_id from state: {user_id}")
    print(f"[EXECUTOR] has_images: {has_images}")

    # Get system prompt with user preferences, timezone, company profile, and user_id
    system_prompt = get_system_prompt(user_preferences, timezone, user_profile, user_id)

    # Log first 500 chars of prompt to verify profile section
    print(f"[EXECUTOR] System prompt preview: {system_prompt[:500]}...")

    # Convert messages to LangChain format
    lc_messages = [SystemMessage(content=system_prompt)]

    for msg in messages:
        if isinstance(msg, dict):
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                # Content can be a string or a list (multimodal with images)
                lc_messages.append(HumanMessage(content=content))
            elif role == "assistant":
                # Convert multimodal content to string for assistant messages
                if isinstance(content, list):
                    text_content = " ".join(
                        item.get("text", "") for item in content
                        if isinstance(item, dict) and item.get("type") == "text"
                    )
                    lc_messages.append(AIMessage(content=text_content or str(content)))
                else:
                    lc_messages.append(AIMessage(content=content))
        else:
            lc_messages.append(msg)

    # Add current plan context if available
    if current_plan:
        lc_messages.append(SystemMessage(content=f"Current plan:\n{current_plan}"))

    emit_status("calling_llm", {"message": "Generating response..."})

    # Choose model based on whether we have images
    if has_images:
        # Use Llama 4 Scout for vision (supports images)
        emit_status("processing_images", {"message": "Analyzing images..."})
        print(f"[EXECUTOR] Using vision model for image analysis")
        llm = ChatGroq(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            temperature=0.3,
            max_tokens=1500,
        )
        # Don't bind tools for vision - just analyze the image
        response = await llm.ainvoke(lc_messages)
    else:
        # Create LLM with tools bound
        llm = ChatGroq(
            model="openai/gpt-oss-120b",
            temperature=0.1,
            max_tokens=1000,
        ).bind_tools(ALL_TOOLS)

        # Invoke LLM
        response = await llm.ainvoke(lc_messages)

    # Check if there are tool calls
    # Reset pending actions each turn — old ones are already stored in actions_dict
    pending_actions = []
    new_messages = []
    food_order_update = None  # Track food order updates from tools

    # Vision model doesn't use tools, just return the response
    if has_images:
        emit_status("response_ready", {"message": "Image analysis complete"})
        new_messages.append(response)
        return {
            "messages": new_messages,
            "pending_actions": pending_actions,
            "needs_approval": False,
            "has_images": False,  # Reset for next message
        }

    if hasattr(response, "tool_calls") and response.tool_calls:
        emit_status("executing_tools", {
            "message": f"Running {len(response.tool_calls)} tool(s)...",
            "tool_count": len(response.tool_calls),
        })

        # Execute all tool calls
        tool_messages = []
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]

            emit_status("tool_start", {
                "message": f"Running {tool_name}...",
                "tool_name": tool_name,
            })

            # Find and execute the tool
            tool_result = None
            tool_error = None
            tool_found = False
            for tool in ALL_TOOLS:
                if tool.name == tool_name:
                    tool_found = True
                    print(f"[EXECUTOR] Calling tool: {tool_name} with args: {tool_args}")
                    try:
                        tool_result = await tool.ainvoke(tool_args)
                        print(f"[EXECUTOR] Tool {tool_name} returned: {tool_result}")
                    except Exception as e:
                        tool_error = str(e)
                        print(f"[EXECUTOR] Tool {tool_name} raised exception: {e}")
                    break

            if not tool_found:
                tool_error = f"Tool '{tool_name}' not found in available tools"
                print(f"[EXECUTOR] WARNING: {tool_error}")

            if tool_error:
                emit_status("tool_error", {
                    "message": f"Error in {tool_name}",
                    "tool_name": tool_name,
                    "error": tool_error,
                })
                tool_messages.append(ToolMessage(
                    content=f"Tool error: {tool_error}",
                    tool_call_id=tool_call.get("id", ""),
                ))
            elif tool_result:
                emit_status("tool_complete", {
                    "message": f"Completed {tool_name}",
                    "tool_name": tool_name,
                })
                # Check if this is a food order update
                if isinstance(tool_result, dict) and tool_result.get("__food_order_update__"):
                    food_order_update = {k: v for k, v in tool_result.items() if k != "__food_order_update__"}
                    tool_messages.append(ToolMessage(
                        content=f"Order details updated: {tool_result.get('selected_vendor', {}).get('name', 'Unknown')} for {tool_result.get('headcount', 0)} people",
                        tool_call_id=tool_call.get("id", ""),
                    ))
                # Check if this creates a pending action
                elif isinstance(tool_result, dict) and tool_result.get("action_type"):
                    pending_actions.append(tool_result)
                    tool_messages.append(ToolMessage(
                        content=f"Action created: {tool_result.get('description')} (requires approval)",
                        tool_call_id=tool_call.get("id", ""),
                    ))
                else:
                    tool_messages.append(ToolMessage(
                        content=str(tool_result),
                        tool_call_id=tool_call.get("id", ""),
                    ))

        # Now call LLM again with tool results to generate final response
        emit_status("generating_response", {"message": "Generating response from results..."})

        # Build a clean message history WITHOUT tool_calls for the final LLM call
        # This avoids the "tool_choice is none but model called a tool" error
        final_messages = [SystemMessage(content=system_prompt)]

        # Add conversation history
        for msg in messages:
            if isinstance(msg, dict):
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "user":
                    final_messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    final_messages.append(AIMessage(content=content))
            else:
                final_messages.append(msg)

        # Summarize tool results as a system message, flagging failures clearly
        tool_summary = "Tool execution results:\n"
        has_failures = False
        for i, tool_call in enumerate(response.tool_calls):
            tool_name = tool_call["name"]
            tool_result_content = tool_messages[i].content if i < len(tool_messages) else "No result"

            # Detect failed tool results (dicts with success: False)
            failed = "success" in tool_result_content.lower() and "'success': false" in tool_result_content.lower()
            if tool_result_content.startswith("Tool error:"):
                failed = True

            if failed:
                has_failures = True
                tool_summary += f"\n⚠️ {tool_name} FAILED: {tool_result_content}\n"
                print(f"[EXECUTOR] Tool FAILED: {tool_name} → {tool_result_content}")
            else:
                tool_summary += f"\n{tool_name}: {tool_result_content}\n"

        failure_instruction = ""
        if has_failures:
            failure_instruction = (
                "\n\nIMPORTANT: One or more tools FAILED (marked with ⚠️ above). "
                "You MUST tell the user the operation failed and ask them to try again. "
                "Do NOT claim the operation succeeded."
            )

        final_messages.append(SystemMessage(
            content=f"{tool_summary}{failure_instruction}\n\nBased on the tool results above, provide a helpful response to the user. Summarize the results in a conversational way."
        ))

        # Final LLM WITHOUT tools — Groq's llama model crashes with tool bindings
        llm_final = ChatGroq(
            model="llama-3.3-70b-versatile",
            temperature=0.3,
            max_tokens=1500,
        )

        final_response = await llm_final.ainvoke(final_messages)
        new_messages.append(final_response)
        emit_status("response_ready", {"message": "Response ready"})

    else:
        # No tool calls, just return the response
        emit_status("response_ready", {"message": "Response ready"})
        new_messages.append(response)

    # --- Sidebar extraction fallback ---
    # If update_food_order was NOT called by the LLM, use qwen3-32b to extract
    # structured order data from the response so the sidebar isn't empty.
    # This runs regardless of whether tools were called.
    if not food_order_update:
        # Get the response content from whichever path we took
        response_content = None
        if new_messages:
            last_msg = new_messages[-1]
            if hasattr(last_msg, "content"):
                response_content = last_msg.content

        if response_content:
            emit_status("syncing_sidebar", {"message": "Syncing order tracker..."})
            try:
                import json as _json

                extract_llm = ChatGroq(
                    model="qwen/qwen3-32b",
                    temperature=0,
                    max_tokens=600,
                )
                extract_result = await extract_llm.ainvoke([
                    SystemMessage(content=(
                        "Extract food order details from the text. Return ONLY valid JSON — no markdown, no explanation.\n"
                        "Schema: {\"vendor_name\":\"\", \"headcount\":0, \"event_date\":\"\", \"event_time\":\"\", "
                        "\"delivery_address\":\"\", \"vendor_address\":\"\", \"vendor_phone\":\"\", "
                        "\"items\":[{\"name\":\"\",\"quantity\":0,\"price\":0.0}], "
                        "\"subtotal\":0.0, \"tax\":0.0, \"delivery_fee\":0.0, \"total\":0.0, \"special_instructions\":\"\"}\n"
                        "Omit fields you cannot find. If no order info exists, return {}"
                    )),
                    HumanMessage(content=response_content),
                ])

                raw = extract_result.content.strip()
                # Strip thinking tags if present (qwen3 sometimes wraps in <think>)
                if "<think>" in raw:
                    raw = raw.split("</think>")[-1].strip()
                # Strip markdown code fences
                if raw.startswith("```"):
                    raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

                data = _json.loads(raw)

                if data and data.get("vendor_name"):
                    food_order_update = {
                        "selected_vendor": {
                            "name": data["vendor_name"],
                            "phone": data.get("vendor_phone", ""),
                            "address": data.get("vendor_address", ""),
                        },
                        "headcount": data.get("headcount", 0),
                        "event_date": data.get("event_date"),
                        "event_time": data.get("event_time"),
                        "delivery_address": data.get("delivery_address"),
                        "menu_items": data.get("items", []),
                        "subtotal": data.get("subtotal"),
                        "tax": data.get("tax"),
                        "delivery_fee": data.get("delivery_fee"),
                        "total": data.get("total"),
                        "special_instructions": data.get("special_instructions"),
                    }
                    print(f"[EXECUTOR] Qwen3 extracted order: vendor={data['vendor_name']}, items={len(data.get('items', []))}")
            except Exception as e:
                print(f"[EXECUTOR] Sidebar extraction failed (non-fatal): {e}")

    result = {
        "messages": new_messages,
        "pending_actions": pending_actions,
        "needs_approval": len(pending_actions) > 0,
    }

    # Pass through food order updates to graph state
    if food_order_update:
        # Merge with existing food_order or create new one
        existing = state.get("food_order")
        if existing:
            fo = existing if isinstance(existing, dict) else existing.dict()
            fo.update({k: v for k, v in food_order_update.items() if v is not None})
        else:
            fo = food_order_update
        # Determine workflow step based on what data we have
        if fo.get("menu_items"):
            fo["current_step"] = "build_order"
        elif fo.get("selected_vendor"):
            fo["current_step"] = "select_vendor"
        else:
            fo["current_step"] = "gather_requirements"
        result["food_order"] = fo
        result["intent"] = "food_order"
        print(f"[EXECUTOR] Food order updated: vendor={fo.get('selected_vendor', {}).get('name')}, headcount={fo.get('headcount')}, items={len(fo.get('menu_items', []))}")

    return result
