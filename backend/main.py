"""
Edesia Agent - Office Food & Event Planning Assistant
Modal deployment with Groq LLM and Weave observability.
Version: 2.1.0 - Direct Redis client (no SSL)
"""

import modal
from typing import Optional

# Modal app setup
app = modal.App("edesia-agent")

# Container image with dependencies
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install_from_requirements("requirements.txt")
    .add_local_python_source("agent", "models", "tools", "lib", "integrations")
    .add_local_dir("templates", "/root/templates")  # Poll mini app templates
)

# Persistent storage for polls and pending actions
polls_dict = modal.Dict.from_name("edesia-polls", create_if_missing=True)
actions_dict = modal.Dict.from_name("edesia-actions", create_if_missing=True)
calls_dict = modal.Dict.from_name("edesia-calls", create_if_missing=True)
orders_dict = modal.Dict.from_name("edesia-orders", create_if_missing=True)


@app.function(
    image=image,
    secrets=[
        modal.Secret.from_name("edesia-secrets"),
        modal.Secret.from_name("vapi-secret"),
        modal.Secret.from_name("firebase-admin"),
        modal.Secret.from_name("yelp-api"),
        modal.Secret.from_name("doordash-api"),
        modal.Secret.from_name("google-maps"),
        modal.Secret.from_name("usda-fooddata"),
        modal.Secret.from_name("redis-cloud-ssl"),
        modal.Secret.from_name("stripe-secret"),
        modal.Secret.from_name("uber-direct"),
        modal.Secret.from_name("unsplash-api"),
        modal.Secret.from_name("slack-credentials"),
        modal.Secret.from_name("brevo-secret"),
        modal.Secret.from_name("instacart-api-key"),
        modal.Secret.from_name("tinyfish-api"),
        modal.Secret.from_name("platform-credentials"),
    ]
)
@modal.asgi_app()
def fastapi_app():
    """Modal ASGI entrypoint."""
    import weave
    from fastapi import FastAPI, HTTPException, Request, Form, Response, File, UploadFile
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
    from fastapi.templating import Jinja2Templates
    from pydantic import BaseModel
    import hashlib
    import json
    import os
    import tempfile

    from agent import create_agent_graph
    from lib.redis import get_checkpointer, get_async_checkpointer
    from lib.firebase import (
        get_db,
        get_poll_doc, create_poll_doc, update_poll_doc,
        get_form_doc, update_form_doc,
        create_order, update_order, find_order_by_session, find_order_by_delivery_id,
    )

    # Initialize Weave
    weave.init("edesia-agent")

    # Note: Redis checkpointer setup is done lazily on first use
    # The schema is created automatically when needed

    # FastAPI app
    web_app = FastAPI(title="Edesia Agent", version="1.0.0")

    # Jinja2 templates for poll pages
    templates = Jinja2Templates(directory="/root/templates")

    # CORS middleware
    web_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    class MessageHistoryItem(BaseModel):
        role: str
        content: str

    class ImageAttachment(BaseModel):
        type: str = "image"
        data: str  # base64 encoded
        mime_type: str
        name: str

    class PdfAttachment(BaseModel):
        type: str = "pdf"
        url: str  # Firebase Storage URL
        name: str

    class UserProfileData(BaseModel):
        accountType: Optional[str] = None  # "individual" or "team"
        displayName: Optional[str] = None
        companyName: Optional[str] = None
        companySize: Optional[str] = None
        city: Optional[str] = None
        state: Optional[str] = None
        phoneNumber: Optional[str] = None
        # Saved addresses
        workAddress: Optional[dict] = None
        homeAddress: Optional[dict] = None
        # Food preferences
        dietaryRestrictions: Optional[list[str]] = None
        allergies: Optional[list[str]] = None
        favoriteCuisines: Optional[list[str]] = None
        dislikedCuisines: Optional[list[str]] = None
        spicePreference: Optional[str] = None
        budgetPerPerson: Optional[float] = None

    class ChatRequest(BaseModel):
        message: str
        session_id: Optional[str] = None
        user_id: Optional[str] = None
        chat_id: Optional[str] = None  # Firestore chat ID for POEM loop
        message_history: Optional[list[MessageHistoryItem]] = None  # Fallback from Firebase
        timezone: Optional[str] = None  # User's timezone (e.g., 'America/New_York')
        user_profile: Optional[UserProfileData] = None  # Company info from onboarding
        attachments: Optional[list[dict]] = None  # Image/PDF attachments for vision

    class ChatResponse(BaseModel):
        response: str
        session_id: str
        pending_actions: list[dict] = []

    class ApprovalRequest(BaseModel):
        approved: bool
        approved_by: Optional[str] = None
        chat_id: Optional[str] = None  # Firestore chat ID for POEM loop

    class StreamChatRequest(BaseModel):
        message: str
        session_id: Optional[str] = None
        user_id: Optional[str] = None
        chat_id: Optional[str] = None  # Firestore chat ID for POEM loop
        stream_mode: list[str] = ["custom", "messages", "updates"]
        timezone: Optional[str] = None  # User's timezone (e.g., 'America/New_York')
        user_profile: Optional[UserProfileData] = None  # Company info from onboarding
        message_history: Optional[list[MessageHistoryItem]] = None  # Fallback from Firebase
        attachments: Optional[list[dict]] = None  # Image/PDF attachments for vision

    class VoteRequest(BaseModel):
        voter_id: str
        option_id: str

    class SetupIntentRequest(BaseModel):
        user_id: str
        email: str

    # ========== POEM Loop Firestore Sync ==========

    # Intents that should proactively create a plan in the sidebar
    PLANNABLE_INTENTS = {"food_order", "reservation", "catering", "delivery"}

    def _extract_basics_from_message(msg):
        """Extract headcount, location, and date hints from user message."""
        import re
        headcount = 0
        location = ""
        event_date = ""

        if not msg:
            return headcount, location, event_date

        lower = msg.lower()

        # Extract headcount: "team of 25", "for 25 people", "25 people", "group of 30"
        hc_match = re.search(r'(?:team\s+of|for|group\s+of|party\s+of)\s+(\d+)', lower)
        if hc_match:
            headcount = int(hc_match.group(1))
        else:
            hc_match = re.search(r'(\d+)\s*(?:people|guests|persons|employees|team members)', lower)
            if hc_match:
                headcount = int(hc_match.group(1))

        # Extract location: "in midtown memphis tn", "in Nashville"
        loc_match = re.search(r'\bin\s+(.+?)(?:\s+for\b|\s+on\b|\s+at\b|$)', lower)
        if loc_match:
            location = loc_match.group(1).strip().rstrip('.,!?').title()

        # Extract date hints
        if "tomorrow" in lower:
            from datetime import datetime, timedelta
            event_date = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        elif "today" in lower:
            from datetime import datetime
            event_date = datetime.now().strftime("%Y-%m-%d")

        return headcount, location, event_date

    def _build_plan_from_intent(intent, user_message=""):
        """Build a lightweight plan order from intent when no formal workflow exists yet.

        This creates an immediate sidebar entry so the user can see the AI is working on their request.
        """
        intent_config = {
            "food_order": ("doordash", "Food Order"),
            "reservation": ("reservation", "Reservation"),
            "catering": ("catering", "Catering Order"),
            "delivery": ("doordash", "Delivery"),
        }
        order_type, label = intent_config.get(intent, ("doordash", "Plan"))

        # Extract basic info from user message
        headcount, location, event_date = _extract_basics_from_message(user_message)

        # Use the user's message as notes for context
        notes = ""
        if user_message:
            notes = user_message[:200] if len(user_message) > 200 else user_message

        return {
            "type": order_type,
            "status": "researching",
            "poemStage": "plan",
            "vendor": "Searching...",
            "vendorPhone": "",
            "vendorAddress": location,
            "eventDate": event_date,
            "guestCount": headcount,
            "estimatedCost": None,
            "notes": notes,
            "actionType": intent,
        }

    def _get_food_order_poem_stage(food_order, pending_actions):
        """Map food order workflow step to POEM stage."""
        fo = food_order if isinstance(food_order, dict) else food_order.dict()
        step = fo.get("current_step", "gather_requirements")
        if step in ("gather_requirements", "search_vendors", "select_vendor"):
            return "plan"
        if step in ("build_order", "review_order", "confirm_order", "submit_order"):
            return "order"
        if step == "track_order":
            return "monitor"
        return "plan"

    def _build_food_order_data(food_order, poem_stage):
        """Build Firestore order data from food order context."""
        fo = food_order if isinstance(food_order, dict) else food_order.dict()
        vendor = fo.get("selected_vendor")
        # Fall back to first vendor option if no vendor selected yet
        if not vendor:
            vendor_options = fo.get("vendor_options", [])
            if vendor_options:
                vendor = vendor_options[0] if isinstance(vendor_options[0], dict) else vendor_options[0].dict()

        status_map = {"plan": "researching", "order": "quoted", "execute": "confirmed", "monitor": "in_progress"}

        # Build itemized list from menu_items
        items = []
        for item in fo.get("menu_items", []):
            it = item if isinstance(item, dict) else item.dict()
            items.append({
                "name": it.get("name", ""),
                "quantity": it.get("quantity", 1),
                "price": it.get("price", 0),
                "notes": it.get("notes", ""),
            })

        vendor_name = "Searching..."
        vendor_phone = ""
        vendor_address = ""
        if vendor:
            vendor_name = vendor.get("name", "Searching...")
            vendor_phone = vendor.get("phone", "")
            vendor_address = vendor.get("address", "")

        data = {
            "type": "doordash",
            "status": status_map.get(poem_stage, "researching"),
            "poemStage": poem_stage,
            "vendor": vendor_name,
            "vendorPhone": vendor_phone,
            "vendorAddress": vendor_address,
            "eventDate": fo.get("event_date", ""),
            "eventTime": fo.get("event_time", ""),
            "guestCount": fo.get("headcount", 0),
            "deliveryAddress": fo.get("delivery_address", ""),
            "estimatedCost": fo.get("total") or fo.get("subtotal"),
            "subtotal": fo.get("subtotal"),
            "tax": fo.get("tax"),
            "deliveryFee": fo.get("delivery_fee"),
            "serviceFee": fo.get("service_fee"),
            "items": items if items else None,
            "notes": fo.get("special_instructions", ""),
            "actionType": "food_order",
        }
        # Remove None values so we don't overwrite existing data with nulls
        return {k: v for k, v in data.items() if v is not None}

    def _build_order_from_action(action):
        """Build Firestore order data from a pending action."""
        action_type = action.get("action_type", "general")
        payload = action.get("payload", {})
        type_map = {
            "food_order": "doordash", "doordash_order": "doordash",
            "reservation": "reservation", "catering_order": "catering",
            "poll_send": "poll", "call_restaurant": "phone_call",
            "call_caterer": "phone_call", "call_chef": "phone_call",
        }
        return {
            "type": type_map.get(action_type, action_type),
            "status": "pending",
            "poemStage": "order",
            "vendor": payload.get("restaurant_name") or payload.get("caterer_name") or payload.get("name", ""),
            "vendorPhone": payload.get("phone_number") or payload.get("phone", ""),
            "eventDate": payload.get("event_date") or payload.get("date", ""),
            "guestCount": payload.get("headcount") or payload.get("party_size", 0),
            "estimatedCost": payload.get("total") or payload.get("estimated_cost"),
            "notes": action.get("description", ""),
            "actionId": action.get("action_id", ""),
            "actionType": action_type,
        }

    async def _sync_firestore_order(chat_id, session_id, state, user_id=None, user_message=""):
        """Create or update Firestore order based on graph state (POEM loop).

        Now also creates lightweight 'plan' orders for any actionable intent,
        so the sidebar shows activity even before a formal workflow kicks in.

        Returns a debug dict describing what happened (for tracing).
        """
        if not chat_id:
            print(f"[POEM] No chat_id, skipping sync")
            return {"action": "skipped", "reason": "no_chat_id"}

        intent = state.get("intent")
        food_order = state.get("food_order")
        pending_actions = state.get("pending_actions", [])
        print(f"[POEM] sync: chat_id={chat_id}, session={session_id[:12]}..., intent={intent}, food_order={food_order is not None}, actions={len(pending_actions)}, msg={user_message[:60] if user_message else 'none'}")

        try:
            # Multi-step food order workflow
            if intent == "food_order" and food_order:
                poem_stage = _get_food_order_poem_stage(food_order, pending_actions)
                order_data = _build_food_order_data(food_order, poem_stage)

                existing = await find_order_by_session(chat_id, session_id)
                if existing:
                    if user_id:
                        order_data["userId"] = user_id
                    order_data["chatId"] = chat_id
                    await update_order(chat_id, existing["id"], order_data)
                    for action in pending_actions:
                        action["firestore_order_id"] = existing["id"]
                        action["chat_id"] = chat_id
                else:
                    order_data["sessionId"] = session_id
                    if user_id:
                        order_data["userId"] = user_id
                    order_data["chatId"] = chat_id
                    order_id = await create_order(chat_id, order_data)
                    for action in pending_actions:
                        action["firestore_order_id"] = order_id
                        action["chat_id"] = chat_id
                return

            # Single-step actions (reservation, catering, poll, call)
            for action in pending_actions:
                if action.get("firestore_order_id"):
                    continue
                order_data = _build_order_from_action(action)
                order_data["sessionId"] = session_id
                if user_id:
                    order_data["userId"] = user_id
                order_data["chatId"] = chat_id
                order_id = await create_order(chat_id, order_data)
                action["firestore_order_id"] = order_id
                action["chat_id"] = chat_id

            # Proactive plan: create a sidebar entry for actionable intents
            # even when no food_order context or pending_actions exist yet.
            # This way the user immediately sees the AI is working on their request.
            # Also catch food-related messages that the router misclassified as "general"
            FOOD_KEYWORDS = {"order", "lunch", "dinner", "breakfast", "food", "pizza",
                             "taco", "burrito", "sushi", "restaurant", "catering",
                             "delivery", "eat", "feed", "meal", "hungry", "reserve",
                             "reservation", "book a table", "doordash", "find",
                             "nearby", "near me", "spot", "spots", "places to eat",
                             "thai", "chinese", "mexican", "indian", "italian",
                             "bbq", "burger", "sandwich", "wings", "ramen", "pho"}
            is_food_related = any(kw in user_message.lower() for kw in FOOD_KEYWORDS) if user_message else False
            should_create_plan = intent in PLANNABLE_INTENTS or (intent in ("general", "location") and is_food_related)

            if not pending_actions and should_create_plan:
                # Override intent for food-related messages misclassified as "general"
                plan_intent = intent if intent in PLANNABLE_INTENTS else "food_order"
                existing = await find_order_by_session(chat_id, session_id)
                if not existing:
                    plan_data = _build_plan_from_intent(plan_intent, user_message)
                    plan_data["sessionId"] = session_id
                    if user_id:
                        plan_data["userId"] = user_id
                    plan_data["chatId"] = chat_id
                    order_id = await create_order(chat_id, plan_data)
                    print(f"[POEM] Created plan order {order_id} for intent={plan_intent} (original={intent})")
                    return {"action": "created_plan", "order_id": order_id, "intent": plan_intent, "chat_id": chat_id}
                else:
                    print(f"[POEM] Plan already exists for session {session_id[:12]}...")
                    return {"action": "plan_exists", "order_id": existing["id"], "chat_id": chat_id}
            else:
                reason = f"intent={intent}, is_food={is_food_related if 'is_food_related' in dir() else 'n/a'}, pending={len(pending_actions)}"
                print(f"[POEM] No plan created: {reason}")
                return {"action": "no_plan", "reason": reason, "intent": intent, "chat_id": chat_id}

        except Exception as e:
            print(f"[POEM] Error syncing Firestore order: {e}")
            import traceback
            traceback.print_exc()
            return {"action": "error", "error": str(e), "chat_id": chat_id}

    @web_app.post("/chat", response_model=ChatResponse)
    async def chat(request: ChatRequest):
        """Main conversation endpoint with Redis-backed persistent memory."""
        import uuid
        from lib.redis import get_user_preferences

        thread_id = request.session_id or str(uuid.uuid4())
        user_id = request.user_id or "anonymous"
        is_new_session = request.session_id is None

        print(f"[CHAT] session_id from request: {request.session_id}")
        print(f"[CHAT] thread_id being used: {thread_id}")
        print(f"[CHAT] is_new_session: {is_new_session}")
        print(f"[CHAT] message: {request.message[:100]}...")
        print(f"[CHAT] attachments: {len(request.attachments) if request.attachments else 0}")

        # Load user preferences for the system prompt
        user_preferences = get_user_preferences(user_id) if user_id != "anonymous" else None

        # Process image attachments for vision
        image_content = None
        if request.attachments:
            image_attachments = [a for a in request.attachments if a.get("type") == "image"]
            if image_attachments:
                # Build multimodal content for Groq vision
                image_content = []
                for img in image_attachments[:5]:  # Groq limit: 5 images
                    image_content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{img['mime_type']};base64,{img['data']}"
                        }
                    })
                print(f"[CHAT] Processing {len(image_content)} images for vision")

        # Log user profile for debugging
        if request.user_profile:
            print(f"[CHAT] User profile received: {request.user_profile.model_dump()}")
        else:
            print(f"[CHAT] No user profile in request")

        async with get_async_checkpointer() as checkpointer:
            graph = create_agent_graph(checkpointer=checkpointer)

            config = {
                "configurable": {
                    "thread_id": thread_id,
                    "user_id": user_id,
                }
            }

            # Check if there's existing state for this thread
            existing_state = await graph.aget_state(config)
            has_existing_state = existing_state and existing_state.values and existing_state.values.get("messages")

            # Build user message content (text or multimodal with images)
            if image_content:
                # Multimodal message with images
                user_message_content = [
                    {"type": "text", "text": request.message or "What's in this image?"}
                ] + image_content
            else:
                user_message_content = request.message

            if has_existing_state:
                existing_messages = existing_state.values.get("messages", [])
                print(f"[CHAT] Found existing state with {len(existing_messages)} messages")
                for i, msg in enumerate(existing_messages[-4:]):  # Show last 4
                    content = msg.content if hasattr(msg, 'content') else msg.get('content', '')
                    role = msg.type if hasattr(msg, 'type') else msg.get('role', 'unknown')
                    print(f"[CHAT]   msg[{i}] ({role}): {str(content)[:80]}...")
                # Just send the new message - checkpointer will merge with existing
                messages_to_send = [{"role": "user", "content": user_message_content}]
            else:
                print(f"[CHAT] No existing state found for thread_id: {thread_id}")
                # Use message_history from Firebase as fallback
                if request.message_history:
                    print(f"[CHAT] Using message_history fallback with {len(request.message_history)} messages")
                    messages_to_send = [{"role": m.role, "content": m.content} for m in request.message_history]
                    messages_to_send.append({"role": "user", "content": user_message_content})
                else:
                    print(f"[CHAT] No message_history provided, starting fresh")
                    messages_to_send = [{"role": "user", "content": user_message_content}]

            # Include user_id, preferences, timezone, and company profile in initial state
            initial_input = {
                "messages": messages_to_send,
                "user_id": user_id,
                "user_preferences": user_preferences,
                "timezone": request.timezone,
                "user_profile": request.user_profile.model_dump() if request.user_profile else None,
                "has_images": image_content is not None,  # Flag for vision model
                "chat_id": request.chat_id,
            }

            with weave.attributes({"session_id": thread_id, "user_id": user_id}):
                result = await graph.ainvoke(initial_input, config=config)

            # Log result
            result_messages = result.get("messages", [])
            print(f"[CHAT] Result has {len(result_messages)} messages")

        last_message = result["messages"][-1] if result["messages"] else None
        if last_message:
            response_message = last_message.content if hasattr(last_message, 'content') else last_message.get("content", "")
        else:
            response_message = "I couldn't process that request."

        pending_actions = result.get("pending_actions", [])

        # POEM Loop: Sync Firestore orders (pass user message for plan labels)
        await _sync_firestore_order(request.chat_id, thread_id, result, user_id=user_id, user_message=request.message or "")

        for action in pending_actions:
            actions_dict[action["action_id"]] = action

        return ChatResponse(
            response=response_message,
            session_id=thread_id,
            pending_actions=pending_actions,
        )

    @web_app.post("/chat/stream")
    async def chat_stream(request: StreamChatRequest):
        """
        Streaming conversation endpoint with real-time status updates.

        Returns Server-Sent Events (SSE) stream with:
        - custom: Status updates (type=status) showing what the AI is doing
        - messages: LLM token chunks for streaming text
        - updates: Graph state updates after each node
        """
        import uuid
        from lib.redis import get_user_preferences

        thread_id = request.session_id or str(uuid.uuid4())
        user_id = request.user_id or "anonymous"

        print(f"[STREAM] session_id from request: {request.session_id}")
        print(f"[STREAM] thread_id being used: {thread_id}")
        print(f"[STREAM] attachments: {len(request.attachments) if request.attachments else 0}")

        # Load user preferences
        user_preferences = get_user_preferences(user_id) if user_id != "anonymous" else None

        # Process image attachments for vision
        image_content = None
        if request.attachments:
            image_attachments = [a for a in request.attachments if a.get("type") == "image"]
            if image_attachments:
                image_content = []
                for img in image_attachments[:5]:
                    image_content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{img['mime_type']};base64,{img['data']}"
                        }
                    })
                print(f"[STREAM] Processing {len(image_content)} images for vision")

        async def generate_stream():
            """Async generator for SSE stream."""
            # Send session info first
            yield f"data: {json.dumps({'type': 'session', 'session_id': thread_id})}\n\n"

            async with get_async_checkpointer() as checkpointer:
                graph = create_agent_graph(checkpointer=checkpointer)

                config = {
                    "configurable": {
                        "thread_id": thread_id,
                        "user_id": user_id,
                    }
                }

                # Check existing state
                existing_state = await graph.aget_state(config)
                has_existing_state = existing_state and existing_state.values and existing_state.values.get("messages")

                if has_existing_state:
                    existing_messages = existing_state.values.get("messages", [])
                    print(f"[STREAM] Found existing state with {len(existing_messages)} messages")
                else:
                    print(f"[STREAM] No existing state for thread_id: {thread_id}")

                # Build user message content (text or multimodal with images)
                if image_content:
                    user_message_content = [
                        {"type": "text", "text": request.message or "What's in this image?"}
                    ] + image_content
                else:
                    user_message_content = request.message

                if has_existing_state:
                    messages_to_send = [{"role": "user", "content": user_message_content}]
                else:
                    if request.message_history:
                        print(f"[STREAM] Using message_history fallback with {len(request.message_history)} messages")
                        messages_to_send = [{"role": m.role, "content": m.content} for m in request.message_history]
                        messages_to_send.append({"role": "user", "content": user_message_content})
                    else:
                        messages_to_send = [{"role": "user", "content": user_message_content}]

                initial_input = {
                    "messages": messages_to_send,
                    "user_id": user_id,
                    "user_preferences": user_preferences,
                    "timezone": request.timezone,
                    "user_profile": request.user_profile.model_dump() if request.user_profile else None,
                    "has_images": image_content is not None,
                    "chat_id": request.chat_id,
                }

                # Track final response, pending actions, and state for POEM sync
                final_response = ""
                all_pending_actions = []
                final_state = {}

                # Stream with multiple modes
                with weave.attributes({"session_id": thread_id, "user_id": user_id, "streaming": True}):
                    async for mode, chunk in graph.astream(
                        initial_input,
                        config=config,
                        stream_mode=request.stream_mode,
                    ):
                        # Format based on stream mode
                        if mode == "custom":
                            # Custom status updates from nodes
                            yield f"data: {json.dumps({'type': 'status', **chunk})}\n\n"

                        elif mode == "messages":
                            # LLM token chunks
                            message_chunk, metadata = chunk
                            if hasattr(message_chunk, "content") and message_chunk.content:
                                yield f"data: {json.dumps({'type': 'token', 'content': message_chunk.content, 'node': metadata.get('langgraph_node', '')})}\n\n"

                        elif mode == "updates":
                            # Graph state updates
                            for node_name, update in chunk.items():
                                if not update or not isinstance(update, dict):
                                    continue
                                event = {
                                    "type": "update",
                                    "node": node_name,
                                }
                                # Include key state info
                                if update.get("messages"):
                                    last_msg = update["messages"][-1]
                                    if hasattr(last_msg, "content"):
                                        event["message"] = last_msg.content
                                        final_response = last_msg.content
                                if "food_order" in update:
                                    fo = update["food_order"]
                                    if isinstance(fo, dict):
                                        event["workflow_step"] = fo.get("current_step")
                                    final_state["food_order"] = fo
                                if "pending_actions" in update:
                                    event["pending_actions"] = update["pending_actions"]
                                    all_pending_actions = update["pending_actions"]
                                if "needs_approval" in update:
                                    event["needs_approval"] = update["needs_approval"]
                                if "intent" in update:
                                    final_state["intent"] = update["intent"]

                                yield f"data: {json.dumps(event)}\n\n"

                # Build state for POEM sync
                final_state["pending_actions"] = all_pending_actions

                # POEM Loop: Sync Firestore orders (pass user message for plan labels)
                poem_result = await _sync_firestore_order(request.chat_id, thread_id, final_state, user_id=user_id, user_message=request.message or "")

                # Register pending actions
                for action in all_pending_actions:
                    if isinstance(action, dict) and "action_id" in action:
                        actions_dict[action["action_id"]] = action

                # Send completion event with final response, pending actions, and POEM debug
                done_event = {
                    'type': 'done',
                    'session_id': thread_id,
                    'response': final_response,
                    'pending_actions': all_pending_actions,
                    'poem_debug': poem_result,  # Debug: shows what happened with order sync
                }
                yield f"data: {json.dumps(done_event)}\n\n"

        return StreamingResponse(
            generate_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @web_app.get("/chat/stream")
    async def chat_stream_get(
        message: str,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        timezone: Optional[str] = None,
        company_name: Optional[str] = None,
        company_size: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
    ):
        """
        GET endpoint for streaming chat (for EventSource clients).

        Same as POST /chat/stream but uses query parameters.

        Example: GET /chat/stream?message=order%20lunch&session_id=abc123&timezone=America/New_York
        """
        user_profile = None
        if any([company_name, company_size, city, state]):
            user_profile = UserProfileData(
                companyName=company_name,
                companySize=company_size,
                city=city,
                state=state,
            )

        stream_request = StreamChatRequest(
            message=message,
            session_id=session_id,
            user_id=user_id,
            timezone=timezone,
            user_profile=user_profile,
        )
        return await chat_stream(stream_request)

    @web_app.get("/debug/orders/{chat_id}")
    async def debug_orders(chat_id: str):
        """Debug: list all orders for a given chat_id."""
        from lib.firebase import get_db
        db = get_db()
        orders_ref = db.collection("chats").document(chat_id).collection("orders")
        orders = orders_ref.get()
        result = []
        for o in orders:
            data = o.to_dict()
            # Convert Timestamps to strings for JSON serialization
            for k, v in data.items():
                if hasattr(v, 'isoformat'):
                    data[k] = v.isoformat()
            result.append({"id": o.id, **data})
        return result

    @web_app.post("/approve/{action_id}")
    async def approve_action(action_id: str, request: ApprovalRequest):
        """Approve or reject a pending action."""
        from datetime import datetime

        action = actions_dict.get(action_id)
        if not action:
            raise HTTPException(status_code=404, detail="Action not found")

        if action["status"] != "pending":
            raise HTTPException(status_code=400, detail=f"Action already {action['status']}")

        action["status"] = "approved" if request.approved else "rejected"
        action["approved_by"] = request.approved_by
        action["approved_at"] = datetime.utcnow().isoformat()
        actions_dict[action_id] = action

        # POEM Loop: Get Firestore IDs for order tracking
        chat_id = action.get("chat_id") or request.chat_id
        order_id = action.get("firestore_order_id")

        if request.approved:
            # POEM: Advance to Execute stage
            if chat_id and order_id:
                try:
                    await update_order(chat_id, order_id, {
                        "status": "confirmed", "poemStage": "execute",
                    })
                except Exception as e:
                    print(f"[POEM] Error updating order to execute: {e}")

            # === STRIPE: Charge before placing order ===
            action_type = action.get("action_type", "")
            amount_cents = 0

            if action_type in ["food_order", "doordash_order"]:
                payload = action.get("payload", {})
                fo = payload.get("food_order", {})
                total = fo.get("total") or fo.get("subtotal") or 0
                amount_cents = int(total * 100)

            if amount_cents > 0:
                from lib.stripe_client import charge_customer

                # Look up user's stripeCustomerId via chat → user
                user_stripe_id = None
                if chat_id:
                    try:
                        chat_doc = get_db().collection("chats").document(chat_id).get()
                        if chat_doc.exists:
                            user_id = chat_doc.to_dict().get("userId")
                            if user_id:
                                user_doc = get_db().collection("users").document(user_id).get()
                                if user_doc.exists:
                                    user_stripe_id = user_doc.to_dict().get("stripeCustomerId")
                    except Exception as e:
                        print(f"[Stripe] Error looking up customer: {e}")

                if not user_stripe_id:
                    # Revert order status
                    if chat_id and order_id:
                        try:
                            await update_order(chat_id, order_id, {
                                "status": "pending", "poemStage": "order",
                                "notes": "Please add a payment method in Settings → Billing",
                            })
                        except Exception:
                            pass
                    return {
                        "status": "error",
                        "error": "no_payment_method",
                        "message": "Please add a payment method in Settings → Billing before approving orders.",
                    }

                payment = await charge_customer(
                    customer_id=user_stripe_id,
                    amount_cents=amount_cents,
                    description=action.get("description", "Edesia order"),
                    metadata={"action_id": action_id, "order_id": order_id or ""},
                )

                if not payment.get("success"):
                    # Revert order status
                    if chat_id and order_id:
                        try:
                            await update_order(chat_id, order_id, {
                                "status": "pending", "poemStage": "order",
                                "notes": f"Payment failed: {payment.get('error', 'unknown')}",
                            })
                        except Exception:
                            pass
                    return {
                        "status": "error",
                        "error": "payment_failed",
                        "message": f"Payment failed: {payment.get('error', 'Card declined')}",
                    }

                # Store payment info on Firestore order
                if chat_id and order_id:
                    try:
                        await update_order(chat_id, order_id, {
                            "paymentIntentId": payment.get("payment_intent_id"),
                            "paymentStatus": "paid",
                        })
                    except Exception as e:
                        print(f"[Stripe] Error saving payment info: {e}")

            result = await execute_approved_action(action)

            # POEM: Advance to Monitor stage
            if chat_id and order_id:
                try:
                    if result.get("success", True):
                        await update_order(chat_id, order_id, {
                            "status": "in_progress",
                            "poemStage": "monitor",
                            "trackingUrl": result.get("tracking_url", ""),
                            "deliveryId": result.get("external_delivery_id") or result.get("delivery_id", ""),
                        })
                    else:
                        await update_order(chat_id, order_id, {
                            "status": "cancelled",
                            "poemStage": "monitor",
                            "notes": result.get("error", ""),
                        })
                except Exception as e:
                    print(f"[POEM] Error updating order to monitor: {e}")

            return {"status": "approved", "result": result}

        # Rejected
        if chat_id and order_id:
            try:
                await update_order(chat_id, order_id, {
                    "status": "cancelled", "poemStage": "monitor",
                })
            except Exception as e:
                print(f"[POEM] Error updating order to cancelled: {e}")

        return {"status": "rejected"}

    async def execute_approved_action(action: dict) -> dict:
        """Execute an approved action."""
        from datetime import datetime

        action_type = action["action_type"]
        payload = action["payload"]

        if action_type == "reservation":
            return {"message": "Reservation confirmed", "confirmation_number": "RSV-" + action["action_id"][:8]}

        elif action_type == "catering_order":
            return {"message": "Catering order placed", "order_number": "CAT-" + action["action_id"][:8]}

        elif action_type == "poll_send":
            import httpx
            async with httpx.AsyncClient() as client:
                await client.post(payload["webhook_url"], json=payload["poll_data"])
            return {"message": "Poll sent via webhook"}

        elif action_type in ["call_restaurant", "call_caterer", "call_chef"]:
            # Execute Vapi outbound call
            from tools.vapi_calls import execute_vapi_call

            result = await execute_vapi_call(
                action_type,
                payload,
                chat_id=action.get("chat_id"),
                order_id=action.get("firestore_order_id"),
            )
            return result

        elif action_type in ["food_order", "doordash_order"]:
            # Execute food order via DoorDash
            from agent.nodes.order_submit import execute_food_order

            result = await execute_food_order(payload)

            if result.get("success"):
                # Store order for tracking
                order_key = result.get("external_delivery_id", action["action_id"])
                orders_dict[order_key] = {
                    "action_id": action["action_id"],
                    "delivery_id": result.get("delivery_id"),
                    "external_delivery_id": result.get("external_delivery_id"),
                    "tracking_url": result.get("tracking_url"),
                    "status": result.get("status", "submitted"),
                    "vendor_name": payload.get("vendor", {}).get("name", "Unknown"),
                    "created_at": datetime.utcnow().isoformat(),
                    "estimated_pickup": result.get("estimated_pickup"),
                    "estimated_delivery": result.get("estimated_delivery"),
                }
                return result
            else:
                return {"success": False, "error": result.get("error", "Order failed")}

        return {"message": "Action executed"}

    # ========== Stripe Payment Endpoints ==========

    @web_app.post("/stripe/setup-intent")
    async def create_stripe_setup_intent(request: SetupIntentRequest):
        """Create a SetupIntent for saving a payment method."""
        from lib.stripe_client import get_or_create_customer, create_setup_intent
        customer_id = await get_or_create_customer(request.user_id, request.email)
        result = await create_setup_intent(customer_id)
        return result

    @web_app.get("/stripe/payment-methods/{user_id}")
    async def list_payment_methods(user_id: str):
        """List saved payment methods for a user."""
        from lib.stripe_client import get_payment_methods
        user_doc = get_db().collection("users").document(user_id).get()
        if not user_doc.exists:
            return {"payment_methods": []}
        data = user_doc.to_dict()
        customer_id = data.get("stripeCustomerId")
        if not customer_id:
            return {"payment_methods": []}
        methods = await get_payment_methods(customer_id)
        return {"payment_methods": methods}

    @web_app.delete("/stripe/payment-methods/{pm_id}")
    async def delete_payment_method(pm_id: str):
        """Remove a saved payment method."""
        from lib.stripe_client import detach_payment_method
        await detach_payment_method(pm_id)
        return {"status": "removed"}

    @web_app.post("/leads/capture")
    async def capture_lead(request: dict):
        """Capture a lead email from the landing page and add to Brevo contacts."""
        import httpx

        email = request.get("email", "").strip()
        source = request.get("source", "event-planners")
        if not email:
            raise HTTPException(status_code=400, detail="Email is required")

        brevo_key = os.getenv("BREVO_API_KEY")
        if brevo_key:
            try:
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        "https://api.brevo.com/v3/contacts",
                        headers={
                            "api-key": brevo_key,
                            "Content-Type": "application/json",
                        },
                        json={
                            "email": email,
                            "attributes": {"SOURCE": source},
                            "listIds": [2],
                            "updateEnabled": True,
                        },
                        timeout=10.0,
                    )
                    print(f"[BREVO] Contact {email} -> {resp.status_code}")
            except Exception as e:
                print(f"[BREVO] Error adding contact {email}: {e}")

        # Also save to Firestore
        try:
            from lib.firebase import get_db
            from firebase_admin import firestore as fs
            db = get_db()
            db.collection("leads").add({
                "email": email,
                "source": source,
                "createdAt": fs.SERVER_TIMESTAMP,
            })
        except Exception as e:
            print(f"[LEADS] Error saving to Firestore: {e}")

        return {"status": "ok"}

    @web_app.post("/webhooks/stripe")
    async def stripe_webhook(request: Request):
        """Handle Stripe webhook events."""
        import stripe as stripe_lib
        stripe_lib.api_key = os.getenv("STRIPE_SECRET_KEY")
        payload = await request.body()
        sig = request.headers.get("stripe-signature")
        webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
        try:
            event = stripe_lib.Webhook.construct_event(payload, sig, webhook_secret)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid webhook signature")
        event_type = event["type"]
        print(f"[Stripe Webhook] {event_type}: {event['id']}")

        # ── Handle completed checkout sessions (split-payment links) ──
        if event_type == "checkout.session.completed":
            from datetime import datetime
            session = event["data"]["object"]
            meta = session.get("metadata", {})
            order_id = meta.get("order_id")
            attendee_email = meta.get("attendee_email")

            if order_id:
                from firebase_admin import firestore as fa_firestore
                db = get_db()
                split_ref = db.collection("payment_splits").document(order_id)
                split_doc = split_ref.get()

                if split_doc.exists:
                    split_ref.update({
                        "paidCount": fa_firestore.Increment(1),
                    })
                    # Mark individual attendee as paid
                    data = split_doc.to_dict()
                    attendees = data.get("attendees", [])
                    for att in attendees:
                        if att.get("email") == attendee_email:
                            att["paid"] = True
                            att["paid_at"] = datetime.utcnow().isoformat()
                            break
                    split_ref.update({"attendees": attendees})

                    # Check if all paid
                    new_paid = data.get("paidCount", 0) + 1
                    if new_paid >= data.get("totalAttendees", 0):
                        split_ref.update({"status": "complete"})
                        print(f"[Stripe] All attendees paid for order {order_id}")

        # ── Handle successful payment intents (corporate card charges) ──
        elif event_type == "payment_intent.succeeded":
            pi = event["data"]["object"]
            meta = pi.get("metadata", {})
            order_id = meta.get("order_id")
            company_id = meta.get("company_id")

            if order_id and company_id:
                db = get_db()
                # Find and update the order
                orders = db.collection_group("orders").where("orderId", "==", order_id).limit(1).stream()
                for doc in orders:
                    doc.reference.update({
                        "paymentStatus": "paid",
                        "paymentIntentId": pi["id"],
                        "paidByCorporateCard": True,
                    })

        return {"status": "ok"}

    @web_app.get("/polls/{poll_id}")
    async def get_poll(poll_id: str):
        """Get poll status and results."""
        poll = get_poll_doc(poll_id)
        if not poll:
            raise HTTPException(status_code=404, detail="Poll not found")
        return poll

    @web_app.post("/polls/{poll_id}/vote")
    async def vote_poll(poll_id: str, request: VoteRequest):
        """Submit a vote to a poll."""
        from datetime import datetime

        poll = get_poll_doc(poll_id)
        if not poll:
            raise HTTPException(status_code=404, detail="Poll not found")

        if poll.get("is_closed"):
            raise HTTPException(status_code=400, detail="Poll is closed")

        existing_votes = [v for v in poll.get("votes", []) if v["voter_id"] == request.voter_id]
        if existing_votes:
            raise HTTPException(status_code=400, detail="Already voted")

        poll.setdefault("votes", []).append({
            "voter_id": request.voter_id,
            "option_id": request.option_id,
            "timestamp": datetime.utcnow().isoformat(),
        })

        for option in poll["options"]:
            if option["option_id"] == request.option_id:
                option["votes"] = option.get("votes", 0) + 1
                break

        update_poll_doc(poll_id, {"votes": poll["votes"], "options": poll["options"]})
        return {"status": "voted", "poll_id": poll_id}

    @web_app.post("/transcribe")
    async def transcribe_audio_endpoint(file: UploadFile = File(...)):
        """
        Transcribe audio using Groq Whisper Large V3.

        Accepts audio files (webm, mp3, wav, m4a, etc.) and returns transcription.
        Max file size: 25MB
        Supported formats: mp3, mp4, mpeg, mpga, m4a, wav, webm
        """
        import os
        from groq import Groq

        # Validate file type
        content_type = file.content_type or ""
        if not any(t in content_type for t in ["audio", "video/webm"]):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type: {content_type}. Supported: webm, mp3, wav, m4a, mp4"
            )

        # Read file content
        content = await file.read()

        # Check file size (25MB limit for Groq)
        if len(content) > 25 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="File too large. Maximum size is 25MB.")

        # Save to temp file (Groq SDK needs a file path)
        suffix = ".webm" if "webm" in content_type else ".mp3"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        try:
            # Initialize Groq client
            client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

            # Transcribe with Whisper Large V3
            with open(tmp_path, "rb") as audio_file:
                transcription = client.audio.transcriptions.create(
                    file=(file.filename or "audio.webm", audio_file.read()),
                    model="whisper-large-v3",
                    language="en",  # Can be removed for auto-detect
                    response_format="json",
                )

            print(f"[TRANSCRIBE] Success: {transcription.text[:100]}...")

            return {
                "text": transcription.text,
                "duration": getattr(transcription, "duration", None),
            }

        except Exception as e:
            print(f"[TRANSCRIBE] Error: {e}")
            raise HTTPException(status_code=500, detail=f"Transcription failed: {str(e)}")

        finally:
            # Cleanup temp file
            try:
                os.unlink(tmp_path)
            except:
                pass

    @web_app.get("/health")
    async def health():
        """Health check endpoint."""
        return {"status": "healthy", "service": "edesia-agent"}

    @web_app.get("/debug/redis")
    async def debug_redis():
        """Debug endpoint to test Redis connection."""
        import traceback
        import os
        result = {
            "env": {
                "REDIS_HOST": os.environ.get("REDIS_HOST", "not set"),
                "REDIS_PORT": os.environ.get("REDIS_PORT", "not set"),
                "REDIS_USER": os.environ.get("REDIS_USER", "not set"),
                "REDIS_PASSWORD": "***" if os.environ.get("REDIS_PASSWORD") else "not set",
            }
        }

        # Test basic Redis connection
        try:
            from lib.redis import get_redis_client
            client = get_redis_client()
            client.set("debug_test", "ok")
            result["basic_redis"] = client.get("debug_test")
            client.close()
        except Exception as e:
            result["basic_redis_error"] = f"{type(e).__name__}: {str(e)}"
            result["basic_redis_traceback"] = traceback.format_exc()

        # Test async checkpointer
        try:
            async with get_async_checkpointer() as checkpointer:
                result["async_checkpointer"] = "connected"
        except Exception as e:
            result["async_checkpointer_error"] = f"{type(e).__name__}: {str(e)}"
            result["async_checkpointer_traceback"] = traceback.format_exc()

        return result

    @web_app.get("/debug/tools")
    async def debug_tools():
        """Debug endpoint to test tool loading."""
        import traceback
        result = {"tools": []}

        try:
            from tools import ALL_TOOLS
            for tool in ALL_TOOLS:
                try:
                    schema = tool.args_schema.schema() if hasattr(tool, "args_schema") and tool.args_schema else None
                    result["tools"].append({
                        "name": tool.name,
                        "description": tool.description[:100] if tool.description else None,
                        "has_schema": schema is not None,
                    })
                except Exception as e:
                    result["tools"].append({
                        "name": getattr(tool, "name", "unknown"),
                        "error": f"{type(e).__name__}: {str(e)}",
                    })
            result["tool_count"] = len(result["tools"])
        except Exception as e:
            result["load_error"] = f"{type(e).__name__}: {str(e)}"
            result["traceback"] = traceback.format_exc()

        return result

    @web_app.post("/webhooks/vapi/tool-calls")
    async def vapi_tool_calls(request: dict):
        """Handle VAPI tool-call requests during inbound voice calls."""
        from integrations.vapi.inbound_tools import INBOUND_TOOL_HANDLERS

        message = request.get("message", {})
        call = message.get("call", {})
        call_id = call.get("id", "")
        tool_call_list = message.get("toolCallList", [])

        results = []
        for tool_call in tool_call_list:
            tc_id = tool_call.get("id", "")
            fn = tool_call.get("function", {})
            tool_name = fn.get("name", "")
            params = fn.get("arguments", {})
            if isinstance(params, str):
                import json as _json
                try:
                    params = _json.loads(params)
                except Exception:
                    params = {}

            handler = INBOUND_TOOL_HANDLERS.get(tool_name)
            if handler:
                try:
                    result = await handler(
                        params,
                        call_id=call_id,
                        calls_dict=calls_dict,
                    )
                except Exception as e:
                    print(f"[VAPI-INBOUND] Tool {tool_name} error: {e}")
                    result = f'{{"error": "Tool error: {e}"}}'
            else:
                result = f'{{"error": "Unknown tool: {tool_name}"}}'

            results.append({"toolCallId": tc_id, "result": result})

        return {"results": results}

    @web_app.post("/webhooks/vapi")
    async def vapi_webhook(request: dict):
        """Handle Vapi call webhooks for status updates and transcripts."""
        from datetime import datetime
        from lib.firebase import get_db

        message_type = request.get("message", {}).get("type")

        # --- Handle assistant-request: return assistant config for inbound calls ---
        if message_type == "assistant-request":
            from integrations.vapi.assistant_config import build_inbound_config
            tool_calls_url = f"{os.environ.get('EDESIA_SERVER_URL', 'https://your-modal-app.modal.run')}/webhooks/vapi/tool-calls"
            config = build_inbound_config(tool_calls_url)
            return {"assistant": config}

        call = request.get("message", {}).get("call", {})
        call_id = call.get("id")
        metadata = call.get("metadata", {})

        if not call_id:
            return {"status": "ok"}

        chat_id = metadata.get("chat_id")
        order_id = metadata.get("order_id")

        call_data = calls_dict.get(call_id, {})
        call_data["last_updated"] = datetime.utcnow().isoformat()
        call_data["chat_id"] = chat_id
        call_data["order_id"] = order_id

        if message_type == "status-update":
            call_data["status"] = request.get("message", {}).get("status")

        elif message_type == "end-of-call-report":
            call_data["status"] = "completed"
            call_data["ended_at"] = datetime.utcnow().isoformat()
            call_data["duration"] = call.get("duration")
            call_data["end_reason"] = call.get("endedReason")
            call_data["transcript"] = request.get("message", {}).get("transcript")
            call_data["summary"] = request.get("message", {}).get("analysis", {}).get("summary")
            call_data["recording_url"] = request.get("message", {}).get("recordingUrl")
            call_data["metadata"] = metadata

            # Write call record to Firestore
            is_inbound = not chat_id and not order_id

            if is_inbound:
                # --- Inbound call: persist to inbound_calls collection ---
                try:
                    from lib.firebase import save_inbound_call
                    import json as _json

                    analysis = request.get("message", {}).get("analysis", {})
                    structured = {}
                    if analysis.get("structuredData"):
                        try:
                            raw_sd = analysis["structuredData"]
                            structured = _json.loads(raw_sd) if isinstance(raw_sd, str) else raw_sd
                        except Exception:
                            pass

                    # Pull caller info from calls_dict (set by collect_caller_info tool)
                    caller_name = call_data.get("caller_name") or structured.get("callerName", "")
                    caller_email = call_data.get("caller_email") or structured.get("callerEmail", "")

                    inbound_doc = {
                        "vapiCallId": call_id,
                        "direction": "inbound",
                        "callerPhone": call.get("customer", {}).get("number", ""),
                        "callerName": caller_name,
                        "callerEmail": caller_email,
                        "status": "completed" if call.get("endedReason") != "error" else "failed",
                        "duration": call.get("duration"),
                        "transcript": request.get("message", {}).get("transcript", ""),
                        "summary": analysis.get("summary", ""),
                        "recordingUrl": request.get("message", {}).get("recordingUrl", ""),
                        "intent": structured.get("intent", ""),
                        "actionsPerformed": structured.get("actionsPerformed", []),
                        "eventDetails": structured.get("eventDetails", {}),
                        "followUpNeeded": structured.get("followUpNeeded", False),
                        "endedAt": datetime.utcnow().isoformat(),
                    }
                    await save_inbound_call(call_id, inbound_doc)
                    print(f"[VAPI-INBOUND] Saved inbound call {call_id} to Firestore")
                except Exception as e:
                    print(f"[VAPI-INBOUND] Error saving inbound call to Firestore: {e}")

            elif chat_id and order_id:
                # --- Outbound call: persist to chats/.../orders/.../calls/... ---
                try:
                    db = get_db()
                    call_ref = db.collection("chats").document(chat_id) \
                                 .collection("orders").document(order_id) \
                                 .collection("calls").document(call_id)

                    from firebase_admin import firestore as fs
                    call_ref.set({
                        "vapiCallId": call_id,
                        "direction": "outbound",
                        "phoneNumber": call.get("customer", {}).get("number", ""),
                        "status": "completed",
                        "duration": call.get("duration"),
                        "transcript": request.get("message", {}).get("transcript"),
                        "summary": request.get("message", {}).get("analysis", {}).get("summary"),
                        "recordingUrl": request.get("message", {}).get("recordingUrl"),
                        "createdAt": fs.SERVER_TIMESTAMP,
                        "endedAt": fs.SERVER_TIMESTAMP,
                    })
                except Exception as e:
                    print(f"[VAPI] Error writing call to Firestore: {e}")

            # Post call summary back into the chat conversation
            if chat_id:
                try:
                    from lib.firebase import add_message
                    summary = call_data.get("summary") or "No summary available."
                    customer_name = call.get("customer", {}).get("name", "Unknown")
                    duration = call.get("duration")
                    duration_str = f"{int(duration)}s" if duration else "unknown"
                    end_reason = call.get("endedReason", "unknown")

                    msg = f"**Call completed with {customer_name}** ({duration_str})\n\n"
                    msg += f"**Summary:** {summary}\n\n"
                    if end_reason and end_reason != "unknown":
                        msg += f"**End reason:** {end_reason}\n"

                    await add_message(chat_id, "assistant", msg)
                    print(f"[VAPI] Posted call summary to chat {chat_id}")
                except Exception as e:
                    print(f"[VAPI] Error posting call summary to chat: {e}")

            # Update order with call results
            if chat_id and order_id:
                try:
                    from lib.firebase import update_order

                    summary_text = call_data.get("summary") or "No summary available."
                    end_reason = call.get("endedReason", "unknown")
                    duration_val = call.get("duration")

                    # Always write the call summary + transcript directly on the order
                    base_updates = {
                        "lastCallId": call_id,
                        "lastCallSummary": summary_text,
                        "lastCallAt": datetime.utcnow().isoformat(),
                        "lastCallDuration": duration_val,
                        "lastCallEndReason": end_reason,
                    }
                    transcript_text = call_data.get("transcript")
                    if transcript_text:
                        # Store transcript (truncate if very long)
                        base_updates["lastCallTranscript"] = str(transcript_text)[:5000]

                    # Try to extract structured order details
                    try:
                        import json as _json
                        from langchain_groq import ChatGroq
                        from langchain_core.messages import SystemMessage as SysMsg, HumanMessage as HumMsg

                        call_text = summary_text

                        extract_llm = ChatGroq(model="qwen/qwen3-32b", temperature=0, max_tokens=600)
                        extract_result = await extract_llm.ainvoke([
                            SysMsg(content=(
                                "Extract order details from this phone call summary. Return ONLY valid JSON — no markdown, no explanation.\n"
                                "Schema: {\"confirmed\": true/false, \"pickup_time\": \"\", \"total\": 0.0, "
                                "\"items\": [{\"name\": \"\", \"quantity\": 0, \"price\": 0.0}], "
                                "\"special_instructions\": \"\", \"confirmation_number\": \"\", \"failure_reason\": \"\"}\n"
                                "Omit fields you cannot find. If the call was unsuccessful, set confirmed=false and describe why in failure_reason."
                            )),
                            HumMsg(content=call_text),
                        ])

                        raw = extract_result.content.strip()
                        if "<think>" in raw:
                            raw = raw.split("</think>")[-1].strip()
                        if raw.startswith("```"):
                            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

                        data = _json.loads(raw)
                        print(f"[VAPI] Extracted order details from call: {data}")

                        if data.get("confirmed"):
                            base_updates["poemStage"] = "execute"
                            base_updates["status"] = "confirmed"
                            if data.get("pickup_time"):
                                base_updates["pickupTime"] = data["pickup_time"]
                            if data.get("total"):
                                base_updates["estimatedCost"] = data["total"]
                            if data.get("items"):
                                base_updates["items"] = data["items"]
                            if data.get("confirmation_number"):
                                base_updates["confirmationNumber"] = data["confirmation_number"]
                        else:
                            base_updates["status"] = "call_failed"
                            base_updates["notes"] = data.get("failure_reason") or summary_text
                    except Exception as e:
                        print(f"[VAPI] Extraction failed (non-fatal), saving raw summary: {e}")
                        base_updates["status"] = "call_completed"
                        base_updates["notes"] = summary_text

                    await update_order(chat_id, order_id, base_updates)
                    print(f"[VAPI] Updated order {order_id}: status={base_updates.get('status')}")
                except Exception as e:
                    print(f"[VAPI] Error updating order from call: {e}")

        elif message_type == "transcript":
            transcript = request.get("message", {}).get("transcript", [])
            call_data["live_transcript"] = transcript

        calls_dict[call_id] = call_data
        return {"status": "ok"}

    @web_app.get("/calls/{call_id}")
    async def get_call(call_id: str):
        """Get call status and details."""
        call_data = calls_dict.get(call_id)
        if not call_data:
            raise HTTPException(status_code=404, detail="Call not found")
        return call_data

    @web_app.get("/calls")
    async def list_calls(limit: int = 20):
        """List recent calls."""
        return {"message": "Use call_id to fetch specific calls"}

    @web_app.post("/webhooks/doordash")
    async def doordash_webhook(request: dict):
        """Handle DoorDash Drive delivery status webhooks."""
        from datetime import datetime
        from lib.notifications import notification_service

        event_type = request.get("event_type")
        delivery = request.get("delivery", {})
        external_delivery_id = delivery.get("external_delivery_id")

        if not external_delivery_id:
            return {"status": "ok"}

        # Get stored order
        order_data = orders_dict.get(external_delivery_id, {})
        order_data["last_updated"] = datetime.utcnow().isoformat()
        order_data["status"] = delivery.get("delivery_status")

        # Map DoorDash status events
        status = delivery.get("delivery_status", "")

        if status == "dasher_confirmed":
            order_data["dasher_confirmed_at"] = datetime.utcnow().isoformat()
            order_data["dasher"] = {
                "name": delivery.get("dasher", {}).get("first_name"),
                "phone": delivery.get("dasher", {}).get("phone_number"),
            }

        elif status == "dasher_picked_up":
            order_data["picked_up_at"] = datetime.utcnow().isoformat()

        elif status == "dasher_dropped_off":
            order_data["delivered_at"] = datetime.utcnow().isoformat()

        elif status == "cancelled":
            order_data["cancelled_at"] = datetime.utcnow().isoformat()
            order_data["cancellation_reason"] = delivery.get("cancellation_reason")

        # Update tracking URL if provided
        if delivery.get("tracking_url"):
            order_data["tracking_url"] = delivery.get("tracking_url")

        # Store updated order
        orders_dict[external_delivery_id] = order_data

        # POEM Loop: Sync Firestore order status
        try:
            firestore_order = await find_order_by_delivery_id(external_delivery_id)
            if firestore_order:
                fs_chat_id = firestore_order["chatId"]
                fs_order_id = firestore_order["id"]
                fs_updates = {"poemStage": "monitor"}

                if status in ("dasher_confirmed", "dasher_picked_up"):
                    fs_updates["status"] = "in_progress"
                elif status == "dasher_dropped_off":
                    fs_updates["status"] = "completed"
                elif status == "cancelled":
                    fs_updates["status"] = "cancelled"

                if delivery.get("tracking_url"):
                    fs_updates["trackingUrl"] = delivery["tracking_url"]

                await update_order(fs_chat_id, fs_order_id, fs_updates)
        except Exception as e:
            print(f"[POEM] Error syncing DoorDash webhook to Firestore: {e}")

        # Send push notification
        user_id = order_data.get("user_id")
        if user_id:
            await notification_service.notify_order_status(
                user_id=user_id,
                status=status,
                order_data=order_data,
            )

        # Send Slack notification if this order originated from Slack
        slack_ctx = order_data.get("slack_context")
        if slack_ctx:
            await notification_service.notify_slack_order_status(
                slack_context=slack_ctx,
                status=status,
                order_data=order_data,
            )

        return {"status": "ok"}

    @web_app.get("/orders/{external_delivery_id}")
    async def get_order_status(external_delivery_id: str):
        """Get food order status by external delivery ID."""
        order_data = orders_dict.get(external_delivery_id)
        if not order_data:
            raise HTTPException(status_code=404, detail="Order not found")
        return order_data

    @web_app.get("/conversations/{thread_id}")
    async def get_conversation(thread_id: str):
        """Get conversation history for a thread."""
        with get_checkpointer() as checkpointer:
            state = checkpointer.get_tuple({"configurable": {"thread_id": thread_id}})

            if not state:
                raise HTTPException(status_code=404, detail="Conversation not found")

            messages = state.checkpoint.get("channel_values", {}).get("messages", [])

            formatted = []
            for msg in messages:
                if hasattr(msg, "content"):
                    formatted.append({
                        "role": msg.type if hasattr(msg, "type") else "unknown",
                        "content": msg.content,
                    })
                elif isinstance(msg, dict):
                    formatted.append(msg)

            return {
                "thread_id": thread_id,
                "message_count": len(formatted),
                "messages": formatted,
                "checkpoint_id": state.config.get("configurable", {}).get("checkpoint_id"),
            }

    @web_app.delete("/conversations/{thread_id}")
    async def delete_conversation(thread_id: str):
        """Delete a conversation thread."""
        with get_checkpointer() as checkpointer:
            checkpointer.delete_thread(thread_id)

        return {"status": "deleted", "thread_id": thread_id}

    # ========== Time Travel (Checkpoint History & Branching) ==========

    @web_app.get("/conversations/{thread_id}/history")
    async def get_conversation_history(thread_id: str, limit: int = 20):
        """
        Get checkpoint history for time-travel.
        Returns all checkpoints in reverse chronological order.
        """
        async with get_async_checkpointer() as checkpointer:
            config = {"configurable": {"thread_id": thread_id}}
            graph = create_agent_graph(checkpointer=checkpointer)

            # Get all states (reverse chronological)
            states = [s async for s in graph.aget_state_history(config)][:limit]

            if not states:
                raise HTTPException(status_code=404, detail="No history found for thread")

            history = []
            for state in states:
                checkpoint_id = state.config["configurable"]["checkpoint_id"]
                values = state.values

                # Extract key info for each checkpoint
                food_order = values.get("food_order")
                if food_order and isinstance(food_order, dict):
                    workflow_step = food_order.get("current_step")
                    completed_steps = food_order.get("completed_steps", [])
                    vendor_name = None
                    if food_order.get("selected_vendor"):
                        vendor_name = food_order["selected_vendor"].get("name")
                    total = food_order.get("total")
                else:
                    workflow_step = None
                    completed_steps = []
                    vendor_name = None
                    total = None

                history.append({
                    "checkpoint_id": checkpoint_id,
                    "next_node": list(state.next) if state.next else [],
                    "workflow_step": workflow_step,
                    "completed_steps": completed_steps,
                    "vendor_selected": vendor_name,
                    "total": total,
                    "intent": values.get("intent"),
                    "message_count": len(values.get("messages", [])),
                    "has_pending_actions": len(values.get("pending_actions", [])) > 0,
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
        message: Optional[str] = None,
    ):
        """
        Resume conversation from a specific checkpoint.
        Optionally provide a new message to continue the conversation.
        """
        async with get_async_checkpointer() as checkpointer:
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

            last_message = result["messages"][-1] if result.get("messages") else None
            response_text = ""
            if last_message:
                response_text = last_message.content if hasattr(last_message, 'content') else last_message.get("content", "")

            return {
                "thread_id": thread_id,
                "resumed_from": checkpoint_id,
                "response": response_text,
                "pending_actions": result.get("pending_actions", []),
            }

    class BranchRequest(BaseModel):
        checkpoint_id: str
        state_updates: Optional[dict] = None
        message: Optional[str] = None

    @web_app.post("/conversations/{thread_id}/branch")
    async def branch_conversation(thread_id: str, request: BranchRequest):
        """
        Branch from a checkpoint with modified state.
        Creates a NEW thread_id for the branch to preserve original history.
        """
        import uuid

        async with get_async_checkpointer() as checkpointer:
            graph = create_agent_graph(checkpointer=checkpointer)

            # Get state at checkpoint
            old_config = {
                "configurable": {
                    "thread_id": thread_id,
                    "checkpoint_id": request.checkpoint_id,
                }
            }

            # Verify checkpoint exists
            state = await graph.aget_state(old_config)
            if not state or not state.values:
                raise HTTPException(status_code=404, detail="Checkpoint not found")

            # Create new branch with new thread_id
            branch_id = str(uuid.uuid4())[:8]
            new_thread_id = f"{thread_id}__branch__{branch_id}"

            # Apply state updates if provided
            if request.state_updates:
                await graph.aupdate_state(old_config, values=request.state_updates)
                # Get the new checkpoint after update
                updated_state = await graph.aget_state(old_config)
                old_config = updated_state.config

            new_config = {
                "configurable": {
                    "thread_id": new_thread_id,
                    "checkpoint_id": old_config["configurable"].get("checkpoint_id"),
                }
            }

            # Continue execution with optional message
            input_state = None
            if request.message:
                input_state = {"messages": [{"role": "user", "content": request.message}]}

            result = await graph.ainvoke(input_state, config=new_config)

            last_message = result["messages"][-1] if result.get("messages") else None
            response_text = ""
            if last_message:
                response_text = last_message.content if hasattr(last_message, 'content') else last_message.get("content", "")

            return {
                "original_thread_id": thread_id,
                "branched_from_checkpoint": request.checkpoint_id,
                "new_thread_id": new_thread_id,
                "response": response_text,
                "pending_actions": result.get("pending_actions", []),
            }

    # ========== Workflow-Specific Time Travel Helpers ==========

    class VendorBranchRequest(BaseModel):
        new_cuisine: Optional[str] = None
        new_location: Optional[str] = None
        budget_per_person: Optional[float] = None

    @web_app.post("/orders/{thread_id}/try-different-vendors")
    async def branch_to_vendor_search(thread_id: str, request: VendorBranchRequest):
        """
        Branch back to vendor search with new preferences.
        Use case: "Actually, show me Thai restaurants instead"
        """
        async with get_async_checkpointer() as checkpointer:
            graph = create_agent_graph(checkpointer=checkpointer)
            config = {"configurable": {"thread_id": thread_id}}

            # Find checkpoint before vendor search completed
            states = [s async for s in graph.aget_state_history(config)]

            target_checkpoint = None
            target_state = None
            for state in states:
                food_order = state.values.get("food_order")
                if food_order and isinstance(food_order, dict):
                    step = food_order.get("current_step")
                    if step in ["gather_requirements", "search_vendors"]:
                        target_checkpoint = state.config["configurable"]["checkpoint_id"]
                        target_state = state
                        break

            if not target_checkpoint:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot find vendor search checkpoint. Start a food order first."
                )

            # Build state updates
            state_updates = {}
            food_order = dict(target_state.values.get("food_order", {}))

            if request.new_cuisine:
                food_order["cuisine_preferences"] = [request.new_cuisine]
            if request.new_location:
                food_order["delivery_address"] = request.new_location
            if request.budget_per_person:
                food_order["budget_per_person"] = request.budget_per_person

            # Clear previous vendor results
            food_order["vendor_options"] = []
            food_order["selected_vendor"] = None
            food_order["current_step"] = "search_vendors"

            state_updates["food_order"] = food_order

            # Build message
            message_parts = []
            if request.new_cuisine:
                message_parts.append(f"{request.new_cuisine} restaurants")
            if request.new_location:
                message_parts.append(f"near {request.new_location}")
            if request.budget_per_person:
                message_parts.append(f"under ${request.budget_per_person}/person")

            message = f"Search for {' '.join(message_parts)}" if message_parts else "Show me other restaurant options"

            # Branch
            branch_request = BranchRequest(
                checkpoint_id=target_checkpoint,
                state_updates=state_updates,
                message=message,
            )
            return await branch_conversation(thread_id, branch_request)

    class BudgetBranchRequest(BaseModel):
        new_total_budget: Optional[float] = None
        new_per_person_budget: Optional[float] = None

    @web_app.post("/orders/{thread_id}/adjust-budget")
    async def branch_to_adjust_budget(thread_id: str, request: BudgetBranchRequest):
        """
        Branch back to order builder with adjusted budget.
        Use case: "What if I only had $15 per person?"
        """
        async with get_async_checkpointer() as checkpointer:
            graph = create_agent_graph(checkpointer=checkpointer)
            config = {"configurable": {"thread_id": thread_id}}

            # Find checkpoint at or before order builder
            states = [s async for s in graph.aget_state_history(config)]

            target_checkpoint = None
            target_state = None
            for state in states:
                next_nodes = state.next or ()
                food_order = state.values.get("food_order")
                if food_order and isinstance(food_order, dict):
                    step = food_order.get("current_step")
                    if "order_builder" in next_nodes or step in ["build_order", "select_vendor"]:
                        target_checkpoint = state.config["configurable"]["checkpoint_id"]
                        target_state = state
                        break

            if not target_checkpoint:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot find order builder checkpoint. Select a vendor first."
                )

            # Update budget in food_order
            state_updates = {}
            food_order = dict(target_state.values.get("food_order", {}))

            if request.new_total_budget:
                food_order["budget_total"] = request.new_total_budget
            if request.new_per_person_budget:
                food_order["budget_per_person"] = request.new_per_person_budget

            # Clear previous menu items and totals
            food_order["menu_items"] = []
            food_order["subtotal"] = None
            food_order["tax"] = None
            food_order["total"] = None
            food_order["current_step"] = "build_order"

            state_updates["food_order"] = food_order

            # Build message
            budget_str = f"${request.new_per_person_budget}/person" if request.new_per_person_budget else f"${request.new_total_budget} total"
            message = f"Suggest menu items that fit a {budget_str} budget"

            # Branch
            branch_request = BranchRequest(
                checkpoint_id=target_checkpoint,
                state_updates=state_updates,
                message=message,
            )
            return await branch_conversation(thread_id, branch_request)

    class DeliveryBranchRequest(BaseModel):
        new_date: Optional[str] = None
        new_time: Optional[str] = None

    @web_app.post("/orders/{thread_id}/change-delivery-time")
    async def branch_to_change_delivery(thread_id: str, request: DeliveryBranchRequest):
        """
        Branch to get new delivery quote with different timing.
        Use case: "What if we do lunch at 1pm instead of noon?"
        """
        async with get_async_checkpointer() as checkpointer:
            graph = create_agent_graph(checkpointer=checkpointer)
            config = {"configurable": {"thread_id": thread_id}}

            # Find checkpoint before DoorDash quote
            states = [s async for s in graph.aget_state_history(config)]

            target_checkpoint = None
            target_state = None
            for state in states:
                next_nodes = state.next or ()
                food_order = state.values.get("food_order")
                if food_order and isinstance(food_order, dict):
                    step = food_order.get("current_step")
                    if "order_submit" in next_nodes or step in ["review_order", "confirm_order"]:
                        target_checkpoint = state.config["configurable"]["checkpoint_id"]
                        target_state = state
                        break

            if not target_checkpoint:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot find delivery checkpoint. Build your order first."
                )

            # Update delivery time
            state_updates = {}
            food_order = dict(target_state.values.get("food_order", {}))

            if request.new_date:
                food_order["event_date"] = request.new_date
            if request.new_time:
                food_order["event_time"] = request.new_time

            # Clear previous quote
            food_order["doordash_quote_id"] = None
            food_order["delivery_fee"] = None
            food_order["estimated_pickup_time"] = None
            food_order["estimated_delivery_time"] = None
            food_order["current_step"] = "confirm_order"

            state_updates["food_order"] = food_order

            # Build message
            time_parts = []
            if request.new_date:
                time_parts.append(request.new_date)
            if request.new_time:
                time_parts.append(f"at {request.new_time}")
            message = f"Get a delivery quote for {' '.join(time_parts)}" if time_parts else "Get a new delivery quote"

            # Branch
            branch_request = BranchRequest(
                checkpoint_id=target_checkpoint,
                state_updates=state_updates,
                message=message,
            )
            return await branch_conversation(thread_id, branch_request)

    # ========== User Preferences (Long-Term Memory) ==========

    class PreferencesUpdate(BaseModel):
        dietary_restrictions: list[str] = []
        allergies: list[str] = []
        favorite_cuisines: list[str] = []
        disliked_cuisines: list[str] = []
        favorite_foods: list[str] = []
        disliked_foods: list[str] = []
        spice_preference: Optional[str] = None
        default_budget_per_person: Optional[float] = None
        preferred_price_level: Optional[str] = None
        favorite_vendors: list[str] = []
        notes: Optional[str] = None

    @web_app.get("/users/{user_id}/preferences")
    async def get_preferences(user_id: str):
        """Get user food preferences."""
        from lib.redis import get_user_preferences

        prefs = get_user_preferences(user_id)
        if not prefs:
            return {"user_id": user_id, "preferences": None, "message": "No preferences stored"}
        return {"user_id": user_id, "preferences": prefs}

    @web_app.put("/users/{user_id}/preferences")
    async def update_preferences(user_id: str, request: PreferencesUpdate):
        """Update user food preferences (merge with existing)."""
        from lib.redis import update_user_preferences

        updates = request.model_dump(exclude_none=True, exclude_unset=True)
        # Filter out empty lists
        updates = {k: v for k, v in updates.items() if v or isinstance(v, (int, float))}

        updated = update_user_preferences(user_id, updates)
        return {"user_id": user_id, "preferences": updated, "message": "Preferences updated"}

    @web_app.delete("/users/{user_id}/preferences")
    async def delete_preferences(user_id: str):
        """Delete all user food preferences."""
        from lib.redis import delete_user_preferences

        deleted = delete_user_preferences(user_id)
        if deleted:
            return {"user_id": user_id, "message": "Preferences deleted"}
        return {"user_id": user_id, "message": "No preferences found to delete"}

    # ========== Poll Mini App (Shareable HTML Pages) ==========

    def get_voter_id(request: Request) -> str:
        """Generate anonymous voter ID from device fingerprint."""
        # Combine user agent + IP for a simple device fingerprint
        user_agent = request.headers.get("user-agent", "")
        ip = request.client.host if request.client else "unknown"
        fingerprint = f"{user_agent}:{ip}"
        return hashlib.sha256(fingerprint.encode()).hexdigest()[:16]

    def format_deadline(deadline_str: str) -> str:
        """Format deadline for display."""
        from datetime import datetime
        try:
            deadline = datetime.fromisoformat(deadline_str.replace("Z", "+00:00"))
            now = datetime.now(deadline.tzinfo) if deadline.tzinfo else datetime.now()
            if deadline < now:
                return "Ended"
            diff = deadline - now
            if diff.days > 0:
                return f"in {diff.days} day{'s' if diff.days > 1 else ''}"
            hours = diff.seconds // 3600
            if hours > 0:
                return f"in {hours} hour{'s' if hours > 1 else ''}"
            minutes = diff.seconds // 60
            return f"in {minutes} minute{'s' if minutes > 1 else ''}"
        except:
            return ""

    @web_app.get("/p/{poll_id}", response_class=HTMLResponse)
    async def poll_vote_page(request: Request, poll_id: str):
        """Shareable poll voting page."""
        poll = get_poll_doc(poll_id)
        if not poll:
            raise HTTPException(status_code=404, detail="Poll not found")

        voter_id = get_voter_id(request)
        already_voted = any(v.get("voter_id") == voter_id for v in poll.get("votes", []))
        deadline_str = format_deadline(poll.get("deadline", "")) if poll.get("deadline") else None

        return templates.TemplateResponse("poll_vote.html", {
            "request": request,
            "poll": poll,
            "already_voted": already_voted,
            "deadline_str": deadline_str,
        })

    @web_app.post("/p/{poll_id}/vote")
    async def poll_vote_submit(request: Request, poll_id: str, option_id: str = Form(...)):
        """Handle vote submission from the poll page."""
        from datetime import datetime

        poll = get_poll_doc(poll_id)
        if not poll:
            raise HTTPException(status_code=404, detail="Poll not found")

        if poll.get("is_closed"):
            return RedirectResponse(url=f"/p/{poll_id}", status_code=303)

        voter_id = get_voter_id(request)

        # Check if already voted
        if any(v.get("voter_id") == voter_id for v in poll.get("votes", [])):
            return RedirectResponse(url=f"/p/{poll_id}", status_code=303)

        # Record the vote
        poll.setdefault("votes", []).append({
            "voter_id": voter_id,
            "option_id": option_id,
            "timestamp": datetime.utcnow().isoformat(),
        })

        # Update option vote count
        for option in poll.get("options", []):
            if option.get("option_id") == option_id:
                option["votes"] = option.get("votes", 0) + 1
                break

        update_poll_doc(poll_id, {"votes": poll["votes"], "options": poll["options"]})

        # Redirect to results page
        return RedirectResponse(url=f"/p/{poll_id}/results", status_code=303)

    @web_app.get("/p/{poll_id}/results", response_class=HTMLResponse)
    async def poll_results_page(request: Request, poll_id: str):
        """Poll results page with live updates."""
        poll = get_poll_doc(poll_id)
        if not poll:
            raise HTTPException(status_code=404, detail="Poll not found")

        voter_id = get_voter_id(request)
        already_voted = any(v.get("voter_id") == voter_id for v in poll.get("votes", []))

        # Calculate results
        total_votes = sum(opt.get("votes", 0) for opt in poll.get("options", []))
        max_votes = max((opt.get("votes", 0) for opt in poll.get("options", [])), default=0)

        results = []
        for option in poll.get("options", []):
            votes = option.get("votes", 0)
            percentage = round((votes / total_votes * 100) if total_votes > 0 else 0)
            is_winner = votes == max_votes and votes > 0
            results.append({
                "text": option.get("text", ""),
                "votes": votes,
                "percentage": percentage,
                "is_winner": is_winner,
            })

        return templates.TemplateResponse("poll_results.html", {
            "request": request,
            "poll": poll,
            "results": results,
            "total_votes": total_votes,
            "already_voted": already_voted,
        })

    # ==================== DIETARY FORM PAGES ====================

    DIETARY_OPTIONS = [
        "Vegetarian", "Vegan", "Gluten-Free", "Halal",
        "Kosher", "Pescatarian", "Keto", "Dairy-Free",
    ]
    ALLERGY_OPTIONS = [
        "Nuts", "Shellfish", "Dairy", "Eggs",
        "Soy", "Wheat", "Fish", "Sesame",
    ]

    @web_app.get("/f/{form_id}", response_class=HTMLResponse)
    async def dietary_form_page(request: Request, form_id: str):
        """Shareable dietary intake form page."""
        form = get_form_doc(form_id)
        if not form:
            raise HTTPException(status_code=404, detail="Form not found")

        voter_id = get_voter_id(request)
        already_submitted = any(
            r.get("fingerprint") == voter_id for r in form.get("responses", [])
        )
        deadline_str = format_deadline(form.get("deadline", "")) if form.get("deadline") else None

        return templates.TemplateResponse("dietary_form.html", {
            "request": request,
            "form": form,
            "already_submitted": already_submitted,
            "deadline_str": deadline_str,
            "dietary_options": DIETARY_OPTIONS,
            "allergy_options": ALLERGY_OPTIONS,
        })

    @web_app.post("/f/{form_id}/submit")
    async def dietary_form_submit(request: Request, form_id: str):
        """Handle dietary form submission."""
        from datetime import datetime
        import uuid as uuid_mod

        form = get_form_doc(form_id)
        if not form:
            raise HTTPException(status_code=404, detail="Form not found")

        if form.get("is_closed"):
            return RedirectResponse(url=f"/f/{form_id}", status_code=303)

        voter_id = get_voter_id(request)

        # Check duplicate
        if any(r.get("fingerprint") == voter_id for r in form.get("responses", [])):
            return RedirectResponse(url=f"/f/{form_id}", status_code=303)

        # Parse form data
        form_data = await request.form()
        name = form_data.get("name", "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name is required")

        email = form_data.get("email", "").strip()
        dietary = form_data.getlist("dietary")
        allergies = form_data.getlist("allergies")
        notes = form_data.get("notes", "").strip()

        # Filter out "None" if other options are selected
        if len(dietary) > 1 and "None" in dietary:
            dietary = [d for d in dietary if d != "None"]
        if len(allergies) > 1 and "None" in allergies:
            allergies = [a for a in allergies if a != "None"]

        response_data = {
            "response_id": str(uuid_mod.uuid4()),
            "name": name,
            "email": email,
            "dietary_restrictions": dietary,
            "allergies": allergies,
            "notes": notes,
            "submitted_at": datetime.utcnow().isoformat(),
            "fingerprint": voter_id,
        }

        # Append response
        responses = form.get("responses", [])
        responses.append(response_data)
        update_form_doc(form_id, {
            "responses": responses,
            "total_responses": len(responses),
        })

        return RedirectResponse(url=f"/f/{form_id}/results", status_code=303)

    @web_app.get("/f/{form_id}/results", response_class=HTMLResponse)
    async def dietary_form_results_page(request: Request, form_id: str):
        """Dietary form results page with aggregated data."""
        from collections import Counter

        form = get_form_doc(form_id)
        if not form:
            raise HTTPException(status_code=404, detail="Form not found")

        responses = form.get("responses", [])
        total_responses = len(responses)

        # Aggregate dietary restrictions
        all_dietary = []
        for r in responses:
            all_dietary.extend(r.get("dietary_restrictions", []))
        dietary_counts = Counter(all_dietary)
        # Remove "None" from display
        dietary_counts.pop("None", None)

        dietary_data = []
        for name, count in dietary_counts.most_common():
            pct = round(count / total_responses * 100) if total_responses > 0 else 0
            dietary_data.append({"name": name, "count": count, "pct": pct})

        # Aggregate allergies
        all_allergies = []
        for r in responses:
            all_allergies.extend(r.get("allergies", []))
        allergy_counts = Counter(all_allergies)
        allergy_counts.pop("None", None)

        allergy_data = []
        for name, count in allergy_counts.most_common():
            pct = round(count / total_responses * 100) if total_responses > 0 else 0
            allergy_data.append({"name": name, "count": count, "pct": pct})

        # Collect notes and respondent names
        notes = [r["notes"] for r in responses if r.get("notes", "").strip()]
        respondents = [r.get("name", "Anonymous") for r in responses]

        return templates.TemplateResponse("dietary_form_results.html", {
            "request": request,
            "form": form,
            "total_responses": total_responses,
            "dietary_data": dietary_data,
            "allergy_data": allergy_data,
            "notes": notes,
            "respondents": respondents,
        })

    # ==================== ORDER APPROVAL PAGES ====================

    @web_app.get("/o/{action_id}", response_class=HTMLResponse)
    async def order_approval_page(request: Request, action_id: str):
        """Shareable order approval page. Requires Firebase auth."""
        # Look up the action
        try:
            action = actions_dict[action_id]
        except KeyError:
            return templates.TemplateResponse("order_status.html", {
                "request": request,
                "status": "not_found",
                "message": "This order was not found or has expired.",
            })

        status = action.get("status", "pending_approval")
        if status != "pending_approval":
            status_msg = {
                "approved": "This order has already been approved.",
                "rejected": "This order was declined.",
                "completed": "This order has been placed.",
            }.get(status, f"This order has status: {status}")
            return templates.TemplateResponse("order_status.html", {
                "request": request,
                "status": status,
                "message": status_msg,
                "action": action,
            })

        # Render approval page with order details
        action_type = action.get("action_type", "")
        payload = action.get("payload", {})

        # Extract order details based on action type
        order_details = {}
        if action_type == "food_order":
            food_order = payload.get("food_order", {})
            quote = payload.get("doordash_quote", {})
            vendor_data = payload.get("vendor", {})
            vendor_name = vendor_data.get("name", "Unknown") if isinstance(vendor_data, dict) else "Unknown"

            items = food_order.get("menu_items", [])
            subtotal = food_order.get("subtotal", 0)
            tax = food_order.get("tax", 0)
            delivery_fee = quote.get("fee_cents", 0) / 100
            service_fee = food_order.get("service_fee", 0)
            total = subtotal + tax + delivery_fee + service_fee
            headcount = food_order.get("headcount", 1)

            order_details = {
                "vendor_name": vendor_name,
                "headcount": headcount,
                "delivery_date": food_order.get("event_date", "Today"),
                "delivery_time": food_order.get("event_time", "ASAP"),
                "delivery_address": food_order.get("delivery_address", "TBD"),
                "items": items,
                "subtotal": subtotal,
                "tax": tax,
                "delivery_fee": delivery_fee,
                "service_fee": service_fee,
                "total": total,
                "per_person": total / headcount if headcount else total,
                "estimated_pickup": quote.get("estimated_pickup_time", ""),
                "estimated_delivery": quote.get("estimated_dropoff_time", ""),
            }
        elif action_type == "catering_order":
            pricing = payload.get("pricing", {})
            order_details = {
                "vendor_name": payload.get("caterer_name", "Unknown"),
                "headcount": payload.get("headcount", 1),
                "items": payload.get("items", []),
                "subtotal": pricing.get("subtotal", 0),
                "tax": pricing.get("tax", 0),
                "delivery_fee": pricing.get("delivery_fee", 0),
                "service_fee": 0,
                "total": pricing.get("total", 0),
                "per_person": pricing.get("per_person", 0),
            }

        return templates.TemplateResponse("order_approval.html", {
            "request": request,
            "action_id": action_id,
            "action_type": action_type,
            "action": action,
            "order": order_details,
        })

    @web_app.post("/o/{action_id}/approve")
    async def order_approval_submit(request: Request, action_id: str):
        """Handle order approval from the shareable page. Requires Firebase auth."""
        import firebase_admin.auth as firebase_auth

        # Verify Firebase ID token from Authorization header
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Authentication required")

        id_token = auth_header.replace("Bearer ", "")
        try:
            decoded_token = firebase_auth.verify_id_token(id_token)
            requesting_user_id = decoded_token["uid"]
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid authentication token")

        # Look up the action
        try:
            action = actions_dict[action_id]
        except KeyError:
            raise HTTPException(status_code=404, detail="Action not found")

        if action.get("status") != "pending_approval":
            raise HTTPException(status_code=400, detail="Action is no longer pending")

        # Parse request body
        body = await request.json()
        approved = body.get("approved", False)

        # Reuse existing approval logic
        if approved:
            action["status"] = "approved"
            actions_dict[action_id] = action

            chat_id = action.get("chat_id")

            try:
                result = await execute_approved_action(action)
                action["status"] = "completed"
                action["result"] = result
                actions_dict[action_id] = action

                # Update Firestore order if applicable
                firestore_order_id = action.get("firestore_order_id")
                if firestore_order_id and chat_id:
                    tracking_url = result.get("tracking_url") if isinstance(result, dict) else None
                    update_order(chat_id, firestore_order_id, {
                        "status": "confirmed",
                        "poemStage": "monitor",
                        "trackingUrl": tracking_url,
                    })

                return {"status": "approved", "result": result}
            except Exception as e:
                action["status"] = "error"
                action["error"] = str(e)
                actions_dict[action_id] = action
                raise HTTPException(status_code=500, detail=f"Failed to execute: {str(e)}")
        else:
            action["status"] = "rejected"
            actions_dict[action_id] = action

            firestore_order_id = action.get("firestore_order_id")
            chat_id = action.get("chat_id")
            if firestore_order_id and chat_id:
                update_order(chat_id, firestore_order_id, {
                    "status": "cancelled",
                    "poemStage": "plan",
                })

            return {"status": "rejected"}

    @web_app.get("/o/{action_id}/status", response_class=HTMLResponse)
    async def order_status_page(request: Request, action_id: str):
        """Order status page after approval/rejection."""
        try:
            action = actions_dict[action_id]
        except KeyError:
            return templates.TemplateResponse("order_status.html", {
                "request": request,
                "status": "not_found",
                "message": "This order was not found or has expired.",
            })

        status = action.get("status", "unknown")
        result = action.get("result", {})
        tracking_url = result.get("tracking_url") if isinstance(result, dict) else None

        status_msg = {
            "approved": "Order approved and being processed.",
            "completed": "Order has been placed!",
            "rejected": "Order was declined.",
            "error": f"Order failed: {action.get('error', 'Unknown error')}",
            "pending_approval": "Order is still waiting for approval.",
        }.get(status, f"Order status: {status}")

        return templates.TemplateResponse("order_status.html", {
            "request": request,
            "status": status,
            "message": status_msg,
            "tracking_url": tracking_url,
            "action": action,
        })

    # ==================== EXPENSE & PAYMENT ENDPOINTS ====================

    @web_app.post("/expenses/generate/{order_id}")
    async def generate_expense_endpoint(order_id: str, cost_splits: Optional[list[dict]] = None):
        """Manually trigger expense generation for a completed order."""
        from tools.expenses import generate_expense
        result = generate_expense.invoke({
            "order_id": order_id,
            "cost_splits": cost_splits,
        })
        return result

    @web_app.get("/expenses/export")
    async def export_expenses_endpoint(start_date: str, end_date: str):
        """Export expenses as CSV for a date range."""
        from tools.expenses import export_expenses_csv
        result = export_expenses_csv.invoke({
            "start_date": start_date,
            "end_date": end_date,
        })
        return result

    @web_app.get("/expenses/{expense_id}")
    async def get_expense(expense_id: str):
        """Get expense status by ID."""
        db = get_db()
        doc = db.collection("expenses").document(expense_id).get()
        if not doc.exists:
            raise HTTPException(status_code=404, detail="Expense not found")
        return doc.to_dict()

    @web_app.post("/payments/split/{order_id}")
    async def create_split(order_id: str, attendee_emails: list[str], total_amount: float):
        """Initiate a cost split for an order."""
        from tools.payments import create_payment_split
        result = create_payment_split.invoke({
            "order_id": order_id,
            "total_amount": total_amount,
            "attendee_emails": attendee_emails,
        })
        return result

    @web_app.get("/payments/split/{order_id}/status")
    async def split_status(order_id: str):
        """Check payment split progress."""
        from tools.payments import check_split_payment_status
        result = check_split_payment_status.invoke({"order_id": order_id})
        return result

    # ==================== GOOGLE CALENDAR INTEGRATION ====================

    @web_app.get("/gcal/auth")
    async def gcal_auth(user_id: str):
        """Redirect user to Google OAuth2 consent screen."""
        from integrations.gcal.auth import get_auth_url

        base_url = os.environ.get("API_BASE_URL", "https://your-modal-app.modal.run")
        redirect_uri = f"{base_url}/gcal/callback"

        url = get_auth_url(user_id, redirect_uri)
        return RedirectResponse(url=url)

    @web_app.get("/gcal/callback")
    async def gcal_callback(code: str, state: str):
        """Handle Google OAuth2 callback, store tokens."""
        from integrations.gcal.auth import handle_oauth_callback

        base_url = os.environ.get("API_BASE_URL", "https://your-modal-app.modal.run")
        redirect_uri = f"{base_url}/gcal/callback"

        result = await handle_oauth_callback(code, user_id=state, redirect_uri=redirect_uri)

        # Redirect back to settings page
        frontend_url = os.environ.get("FRONTEND_URL", "https://edesia-agent.vercel.app")
        return RedirectResponse(url=f"{frontend_url}/settings?gcal=connected")

    @web_app.get("/gcal/status/{user_id}")
    async def gcal_status(user_id: str):
        """Check if Google Calendar is connected for a user."""
        db = get_db()
        doc = db.collection("users").document(user_id).get()
        if doc.exists:
            data = doc.to_dict()
            return {"connected": data.get("gcalConnected", False)}
        return {"connected": False}

    @web_app.delete("/gcal/disconnect/{user_id}")
    async def gcal_disconnect(user_id: str):
        """Disconnect Google Calendar for a user."""
        from integrations.gcal.auth import disconnect
        await disconnect(user_id)
        return {"status": "disconnected"}

    # ==================== SLACK INTEGRATION ====================

    # Initialize Slack Bolt app with multi-workspace OAuth support
    try:
        import os
        if os.getenv("SLACK_CLIENT_ID") and os.getenv("SLACK_SIGNING_SECRET"):
            from integrations.slack.app import slack_handler, register_handlers
            register_handlers()

            # OAuth install flow
            @web_app.get("/slack/install")
            async def slack_install(request: Request):
                """Redirect to Slack's OAuth authorize page."""
                return await slack_handler.handle(request)

            @web_app.get("/slack/oauth/callback")
            async def slack_oauth_callback(request: Request):
                """Handle OAuth callback — exchanges code for bot token, saves to Firestore."""
                return await slack_handler.handle(request)

            # Slack event endpoints
            @web_app.post("/slack/commands")
            async def slack_commands(request: Request):
                """Handle Slack slash commands (/lunch, /poll)."""
                return await slack_handler.handle(request)

            @web_app.post("/slack/events")
            async def slack_events(request: Request):
                """Handle Slack event subscriptions (@mentions, DMs)."""
                # Fast-path: respond to Slack's URL verification challenge immediately
                body = await request.json()
                if body.get("type") == "url_verification":
                    from starlette.responses import JSONResponse
                    return JSONResponse({"challenge": body.get("challenge", "")})
                # Re-construct the request for Bolt (body already consumed)
                from starlette.requests import Request as StarletteRequest
                import json
                scope = request.scope
                async def receive():
                    return {"type": "http.request", "body": json.dumps(body).encode()}
                patched_request = StarletteRequest(scope, receive)
                return await slack_handler.handle(patched_request)

            @web_app.post("/slack/interactions")
            async def slack_interactions(request: Request):
                """Handle Slack interactive components (buttons, modals)."""
                return await slack_handler.handle(request)

            print("[SLACK] Slack integration enabled (OAuth multi-workspace)")
        else:
            print("[SLACK] SLACK_CLIENT_ID or SLACK_SIGNING_SECRET not set — Slack disabled")
    except Exception as e:
        print(f"[SLACK] Failed to initialize Slack integration: {e}")

    return web_app
