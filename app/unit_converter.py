"""Unit conversion utilities for aggregating and converting ingredients."""

from typing import Optional
import re

# Base unit conversion table (everything converts to a base unit)
# Volume: base unit is tsp
# Weight: base unit is oz

VOLUME_TO_TSP = {
    "tsp": 1,
    "teaspoon": 1,
    "teaspoons": 1,
    "tbsp": 3,
    "tablespoon": 3,
    "tablespoons": 3,
    "cup": 48,
    "cups": 48,
    "c": 48,
    "pint": 96,
    "pints": 96,
    "pt": 96,
    "quart": 192,
    "quarts": 192,
    "qt": 192,
    "gallon": 768,
    "gallons": 768,
    "gal": 768,
    "fl oz": 6,
    "fluid ounce": 6,
    "fluid ounces": 6,
    "ml": 0.202884,
    "milliliter": 0.202884,
    "milliliters": 0.202884,
    "liter": 202.884,
    "liters": 202.884,
    "l": 202.884,
}

WEIGHT_TO_OZ = {
    "oz": 1,
    "ounce": 1,
    "ounces": 1,
    "lb": 16,
    "lbs": 16,
    "pound": 16,
    "pounds": 16,
    "g": 0.035274,
    "gram": 0.035274,
    "grams": 0.035274,
    "kg": 35.274,
    "kilogram": 35.274,
    "kilograms": 35.274,
}

# Count units (no conversion, just aggregate)
COUNT_UNITS = {
    "unit", "units", "piece", "pieces",
    "clove", "cloves",
    "slice", "slices",
    "can", "cans",
    "bunch", "bunches",
    "head", "heads",
    "stalk", "stalks",
    "sprig", "sprigs",
    "leaf", "leaves",
    "whole", "",
}

# Ingredient-specific conversions
INGREDIENT_CONVERSIONS = {
    "butter": {
        "stick": ("tbsp", 8),
        "sticks": ("tbsp", 8),
    },
    "egg": {
        "large": ("unit", 1),
        "medium": ("unit", 1),
        "small": ("unit", 1),
    },
}


def normalize_unit(unit: str) -> str:
    """Normalize unit string."""
    if not unit:
        return ""
    return unit.lower().strip().rstrip(".")


def get_base_unit_and_factor(unit: str, ingredient_name: str = "") -> tuple[str, float, str]:
    """
    Get the base unit and conversion factor for a given unit.
    Returns: (base_unit, factor, unit_type) where unit_type is 'volume', 'weight', or 'count'
    """
    unit = normalize_unit(unit)
    ingredient_lower = ingredient_name.lower()

    # Check ingredient-specific conversions first
    for ingredient_key, conversions in INGREDIENT_CONVERSIONS.items():
        if ingredient_key in ingredient_lower:
            if unit in conversions:
                base_unit, factor = conversions[unit]
                # Recurse to get the actual base unit
                if base_unit in VOLUME_TO_TSP:
                    return "tsp", factor * VOLUME_TO_TSP[base_unit], "volume"
                elif base_unit in WEIGHT_TO_OZ:
                    return "oz", factor * WEIGHT_TO_OZ[base_unit], "weight"
                else:
                    return base_unit, factor, "count"

    # Check volume units
    if unit in VOLUME_TO_TSP:
        return "tsp", VOLUME_TO_TSP[unit], "volume"

    # Check weight units
    if unit in WEIGHT_TO_OZ:
        return "oz", WEIGHT_TO_OZ[unit], "weight"

    # Count units
    if unit in COUNT_UNITS or not unit:
        return "unit", 1, "count"

    # Unknown unit, treat as count
    return unit, 1, "count"


def convert_to_base(quantity: float, unit: str, ingredient_name: str = "") -> tuple[float, str, str]:
    """
    Convert a quantity to base units.
    Returns: (converted_quantity, base_unit, unit_type)
    """
    if quantity is None:
        quantity = 1

    base_unit, factor, unit_type = get_base_unit_and_factor(unit, ingredient_name)
    return quantity * factor, base_unit, unit_type


