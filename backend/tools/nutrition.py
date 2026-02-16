"""USDA FoodData Central API tools for nutrition information."""

import os
from typing import Optional, Annotated
import httpx
from langchain_core.tools import tool

FOODDATA_API_BASE = "https://api.nal.usda.gov/fdc/v1"


def _get_api_key() -> str:
    """Get USDA FoodData API key."""
    api_key = os.getenv("USDA_API_KEY")
    if not api_key:
        raise ValueError("USDA_API_KEY not set")
    return api_key


@tool
async def search_foods(
    query: str,
    data_type: Optional[str] = None,
    page_size: int = 10,
) -> dict:
    """
    Search for foods in the USDA FoodData Central database.

    Args:
        query: Search terms (e.g., "chicken breast", "apple", "cheddar cheese")
        data_type: Filter by data type - "Branded", "Foundation", "SR Legacy", "Survey (FNDDS)"
        page_size: Number of results to return (max 50)

    Returns:
        List of foods with FDC ID, name, and brand info
    """
    payload = {
        "query": query,
        "pageSize": min(page_size, 50),
    }

    if data_type:
        payload["dataType"] = [data_type]

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{FOODDATA_API_BASE}/foods/search",
            params={"api_key": _get_api_key()},
            json=payload,
            timeout=30.0
        )
        response.raise_for_status()
        data = response.json()

    foods = []
    for food in data.get("foods", []):
        food_item = {
            "fdc_id": food.get("fdcId"),
            "description": food.get("description"),
            "data_type": food.get("dataType"),
            "brand_owner": food.get("brandOwner"),
            "brand_name": food.get("brandName"),
            "ingredients": food.get("ingredients", "")[:200] if food.get("ingredients") else None,
        }

        # Extract key nutrients if available
        nutrients = {}
        for nutrient in food.get("foodNutrients", []):
            name = nutrient.get("nutrientName", "")
            value = nutrient.get("value")
            unit = nutrient.get("unitName", "")

            if name in ["Energy", "Protein", "Total lipid (fat)", "Carbohydrate, by difference", "Fiber, total dietary", "Sugars, total including NLEA", "Sodium, Na"]:
                key = name.replace(", by difference", "").replace(", total dietary", "").replace(", total including NLEA", "").replace(", Na", "")
                nutrients[key] = f"{value} {unit}" if value else None

        if nutrients:
            food_item["nutrients_preview"] = nutrients

        foods.append(food_item)

    return {
        "total_hits": data.get("totalHits", 0),
        "foods": foods,
    }


