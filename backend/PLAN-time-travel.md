# Time-Travel Integration Plan for Edesia Food Ordering Agent

## Overview

LangGraph's time-travel feature allows us to:
1. **Understand reasoning**: See exactly what led to vendor/menu decisions
2. **Debug mistakes**: Find where budget exceeded or dietary requirements missed
3. **Explore alternatives**: Try different vendors/menus without restarting entire order

## Current Architecture Analysis

### What We Already Have
- ✅ Redis checkpointer (`lib/redis.py`) - stores all checkpoints
- ✅ `thread_id` pattern in `/chat` endpoint
- ✅ Workflow steps tracked in `FoodOrderContext.current_step` and `completed_steps`
- ✅ `/conversations/{thread_id}` endpoint - retrieves conversation history

### Critical Decision Points (Where Time-Travel Helps)

| Decision Point | Current Node | What User Might Want |
|----------------|--------------|---------------------|
| Vendor Selection | `vendor_search` | "Show me different cuisines" without re-searching |
| Menu Recommendations | `order_builder` | "What if I had a smaller budget?" |
| Budget Validation | `order_validator` | Go back and adjust items to fit budget |
| Delivery Quote | `order_submit` | Change delivery time and get new quote |

## Implementation Plan

### Phase 1: State History API Endpoints

Add endpoints to expose checkpoint history:

```
GET /conversations/{thread_id}/history
  → Returns list of checkpoints with metadata

GET /conversations/{thread_id}/checkpoints/{checkpoint_id}
  → Returns specific checkpoint state

POST /conversations/{thread_id}/branch
  → Branch from a checkpoint with modified state
```

### Phase 2: Workflow-Specific Time Travel

Add smart branching for common food order scenarios:

```
POST /conversations/{thread_id}/branch/vendors
  → Branch back to vendor search with new preferences

POST /conversations/{thread_id}/branch/menu
  → Branch back to menu selection with adjusted budget

POST /conversations/{thread_id}/branch/delivery
  → Branch back to get new delivery quote
```

### Phase 3: Frontend Integration Points

The API should support UI patterns like:
- "Try different restaurants" button → branches to vendor_search step
- "Adjust budget" → branches to order_builder with new budget
- "Change delivery time" → branches to order_submit

## Detailed Implementation

### 1. New Endpoints for `main.py`

```python
@web_app.get("/conversations/{thread_id}/history")
async def get_conversation_history(thread_id: str, limit: int = 20):
    """Get checkpoint history for time-travel."""
    with get_checkpointer() as checkpointer:
        config = {"configurable": {"thread_id": thread_id}}

        # Get all states (reverse chronological)
        states = list(checkpointer.get_state_history(config))[:limit]

        history = []
        for state in states:
            checkpoint_id = state.config["configurable"]["checkpoint_id"]
            values = state.values

            # Extract key info for each checkpoint
            food_order = values.get("food_order", {})
            history.append({
                "checkpoint_id": checkpoint_id,
                "next_node": state.next,  # What would execute next
                "workflow_step": food_order.get("current_step") if food_order else None,
                "completed_steps": food_order.get("completed_steps", []) if food_order else [],
                "vendor_selected": food_order.get("selected_vendor", {}).get("name") if food_order else None,
                "total": food_order.get("total") if food_order else None,
                "message_count": len(values.get("messages", [])),
                "created_at": state.metadata.get("created_at"),
            })

        return {
            "thread_id": thread_id,
            "checkpoint_count": len(history),
            "checkpoints": history,
        }


@web_app.post("/conversations/{thread_id}/resume/{checkpoint_id}")
async def resume_from_checkpoint(
    thread_id: str,
    checkpoint_id: str,
    message: Optional[str] = None
):
    """Resume conversation from a specific checkpoint."""
    with get_checkpointer() as checkpointer:
        graph = create_agent_graph(checkpointer=checkpointer)

        config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
            }
        }

        # Resume with optional new message
        input_state = None
        if message:
            input_state = {"messages": [{"role": "user", "content": message}]}

        result = await graph.ainvoke(input_state, config=config)

        return {
            "thread_id": thread_id,
            "resumed_from": checkpoint_id,
            "response": result["messages"][-1].content if result["messages"] else "",
            "new_checkpoint_id": result.get("checkpoint_id"),
        }


@web_app.post("/conversations/{thread_id}/branch")
async def branch_conversation(
    thread_id: str,
    checkpoint_id: str,
    state_updates: dict = None,
    message: Optional[str] = None,
):
    """
    Branch from a checkpoint with modified state.
    Creates a NEW thread_id for the branch.
    """
    import uuid

    with get_checkpointer() as checkpointer:
        graph = create_agent_graph(checkpointer=checkpointer)

        # Get state at checkpoint
        old_config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_id": checkpoint_id,
            }
        }

        state = checkpointer.get_tuple(old_config)
        if not state:
            raise HTTPException(status_code=404, detail="Checkpoint not found")

        # Create new branch with new thread_id
        new_thread_id = f"{thread_id}__branch__{str(uuid.uuid4())[:8]}"

        new_config = {
            "configurable": {
                "thread_id": new_thread_id,
            }
        }

        # Apply state updates if provided
        if state_updates:
            graph.update_state(old_config, values=state_updates)

        # Continue execution
        input_state = None
        if message:
            input_state = {"messages": [{"role": "user", "content": message}]}

        result = await graph.ainvoke(input_state, config=new_config)

        return {
            "original_thread_id": thread_id,
            "branched_from_checkpoint": checkpoint_id,
            "new_thread_id": new_thread_id,
            "response": result["messages"][-1].content if result["messages"] else "",
        }
```

