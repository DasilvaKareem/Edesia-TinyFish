"""Prompt templates for specific scenarios."""

RESERVATION_TEMPLATE = """I'll help you make a restaurant reservation. Let me confirm the details:

**Restaurant:** {restaurant_name}
**Party Size:** {party_size} people
**Date:** {date}
**Time:** {time}
**Contact:** {contact_name} ({contact_email})
{special_requests}

This reservation requires your approval. Reply 'approve' to confirm or let me know if you'd like to make changes."""

CATERING_QUOTE_TEMPLATE = """Here's a catering quote from {caterer_name}:

**Items:**
{items_list}

**Breakdown:**
- Subtotal: ${subtotal:.2f}
- Tax: ${tax:.2f}
- Delivery: ${delivery_fee:.2f}
- **Total: ${total:.2f}**

For {headcount} people, that's **${per_person:.2f} per person**.

This quote is valid until {valid_until}. Would you like to proceed with this order?"""

POLL_TEMPLATE = """I've created a poll for you:

**Question:** {question}

**Options:**
{options_list}

**Deadline:** {deadline}

To send this poll to your team, I'll POST it to your webhook. This requires your approval."""

BUDGET_COMPARISON_TEMPLATE = """Here's a comparison of your options:

{comparison_table}

**Recommendation:** {recommendation}

Based on your budget of ${budget:.2f} for {headcount} people (${per_person:.2f}/person), {recommendation_detail}."""

FOOD_ORDER_TEMPLATE = """**Ready to order from {restaurant_name}**

**Headcount:** {headcount} people
**Delivery:** {delivery_date} at {delivery_time}
**Address:** {delivery_address}

**Items:**
{items_list}

**Pricing:**
- Subtotal: ${subtotal:.2f}
- Tax: ${tax:.2f}
- Delivery Fee: ${delivery_fee:.2f}
- Service Fee: ${service_fee:.2f}
- **Total: ${total:.2f}** (${per_person:.2f}/person)

**Estimated Pickup:** {estimated_pickup}
**Estimated Delivery:** {estimated_delivery}

Reply 'approve' to place this order, or let me know if you'd like to make changes."""
