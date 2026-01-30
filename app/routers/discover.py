from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import aiosqlite
import httpx
from bs4 import BeautifulSoup
import json
import re
from typing import Optional
import asyncio

from ..database import get_db
from ..models import calculate_complexity

router = APIRouter(prefix="/discover", tags=["discover"])
templates = Jinja2Templates(directory="app/templates")

# API endpoints
MEALDB_BASE = "https://www.themealdb.com/api/json/v1/1"
BBC_BASE = "https://www.bbcgoodfood.com"
SKINNYTASTE_BASE = "https://www.skinnytaste.com"
HEYGRILLHEY_BASE = "https://heygrillhey.com"

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

COMPLEXITY_ORDER = {"easy": 1, "medium": 2, "hard": 3}


def calc_complexity_from_counts(ing_count: int, step_count: int) -> str:
    """Calculate complexity from ingredient and step counts."""
    combined = ing_count + step_count
    if combined <= 16:
        return "easy"
    elif combined >= 30:
        return "hard"
    return "medium"


def filter_by_complexity(recipes: list[dict], max_complexity: str) -> list[dict]:
    """Filter recipes by maximum complexity."""
    if not max_complexity or max_complexity == "hard":
        return recipes
    max_level = COMPLEXITY_ORDER.get(max_complexity, 3)
    return [r for r in recipes if COMPLEXITY_ORDER.get(r.get("complexity", "medium"), 2) <= max_level]


@router.get("", response_class=HTMLResponse)
async def discover_home(request: Request):
    """Recipe discovery page."""
    return templates.TemplateResponse("discover/index.html", {
        "request": request,
        "recipes": [],
        "message": "Click 'Surprise Me!' or search to discover new recipes!",
    })


@router.get("/search", response_class=HTMLResponse)
async def search_recipes(
    request: Request,
    q: str = "",
    max_complexity: str = "hard",
):
    """Search for recipes from multiple sources."""
    recipes = []
    error_message = None
    search_term = q.strip() if q else ""

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            if search_term:
                # Search all sources in parallel
                results = await asyncio.gather(
                    search_mealdb(client, search_term),
                    search_bbc(client, search_term),
                    search_skinnytaste(client, search_term),
                    search_heygrillhey(client, search_term),
                    return_exceptions=True
                )

                # Collect valid results
                all_lists = [r for r in results if isinstance(r, list)]

                # Interleave results from all sources
                max_len = max((len(lst) for lst in all_lists), default=0)
                for i in range(max_len):
                    for lst in all_lists:
                        if i < len(lst):
                            recipes.append(lst[i])

                # Apply complexity filter
                recipes = filter_by_complexity(recipes, max_complexity)[:12]
            else:
                # Random: only MealDB supports random
                meals = []
                for _ in range(12):
                    response = await client.get(f"{MEALDB_BASE}/random.php")
                    if response.status_code == 200:
                        data = response.json()
                        if data.get("meals"):
                            meals.extend(data["meals"])

                # Filter out Indian cuisine and format
                filtered = [m for m in meals if m.get("strArea") != "Indian"]
                recipes = [format_mealdb_card(meal) for meal in filtered]
                recipes = filter_by_complexity(recipes, max_complexity)[:6]

    except Exception as e:
        error_message = f"Could not fetch recipes: {str(e)}"

    return templates.TemplateResponse("discover/partials/recipe_cards.html", {
        "request": request,
        "recipes": recipes,
        "search_term": search_term or "random picks",
        "error_message": error_message,
    })


# ============ TheMealDB Functions ============

async def search_mealdb(client: httpx.AsyncClient, query: str) -> list[dict]:
    """Search TheMealDB for recipes."""
    recipes = []
    try:
        response = await client.get(
            f"{MEALDB_BASE}/search.php",
            params={"s": query},
        )
        if response.status_code == 200:
            data = response.json()
            if data.get("meals"):
                filtered = [m for m in data["meals"] if m.get("strArea") != "Indian"]
                recipes = [format_mealdb_card(meal) for meal in filtered]
    except Exception:
        pass
    return recipes


