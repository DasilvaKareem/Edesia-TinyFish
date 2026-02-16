"""TinyFish-powered web automation tools for scraping and form filling."""

import os
import httpx
from langchain_core.tools import tool
from typing import Optional

TINYFISH_API_URL = "https://agent.tinyfish.ai/v1/automation/run"

# Platform credentials: name → (email_env_var, password_env_var, login_url)
PLATFORM_CREDENTIALS = {
    "partyslate": ("PARTYSLATE_EMAIL", "PARTYSLATE_PASSWORD", "https://www.partyslate.com/login"),
    "doordash": ("DOORDASH_EMAIL", "DOORDASH_PASSWORD", "https://www.doordash.com/consumer/login/"),
    "ubereats": ("UBEREATS_EMAIL", "UBEREATS_PASSWORD", "https://auth.uber.com/v2/"),
    "grubhub": ("GRUBHUB_EMAIL", "GRUBHUB_PASSWORD", "https://www.grubhub.com/login"),
}


def _get_platform_credentials(platform: str) -> tuple[str, str, str]:
    """Look up credentials for a known platform.

    Returns (email, password, login_url) or raises ValueError.
    """
    platform = platform.lower().strip()
    if platform not in PLATFORM_CREDENTIALS:
        raise ValueError(f"Unknown platform '{platform}'. Known: {', '.join(PLATFORM_CREDENTIALS)}")
    email_var, pass_var, login_url = PLATFORM_CREDENTIALS[platform]
    email = os.getenv(email_var)
    password = os.getenv(pass_var)
    if not email or not password:
        raise ValueError(f"Credentials not configured for {platform}")
    return email, password, login_url


