"""Quantity parsing, unit normalization and ingredient merging.

This is the core business logic of the app and the most heavily tested part.
Quantities are Decimals throughout: floats would turn 1/3 + 2/3 into 0.9999.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

UNICODE_FRACTIONS = {
    "½": "1/2", "⅓": "1/3", "⅔": "2/3", "¼": "1/4", "¾": "3/4",
    "⅕": "1/5", "⅛": "1/8", "⅜": "3/8", "⅝": "5/8", "⅞": "7/8",
}

WORD_NUMBERS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "half": Fraction(1, 2),
    "a half": Fraction(1, 2), "a quarter": Fraction(1, 4), "dozen": 12, "a dozen": 12,
}

# alias -> canonical unit. "" means a countable item (2 onions).
UNIT_ALIASES = {
    "teaspoon": "tsp", "teaspoons": "tsp", "tsp": "tsp", "tsps": "tsp", "t": "tsp",
    "tablespoon": "tbsp", "tablespoons": "tbsp", "tbsp": "tbsp", "tbsps": "tbsp", "tbs": "tbsp", "tbl": "tbsp",
    "cup": "cup", "cups": "cup", "c": "cup",
    "milliliter": "ml", "milliliters": "ml", "millilitre": "ml", "millilitres": "ml", "ml": "ml",
    "liter": "l", "liters": "l", "litre": "l", "litres": "l", "l": "l",
    "fl oz": "fl oz", "fluid ounce": "fl oz", "fluid ounces": "fl oz",
    "gram": "g", "grams": "g", "g": "g", "gr": "g",
    "kilogram": "kg", "kilograms": "kg", "kg": "kg", "kgs": "kg",
    "ounce": "oz", "ounces": "oz", "oz": "oz",
    "pound": "lb", "pounds": "lb", "lb": "lb", "lbs": "lb",
    "clove": "clove", "cloves": "clove",
    "can": "can", "cans": "can", "tin": "can", "tins": "can",
    "pinch": "pinch", "pinches": "pinch", "dash": "pinch", "dashes": "pinch",
    "bunch": "bunch", "bunches": "bunch",
    "slice": "slice", "slices": "slice",
    "stick": "stick", "sticks": "stick",
    "sprig": "sprig", "sprigs": "sprig",
    "piece": "", "pieces": "", "whole": "",
}

# Base unit per family: ml for volume, g for mass.
VOLUME = {"tsp": Decimal("4.92892"), "tbsp": Decimal("14.7868"), "cup": Decimal("236.588"),
          "ml": Decimal("1"), "l": Decimal("1000"), "fl oz": Decimal("29.5735")}
MASS = {"g": Decimal("1"), "kg": Decimal("1000"), "oz": Decimal("28.3495"), "lb": Decimal("453.592")}

# Words that describe preparation, not what you buy.
DESCRIPTORS = {
    "fresh", "freshly", "chopped", "diced", "minced", "sliced", "grated", "shredded", "crushed",
    "finely", "roughly", "thinly", "large", "small", "medium", "big", "ripe", "softened", "melted",
    "room", "temperature", "cold", "warm", "hot", "boneless", "skinless", "peeled", "about",
    "approximately", "heaping", "level", "packed", "ground", "to", "taste", "optional", "of",
}

# Plurals that simple "strip the s" gets wrong.
IRREGULAR_SINGULARS = {
    "tomatoes": "tomato", "potatoes": "potato", "leaves": "leaf", "loaves": "loaf",
    "berries": "berry", "cherries": "cherry", "chillies": "chilli", "chilies": "chili",
    "anchovies": "anchovy", "radishes": "radish", "peaches": "peach", "knives": "knife",
}
NO_SINGULAR = {"asparagus", "hummus", "couscous", "molasses", "swiss", "brussels", "peas", "oats",
               "noodles", "chips", "greens", "sprouts", "grits", "rice", "flour", "lettuce"}

AISLES = [
    ("Produce", ["onion", "garlic", "tomato", "potato", "lemon", "lime", "apple", "banana", "carrot",
                 "celery", "pepper", "lettuce", "spinach", "kale", "avocado", "cilantro", "parsley",
                 "basil", "ginger", "cucumber", "zucchini", "mushroom", "scallion", "shallot", "berry",
                 "broccoli", "cabbage", "jalapeno", "chili", "chilli", "herb", "mint", "corn"]),
    ("Meat & seafood", ["chicken", "beef", "pork", "bacon", "sausage", "turkey", "lamb", "salmon",
                        "shrimp", "tuna", "fish", "steak", "mince", "prawn"]),
    ("Dairy & eggs", ["milk", "butter", "cheese", "cream", "yogurt", "yoghurt", "egg", "parmesan",
                      "mozzarella", "feta", "cheddar", "ricotta"]),
    ("Bakery", ["bread", "tortilla", "bun", "baguette", "pita", "wrap", "naan"]),
    ("Pantry", ["flour", "sugar", "rice", "pasta", "noodle", "oil", "vinegar", "soy sauce", "honey",
                "salt", "stock", "broth", "bean", "lentil", "oat", "baking", "vanilla", "cocoa",
                "chocolate", "sauce", "paste", "can", "syrup", "nut", "seed", "spice", "cumin",
                "paprika", "oregano", "cinnamon", "chickpea", "coconut", "mayo", "mustard", "ketchup"]),
    ("Frozen", ["frozen", "ice cream"]),
]


def parse_quantity(text: str) -> Decimal | None:
    """Parse '2', '1.5', '1/2', '1 1/2', '½', '1½', 'a', 'half', '2-3' (takes the higher end)."""
    if text is None:
        return None
    s = text.strip().lower()
    if not s:
        return None
    for uni, ascii_frac in UNICODE_FRACTIONS.items():
        s = re.sub(rf"(\d){uni}", rf"\1 {ascii_frac}", s)
        s = s.replace(uni, ascii_frac)
    if s in WORD_NUMBERS:
        return _to_decimal(Fraction(WORD_NUMBERS[s]))
    # Ranges like "2-3" or "2 to 3": buy for the upper end.
    range_match = re.fullmatch(r"(.+?)\s*(?:-|–|to)\s*(.+)", s)
    if range_match and re.search(r"\d", range_match.group(2)):
        high = parse_quantity(range_match.group(2))
        return high if high is not None else parse_quantity(range_match.group(1))
    total = Fraction(0)
    try:
        for part in s.split():
            total += Fraction(part)
    except (ValueError, ZeroDivisionError):
        return None
    return _to_decimal(total) if total > 0 else None


def _to_decimal(value: Fraction) -> Decimal:
    return (Decimal(value.numerator) / Decimal(value.denominator)).quantize(
        Decimal("0.001"), rounding=ROUND_HALF_UP
    )


def normalize_unit(unit: str | None) -> str:
    if not unit:
        return ""
    u = unit.strip().lower().rstrip(".")
    return UNIT_ALIASES.get(u, u)


def unit_family(unit: str) -> str:
    if unit in VOLUME:
        return "volume"
    if unit in MASS:
        return "mass"
    return unit or "count"


def singularize(word: str) -> str:
    if word in NO_SINGULAR or len(word) <= 3:
        return word
    if word in IRREGULAR_SINGULARS:
        return IRREGULAR_SINGULARS[word]
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith(("ches", "shes", "sses", "xes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith(("ss", "us")):
        return word[:-1]
    return word


def normalize_name(name: str) -> str:
    """'2 Large Onions, finely diced' -> 'onion'. Used as the merge key."""
    s = name.lower()
    s = re.split(r"[,(]", s, maxsplit=1)[0]  # drop ", diced" and "(optional)"
    s = re.sub(r"[^a-z\s'-]", " ", s)
    words = [w for w in s.split() if w not in DESCRIPTORS]
    if not words:
        return name.strip().lower()
    words[-1] = singularize(words[-1])
    return " ".join(words)


def guess_aisle(name: str) -> str:
    n = normalize_name(name)
    for aisle, keywords in AISLES:
        if any(k in n for k in keywords):
            return aisle
    return "Other"


@dataclass
class Item:
    name: str
    quantity: Decimal | None
    unit: str


def merge_ingredients(items: list[Item]) -> list[Item]:
    """Merge duplicate ingredients across recipes.

    Items merge when their normalized names match and their units are in the same
    family (volume, mass, or the same count unit). '1 cup flour' + '2 tbsp flour'
    merges; '1 cup flour' + '200 g flour' stays as two lines because converting
    volume to mass depends on the ingredient's density.
    """
    groups: dict[tuple[str, str], list[Item]] = {}
    order: list[tuple[str, str]] = []
    for it in items:
        unit = normalize_unit(it.unit)
        key = (normalize_name(it.name), unit_family(unit))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(Item(it.name, it.quantity, unit))

    merged = []
    for key in order:
        group = groups[key]
        name, family = key
        quantified = [g for g in group if g.quantity is not None]
        if not quantified:
            merged.append(Item(name, None, group[0].unit))
            continue
        units = {g.unit for g in quantified}
        if len(units) == 1:
            unit = units.pop()
            total = sum((g.quantity for g in quantified), Decimal(0))
            merged.append(Item(name, total, unit))
        elif family == "volume":
            ml = sum((g.quantity * VOLUME[g.unit] for g in quantified), Decimal(0))
            merged.append(Item(name, *_best_volume(ml)))
        elif family == "mass":
            grams = sum((g.quantity * MASS[g.unit] for g in quantified), Decimal(0))
            merged.append(Item(name, *_best_mass(grams, metric=bool(units & {"g", "kg"}))))
        else:  # same family key means same unit, so this is unreachable in practice
            merged.append(Item(name, quantified[0].quantity, quantified[0].unit))
    return merged


def _round_to_quarter(value: Decimal) -> Decimal:
    return (value * 4).quantize(Decimal("1"), rounding=ROUND_HALF_UP) / 4


def _best_volume(ml: Decimal) -> tuple[Decimal, str]:
    cups = ml / VOLUME["cup"]
    if cups >= Decimal("0.25"):
        return _round_to_quarter(cups).normalize(), "cup"
    tbsp = ml / VOLUME["tbsp"]
    if tbsp >= 1:
        return _round_to_quarter(tbsp).normalize(), "tbsp"
    return _round_to_quarter(ml / VOLUME["tsp"]).normalize(), "tsp"


def _best_mass(grams: Decimal, metric: bool) -> tuple[Decimal, str]:
    if metric:
        if grams >= 1000:
            return (grams / 1000).quantize(Decimal("0.01")).normalize(), "kg"
        return grams.quantize(Decimal("1")), "g"
    pounds = grams / MASS["lb"]
    if pounds >= 1:
        return _round_to_quarter(pounds).normalize(), "lb"
    return (grams / MASS["oz"]).quantize(Decimal("0.1")).normalize(), "oz"


def format_quantity(q: Decimal | None) -> str:
    """Decimal('1.5') -> '1 1/2'. Readable on a shopping list."""
    if q is None:
        return ""
    frac = Fraction(q).limit_denominator(8)
    whole, rem = divmod(frac.numerator, frac.denominator)
    if abs(Fraction(q) - frac) > Fraction(1, 500):
        return f"{q.normalize():f}"
    if rem == 0:
        return str(whole)
    part = f"{rem}/{frac.denominator}"
    return f"{whole} {part}" if whole else part
