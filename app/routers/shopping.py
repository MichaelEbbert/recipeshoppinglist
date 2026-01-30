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
    cursor = await db.execute(
        "SELECT id, name, description FROM recipes ORDER BY name"
    )
    recipes = await cursor.fetchall()

    return templates.TemplateResponse("shopping/select.html", {
        "request": request,
        "recipes": recipes,
    })


@router.post("/inventory", response_class=HTMLResponse)
async def inventory_check(
    request: Request,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Show aggregated ingredients and collect on-hand amounts."""
    form_data = await request.form()
    recipe_ids = [int(v) for k, v in form_data.multi_items() if k == "recipe_ids"]

    if not recipe_ids:
        return templates.TemplateResponse("shopping/inventory.html", {
            "request": request,
            "items": [],
            "recipe_ids": [],
            "message": "No recipes selected. Please go back and select recipes.",
        })

    aggregated = await get_aggregated_ingredients(db, recipe_ids)

    return templates.TemplateResponse("shopping/inventory.html", {
        "request": request,
        "items": aggregated,
        "recipe_ids": recipe_ids,
    })


@router.post("/generate", response_class=HTMLResponse)
async def generate_shopping_list(
    request: Request,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Generate the final shopping list based on inventory."""
    form_data = await request.form()

    # Get recipe IDs from form (passed as hidden fields)
    recipe_ids = [int(v) for k, v in form_data.multi_items() if k == "recipe_ids"]

    if not recipe_ids:
        return templates.TemplateResponse("shopping/list.html", {
            "request": request,
            "items": [],
            "message": "No recipes selected.",
        })

    aggregated = await get_aggregated_ingredients(db, recipe_ids)

    shopping_list = []
    for item in aggregated:
        # Get on-hand amount from form (entered in shopping units)
        on_hand_key = f"onhand_{item.name}"
        on_hand_str = form_data.get(on_hand_key, "0")
        try:
            on_hand = float(on_hand_str) if on_hand_str else 0
        except ValueError:
            on_hand = 0

        # Convert on-hand from shopping units to base units
        on_hand_base, _, _ = convert_to_base(on_hand, item.shopping_unit, item.name)

        # Calculate what's needed (both in base units now)
        needed = item.total_quantity - on_hand_base
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


async def get_aggregated_ingredients(db: aiosqlite.Connection, recipe_ids: list[int]) -> list[ShoppingItem]:
    """Get aggregated ingredients from selected recipes."""
    if not recipe_ids:
        return []

    # Get all ingredients from selected recipes
    placeholders = ",".join("?" * len(recipe_ids))
    cursor = await db.execute(
        f"SELECT * FROM ingredients WHERE recipe_id IN ({placeholders})",
        recipe_ids
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