async def _run_tinyfish(url: str, goal: str, stealth: bool = False) -> dict:
    """Run a TinyFish web automation and return the result."""
    payload = {
        "url": url,
        "goal": goal,
        "browser_profile": "stealth" if stealth else "lite",
    }
    headers = {
        "X-API-Key": os.getenv("TINYFISH_API_KEY"),
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=180) as client:
        resp = await client.post(TINYFISH_API_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()

    if data.get("status") == "COMPLETED":
        return data.get("result") or {}
    else:
        error_msg = (data.get("error") or {}).get("message", "Unknown error")
        return {"error": error_msg}


@tool
async def scrape_contact_info(url: str) -> dict:
    """
    Scrape contact information (emails, phone numbers, address) from a website.

    Args:
        url: The website URL to scrape

    Returns:
        Dictionary with found contact information
    """
    goal = (
        "Extract all contact information from this page. "
        "Also check for a /contact page link and extract info from there too. "
        "Return JSON with: emails (array of strings), phone_numbers (array of strings), "
        "address (string or null), contact_page (URL string or null)."
    )
    result = await _run_tinyfish(url, goal)

    if "error" in result:
        return {"url": url, "error": result["error"]}

    return {
        "url": url,
        "emails": result.get("emails", [])[:5],
        "phone_numbers": result.get("phone_numbers", [])[:5],
        "address": result.get("address"),
        "contact_page": result.get("contact_page"),
    }


@tool
async def scrape_menu(url: str) -> dict:
    """
    Scrape menu items and prices from a restaurant website or delivery platform.

    Args:
        url: The restaurant website URL, or DoorDash/UberEats/Grubhub URL

    Returns:
        Dictionary with menu items grouped by category
    """
    goal = (
        "Extract the full restaurant menu from this page. "
        "If there is a menu link/tab, navigate to it first. "
        "Return JSON with: restaurant_name (string), menu_categories (object where keys are "
        "category names and values are arrays of items). Each item should have: "
        "name (string), price (string like '$12.99'), description (string, max 150 chars). "
        "Include up to 50 items total."
    )
    result = await _run_tinyfish(url, goal, stealth=True)

    if "error" in result:
        return {"url": url, "error": result["error"]}

    categories = result.get("menu_categories", {})
    total_items = sum(len(items) for items in categories.values())

    return {
        "url": url,
        "restaurant_name": result.get("restaurant_name", ""),
        "menu_categories": categories,
        "total_items": total_items,
    }


@tool
async def fill_form(
    url: str,
    form_data: dict,
    submit: bool = True,
) -> dict:
    """
    Intelligently fill out any web form (contact, inquiry, order, registration, etc.)

    Args:
        url: The form page URL
        form_data: Dictionary of field names/types to values. Examples:
            - {"name": "John Doe", "email": "john@acme.com", "phone": "555-1234"}
            - {"first_name": "John", "last_name": "Doe", "company": "Acme Inc"}
            - {"message": "I'd like to inquire about catering for 50 people"}
            - {"date": "2024-03-15", "guests": "25", "event_type": "Corporate Lunch"}
        submit: Whether to click the submit button (default True)

    Returns:
        Result with filled fields and submission status
    """
    # Build natural language instructions from form_data
    field_instructions = "\n".join(
        f"- {key}: {value}" for key, value in form_data.items()
    )
    submit_instruction = (
        "After filling all fields, click the submit/send button and wait for confirmation."
        if submit
        else "Do NOT click submit after filling the fields."
    )

    goal = (
        f"Fill out the form on this page with the following values:\n"
        f"{field_instructions}\n\n"
        f"{submit_instruction}\n\n"
        f"Return JSON with: filled_fields (array of field names successfully filled), "
        f"failed_fields (array of field names that could not be found), "
        f"submitted (boolean), submission_result ('success', 'error', or 'submitted')."
    )

    result = await _run_tinyfish(url, goal)

    if "error" in result:
        return {"url": url, "error": result["error"]}

    filled = result.get("filled_fields", list(form_data.keys()))
    failed = result.get("failed_fields", [])
    submitted = result.get("submitted", submit)
    submission_result = result.get("submission_result", "submitted" if submit else None)

    return {
        "url": url,
        "filled_fields": filled,
        "failed_fields": failed,
        "submitted": submitted,
        "submission_result": submission_result,
        "fields_attempted": len(form_data),
        "fields_filled": len(filled),
        "message": _get_form_result_message(filled, failed, submitted, submission_result),
    }


def _get_form_result_message(filled: list, failed: list, submitted: bool, result: str) -> str:
    """Generate a human-readable result message."""
    if not filled:
        return "Could not fill any form fields."

    msg = f"Filled {len(filled)} field(s): {', '.join(filled)}."

    if failed:
        msg += f" Could not find: {', '.join(failed)}."

    if submitted:
        if result == "success":
            msg += " Form submitted successfully!"
        elif result == "error":
            msg += " Form submitted but may have errors - check confirmation."
        else:
            msg += " Form submitted - verify confirmation."
    else:
        msg += " Form was NOT submitted (submit=False or no submit button found)."

    return msg


@tool
async def browse_and_extract(
    url: str,
    extract_type: str = "all",
) -> dict:
    """
    Browse a URL and extract relevant information.

    Args:
        url: The URL to browse
        extract_type: What to extract - "contact", "menu", "hours", or "all"

    Returns:
        Extracted information from the page
    """
    extract_parts = []
    if extract_type in ("contact", "all"):
        extract_parts.append("emails (array), phone numbers (array)")
    if extract_type in ("hours", "all"):
        extract_parts.append("business hours/schedule (string)")
    if extract_type in ("menu", "all"):
        extract_parts.append("whether a menu page exists (has_menu_page boolean, menu_url string)")

    goal = (
        f"Extract the following from this page: {', '.join(extract_parts)}. "
        f"Also get the page title and meta description. "
        f"Return as JSON."
    )
    result = await _run_tinyfish(url, goal)

    if "error" in result:
        return {"url": url, "error": result["error"]}

    result["url"] = url
    return result


@tool
async def authenticated_browse(
    url: str,
    goal: str,
    platform: Optional[str] = None,
    email: Optional[str] = None,
    password: Optional[str] = None,
) -> dict:
    """
    Browse a website that requires login. Logs in first, then performs the goal.

    Use the platform parameter for known platforms (partyslate, doordash, ubereats, grubhub).
    For other sites, pass email and password directly.

    Args:
        url: The target URL to navigate to after login
        goal: What to do on the site after logging in
        platform: Known platform name (uses stored credentials)
        email: Login email (only if platform is not provided)
        password: Login password (only if platform is not provided)

    Returns:
        Dictionary with login_success, action_result, and any extracted data
    """
    try:
        if platform:
            cred_email, cred_password, login_url = _get_platform_credentials(platform)
        elif email and password:
            cred_email, cred_password = email, password
            login_url = url
        else:
            return {"url": url, "error": "Provide either a platform name or email+password"}

        combined_goal = (
            f"STEP 1: Go to the login page. Log in with email '{cred_email}' and password '{cred_password}'. "
            f"Wait until login is complete and you are on the logged-in dashboard or homepage.\n\n"
            f"STEP 2: Navigate to {url} and perform the following task: {goal}\n\n"
            f"Return JSON with: login_success (boolean), action_result (the extracted data or action outcome)."
        )

        result = await _run_tinyfish(login_url, combined_goal, stealth=True)

        if "error" in result:
            return {
                "url": url,
                "platform": platform,
                "login_success": False,
                "action_result": None,
                "error": result["error"],
            }

        return {
            "url": url,
            "platform": platform,
            "login_success": result.get("login_success", True),
            "action_result": result.get("action_result", result),
        }

    except ValueError as e:
        return {"url": url, "platform": platform, "login_success": False, "action_result": None, "error": str(e)}
    except Exception as e:
        return {"url": url, "platform": platform, "login_success": False, "action_result": None, "error": str(e)}


browser_tools = [
    scrape_contact_info,
    scrape_menu,
    fill_form,
    browse_and_extract,
    authenticated_browse,
]
