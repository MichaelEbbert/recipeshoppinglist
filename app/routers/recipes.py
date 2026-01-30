from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import aiosqlite
from typing import Optional
import re

from ..database import get_db
from ..models import Recipe, Ingredient

router = APIRouter(prefix="/recipes", tags=["recipes"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def list_recipes(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    """List all recipes."""
    cursor = await db.execute(
        "SELECT id, name, description FROM recipes ORDER BY name"
    )
    recipes = await cursor.fetchall()

    return templates.TemplateResponse("recipes/list.html", {
        "request": request,
        "recipes": recipes,
    })


@router.get("/new", response_class=HTMLResponse)
async def new_recipe_form(request: Request):
    """Show form to create a new recipe."""
    return templates.TemplateResponse("recipes/edit.html", {
        "request": request,
        "recipe": None,
    })


@router.post("/new")
async def create_recipe(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    instructions: str = Form(""),
    ingredients_text: str = Form(""),
    source_url: str = Form(""),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Create a new recipe."""
    cursor = await db.execute(
        "INSERT INTO recipes (name, description, instructions, source_url) VALUES (?, ?, ?, ?)",
        (name, description, instructions, source_url or None)
    )
    recipe_id = cursor.lastrowid

    # Parse and insert ingredients
    await save_ingredients(db, recipe_id, ingredients_text)

    await db.commit()
    return RedirectResponse(f"/recipes/{recipe_id}", status_code=303)


@router.get("/{recipe_id}", response_class=HTMLResponse)
async def view_recipe(request: Request, recipe_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """View a single recipe."""
    cursor = await db.execute(
        "SELECT * FROM recipes WHERE id = ?", (recipe_id,)
    )
    recipe_row = await cursor.fetchone()
    if not recipe_row:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "message": "Recipe not found",
        }, status_code=404)

    recipe = Recipe(
        id=recipe_row["id"],
        name=recipe_row["name"],
        description=recipe_row["description"],
        instructions=recipe_row["instructions"],
        source_url=recipe_row["source_url"],
    )

    cursor = await db.execute(
        "SELECT * FROM ingredients WHERE recipe_id = ? ORDER BY sort_order",
        (recipe_id,)
    )
    ingredient_rows = await cursor.fetchall()
    recipe.ingredients = [
        Ingredient(
            id=row["id"],
            recipe_id=row["recipe_id"],
            name=row["name"],
            quantity=row["quantity"],
            unit=row["unit"],
            sort_order=row["sort_order"],
        )
        for row in ingredient_rows
    ]

    return templates.TemplateResponse("recipes/detail.html", {
        "request": request,
        "recipe": recipe,
    })


@router.get("/{recipe_id}/print", response_class=HTMLResponse)
async def print_recipe(request: Request, recipe_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Print-friendly view of a recipe."""
    cursor = await db.execute(
        "SELECT * FROM recipes WHERE id = ?", (recipe_id,)
    )
    recipe_row = await cursor.fetchone()
    if not recipe_row:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "message": "Recipe not found",
        }, status_code=404)

    recipe = Recipe(
        id=recipe_row["id"],
        name=recipe_row["name"],
        description=recipe_row["description"],
        instructions=recipe_row["instructions"],
        source_url=recipe_row["source_url"],
    )

    cursor = await db.execute(
        "SELECT * FROM ingredients WHERE recipe_id = ? ORDER BY sort_order",
        (recipe_id,)
    )
    ingredient_rows = await cursor.fetchall()
    recipe.ingredients = [
        Ingredient(
            id=row["id"],
            recipe_id=row["recipe_id"],
            name=row["name"],
            quantity=row["quantity"],
            unit=row["unit"],
            sort_order=row["sort_order"],
        )
        for row in ingredient_rows
    ]

    return templates.TemplateResponse("recipes/print.html", {
        "request": request,
        "recipe": recipe,
    })


@router.get("/{recipe_id}/edit", response_class=HTMLResponse)
async def edit_recipe_form(request: Request, recipe_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Show form to edit a recipe."""
    cursor = await db.execute(
        "SELECT * FROM recipes WHERE id = ?", (recipe_id,)
    )
    recipe_row = await cursor.fetchone()
    if not recipe_row:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "message": "Recipe not found",
        }, status_code=404)

    cursor = await db.execute(
        "SELECT * FROM ingredients WHERE recipe_id = ? ORDER BY sort_order",
        (recipe_id,)
    )
    ingredient_rows = await cursor.fetchall()

    # Format ingredients as text for editing
    ingredients_text = "\n".join(
        f"{row['quantity'] or ''} {row['unit'] or ''} {row['name']}".strip()
        for row in ingredient_rows
    )

    return templates.TemplateResponse("recipes/edit.html", {
        "request": request,
        "recipe": dict(recipe_row),
        "ingredients_text": ingredients_text,
    })


@router.post("/{recipe_id}/edit")
async def update_recipe(
    request: Request,
    recipe_id: int,
    name: str = Form(...),
    description: str = Form(""),
    instructions: str = Form(""),
    ingredients_text: str = Form(""),
    source_url: str = Form(""),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Update an existing recipe."""
    await db.execute(
        """UPDATE recipes
           SET name = ?, description = ?, instructions = ?, source_url = ?, updated_at = CURRENT_TIMESTAMP
           WHERE id = ?""",
        (name, description, instructions, source_url or None, recipe_id)
    )

    # Delete existing ingredients and re-insert
    await db.execute("DELETE FROM ingredients WHERE recipe_id = ?", (recipe_id,))
    await save_ingredients(db, recipe_id, ingredients_text)

    await db.commit()
    return RedirectResponse(f"/recipes/{recipe_id}", status_code=303)


@router.post("/{recipe_id}/delete")
async def delete_recipe(recipe_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Delete a recipe."""
    await db.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))
    await db.commit()
    return RedirectResponse("/recipes", status_code=303)


async def save_ingredients(db: aiosqlite.Connection, recipe_id: int, ingredients_text: str):
    """Parse ingredients text and save to database."""
    lines = ingredients_text.strip().split("\n")
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        quantity, unit, name = parse_ingredient_line(line)

        await db.execute(
            "INSERT INTO ingredients (recipe_id, name, quantity, unit, sort_order) VALUES (?, ?, ?, ?, ?)",
            (recipe_id, name, quantity, unit, i)
        )


def parse_ingredient_line(line: str) -> tuple[Optional[float], Optional[str], str]:
    """
    Parse an ingredient line like "2 cups flour" or "1/2 tsp salt".
    Returns: (quantity, unit, name)
    """
    line = line.strip()

    # Pattern to match quantity (including fractions)
    qty_pattern = r'^([\d]+(?:/[\d]+)?(?:\s+[\d]+/[\d]+)?|\d+\.?\d*)\s*'

    # Common units
    units = [
        'cups?', 'c', 'tablespoons?', 'tbsp', 'teaspoons?', 'tsp',
        'ounces?', 'oz', 'pounds?', 'lbs?', 'lb', 'grams?', 'g',
        'kilograms?', 'kg', 'milliliters?', 'ml', 'liters?', 'l',
        'pints?', 'pt', 'quarts?', 'qt', 'gallons?', 'gal',
        'sticks?', 'cloves?', 'slices?', 'pieces?', 'cans?',
        'bunche?s?', 'heads?', 'stalks?', 'sprigs?', 'leaves?',
        'pinch(?:es)?', 'dash(?:es)?', 'large', 'medium', 'small',
    ]
    unit_pattern = r'(' + '|'.join(units) + r')\s+'

    quantity = None
    unit = None
    name = line

    # Try to extract quantity
    qty_match = re.match(qty_pattern, line, re.IGNORECASE)
    if qty_match:
        qty_str = qty_match.group(1)
        quantity = parse_quantity(qty_str)
        line = line[qty_match.end():].strip()

    # Try to extract unit
    unit_match = re.match(unit_pattern, line, re.IGNORECASE)
    if unit_match:
        unit = unit_match.group(1).lower()
        # Normalize common units
        unit = normalize_parsed_unit(unit)
        name = line[unit_match.end():].strip()
    else:
        name = line

    return quantity, unit, name


def parse_quantity(qty_str: str) -> float:
    """Parse a quantity string like '2', '1/2', or '1 1/2'."""
    qty_str = qty_str.strip()

    # Handle mixed fractions like "1 1/2"
    parts = qty_str.split()
    if len(parts) == 2:
        whole = float(parts[0])
        frac_parts = parts[1].split('/')
        if len(frac_parts) == 2:
            frac = float(frac_parts[0]) / float(frac_parts[1])
            return whole + frac
        return whole

    # Handle simple fractions like "1/2"
    if '/' in qty_str:
        parts = qty_str.split('/')
        return float(parts[0]) / float(parts[1])

    # Handle decimals and integers
    return float(qty_str)


def normalize_parsed_unit(unit: str) -> str:
    """Normalize parsed unit to standard form."""
    unit = unit.lower()
    normalizations = {
        'tablespoon': 'tbsp',
        'tablespoons': 'tbsp',
        'teaspoon': 'tsp',
        'teaspoons': 'tsp',
        'cup': 'cup',
        'cups': 'cup',
        'ounce': 'oz',
        'ounces': 'oz',
        'pound': 'lb',
        'pounds': 'lb',
        'lbs': 'lb',
    }
    return normalizations.get(unit, unit)
