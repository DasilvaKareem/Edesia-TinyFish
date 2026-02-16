"""Receipt generation for expense attachment."""

import io
import logging
from typing import Optional
from datetime import datetime

from models.integrations import ReceiptData
from models.orders import FoodOrderContext

logger = logging.getLogger(__name__)


def build_receipt(order: FoodOrderContext, payment_data: Optional[dict] = None) -> ReceiptData:
    """Build structured receipt data from a completed food order.

    Args:
        order: The completed FoodOrderContext.
        payment_data: Optional Stripe payment info (last4, brand, etc.).

    Returns:
        ReceiptData with all fields populated.
    """
    fo = order if isinstance(order, dict) else order.model_dump()

    items = fo.get("menu_items", [])
    subtotal = fo.get("subtotal", 0) or 0
    tax = fo.get("tax", 0) or 0
    delivery_fee = fo.get("delivery_fee", 0) or 0
    service_fee = fo.get("service_fee", 0) or 0
    total = fo.get("total", 0) or subtotal + tax + delivery_fee + service_fee
    headcount = fo.get("headcount", 1) or 1

    # Payment method display
    payment_method = "Card on file"
    if payment_data:
        brand = payment_data.get("brand", "Card")
        last4 = payment_data.get("last4", "****")
        payment_method = f"{brand} ending {last4}"

    vendor_name = "Unknown"
    vendor = fo.get("selected_vendor")
    if vendor:
        vendor_name = vendor.get("name", "Unknown") if isinstance(vendor, dict) else vendor.name

    order_date = fo.get("event_date", datetime.utcnow().strftime("%Y-%m-%d"))

    return ReceiptData(
        order_id=fo.get("order_id", ""),
        vendor_name=vendor_name,
        items=items if isinstance(items, list) else [],
        subtotal=subtotal,
        tax=tax,
        delivery_fee=delivery_fee,
        tip=service_fee,
        total=total,
        payment_method=payment_method,
        date=order_date,
        attendee_count=headcount,
        per_person_cost=round(total / headcount, 2) if headcount > 0 else total,
    )


def render_receipt_text(receipt: ReceiptData) -> str:
    """Render receipt as plain text (for CSV and Slack)."""
    lines = [
        f"RECEIPT — {receipt.vendor_name}",
        f"Date: {receipt.date}",
        f"Order ID: {receipt.order_id}",
        "",
        "Items:",
    ]

    for item in receipt.items:
        if isinstance(item, dict):
            name = item.get("name", "")
            qty = item.get("quantity", 1)
            price = item.get("price", 0)
        else:
            name = item.name
            qty = item.quantity
            price = item.price
        lines.append(f"  {qty}x {name} — ${price * qty:.2f}")

    lines.extend([
        "",
        f"Subtotal: ${receipt.subtotal:.2f}",
        f"Tax: ${receipt.tax:.2f}",
        f"Delivery: ${receipt.delivery_fee:.2f}",
    ])

    if receipt.tip > 0:
        lines.append(f"Tip/Service: ${receipt.tip:.2f}")

    lines.extend([
        f"TOTAL: ${receipt.total:.2f}",
        "",
        f"Payment: {receipt.payment_method}",
        f"Attendees: {receipt.attendee_count}",
        f"Per person: ${receipt.per_person_cost:.2f}",
    ])

    return "\n".join(lines)


def render_receipt_pdf(receipt: ReceiptData) -> bytes:
    """Render receipt as a PDF using ReportLab.

    Returns:
        PDF bytes.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib import colors

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.75 * inch)
    styles = getSampleStyleSheet()
    story = []

    # Header
    story.append(Paragraph(f"<b>Receipt — {receipt.vendor_name}</b>", styles["Title"]))
    story.append(Paragraph(f"Date: {receipt.date} | Order: {receipt.order_id}", styles["Normal"]))
    story.append(Spacer(1, 12))

    # Items table
    table_data = [["Qty", "Item", "Price"]]
    for item in receipt.items:
        if isinstance(item, dict):
            name = item.get("name", "")
            qty = item.get("quantity", 1)
            price = item.get("price", 0)
        else:
            name = item.name
            qty = item.quantity
            price = item.price
        table_data.append([str(qty), name, f"${price * qty:.2f}"])

    if len(table_data) > 1:
        table = Table(table_data, colWidths=[0.5 * inch, 4 * inch, 1.2 * inch])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.grey),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (2, 0), (2, -1), "RIGHT"),
        ]))
        story.append(table)
        story.append(Spacer(1, 12))

    # Totals
    totals = [
        f"Subtotal: ${receipt.subtotal:.2f}",
        f"Tax: ${receipt.tax:.2f}",
        f"Delivery: ${receipt.delivery_fee:.2f}",
    ]
    if receipt.tip > 0:
        totals.append(f"Tip/Service: ${receipt.tip:.2f}")
    totals.append(f"<b>Total: ${receipt.total:.2f}</b>")

    for line in totals:
        story.append(Paragraph(line, styles["Normal"]))

    story.append(Spacer(1, 12))
    story.append(Paragraph(f"Payment: {receipt.payment_method}", styles["Normal"]))
    story.append(Paragraph(f"Attendees: {receipt.attendee_count} | Per person: ${receipt.per_person_cost:.2f}", styles["Normal"]))

    doc.build(story)
    return buffer.getvalue()
