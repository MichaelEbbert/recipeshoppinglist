from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Ingredient:
    id: Optional[int]
    recipe_id: int
    name: str
    quantity: Optional[float]
    unit: Optional[str]
    sort_order: int = 0

    @property
    def display(self) -> str:
        """Format ingredient for display."""
        parts = []
        if self.quantity:
            # Format quantity nicely (1.0 -> 1, 0.5 -> 1/2, etc.)
            parts.append(format_quantity(self.quantity))
        if self.unit:
            parts.append(self.unit)
        parts.append(self.name)
        return " ".join(parts)


@dataclass
class Recipe:
    id: Optional[int]
    name: str
    description: Optional[str] = None
    instructions: Optional[str] = None
    source_url: Optional[str] = None
    complexity: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    ingredients: list[Ingredient] = None

    def __post_init__(self):
        if self.ingredients is None:
            self.ingredients = []


def calculate_complexity(num_ingredients: int, instructions: str) -> str:
    """
    Calculate recipe complexity based on ingredients and steps.

    Thresholds based on analysis of 595 recipes:
    - Easy: combined score ≤16 (roughly bottom 25%)
    - Medium: combined score 17-29
    - Hard: combined score ≥30 (roughly top 25%)
    """
    import re

    # Count steps by splitting on newlines or sentence boundaries
    if instructions:
        steps = re.split(r'(?:\r?\n)+|(?<=\.)\s+(?=[A-Z0-9])', instructions)
        steps = [s.strip() for s in steps if s.strip() and len(s.strip()) > 10]
        num_steps = len(steps)
    else:
        num_steps = 0

    combined_score = num_ingredients + num_steps

    if combined_score <= 16:
        return "easy"
    elif combined_score >= 30:
        return "hard"
    else:
        return "medium"


@dataclass
class ShoppingItem:
    """Aggregated ingredient for shopping list."""
    name: str
    total_quantity: float
    base_unit: str
    shopping_quantity: Optional[str] = None  # Fraction string like "1/4" or "1 1/2"
    shopping_unit: Optional[str] = None
    on_hand: float = 0
    needed: float = 0


def format_quantity(qty: float) -> str:
    """Format a quantity for display (handles fractions)."""
    if qty is None:
        return ""

    # Common fractions
    fractions = {
        0.125: "1/8",
        0.25: "1/4",
        0.333: "1/3",
        0.375: "3/8",
        0.5: "1/2",
        0.625: "5/8",
        0.666: "2/3",
        0.75: "3/4",
        0.875: "7/8",
    }

    whole = int(qty)
    frac = qty - whole

    # Check if fraction part matches a common fraction
    frac_str = ""
    for value, display in fractions.items():
        if abs(frac - value) < 0.01:
            frac_str = display
            break

    if whole == 0 and frac_str:
        return frac_str
    elif whole > 0 and frac_str:
        return f"{whole} {frac_str}"
    elif whole > 0 and frac < 0.01:
        return str(whole)
    else:
        # Just return the number rounded
        return str(round(qty, 2))