def format_mealdb_card(meal: dict) -> dict:
    """Format a MealDB meal for display as a card."""
    ing_count = sum(1 for i in range(1, 21) if (meal.get(f"strIngredient{i}") or "").strip())
    instructions = meal.get("strInstructions", "") or ""
    steps = re.split(r'(?:\r?\n)+|(?<=\.)\s+(?=[A-Z0-9])', instructions)
    steps = [s.strip() for s in steps if s.strip() and len(s.strip()) > 10]

    return {
        "id": meal.get("idMeal", ""),
        "title": meal.get("strMeal", ""),
        "image": meal.get("strMealThumb", ""),
        "description": meal.get("strCategory", "") + (" - " + meal.get("strArea", "") if meal.get("strArea") else ""),
        "source": "TheMealDB",
        "source_type": "mealdb",
        "complexity": calc_complexity_from_counts(ing_count, len(steps)),
    }


async def fetch_mealdb_recipe(client: httpx.AsyncClient, recipe_id: str) -> Optional[dict]:
    """Fetch full recipe from TheMealDB."""
    response = await client.get(f"{MEALDB_BASE}/lookup.php", params={"i": recipe_id})
    if response.status_code == 200:
        data = response.json()
        if data.get("meals"):
            meal = data["meals"][0]
            ingredients = []
            for i in range(1, 21):
                ingredient = meal.get(f"strIngredient{i}", "")
                measure = meal.get(f"strMeasure{i}", "")
                if ingredient and ingredient.strip():
                    if measure and measure.strip():
                        ingredients.append(f"{measure.strip()} {ingredient.strip()}")
                    else:
                        ingredients.append(ingredient.strip())
            return {
                "name": meal.get("strMeal", ""),
                "description": f"{meal.get('strCategory', '')} - {meal.get('strArea', '')} cuisine",
                "ingredients": ingredients,
                "instructions": meal.get("strInstructions", ""),
                "source_url": meal.get("strSource", "") or meal.get("strYoutube", ""),
            }
    return None


# ============ BBC Good Food Functions ============

async def search_bbc(client: httpx.AsyncClient, query: str) -> list[dict]:
    """Search BBC Good Food for recipes."""
    recipes = []
    try:
        response = await client.get(f"{BBC_BASE}/search", params={"q": query}, headers=HTTP_HEADERS)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            cards = soup.select("article.card")[:6]
            for card in cards:
                link = card.select_one("a.link")
                title = card.select_one("h2")
                img = card.select_one("img")
                if link and title:
                    href = link.get("href", "")
                    if not href.startswith("http"):
                        href = BBC_BASE + href
                    if "/recipes/" not in href:
                        continue
                    recipes.append({
                        "id": href,
                        "title": title.get_text(strip=True),
                        "image": img.get("src", "") if img else "",
                        "description": "BBC Good Food",
                        "source": "BBC Good Food",
                        "source_type": "bbc",
                        "complexity": "medium",
                    })
    except Exception:
        pass
    return recipes


async def fetch_bbc_recipe(client: httpx.AsyncClient, url: str) -> Optional[dict]:
    """Fetch full recipe from BBC Good Food using JSON-LD."""
    response = await client.get(url, headers=HTTP_HEADERS)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, "html.parser")
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                if isinstance(data, dict) and data.get("@type") == "Recipe":
                    instructions = data.get("recipeInstructions", [])
                    if isinstance(instructions, list):
                        inst_text = "\n".join(
                            step.get("text", step) if isinstance(step, dict) else str(step)
                            for step in instructions
                        )
                    else:
                        inst_text = str(instructions)
                    return {
                        "name": data.get("name", ""),
                        "description": data.get("description", "")[:200] if data.get("description") else "",
                        "ingredients": data.get("recipeIngredient", []),
                        "instructions": inst_text,
                        "source_url": url,
                    }
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
    return None


# ============ Skinnytaste Functions (Air Fryer) ============

async def search_skinnytaste(client: httpx.AsyncClient, query: str) -> list[dict]:
    """Search Skinnytaste for recipes (great for air fryer)."""
    recipes = []
    try:
        response = await client.get(f"{SKINNYTASTE_BASE}/", params={"s": query}, headers=HTTP_HEADERS)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            articles = soup.select("article")[:6]
            for article in articles:
                title_link = article.select_one("h2 a, .entry-title a")
                img = article.select_one("img")
                if title_link:
                    href = title_link.get("href", "")
                    title = title_link.get_text(strip=True)
                    if title and href:
                        recipes.append({
                            "id": href,
                            "title": title,
                            "image": img.get("src", "") if img else "",
                            "description": "Skinnytaste (Air Fryer)",
                            "source": "Skinnytaste",
                            "source_type": "skinnytaste",
                            "complexity": "medium",
                        })
    except Exception:
        pass
    return recipes