### 2. Workflow-Specific Branch Helpers

```python
@web_app.post("/orders/{thread_id}/try-different-vendors")
async def branch_to_vendor_search(
    thread_id: str,
    new_cuisine: Optional[str] = None,
    new_location: Optional[str] = None,
    budget_per_person: Optional[float] = None,
):
    """
    Branch back to vendor search with new preferences.
    User says: "Actually, let me try Italian restaurants instead"
    """
    with get_checkpointer() as checkpointer:
        graph = create_agent_graph(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": thread_id}}

        # Find checkpoint before vendor search completed
        states = list(checkpointer.get_state_history(config))

        target_checkpoint = None
        for state in states:
            food_order = state.values.get("food_order", {})
            if food_order:
                step = food_order.get("current_step")
                if step in ["gather_requirements", "search_vendors"]:
                    target_checkpoint = state.config["configurable"]["checkpoint_id"]
                    break

        if not target_checkpoint:
            raise HTTPException(
                status_code=400,
                detail="Cannot find vendor search checkpoint"
            )

        # Build state updates
        state_updates = {}
        if new_cuisine:
            food_order = state.values.get("food_order", {})
            food_order["cuisine_preferences"] = [new_cuisine]
            state_updates["food_order"] = food_order

        if new_location:
            food_order = state.values.get("food_order", {})
            food_order["delivery_address"] = new_location
            state_updates["food_order"] = food_order

        # Branch with updates
        return await branch_conversation(
            thread_id=thread_id,
            checkpoint_id=target_checkpoint,
            state_updates=state_updates,
            message=f"Search for {new_cuisine or 'different'} restaurants" if new_cuisine else "Show me other options",
        )


@web_app.post("/orders/{thread_id}/adjust-budget")
async def branch_to_adjust_budget(
    thread_id: str,
    new_total_budget: Optional[float] = None,
    new_per_person_budget: Optional[float] = None,
):
    """
    Branch back to order builder with adjusted budget.
    User says: "What if I only had $15 per person?"
    """
    with get_checkpointer() as checkpointer:
        graph = create_agent_graph(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": thread_id}}

        # Find checkpoint at order builder
        states = list(checkpointer.get_state_history(config))

        target_checkpoint = None
        for state in states:
            if "build_order" in (state.next or ()):
                target_checkpoint = state.config["configurable"]["checkpoint_id"]
                break

        if not target_checkpoint:
            raise HTTPException(
                status_code=400,
                detail="Cannot find order builder checkpoint"
            )

        # Update budget in food_order
        state_updates = {}
        food_order = state.values.get("food_order", {})

        if new_total_budget:
            food_order["budget_total"] = new_total_budget
        if new_per_person_budget:
            food_order["budget_per_person"] = new_per_person_budget

        state_updates["food_order"] = food_order

        # Clear previous menu items
        food_order["menu_items"] = []
        food_order["subtotal"] = None
        food_order["total"] = None

        return await branch_conversation(
            thread_id=thread_id,
            checkpoint_id=target_checkpoint,
            state_updates=state_updates,
            message=f"Adjust the order to fit ${new_per_person_budget or new_total_budget} budget",
        )


@web_app.post("/orders/{thread_id}/change-delivery-time")
async def branch_to_change_delivery(
    thread_id: str,
    new_date: Optional[str] = None,
    new_time: Optional[str] = None,
):
    """
    Branch to get new delivery quote with different timing.
    User says: "What if we do lunch at 1pm instead?"
    """
    with get_checkpointer() as checkpointer:
        graph = create_agent_graph(checkpointer=checkpointer)
        config = {"configurable": {"thread_id": thread_id}}

        # Find checkpoint before DoorDash quote
        states = list(checkpointer.get_state_history(config))

        target_checkpoint = None
        for state in states:
            if "order_submit" in (state.next or ()):
                target_checkpoint = state.config["configurable"]["checkpoint_id"]
                break

        if not target_checkpoint:
            raise HTTPException(
                status_code=400,
                detail="Cannot find order submit checkpoint"
            )

        # Update delivery time
        state_updates = {}
        food_order = state.values.get("food_order", {})

        if new_date:
            food_order["event_date"] = new_date
        if new_time:
            food_order["event_time"] = new_time

        # Clear previous quote
        food_order["doordash_quote_id"] = None
        food_order["delivery_fee"] = None

        state_updates["food_order"] = food_order

        return await branch_conversation(
            thread_id=thread_id,
            checkpoint_id=target_checkpoint,
            state_updates=state_updates,
            message=f"Get a new delivery quote for {new_time or 'different time'}",
        )
```

