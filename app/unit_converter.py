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

# Count units - map to singular form for consistent aggregation
COUNT_UNITS_SINGULAR = {
    "unit": "unit", "units": "unit",
    "piece": "piece", "pieces": "piece",
    "clove": "clove", "cloves": "clove",
    "slice": "slice", "slices": "slice",
    "can": "can", "cans": "can",
    "bunch": "bunch", "bunches": "bunch",
    "head": "head", "heads": "head",
    "stalk": "stalk", "stalks": "stalk",
    "sprig": "sprig", "sprigs": "sprig",
    "leaf": "leaf", "leaves": "leaf",
    "whole": "whole", "": "unit",
}

# Set of all count units for quick lookup
COUNT_UNITS = set(COUNT_UNITS_SINGULAR.keys())

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

    # Count units - preserve the specific unit type (slice, clove, etc.)
    if unit in COUNT_UNITS:
        return COUNT_UNITS_SINGULAR[unit], 1, "count"

    # Empty unit
    if not unit:
        return "unit", 1, "count"

    # Unknown unit, treat as count but preserve the unit name
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


def to_fraction_string(value: float) -> str:
    """
    Convert a decimal to a shopping-friendly fraction string.
    Rounds up to nearest common fraction for shopping bias.
    """
    if value <= 0:
        return "0"

    # Common fractions used in cooking/shopping
    fractions = [
        (1/8, "1/8"),
        (1/4, "1/4"),
        (1/3, "1/3"),
        (1/2, "1/2"),
        (2/3, "2/3"),
        (3/4, "3/4"),
        (1, "1"),
    ]

    whole = int(value)
    remainder = value - whole

    # If very close to a whole number, round up
    if remainder < 0.05:
        if whole == 0:
            return fractions[0][1]  # At least 1/8
        return str(whole)
    if remainder > 0.95:
        return str(whole + 1)

    # Find the smallest fraction >= remainder (round up for shopping)
    frac_str = "1"  # Default to rounding up to next whole
    for frac_val, frac_name in fractions:
        if remainder <= frac_val + 0.02:  # Small tolerance
            frac_str = frac_name
            break

    if whole == 0:
        return frac_str
    if frac_str == "1":
        return str(whole + 1)
    return f"{whole} {frac_str}"


def suggest_shopping_unit(quantity_in_base: float, base_unit: str, ingredient_name: str) -> tuple[str, str]:
    """
    Suggest a practical shopping unit for an ingredient.
    Returns: (shopping_quantity_string, shopping_unit)

    Display rules:
    - Prefer fractions over decimals (1/4 cup, 1/2 lb)
    - Don't display tbsp/tsp if >= 1/8 cup (6 tsp)
    - Don't display oz if >= 1/8 lb (2 oz)
    - Round up for shopping bias
    """
    ingredient_lower = ingredient_name.lower()

    # Butter: convert to sticks (1 stick = 8 tbsp = 24 tsp = 1/2 cup)
    if "butter" in ingredient_lower and base_unit == "tsp":
        sticks = quantity_in_base / 24  # 24 tsp per stick
        if sticks <= 0.5:
            return "1/2", "stick"
        return to_fraction_string(sticks), "stick"

    # Eggs: round up to buyable quantity
    if "egg" in ingredient_lower:
        count = int(quantity_in_base)
        if count <= 6:
            return "6", "eggs (half dozen)"
        return str(((count + 11) // 12) * 12), "eggs (dozen)"

    # Volume: convert to cups if >= 1/8 cup (6 tsp)
    if base_unit == "tsp":
        cups = quantity_in_base / 48

        # Milk: suggest gallon for larger quantities
        if "milk" in ingredient_lower:
            if cups <= 4:
                return to_fraction_string(cups), "cup"
            elif cups <= 12:
                return "1/2", "gallon"
            return "1", "gallon"

        # Flour: suggest bag for large quantities
        if "flour" in ingredient_lower and cups > 5:
            return "1", "bag (5 lb)"

        # General volume rule: roll up to larger units
        # 1 gallon = 16 cups = 768 tsp
        # 1 quart = 4 cups = 192 tsp
        # 1 pint = 2 cups = 96 tsp
        if quantity_in_base >= 768:  # >= 1 gallon
            gallons = quantity_in_base / 768
            return to_fraction_string(gallons), "gallon"
        elif quantity_in_base >= 192:  # >= 1 quart
            quarts = quantity_in_base / 192
            return to_fraction_string(quarts), "quart"
        elif quantity_in_base >= 96:  # >= 1 pint
            pints = quantity_in_base / 96
            return to_fraction_string(pints), "pint"
        elif quantity_in_base >= 6:  # >= 1/8 cup
            return to_fraction_string(cups), "cup"
        else:
            # Small amounts: show as tsp
            return to_fraction_string(quantity_in_base), "tsp"

    # Weight: convert to pounds if >= 1/8 lb (2 oz)
    if base_unit == "oz":
        if quantity_in_base >= 2:  # 2 oz = 1/8 lb
            pounds = quantity_in_base / 16
            return to_fraction_string(pounds), "lb"
        else:
            return to_fraction_string(quantity_in_base), "oz"

    # Count units: round up to whole numbers, preserve specific unit names
    import math
    count = math.ceil(quantity_in_base)

    # Generic "unit" becomes "count", but specific units (slice, clove, etc.) stay as-is
    if base_unit == "unit":
        return str(count), "count"
    elif base_unit in COUNT_UNITS_SINGULAR.values():
        return str(count), base_unit

    return to_fraction_string(quantity_in_base), base_unit


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
