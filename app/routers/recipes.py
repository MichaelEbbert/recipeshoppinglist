from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import aiosqlite
from typing import Optional, List, Dict
import re

from ..database import get_db
from ..models import Recipe, Ingredient, calculate_complexity
from ..unit_converter import check_unsupported_units

router = APIRouter(prefix="/recipes", tags=["recipes"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def list_recipes(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    """List all recipes."""
    cursor = await db.execute(
        "SELECT id, name, description, complexity, favorite FROM recipes ORDER BY name"
    )
    recipes = await cursor.fetchall()

    return templates.TemplateResponse("recipes/list.html", {
        "request": request,
        "recipes": recipes,
    })


@router.get("/favorites", response_class=HTMLResponse)
async def list_favorites(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    """List favorite recipes."""
    cursor = await db.execute(
        "SELECT id, name, description, complexity, favorite FROM recipes WHERE favorite = 1 ORDER BY name"
    )
    recipes = await cursor.fetchall()

    return templates.TemplateResponse("recipes/list.html", {
        "request": request,
        "recipes": recipes,
        "favorites_only": True,
    })


@router.get("/new", response_class=HTMLResponse)
async def new_recipe_form(request: Request):
    """Show form to create a new recipe."""
    return templates.TemplateResponse("recipes/edit.html", {
        "request": request,
        "recipe": None,
    })


def find_unsupported_units(ingredients_text: str) -> List[Dict]:
    """Find ingredients with unsupported units. Returns list of {line, unit} dicts."""
    warnings = []
    lines = ingredients_text.strip().split("\n")
    for line in lines:
        line = line.strip()
        if not line:
            continue
        quantity, unit, name = parse_ingredient_line(line)
        if unit and check_unsupported_units(unit):
            warnings.append({"line": line, "unit": unit})
    return warnings


@router.post("/new")
async def create_recipe(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    instructions: str = Form(""),
    ingredients_text: str = Form(""),
    source_url: str = Form(""),
    confirm_unsupported: str = Form(""),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Create a new recipe."""
    # Check for unsupported units
    unit_warnings = find_unsupported_units(ingredients_text)

    # If warnings exist and not confirmed, show warning and return form
    if unit_warnings and not confirm_unsupported:
        return templates.TemplateResponse("recipes/edit.html", {
            "request": request,
            "recipe": None,
            "name": name,
            "description": description,
            "instructions": instructions,
            "ingredients_text": ingredients_text,
            "source_url": source_url,
            "unit_warnings": unit_warnings,
        })

    # Count ingredients for complexity calculation
    ingredient_lines = [l.strip() for l in ingredients_text.strip().split("\n") if l.strip()]
    complexity = calculate_complexity(len(ingredient_lines), instructions)

    cursor = await db.execute(
        "INSERT INTO recipes (name, description, instructions, source_url, complexity) VALUES (?, ?, ?, ?, ?)",
        (name, description, instructions, source_url or None, complexity)
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
        complexity=recipe_row["complexity"] if "complexity" in recipe_row.keys() else "medium",
    )
    # Get favorite status (handle column not existing)
    favorite = recipe_row["favorite"] if "favorite" in recipe_row.keys() else 0

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
        "favorite": favorite,
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
        complexity=recipe_row["complexity"] if "complexity" in recipe_row.keys() else "medium",
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
    confirm_unsupported: str = Form(""),
    db: aiosqlite.Connection = Depends(get_db),
):
    """Update an existing recipe."""
    # Check for unsupported units
    unit_warnings = find_unsupported_units(ingredients_text)

    # If warnings exist and not confirmed, show warning and return form
    if unit_warnings and not confirm_unsupported:
        return templates.TemplateResponse("recipes/edit.html", {
            "request": request,
            "recipe": {"id": recipe_id},
            "name": name,
            "description": description,
            "instructions": instructions,
            "ingredients_text": ingredients_text,
            "source_url": source_url,
            "unit_warnings": unit_warnings,
        })

    # Recalculate complexity
    ingredient_lines = [l.strip() for l in ingredients_text.strip().split("\n") if l.strip()]
    complexity = calculate_complexity(len(ingredient_lines), instructions)

    await db.execute(
        """UPDATE recipes
           SET name = ?, description = ?, instructions = ?, source_url = ?, complexity = ?, updated_at = CURRENT_TIMESTAMP
           WHERE id = ?""",
        (name, description, instructions, source_url or None, complexity, recipe_id)
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


@router.post("/{recipe_id}/favorite")
async def toggle_favorite(request: Request, recipe_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """Toggle favorite status for a recipe."""
    # Get current favorite status
    cursor = await db.execute("SELECT favorite FROM recipes WHERE id = ?", (recipe_id,))
    row = await cursor.fetchone()
    if not row:
        return RedirectResponse("/recipes", status_code=303)

    # Toggle the value
    new_value = 0 if row["favorite"] else 1
    await db.execute("UPDATE recipes SET favorite = ? WHERE id = ?", (new_value, recipe_id))
    await db.commit()

    # Return to the referring page or recipe detail
    referer = request.headers.get("referer", f"/recipes/{recipe_id}")
    return RedirectResponse(referer, status_code=303)


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

    # Pattern to match quantity (including fractions and decimals)
    # Order matters: try decimals first, then fractions, then whole numbers
    qty_pattern = r'^(\d+\.\d+|\d+\s+\d+/\d+|\d+/\d+|\d+)\s*'

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
