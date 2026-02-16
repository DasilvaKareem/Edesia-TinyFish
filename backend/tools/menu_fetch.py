"""Composite menu fetching tool with automatic fallback across multiple sources."""

import asyncio
from typing import Optional
from langchain_core.tools import tool

from .yelp_search import yelp_search_restaurants, get_business_details
from .google_places import search_places, get_place_details
from .browser import scrape_menu
from .unsplash import get_restaurant_photos, get_food_item_photo


def _best_yelp_match(yelp_result, restaurant_name: str) -> Optional[dict]:
    """Find the best matching business from Yelp search results."""
    if isinstance(yelp_result, Exception) or not isinstance(yelp_result, dict):
        return None
    businesses = yelp_result.get("businesses", [])
    if not businesses:
        return None
    name_lower = restaurant_name.lower()
    # Prefer exact-ish match
    for biz in businesses:
        if name_lower in biz.get("name", "").lower() or biz.get("name", "").lower() in name_lower:
            return biz
    return businesses[0]


def _best_google_match(google_result, restaurant_name: str) -> Optional[dict]:
    """Find the best matching place from Google Places results."""
    if isinstance(google_result, Exception) or not isinstance(google_result, dict):
        return None
    places = google_result.get("places", [])
    if not places:
        return None
    name_lower = restaurant_name.lower()
    for place in places:
        if name_lower in place.get("name", "").lower() or place.get("name", "").lower() in name_lower:
            return place
    return places[0]