@tool
async def get_food_nutrition(fdc_id: int) -> dict:
    """
    Get detailed nutrition information for a specific food.

    Args:
        fdc_id: The FoodData Central ID (from search results)

    Returns:
        Complete nutrition facts including all vitamins and minerals
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{FOODDATA_API_BASE}/food/{fdc_id}",
            params={"api_key": _get_api_key()},
            timeout=30.0
        )
        response.raise_for_status()
        data = response.json()

    # Parse nutrients into categories
    macros = {}
    vitamins = {}
    minerals = {}
    other = {}

    macro_names = ["Energy", "Protein", "Total lipid (fat)", "Carbohydrate, by difference",
                   "Fiber, total dietary", "Sugars, total including NLEA", "Total Sugars"]
    vitamin_names = ["Vitamin A", "Vitamin C", "Vitamin D", "Vitamin E", "Vitamin K",
                     "Thiamin", "Riboflavin", "Niacin", "Vitamin B-6", "Folate", "Vitamin B-12"]
    mineral_names = ["Calcium", "Iron", "Magnesium", "Phosphorus", "Potassium",
                     "Sodium", "Zinc", "Copper", "Selenium"]

    for nutrient in data.get("foodNutrients", []):
        name = nutrient.get("nutrient", {}).get("name", "")
        value = nutrient.get("amount")
        unit = nutrient.get("nutrient", {}).get("unitName", "")

        if value is None:
            continue

        formatted = f"{value:.2f} {unit}" if isinstance(value, float) else f"{value} {unit}"

        if any(m in name for m in macro_names):
            macros[name] = formatted
        elif any(v in name for v in vitamin_names):
            vitamins[name] = formatted
        elif any(m in name for m in mineral_names):
            minerals[name] = formatted
        else:
            other[name] = formatted

    # Get serving size info
    serving_size = None
    serving_unit = None
    if data.get("servingSize"):
        serving_size = data.get("servingSize")
        serving_unit = data.get("servingSizeUnit")

    return {
        "fdc_id": fdc_id,
        "description": data.get("description"),
        "brand_owner": data.get("brandOwner"),
        "brand_name": data.get("brandName"),
        "serving_size": f"{serving_size} {serving_unit}" if serving_size else "100g (standard)",
        "ingredients": data.get("ingredients"),
        "macronutrients": macros,
        "vitamins": vitamins,
        "minerals": minerals,
        "data_type": data.get("dataType"),
    }


@tool
async def compare_food_nutrition(fdc_ids: list[int]) -> dict:
    """
    Compare nutrition information across multiple foods.

    Args:
        fdc_ids: List of FoodData Central IDs to compare (max 5)

    Returns:
        Side-by-side comparison of key nutrients
    """
    fdc_ids = fdc_ids[:5]  # Limit to 5 foods

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{FOODDATA_API_BASE}/foods",
            params={"api_key": _get_api_key()},
            json={"fdcIds": fdc_ids},
            timeout=30.0
        )
        response.raise_for_status()
        foods = response.json()

    # Key nutrients to compare
    key_nutrients = [
        "Energy", "Protein", "Total lipid (fat)", "Carbohydrate, by difference",
        "Fiber, total dietary", "Sodium, Na", "Sugars, total including NLEA"
    ]

    comparison = []
    for food in foods:
        food_data = {
            "fdc_id": food.get("fdcId"),
            "description": food.get("description"),
            "brand": food.get("brandOwner") or food.get("brandName"),
        }

        nutrients = {}
        for nutrient in food.get("foodNutrients", []):
            name = nutrient.get("nutrient", {}).get("name", "")
            if name in key_nutrients:
                value = nutrient.get("amount")
                unit = nutrient.get("nutrient", {}).get("unitName", "")
                nutrients[name] = f"{value:.1f} {unit}" if value else "N/A"

        food_data["nutrients"] = nutrients
        comparison.append(food_data)

    return {
        "foods_compared": len(comparison),
        "comparison": comparison,
    }


@tool
async def get_food_list(
    data_type: str = "Foundation",
    page_size: int = 20,
) -> dict:
    """
    Get a list of foods from FoodData Central.

    Args:
        data_type: Type of food data - "Branded", "Foundation", "SR Legacy", "Survey (FNDDS)"
        page_size: Number of results (max 200)

    Returns:
        List of foods with basic info
    """
    payload = {
        "dataType": [data_type],
        "pageSize": min(page_size, 200),
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{FOODDATA_API_BASE}/foods/list",
            params={"api_key": _get_api_key()},
            json=payload,
            timeout=30.0
        )
        response.raise_for_status()
        foods = response.json()

    return {
        "data_type": data_type,
        "count": len(foods),
        "foods": [
            {
                "fdc_id": f.get("fdcId"),
                "description": f.get("description"),
                "food_category": f.get("foodCategory"),
            }
            for f in foods
        ],
    }


@tool
async def calculate_meal_nutrition(
    meal_items_json: str,
) -> dict:
    """
    Calculate total nutrition for a meal from multiple food items.

    Args:
        meal_items_json: JSON string containing array of objects with fdc_id and servings.
                        Example: '[{"fdc_id": 123, "servings": 1.5}, {"fdc_id": 456, "servings": 2}]'

    Returns:
        Total nutrition values for the meal
    """
    import json

    try:
        meal_items_input = json.loads(meal_items_json)
    except json.JSONDecodeError:
        return {"error": "Invalid JSON format. Expected array of {fdc_id, servings} objects."}

    fdc_ids = [item.get("fdc_id") for item in meal_items_input]
    servings_map = {item.get("fdc_id"): item.get("servings", 1) for item in meal_items_input}

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{FOODDATA_API_BASE}/foods",
            params={"api_key": _get_api_key()},
            json={"fdcIds": fdc_ids},
            timeout=30.0
        )
        response.raise_for_status()
        food_data = response.json()

    # Sum up nutrients
    totals = {
        "Energy": 0,
        "Protein": 0,
        "Total lipid (fat)": 0,
        "Carbohydrate, by difference": 0,
        "Fiber, total dietary": 0,
        "Sodium, Na": 0,
        "Sugars, total including NLEA": 0,
    }

    meal_items = []
    for food in food_data:
        fdc_id = food.get("fdcId")
        servings = servings_map.get(fdc_id, 1)

        item = {
            "description": food.get("description"),
            "servings": servings,
        }

        for nutrient in food.get("foodNutrients", []):
            name = nutrient.get("nutrient", {}).get("name", "")
            value = nutrient.get("amount")

            if name in totals and value:
                totals[name] += value * servings

        meal_items.append(item)

    # Format totals
    formatted_totals = {
        "Calories": f"{totals['Energy']:.0f} kcal",
        "Protein": f"{totals['Protein']:.1f} g",
        "Fat": f"{totals['Total lipid (fat)']:.1f} g",
        "Carbohydrates": f"{totals['Carbohydrate, by difference']:.1f} g",
        "Fiber": f"{totals['Fiber, total dietary']:.1f} g",
        "Sugar": f"{totals['Sugars, total including NLEA']:.1f} g",
        "Sodium": f"{totals['Sodium, Na']:.0f} mg",
    }

    return {
        "meal_items": meal_items,
        "total_nutrition": formatted_totals,
    }


# Export all tools
nutrition_tools = [
    search_foods,
    get_food_nutrition,
    compare_food_nutrition,
    get_food_list,
    calculate_meal_nutrition,
]