def convert_from_base(quantity: float, base_unit: str, target_unit: str) -> float:
    """Convert from base unit to target unit."""
    target = normalize_unit(target_unit)

    if base_unit == "tsp" and target in VOLUME_TO_TSP:
        return quantity / VOLUME_TO_TSP[target]
    elif base_unit == "oz" and target in WEIGHT_TO_OZ:
        return quantity / WEIGHT_TO_OZ[target]

    return quantity


def suggest_shopping_unit(quantity_in_base: float, base_unit: str, ingredient_name: str) -> tuple[float, str]:
    """
    Suggest a practical shopping unit for an ingredient.
    Returns: (shopping_quantity, shopping_unit)
    """
    ingredient_lower = ingredient_name.lower()

    # Butter: convert to sticks
    if "butter" in ingredient_lower and base_unit == "tsp":
        tbsp = quantity_in_base / 3
        sticks = tbsp / 8
        if sticks < 1:
            return 1, "stick"
        return round(sticks + 0.49), "stick"  # Round up

    # Eggs: round up to buyable quantity
    if "egg" in ingredient_lower:
        if quantity_in_base <= 6:
            return 6, "eggs (half dozen)"
        return ((int(quantity_in_base) + 11) // 12) * 12, "eggs (dozen)"

    # Flour: convert to cups, suggest bags
    if "flour" in ingredient_lower and base_unit == "tsp":
        cups = quantity_in_base / 48
        if cups <= 5:
            return round(cups, 1), "cup"
        return 1, "bag (5 lb)"

    # Sugar: convert to cups
    if "sugar" in ingredient_lower and base_unit == "tsp":
        cups = quantity_in_base / 48
        return round(cups, 1), "cup"

    # Milk: convert to cups or gallons
    if "milk" in ingredient_lower and base_unit == "tsp":
        cups = quantity_in_base / 48
        if cups <= 4:
            return round(cups, 1), "cup"
        elif cups <= 8:
            return 0.5, "gallon"
        return 1, "gallon"

    # Default: convert back to a readable unit
    if base_unit == "tsp":
        if quantity_in_base >= 48:
            return round(quantity_in_base / 48, 2), "cup"
        elif quantity_in_base >= 3:
            return round(quantity_in_base / 3, 2), "tbsp"
        return round(quantity_in_base, 2), "tsp"

    if base_unit == "oz":
        if quantity_in_base >= 16:
            return round(quantity_in_base / 16, 2), "lb"
        return round(quantity_in_base, 2), "oz"

    return round(quantity_in_base, 2), base_unit


def get_supported_units() -> set[str]:
    """Return all supported units for conversion."""
    supported = set()
    supported.update(VOLUME_TO_TSP.keys())
    supported.update(WEIGHT_TO_OZ.keys())
    supported.update(COUNT_UNITS)
    # Add ingredient-specific units
    for conversions in INGREDIENT_CONVERSIONS.values():
        supported.update(conversions.keys())
    return supported


def check_unsupported_units(unit: str) -> bool:
    """Check if a unit is unsupported for aggregation. Returns True if unsupported."""
    if not unit:
        return False
    unit = normalize_unit(unit)
    supported = get_supported_units()
    return unit not in supported


def normalize_ingredient_name(name: str) -> str:
    """Normalize ingredient name for matching."""
    # Remove common modifiers
    name = name.lower().strip()

    # Remove preparation instructions in parentheses
    name = re.sub(r'\([^)]*\)', '', name)

    # Remove common descriptors
    remove_words = [
        'fresh', 'dried', 'ground', 'chopped', 'minced', 'diced', 'sliced',
        'large', 'medium', 'small', 'whole', 'crushed', 'grated', 'shredded',
        'melted', 'softened', 'room temperature', 'cold', 'warm', 'hot',
        'organic', 'all-purpose', 'all purpose', 'unsalted', 'salted',
    ]

    for word in remove_words:
        name = re.sub(rf'\b{word}\b', '', name)

    # Clean up whitespace
    name = ' '.join(name.split())

    return name