async def fetch_skinnytaste_recipe(client: httpx.AsyncClient, url: str) -> Optional[dict]:
    """Fetch full recipe from Skinnytaste using JSON-LD."""
    return await fetch_wordpress_recipe(client, url)


# ============ Hey Grill Hey Functions (BBQ) ============

async def search_heygrillhey(client: httpx.AsyncClient, query: str) -> list[dict]:
    """Search Hey Grill Hey for BBQ recipes."""
    recipes = []
    try:
        response = await client.get(f"{HEYGRILLHEY_BASE}/", params={"s": query}, headers=HTTP_HEADERS)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, "html.parser")
            articles = soup.select("article")[:6]
            for article in articles:
                title_link = article.select_one("h2 a, .entry-title a")
                img = article.select_one("img")
                if title_link:
                    href = title_link.get("href", "")
                    title = title_link.get_text(strip=True)
                    if title and href:
                        recipes.append({
                            "id": href,
                            "title": title,
                            "image": img.get("src", "") if img else "",
                            "description": "Hey Grill Hey (BBQ)",
                            "source": "Hey Grill Hey",
                            "source_type": "heygrillhey",
                            "complexity": "medium",
                        })
    except Exception:
        pass
    return recipes


async def fetch_heygrillhey_recipe(client: httpx.AsyncClient, url: str) -> Optional[dict]:
    """Fetch full recipe from Hey Grill Hey using JSON-LD."""
    return await fetch_wordpress_recipe(client, url)


# ============ Shared WordPress Recipe Fetcher ============

async def fetch_wordpress_recipe(client: httpx.AsyncClient, url: str) -> Optional[dict]:
    """Fetch recipe from WordPress sites using JSON-LD (works for most recipe blogs)."""
    response = await client.get(url, headers=HTTP_HEADERS)
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, "html.parser")
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)

                # Handle @graph structure (common in WordPress)
                if "@graph" in data:
                    for item in data["@graph"]:
                        if item.get("@type") == "Recipe":
                            data = item
                            break
                    else:
                        continue

                if data.get("@type") == "Recipe":
                    instructions = data.get("recipeInstructions", [])
                    if isinstance(instructions, list):
                        inst_text = "\n".join(
                            step.get("text", step) if isinstance(step, dict) else str(step)
                            for step in instructions
                        )
                    else:
                        inst_text = str(instructions)

                    return {
                        "name": data.get("name", ""),
                        "description": data.get("description", "")[:200] if data.get("description") else "",
                        "ingredients": data.get("recipeIngredient", []),
                        "instructions": inst_text,
                        "source_url": url,
                    }
            except (json.JSONDecodeError, KeyError, TypeError):
                continue
    return None


# ============ Unified Fetch Endpoint ============

@router.get("/fetch-recipe", response_class=HTMLResponse)
async def fetch_recipe_details(
    request: Request,
    id: str = "",
    source: str = "mealdb",
):
    """Fetch full recipe details from the appropriate source."""
    recipe_data = None
    error_message = None

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            if source == "bbc":
                recipe_data = await fetch_bbc_recipe(client, id)
            elif source == "skinnytaste":
                recipe_data = await fetch_skinnytaste_recipe(client, id)
            elif source == "heygrillhey":
                recipe_data = await fetch_heygrillhey_recipe(client, id)
            else:
                recipe_data = await fetch_mealdb_recipe(client, id)
    except Exception as e:
        error_message = f"Could not fetch recipe: {str(e)}"

    return templates.TemplateResponse("discover/partials/recipe_preview.html", {
        "request": request,
        "recipe": recipe_data,
        "error_message": error_message,
    })


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
    ingredient_lines = [l.strip() for l in ingredients.strip().split("\n") if l.strip()]
    complexity = calculate_complexity(len(ingredient_lines), instructions)

    cursor = await db.execute(
        "INSERT INTO recipes (name, description, instructions, source_url, complexity) VALUES (?, ?, ?, ?, ?)",
        (name, description, instructions, source_url or None, complexity)
    )
    recipe_id = cursor.lastrowid

    from .recipes import save_ingredients
    await save_ingredients(db, recipe_id, ingredients)

    await db.commit()

    return RedirectResponse(f"/recipes/{recipe_id}", status_code=303)