### 3. Agent System Prompt Enhancement

Update system prompt to make the agent aware of time-travel capabilities:

```python
# In agent/prompts/system.py, add to SYSTEM_PROMPT:

TIME_TRAVEL_GUIDANCE = """
## Conversation History & Alternatives

Users can explore alternatives without starting over:
- "Try different restaurants" → Branches back to vendor search
- "What if I had $X budget?" → Re-runs menu suggestions with new budget
- "Change delivery to X time" → Gets new delivery quote

When a user wants to explore alternatives, acknowledge this capability:
- "I can search for different options while keeping your other requirements"
- "Let me recalculate with that budget - I'll preserve your vendor selection"

The system automatically saves checkpoints at each decision point, allowing
users to branch and explore without losing progress.
"""
```

### 4. Frontend/Chat Integration

Users can naturally trigger time-travel through conversation:

| User Says | Agent Response | Action |
|-----------|---------------|--------|
| "Actually, show me Thai restaurants instead" | "Let me search for Thai options..." | Branch to vendor_search with cuisine=Thai |
| "What if my budget was only $12/person?" | "I'll recalculate the order..." | Branch to order_builder with new budget |
| "Can we do 12:30 instead of noon?" | "Getting a new delivery estimate..." | Branch to order_submit with new time |
| "Go back to restaurant selection" | "Here are the vendors again..." | Resume from select_vendor checkpoint |

## Benefits for Office Food Coordination

1. **No wasted planning**: User spends 10 mins configuring order, realizes budget too low → branch and adjust, don't restart

2. **Team consensus**: Manager picks restaurant, team objects → branch to show alternatives while keeping headcount/date

3. **Quote comparison**: Get DoorDash quote, want to try different time → branch to compare delivery windows

4. **Error recovery**: Validation fails on budget → automatically branch back to order_builder instead of manual restart

5. **A/B exploration**: "Show me what this looks like with Italian" AND "also with Mexican" → parallel branches

## Implementation Priority

1. **Phase 1** (Essential): `/history` and `/resume` endpoints
2. **Phase 2** (High Value): `try-different-vendors` and `adjust-budget` helpers
3. **Phase 3** (Polish): Agent prompt updates, automatic branch suggestions

## Files to Modify

| File | Changes |
|------|---------|
| `main.py` | Add 6 new endpoints |
| `agent/prompts/system.py` | Add TIME_TRAVEL_GUIDANCE |
| `agent/state.py` | Add `parent_thread_id` for branch tracking (optional) |
| `agent/nodes/vendor_search.py` | Log checkpoint reasons |
| `agent/nodes/order_builder.py` | Log checkpoint reasons |