@tool
async def fetch_restaurant_menu(restaurant_name: str, location: str) -> dict:
    """Fetch restaurant info and menu with automatic fallback across Yelp, Google, and website scraping.

    This is the BEST tool for getting a restaurant's menu. It automatically tries multiple
    sources and returns the richest data available. Always returns restaurant info (address,
    phone, hours) even if the full menu isn't available.

    Args:
        restaurant_name: Name of the restaurant (e.g., "Central BBQ", "Hopdoddy Burger Bar")
        location: City or address (e.g., "Memphis, TN", "Nashville, TN")

    Returns:
        Restaurant info + menu items with prices from the best available source.
    """
    result = {
        "found": False,
        "restaurant_name": restaurant_name,
        "address": "",
        "phone": "",
        "website": "",
        "hours": [],
        "rating": None,
        "price_level": "",
        "image_url": "",
        "photos": [],
        "menu_source": "none",
        "menu_categories": {},
        "total_items": 0,
        "delivery_available": False,
        "yelp_url": "",
        "google_maps_url": "",
        "categories": [],
        "editorial_summary": "",
        "service_options": {},
        "serves": {},
    }

    # ---- Step 1: Yelp + Google in parallel for restaurant info ----
    print(f"[MENU_FETCH] Searching Yelp + Google for '{restaurant_name}' in '{location}'")

    yelp_search_result, google_search_result = await asyncio.gather(
        yelp_search_restaurants.ainvoke({
            "location": location,
            "term": restaurant_name,
            "limit": 3,
        }),
        search_places.ainvoke({
            "query": f"{restaurant_name} {location}",
        }),
        return_exceptions=True,
    )

    yelp_biz = _best_yelp_match(yelp_search_result, restaurant_name)
    google_place = _best_google_match(google_search_result, restaurant_name)

    website_url = None
    yelp_url = None
    yelp_id = None
    google_place_id = None

    # Enrich from Yelp match
    if yelp_biz:
        result["found"] = True
        result["restaurant_name"] = yelp_biz.get("name", restaurant_name)
        result["address"] = result["address"] or yelp_biz.get("address", "")
        result["phone"] = result["phone"] or yelp_biz.get("phone", "")
        result["rating"] = yelp_biz.get("rating")
        result["price_level"] = yelp_biz.get("price", "")
        result["categories"] = yelp_biz.get("categories", [])
        result["delivery_available"] = "delivery" in yelp_biz.get("transactions", [])
        if yelp_biz.get("image_url"):
            result["image_url"] = yelp_biz["image_url"]
        yelp_url = yelp_biz.get("url", "")
        yelp_id = yelp_biz.get("id")
        result["yelp_url"] = yelp_url
        print(f"[MENU_FETCH] Yelp match: {yelp_biz.get('name')} (id={yelp_id})")

    # Enrich from Google match
    if google_place:
        result["found"] = True
        result["restaurant_name"] = result["restaurant_name"] or google_place.get("name", restaurant_name)
        result["address"] = result["address"] or google_place.get("address", "")
        result["rating"] = result["rating"] or google_place.get("rating")
        result["price_level"] = result["price_level"] or google_place.get("price_level", "")
        google_place_id = google_place.get("place_id")
        print(f"[MENU_FETCH] Google match: {google_place.get('name')} (place_id={google_place_id})")

    # Get detailed info from both (phone, hours, website) in parallel
    detail_tasks = []
    if yelp_id:
        detail_tasks.append(("yelp", get_business_details.ainvoke({"business_id": yelp_id})))
    if google_place_id:
        detail_tasks.append(("google", get_place_details.ainvoke({"place_id": google_place_id})))

    if detail_tasks:
        detail_results = await asyncio.gather(
            *[t[1] for t in detail_tasks],
            return_exceptions=True,
        )
        for (source, _), detail in zip(detail_tasks, detail_results):
            if isinstance(detail, Exception) or not isinstance(detail, dict):
                continue
            if source == "yelp":
                result["phone"] = result["phone"] or detail.get("display_phone") or detail.get("phone", "")
                result["hours"] = result["hours"] or detail.get("hours", [])
                yelp_url = detail.get("url", yelp_url)
                result["yelp_url"] = yelp_url or result["yelp_url"]
                result["delivery_available"] = result["delivery_available"] or "delivery" in detail.get("transactions", [])
                if detail.get("photos"):
                    result["photos"] = detail["photos"][:3]
            elif source == "google":
                result["phone"] = result["phone"] or detail.get("phone", "")
                result["website"] = detail.get("website", "")
                result["google_maps_url"] = detail.get("google_maps_url", "")
                result["hours"] = result["hours"] or detail.get("hours", [])
                website_url = detail.get("website")
                # Photos from Google Places
                google_photos = detail.get("photos", [])
                if google_photos:
                    if not result["image_url"]:
                        result["image_url"] = google_photos[0]
                    if not result["photos"]:
                        result["photos"] = google_photos[:3]
                # Delivery flag from Google
                svc = detail.get("service_options", {})
                if svc.get("delivery"):
                    result["delivery_available"] = True
                # Editorial summary, service options, serves
                result["editorial_summary"] = detail.get("editorial_summary", "")
                result["service_options"] = svc
                result["serves"] = detail.get("serves", {})

    # ---- Step 2: Fallback — scrape restaurant website ----
    if result["menu_source"] == "none" and website_url:
        print(f"[MENU_FETCH] Trying restaurant website: {website_url}")
        try:
            menu = await scrape_menu.ainvoke({"url": website_url})
            if isinstance(menu, dict) and menu.get("total_items", 0) > 0:
                result["menu_categories"] = menu["menu_categories"]
                result["menu_source"] = "website"
                result["total_items"] = menu["total_items"]
                result["found"] = True
                print(f"[MENU_FETCH] Website menu found: {menu['total_items']} items")
        except Exception as e:
            print(f"[MENU_FETCH] Website scrape failed: {e}")

    # ---- Step 3: Fallback — scrape Yelp page menu tab ----
    if result["menu_source"] == "none" and yelp_url:
        print(f"[MENU_FETCH] Trying Yelp page scrape: {yelp_url}")
        try:
            menu = await scrape_menu.ainvoke({"url": yelp_url})
            if isinstance(menu, dict) and menu.get("total_items", 0) > 0:
                result["menu_categories"] = menu["menu_categories"]
                result["menu_source"] = "yelp_scrape"
                result["total_items"] = menu["total_items"]
                result["found"] = True
                print(f"[MENU_FETCH] Yelp scrape menu found: {menu['total_items']} items")
        except Exception as e:
            print(f"[MENU_FETCH] Yelp scrape failed: {e}")

    # ---- Step 4: Unsplash fallback for missing images ----
    unsplash_tasks = []

    # Fallback for restaurant-level photos
    if not result["image_url"] and not result["photos"]:
        print(f"[MENU_FETCH] No restaurant photos — trying Unsplash fallback")
        unsplash_tasks.append(("restaurant", get_restaurant_photos(
            restaurant_name=result["restaurant_name"],
            cuisine_categories=result.get("categories"),
            count=3,
        )))

    # Fallback for menu item images (items that have no image_url)
    items_needing_photos = []
    for cat_name, items in result.get("menu_categories", {}).items():
        for item in items:
            if not item.get("image_url") and item.get("name"):
                items_needing_photos.append(item)

    # Cap at 6 Unsplash lookups to stay within rate limits
    for item in items_needing_photos[:6]:
        unsplash_tasks.append(("item", get_food_item_photo(item["name"]), item))

    if unsplash_tasks:
        # Build coroutine list (skip the extra metadata for gather)
        coros = []
        task_meta = []
        for entry in unsplash_tasks:
            if entry[0] == "restaurant":
                coros.append(entry[1])
                task_meta.append(("restaurant", None))
            else:
                coros.append(entry[1])
                task_meta.append(("item", entry[2]))

        unsplash_results = await asyncio.gather(*coros, return_exceptions=True)

        for (kind, item_ref), photo_result in zip(task_meta, unsplash_results):
            if isinstance(photo_result, Exception):
                continue
            if kind == "restaurant" and isinstance(photo_result, list) and photo_result:
                result["image_url"] = photo_result[0]
                result["photos"] = photo_result
                print(f"[MENU_FETCH] Unsplash provided {len(photo_result)} restaurant photos")
            elif kind == "item" and photo_result and item_ref is not None:
                item_ref["image_url"] = photo_result

        item_photos_filled = sum(
            1 for (kind, _), r in zip(task_meta, unsplash_results)
            if kind == "item" and r and not isinstance(r, Exception)
        )
        if item_photos_filled:
            print(f"[MENU_FETCH] Unsplash provided {item_photos_filled} menu item photos")

    # Summary log
    print(f"[MENU_FETCH] Done: found={result['found']}, source={result['menu_source']}, items={result['total_items']}, "
          f"phone={bool(result['phone'])}, address={bool(result['address'])}")

    return result


menu_fetch_tools = [fetch_restaurant_menu]
