"""Instacart Connect API tools for grocery shopping and recipe ingredients."""

import os
from typing import Optional
import httpx
from langchain_core.tools import tool

INSTACART_API_BASE = "https://connect.instacart.com"


def _get_headers() -> dict:
    """Get Instacart API headers with Bearer token auth."""
    api_key = os.getenv("INSTACART_API_KEY")
    if not api_key:
        raise ValueError("INSTACART_API_KEY not set")
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


@tool
async def instacart_create_recipe_page(
    title: str,
    ingredients: list[dict],
    servings: Optional[int] = None,
    cooking_time: Optional[str] = None,
    instructions: Optional[list[str]] = None,
    image_url: Optional[str] = None,
) -> dict:
    """
    Create a shoppable recipe page on Instacart. Users click the link to add all ingredients to their cart.

    Args:
        title: Recipe name (e.g., "Chicken Parmesan")
        ingredients: List of ingredient dicts, each with "name", "quantity" (float), and "unit" (string).
                     Example: [{"name": "chicken breast", "quantity": 2.0, "unit": "pound"}]
        servings: Number of servings the recipe makes
        cooking_time: Cooking time description (e.g., "45 minutes")
        instructions: List of step-by-step cooking instructions
        image_url: URL of an image for the recipe page

    Returns:
        Dict with recipe_url link to the Instacart recipe page
    """
    line_items = []
    for ing in ingredients:
        item = {"name": ing["name"]}
        if ing.get("quantity") or ing.get("unit"):
            measurement = {}
            if ing.get("quantity"):
                measurement["quantity"] = float(ing["quantity"])
            if ing.get("unit"):
                measurement["unit"] = ing["unit"]
            item["measurements"] = [measurement]
        line_items.append(item)

    recipe_data = {
        "title": title,
        "line_items": line_items,
    }

    if servings:
        recipe_data["servings"] = servings
    if cooking_time:
        recipe_data["cooking_time"] = cooking_time
    if instructions:
        recipe_data["instructions"] = instructions
    if image_url:
        recipe_data["image_url"] = image_url

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{INSTACART_API_BASE}/idp/v1/products/recipe",
            headers=_get_headers(),
            json=recipe_data,
            timeout=30.0,
        )

        if response.status_code not in [200, 201]:
            return {
                "error": f"Instacart API error: {response.status_code}",
                "details": response.text,
            }

        data = response.json()

    return {
        "recipe_url": data.get("products_link_url") or data.get("url"),
        "title": title,
        "ingredient_count": len(line_items),
    }


@tool
async def instacart_create_shopping_list(
    title: str,
    items: list[dict],
) -> dict:
    """
    Create a grocery shopping list on Instacart. Users click the link to shop all items.

    Args:
        title: Shopping list name (e.g., "Weekly Groceries", "Office Snacks")
        items: List of item dicts, each with "name", optional "quantity" (int/float), optional "unit" (string).
               Example: [{"name": "Organic Milk", "quantity": 1, "unit": "gallon"}]

    Returns:
        Dict with shopping_list_url link to the Instacart shopping list
    """
    line_items = []
    for item in items:
        li = {"name": item["name"]}
        if item.get("quantity") or item.get("unit"):
            measurement = {}
            if item.get("quantity"):
                measurement["quantity"] = float(item["quantity"])
            if item.get("unit"):
                measurement["unit"] = item["unit"]
            li["measurements"] = [measurement]
        if item.get("filters"):
            li["filters"] = item["filters"]
        line_items.append(li)

    payload = {
        "title": title,
        "line_items": line_items,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{INSTACART_API_BASE}/idp/v1/products/products_link",
            headers=_get_headers(),
            json=payload,
            timeout=30.0,
        )

        if response.status_code not in [200, 201]:
            return {
                "error": f"Instacart API error: {response.status_code}",
                "details": response.text,
            }

        data = response.json()

    return {
        "shopping_list_url": data.get("products_link_url") or data.get("url"),
        "title": title,
        "item_count": len(line_items),
    }


@tool
async def instacart_get_nearby_retailers(
    postal_code: str,
    country_code: Optional[str] = "US",
) -> dict:
    """
    Find grocery stores available on Instacart near a postal code.

    Args:
        postal_code: ZIP/postal code to search near (e.g., "94105")
        country_code: Country code, defaults to "US"

    Returns:
        List of nearby retailers with names, keys, and logos
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{INSTACART_API_BASE}/idp/v1/retailers",
            headers=_get_headers(),
            params={"postal_code": postal_code, "country_code": country_code},
            timeout=30.0,
        )

        if response.status_code != 200:
            return {
                "error": f"Instacart API error: {response.status_code}",
                "details": response.text,
            }

        data = response.json()

    retailers = []
    for r in data.get("retailers", []):
        retailers.append({
            "retailer_key": r.get("retailer_key"),
            "name": r.get("name"),
            "logo_url": r.get("logo_url"),
        })

    return {
        "postal_code": postal_code,
        "retailer_count": len(retailers),
        "retailers": retailers,
    }


@tool
async def instacart_search_products(
    query: str,
    postal_code: Optional[str] = None,
) -> dict:
    """
    Quick product search on Instacart. Creates a shoppable link for the product.

    Args:
        query: Product to search for (e.g., "organic eggs", "almond milk")
        postal_code: Optional ZIP code for local availability

    Returns:
        Dict with shopping link for the product
    """
    line_items = [{"name": query}]

    payload = {
        "title": f"Search: {query}",
        "line_items": line_items,
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{INSTACART_API_BASE}/idp/v1/products/products_link",
            headers=_get_headers(),
            json=payload,
            timeout=30.0,
        )

        if response.status_code not in [200, 201]:
            return {
                "error": f"Instacart API error: {response.status_code}",
                "details": response.text,
            }

        data = response.json()

    return {
        "product_url": data.get("products_link_url") or data.get("url"),
        "query": query,
    }


# Export all tools
instacart_tools = [
    instacart_create_recipe_page,
    instacart_create_shopping_list,
    instacart_get_nearby_retailers,
    instacart_search_products,
]
