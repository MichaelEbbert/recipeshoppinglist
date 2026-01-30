from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import aiosqlite
import httpx
from bs4 import BeautifulSoup
import json
import re
from typing import Optional
import random

from ..database import get_db

router = APIRouter(prefix="/discover", tags=["discover"])
templates = Jinja2Templates(directory="app/templates")

# Recipe sources that are relatively easy to parse
RECIPE_SOURCES = [
    {
        "name": "Tasty",
        "search_url": "https://tasty.co/search?q={query}",
        "base_url": "https://tasty.co",
    },
]

# Sample search terms for discovery
SEARCH_TERMS = [
    "chicken dinner", "pasta", "soup", "salad", "beef",
    "vegetarian", "quick meals", "casserole", "mexican",
    "italian", "asian", "breakfast", "dessert", "cookies",
    "cake", "seafood", "pork", "healthy", "comfort food",
]


@router.get("", response_class=HTMLResponse)
async def discover_home(request: Request):
    """Recipe discovery page."""
    return templates.TemplateResponse("discover/index.html", {
        "request": request,
        "recipes": [],
        "message": "Click 'Find Recipes' to discover new recipes!",
    })


@router.get("/search", response_class=HTMLResponse)
async def search_recipes(
    request: Request,
    q: str = "",
):
    """Search for recipes from external sources."""
    if not q:
        q = random.choice(SEARCH_TERMS)

    recipes = []
    error_message = None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Try to fetch from Tasty
            tasty_recipes = await fetch_tasty_recipes(client, q)
            recipes.extend(tasty_recipes)
    except Exception as e:
        error_message = f"Could not fetch recipes: {str(e)}"

    return templates.TemplateResponse("discover/partials/recipe_cards.html", {
        "request": request,
        "recipes": recipes,
        "search_term": q,
        "error_message": error_message,
    })


async def fetch_tasty_recipes(client: httpx.AsyncClient, query: str) -> list[dict]:
    """Fetch recipes from Tasty."""
    recipes = []

    try:
        # Tasty has a public API we can use
        api_url = "https://tasty.co/api/recipes/search"
        response = await client.get(
            api_url,
            params={"q": query, "size": 10},
            headers={"User-Agent": "Mozilla/5.0 (compatible; recipe-app)"},
        )

        if response.status_code == 200:
            data = response.json()
            for item in data.get("items", [])[:6]:
                recipes.append({
                    "title": item.get("name", ""),
                    "url": f"https://tasty.co{item.get('canonical_url', '')}",
                    "image": item.get("thumbnail_url", ""),
                    "description": item.get("description", "")[:150],
                    "source": "Tasty",
                })
    except Exception:
        # If API fails, try scraping
        try:
            search_url = f"https://tasty.co/search?q={query}"
            response = await client.get(
                search_url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; recipe-app)"},
                follow_redirects=True,
            )

            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                # Look for recipe cards
                cards = soup.select("a[href*='/recipe/']")[:6]
                for card in cards:
                    href = card.get("href", "")
                    if not href.startswith("http"):
                        href = f"https://tasty.co{href}"

                    title = card.get_text(strip=True)[:100]
                    if title:
                        recipes.append({
                            "title": title,
                            "url": href,
                            "image": "",
                            "description": "",
                            "source": "Tasty",
                        })
        except Exception:
            pass

    return recipes


@router.get("/fetch-recipe", response_class=HTMLResponse)
async def fetch_recipe_details(request: Request, url: str):
    """Fetch full recipe details from a URL."""
    recipe_data = None
    error_message = None

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; recipe-app)"},
                follow_redirects=True,
            )

            if response.status_code == 200:
                recipe_data = parse_recipe_page(response.text, url)
    except Exception as e:
        error_message = f"Could not fetch recipe: {str(e)}"

    return templates.TemplateResponse("discover/partials/recipe_preview.html", {
        "request": request,
        "recipe": recipe_data,
        "url": url,
        "error_message": error_message,
    })


def parse_recipe_page(html: str, url: str) -> Optional[dict]:
    """Parse a recipe page to extract structured data."""
    soup = BeautifulSoup(html, "html.parser")

    # Try to find JSON-LD structured data first (most reliable)
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
            if isinstance(data, list):
                data = data[0]

            # Handle @graph structure
            if "@graph" in data:
                for item in data["@graph"]:
                    if item.get("@type") == "Recipe":
                        data = item
                        break

            if data.get("@type") == "Recipe":
                return {
                    "name": data.get("name", ""),
                    "description": data.get("description", ""),
                    "ingredients": data.get("recipeIngredient", []),
                    "instructions": extract_instructions(data.get("recipeInstructions", [])),
                    "source_url": url,
                }
        except (json.JSONDecodeError, KeyError, TypeError):
            continue

    # Fallback: try to scrape common patterns
    name = ""
    title_tag = soup.find("h1")
    if title_tag:
        name = title_tag.get_text(strip=True)

    # Look for ingredient lists
    ingredients = []
    for ul in soup.find_all(["ul", "ol"]):
        # Check if this looks like an ingredient list
        list_text = ul.get_text().lower()
        if any(word in list_text for word in ["cup", "tbsp", "tsp", "ounce", "pound"]):
            for li in ul.find_all("li"):
                text = li.get_text(strip=True)
                if text and len(text) < 200:
                    ingredients.append(text)
            if ingredients:
                break

    return {
        "name": name,
        "description": "",
        "ingredients": ingredients,
        "instructions": "",
        "source_url": url,
    } if name or ingredients else None


def extract_instructions(instructions_data) -> str:
    """Extract instructions from various formats."""
    if isinstance(instructions_data, str):
        return instructions_data

    if isinstance(instructions_data, list):
        steps = []
        for i, step in enumerate(instructions_data, 1):
            if isinstance(step, str):
                steps.append(f"{i}. {step}")
            elif isinstance(step, dict):
                text = step.get("text", "")
                if text:
                    steps.append(f"{i}. {text}")
        return "\n".join(steps)

    return ""


@router.post("/add-recipe")
async def add_discovered_recipe(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    ingredients: str = Form(""),
    instructions: str = Form(""),
    source_url: str = Form(""),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Add a discovered recipe to the user's collection."""
    cursor = await db.execute(
        "INSERT INTO recipes (name, description, instructions, source_url) VALUES (?, ?, ?, ?)",
        (name, description, instructions, source_url or None)
    )
    recipe_id = cursor.lastrowid

    # Parse and save ingredients
    from .recipes import save_ingredients
    await save_ingredients(db, recipe_id, ingredients)

    await db.commit()

    return RedirectResponse(f"/recipes/{recipe_id}", status_code=303)
