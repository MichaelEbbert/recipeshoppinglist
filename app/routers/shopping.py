from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import aiosqlite
from typing import Optional
from collections import defaultdict

from ..database import get_db
from ..models import Recipe, Ingredient, ShoppingItem
from ..unit_converter import (
    convert_to_base, suggest_shopping_unit, normalize_ingredient_name
)

router = APIRouter(prefix="/shopping", tags=["shopping"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def shopping_home(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    """Shopping list home - select recipes."""
    # Get all recipes
    cursor = await db.execute(
        "SELECT id, name, description FROM recipes ORDER BY name"
    )
    recipes = await cursor.fetchall()

    # Get currently selected recipes
    cursor = await db.execute(
        "SELECT recipe_id FROM shopping_selections"
    )
    selected_ids = {row[0] for row in await cursor.fetchall()}

    return templates.TemplateResponse("shopping/select.html", {
        "request": request,
        "recipes": recipes,
        "selected_ids": selected_ids,
    })


@router.get("/selected-partial", response_class=HTMLResponse)
async def selected_recipes_partial(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    """HTMX partial: return currently selected recipes (for live updates)."""
    cursor = await db.execute("""
        SELECT r.id, r.name
        FROM recipes r
        JOIN shopping_selections s ON r.id = s.recipe_id
        ORDER BY s.selected_at
    """)
    selected = await cursor.fetchall()

    return templates.TemplateResponse("shopping/partials/selected_list.html", {
        "request": request,
        "selected": selected,
    })


@router.post("/select/{recipe_id}")
async def select_recipe(recipe_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Add a recipe to the shopping selection."""
    # Check if already selected
    cursor = await db.execute(
        "SELECT id FROM shopping_selections WHERE recipe_id = ?", (recipe_id,)
    )
    if not await cursor.fetchone():
        await db.execute(
            "INSERT INTO shopping_selections (recipe_id) VALUES (?)", (recipe_id,)
        )
        await db.commit()

    return HTMLResponse('<span class="selected-indicator">✓ Selected</span>')


@router.post("/deselect/{recipe_id}")
async def deselect_recipe(recipe_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Remove a recipe from the shopping selection."""
    await db.execute(
        "DELETE FROM shopping_selections WHERE recipe_id = ?", (recipe_id,)
    )
    await db.commit()

    return HTMLResponse('<span class="deselected-indicator">Select</span>')


@router.post("/clear")
async def clear_selections(db: aiosqlite.Connection = Depends(get_db)):
    """Clear all shopping selections."""
    await db.execute("DELETE FROM shopping_selections")
    await db.commit()
    return RedirectResponse("/shopping", status_code=303)


@router.get("/inventory", response_class=HTMLResponse)
async def inventory_check(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    """Show aggregated ingredients and collect on-hand amounts."""
    aggregated = await get_aggregated_ingredients(db)

    if not aggregated:
        return templates.TemplateResponse("shopping/inventory.html", {
            "request": request,
            "items": [],
            "message": "No recipes selected. Please select recipes first.",
        })

    return templates.TemplateResponse("shopping/inventory.html", {
        "request": request,
        "items": aggregated,
    })


@router.post("/generate", response_class=HTMLResponse)
async def generate_shopping_list(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    """Generate the final shopping list based on inventory."""
    form_data = await request.form()
    aggregated = await get_aggregated_ingredients(db)

    shopping_list = []
    for item in aggregated:
        # Get on-hand amount from form
        on_hand_key = f"onhand_{item.name}"
        on_hand_str = form_data.get(on_hand_key, "0")
        try:
            on_hand = float(on_hand_str) if on_hand_str else 0
        except ValueError:
            on_hand = 0

        # Calculate what's needed
        needed = item.total_quantity - (on_hand * get_unit_factor(item.base_unit))
        if needed > 0:
            shop_qty, shop_unit = suggest_shopping_unit(needed, item.base_unit, item.name)
            shopping_list.append({
                "name": item.name,
                "quantity": shop_qty,
                "unit": shop_unit,
            })

    return templates.TemplateResponse("shopping/list.html", {
        "request": request,
        "items": shopping_list,
    })


def get_unit_factor(base_unit: str) -> float:
    """Get conversion factor for on-hand input (assumed to be in common units)."""
    # For now, assume on-hand is entered in the same unit as displayed
    return 1


async def get_aggregated_ingredients(db: aiosqlite.Connection) -> list[ShoppingItem]:
    """Get aggregated ingredients from selected recipes."""
    # Get all selected recipe IDs
    cursor = await db.execute("SELECT recipe_id FROM shopping_selections")
    selected_ids = [row[0] for row in await cursor.fetchall()]

    if not selected_ids:
        return []

    # Get all ingredients from selected recipes
    placeholders = ",".join("?" * len(selected_ids))
    cursor = await db.execute(
        f"SELECT * FROM ingredients WHERE recipe_id IN ({placeholders})",
        selected_ids
    )
    ingredients = await cursor.fetchall()

    # Aggregate by normalized name and base unit
    aggregated: dict[str, dict] = defaultdict(lambda: {
        "total_base": 0,
        "base_unit": None,
        "unit_type": None,
    })

    for ing in ingredients:
        name = ing["name"]
        normalized = normalize_ingredient_name(name)
        quantity = ing["quantity"] or 1
        unit = ing["unit"] or ""

        base_qty, base_unit, unit_type = convert_to_base(quantity, unit, name)

        key = (normalized, unit_type)
        agg = aggregated[key]

        # If first time seeing this ingredient
        if agg["base_unit"] is None:
            agg["base_unit"] = base_unit
            agg["unit_type"] = unit_type
            agg["original_name"] = name  # Keep a display name

        agg["total_base"] += base_qty

    # Convert to ShoppingItem list
    result = []
    for (normalized, unit_type), data in sorted(aggregated.items()):
        shop_qty, shop_unit = suggest_shopping_unit(
            data["total_base"], data["base_unit"], data["original_name"]
        )
        result.append(ShoppingItem(
            name=data["original_name"],
            total_quantity=data["total_base"],
            base_unit=data["base_unit"],
            shopping_quantity=shop_qty,
            shopping_unit=shop_unit,
        ))

    return result
