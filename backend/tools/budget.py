"""Budget calculation and comparison tools."""

from typing import Optional
from langchain_core.tools import tool


@tool
def calculate_per_person(
    total_budget: float,
    headcount: int,
    tip_percent: float = 18.0,
    tax_percent: float = 8.0,
) -> dict:
    """
    Calculate per-person budget after accounting for tip and tax.

    Args:
        total_budget: Total budget available
        headcount: Number of people
        tip_percent: Tip percentage (default 18%)
        tax_percent: Tax percentage (default 8%)

    Returns:
        Budget breakdown with per-person spending
    """
    # Work backwards: total_budget = (food_cost * (1 + tax)) * (1 + tip)
    # So food_cost = total_budget / ((1 + tax/100) * (1 + tip/100))
    multiplier = (1 + tax_percent / 100) * (1 + tip_percent / 100)
    food_budget = total_budget / multiplier

    per_person_food = food_budget / headcount
    per_person_total = total_budget / headcount

    return {
        "total_budget": total_budget,
        "headcount": headcount,
        "breakdown": {
            "food_budget": round(food_budget, 2),
            "estimated_tax": round(food_budget * tax_percent / 100, 2),
            "estimated_tip": round((food_budget * (1 + tax_percent / 100)) * tip_percent / 100, 2),
        },
        "per_person": {
            "food_allowance": round(per_person_food, 2),
            "total_cost": round(per_person_total, 2),
        },
        "recommendation": _get_price_recommendation(per_person_food),
    }


def _get_price_recommendation(per_person: float) -> str:
    """Get dining recommendation based on per-person budget."""
    if per_person < 10:
        return "Budget dining: fast casual, pizza, sandwiches"
    elif per_person < 20:
        return "Casual dining: mid-range restaurants, catering boxes"
    elif per_person < 35:
        return "Upscale casual: quality restaurants, buffet catering"
    elif per_person < 50:
        return "Fine casual: steakhouses, premium catering"
    else:
        return "Fine dining: upscale restaurants, premium full-service catering"


@tool
def compare_options(options: list[dict]) -> dict:
    """
    Compare multiple catering or dining options side-by-side.

    Args:
        options: List of options to compare, each with:
            - name: Option name
            - price_per_person: Cost per person
            - rating: Rating (optional)
            - features: List of features (optional)

    Returns:
        Comparison table with recommendation
    """
    if not options:
        return {"error": "No options provided to compare"}

    # Sort by value (rating / price ratio if available)
    for opt in options:
        if opt.get("rating") and opt.get("price_per_person"):
            opt["value_score"] = round(opt["rating"] / opt["price_per_person"] * 10, 2)
        else:
            opt["value_score"] = None

    # Find cheapest, highest rated, best value
    cheapest = min(options, key=lambda x: x.get("price_per_person", float("inf")))
    has_ratings = [o for o in options if o.get("rating")]
    highest_rated = max(has_ratings, key=lambda x: x["rating"]) if has_ratings else None
    has_value = [o for o in options if o.get("value_score")]
    best_value = max(has_value, key=lambda x: x["value_score"]) if has_value else None

    comparison = {
        "options_count": len(options),
        "options": [
            {
                "name": opt["name"],
                "price_per_person": opt.get("price_per_person"),
                "rating": opt.get("rating"),
                "features": opt.get("features", []),
                "value_score": opt.get("value_score"),
                "badges": [],
            }
            for opt in options
        ],
        "analysis": {
            "cheapest": cheapest["name"],
            "cheapest_price": cheapest.get("price_per_person"),
        },
    }

    # Add badges
    for opt in comparison["options"]:
        if opt["name"] == cheapest["name"]:
            opt["badges"].append("Most Affordable")
        if highest_rated and opt["name"] == highest_rated["name"]:
            opt["badges"].append("Highest Rated")
            comparison["analysis"]["highest_rated"] = opt["name"]
        if best_value and opt["name"] == best_value["name"]:
            opt["badges"].append("Best Value")
            comparison["analysis"]["best_value"] = opt["name"]

    # Generate recommendation
    if best_value:
        comparison["recommendation"] = f"Best overall value: {best_value['name']} (${best_value['price_per_person']}/person, {best_value['rating']} rating)"
    elif highest_rated:
        comparison["recommendation"] = f"Highest rated: {highest_rated['name']} ({highest_rated['rating']} stars)"
    else:
        comparison["recommendation"] = f"Most affordable: {cheapest['name']} (${cheapest.get('price_per_person')}/person)"

    return comparison


@tool
def generate_expense_report(
    expenses: list[dict],
    event_name: Optional[str] = None,
) -> dict:
    """
    Generate an expense report for an event.

    Args:
        expenses: List of expenses, each with:
            - description: What was purchased
            - amount: Cost
            - category: Category (food, beverage, service, etc.)
            - vendor: Vendor name (optional)
        event_name: Name of the event (optional)

    Returns:
        Expense report with totals by category
    """
    if not expenses:
        return {"error": "No expenses provided"}

    # Calculate totals by category
    by_category: dict[str, float] = {}
    for exp in expenses:
        cat = exp.get("category", "Other")
        by_category[cat] = by_category.get(cat, 0) + exp.get("amount", 0)

    total = sum(exp.get("amount", 0) for exp in expenses)

    report = {
        "event_name": event_name or "Untitled Event",
        "total_expenses": round(total, 2),
        "expense_count": len(expenses),
        "by_category": {
            cat: {
                "amount": round(amt, 2),
                "percentage": round(amt / total * 100, 1) if total > 0 else 0,
            }
            for cat, amt in sorted(by_category.items(), key=lambda x: x[1], reverse=True)
        },
        "line_items": [
            {
                "description": exp.get("description"),
                "amount": exp.get("amount"),
                "category": exp.get("category", "Other"),
                "vendor": exp.get("vendor"),
            }
            for exp in expenses
        ],
        "summary": f"Total: ${total:.2f} across {len(expenses)} items in {len(by_category)} categories",
    }

    # Add insights
    largest_category = max(by_category.items(), key=lambda x: x[1])
    report["insights"] = [
        f"Largest expense category: {largest_category[0]} (${largest_category[1]:.2f}, {round(largest_category[1]/total*100, 1)}%)",
    ]

    if total > 1000:
        report["insights"].append("Consider negotiating bulk discounts for future large orders")

    return report


budget_tools = [calculate_per_person, compare_options, generate_expense_report]
