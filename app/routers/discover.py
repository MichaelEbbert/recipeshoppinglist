from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import aiosqlite
import httpx
import random
from typing import Optional

from ..database import get_db
from ..models import calculate_complexity

router = APIRouter(prefix="/discover", tags=["discover"])
templates = Jinja2Templates(directory="app/templates")

# TheMealDB API (free, no key required)
MEALDB_BASE = "https://www.themealdb.com/api/json/v1/1"

# Sample search terms for discovery
SEARCH_TERMS = [
    "chicken", "pasta", "soup", "salad", "beef",
    "vegetarian", "fish", "pork", "lamb", "seafood",
    "breakfast", "dessert", "cake", "pie", "rice",
]


@router.get("", response_class=HTMLResponse)
async def discover_home(request: Request):
    """Recipe discovery page."""
    return templates.TemplateResponse("discover/index.html", {
        "request": request,
        "recipes": [],
        "message": "Click 'Surprise Me!' or search to discover new recipes!",
    })


COMPLEXITY_ORDER = {"easy": 1, "medium": 2, "hard": 3}


def filter_by_complexity(recipes: list[dict], max_complexity: str) -> list[dict]:
    """Filter recipes by maximum complexity."""
    if not max_complexity or max_complexity == "hard":
        return recipes
    max_level = COMPLEXITY_ORDER.get(max_complexity, 3)
    return [r for r in recipes if COMPLEXITY_ORDER.get(r.get("complexity", "medium"), 2) <= max_level]


@router.get("/search", response_class=HTMLResponse)
async def search_recipes(
    request: Request,
    q: str = "",
    max_complexity: str = "hard",
):
    """Search for recipes from TheMealDB."""
    recipes = []
    error_message = None
    search_term = q.strip() if q else ""

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if search_term:
                # Search by name
                response = await client.get(
                    f"{MEALDB_BASE}/search.php",
                    params={"s": search_term},
                )
            else:
                # Get random recipes (call multiple times for variety)
                meals = []
                for _ in range(12):  # Get more to have enough after filtering
                    response = await client.get(f"{MEALDB_BASE}/random.php")
                    if response.status_code == 200:
                        data = response.json()
                        if data.get("meals"):
                            meals.extend(data["meals"])

                # Filter out Indian cuisine and format
                filtered = [m for m in meals if m.get("strArea") != "Indian"]
                recipes = [format_meal_card(meal) for meal in filtered]
                recipes = filter_by_complexity(recipes, max_complexity)[:6]
                return templates.TemplateResponse("discover/partials/recipe_cards.html", {
                    "request": request,
                    "recipes": recipes,
                    "search_term": "random picks",
                    "error_message": None,
                })

            if response.status_code == 200:
                data = response.json()
                if data.get("meals"):
                    # Filter out Indian cuisine
                    filtered = [m for m in data["meals"] if m.get("strArea") != "Indian"]
                    recipes = [format_meal_card(meal) for meal in filtered]
                    recipes = filter_by_complexity(recipes, max_complexity)[:12]

    except Exception as e:
        error_message = f"Could not fetch recipes: {str(e)}"

    return templates.TemplateResponse("discover/partials/recipe_cards.html", {
        "request": request,
        "recipes": recipes,
        "search_term": search_term or "random",
        "error_message": error_message,
    })


def format_meal_card(meal: dict) -> dict:
    """Format a MealDB meal for display as a card."""
    # Count ingredients for complexity
    ing_count = sum(1 for i in range(1, 21) if meal.get(f"strIngredient{i}", "").strip())

    # Count steps
    instructions = meal.get("strInstructions", "") or ""
    import re
    steps = re.split(r'(?:\r?\n)+|(?<=\.)\s+(?=[A-Z0-9])', instructions)
    steps = [s.strip() for s in steps if s.strip() and len(s.strip()) > 10]
    step_count = len(steps)

    # Calculate complexity
    combined = ing_count + step_count
    if combined <= 16:
        complexity = "easy"
    elif combined >= 30:
        complexity = "hard"
    else:
        complexity = "medium"

    return {
        "id": meal.get("idMeal", ""),
        "title": meal.get("strMeal", ""),
        "image": meal.get("strMealThumb", ""),
        "description": meal.get("strCategory", "") + (" - " + meal.get("strArea", "") if meal.get("strArea") else ""),
        "source": "TheMealDB",
        "complexity": complexity,
    }


@router.get("/fetch-recipe", response_class=HTMLResponse)
async def fetch_recipe_details(request: Request, id: str):
    """Fetch full recipe details from TheMealDB by ID."""
    recipe_data = None
    error_message = None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{MEALDB_BASE}/lookup.php",
                params={"i": id},
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("meals"):
                    recipe_data = format_full_recipe(data["meals"][0])
    except Exception as e:
        error_message = f"Could not fetch recipe: {str(e)}"

    return templates.TemplateResponse("discover/partials/recipe_preview.html", {
        "request": request,
        "recipe": recipe_data,
        "error_message": error_message,
    })


def format_full_recipe(meal: dict) -> dict:
    """Format a MealDB meal as a full recipe."""
    # Extract ingredients and measures (MealDB uses strIngredient1-20 and strMeasure1-20)
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
    # Calculate complexity
    ingredient_lines = [l.strip() for l in ingredients.strip().split("\n") if l.strip()]
    complexity = calculate_complexity(len(ingredient_lines), instructions)

    cursor = await db.execute(
        "INSERT INTO recipes (name, description, instructions, source_url, complexity) VALUES (?, ?, ?, ?, ?)",
        (name, description, instructions, source_url or None, complexity)
    )
    recipe_id = cursor.lastrowid

    # Parse and save ingredients
    from .recipes import save_ingredients
    await save_ingredients(db, recipe_id, ingredients)

    await db.commit()

    return RedirectResponse(f"/recipes/{recipe_id}", status_code=303)
