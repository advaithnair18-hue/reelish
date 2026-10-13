from decimal import Decimal as D

import pytest

from app.services.units import (
    Item,
    format_quantity,
    guess_aisle,
    merge_ingredients,
    normalize_name,
    normalize_unit,
    parse_quantity,
)


@pytest.mark.parametrize("text,expected", [
    ("2", D("2")), ("1.5", D("1.5")), ("1/2", D("0.5")), ("1 1/2", D("1.5")),
    ("½", D("0.5")), ("1½", D("1.5")), ("a", D("1")), ("half", D("0.5")),
    ("two", D("2")), ("2-3", D("3")), ("2 to 3", D("3")), ("1/3", D("0.333")),
])
def test_parse_quantity(text, expected):
    assert parse_quantity(text) == expected


@pytest.mark.parametrize("text", ["", "   ", "some", "0", "1/0", None])
def test_parse_quantity_rejects_junk(text):
    assert parse_quantity(text) is None


@pytest.mark.parametrize("raw,unit", [
    ("Tablespoons", "tbsp"), ("tbsp.", "tbsp"), ("cups", "cup"), ("grams", "g"),
    ("cloves", "clove"), ("", ""), (None, ""), ("pieces", ""),
])
def test_normalize_unit(raw, unit):
    assert normalize_unit(raw) == unit


@pytest.mark.parametrize("raw,name", [
    ("Large Onions, finely diced", "onion"),
    ("onions", "onion"), ("Fresh basil leaves", "basil leaf"), ("tomatoes", "tomato"),
    ("garlic (optional)", "garlic"), ("rice", "rice"), ("berries", "berry"), ("peas", "peas"),
    ("ground cumin", "cumin"),
])
def test_normalize_name(raw, name):
    assert normalize_name(raw) == name


def test_merge_same_unit():
    out = merge_ingredients([Item("garlic", D("2"), "cloves"), Item("Garlic", D("3"), "clove")])
    assert [(i.name, i.quantity, i.unit) for i in out] == [("garlic", D("5"), "clove")]


def test_merge_countable_plurals():
    out = merge_ingredients([Item("onion", D("1"), ""), Item("onions, diced", D("0.5"), "")])
    assert [(i.name, i.quantity) for i in out] == [("onion", D("1.5"))]


def test_merge_converts_volume_units():
    # 1 cup + 4 tbsp = 1.25 cups
    out = merge_ingredients([Item("flour", D("1"), "cup"), Item("flour", D("4"), "tbsp")])
    assert (out[0].quantity, out[0].unit) == (D("1.25"), "cup")


def test_merge_small_volumes_stay_small():
    out = merge_ingredients([Item("salt", D("1"), "tsp"), Item("salt", D("0.5"), "tsp")])
    assert (out[0].quantity, out[0].unit) == (D("1.5"), "tsp")
    out = merge_ingredients([Item("salt", D("1"), "tsp"), Item("salt", D("1"), "tbsp")])
    assert (out[0].quantity, out[0].unit) == (D("1.25"), "tbsp")


def test_merge_metric_mass():
    out = merge_ingredients([Item("chicken", D("500"), "g"), Item("chicken", D("1"), "kg")])
    assert (out[0].quantity, out[0].unit) == (D("1.5"), "kg")


def test_merge_imperial_mass():
    out = merge_ingredients([Item("beef", D("8"), "oz"), Item("beef", D("1"), "lb")])
    assert (out[0].quantity, out[0].unit) == (D("1.5"), "lb")


def test_volume_and_mass_never_merge():
    # Converting cups to grams depends on density, so keep two lines.
    out = merge_ingredients([Item("flour", D("1"), "cup"), Item("flour", D("200"), "g")])
    assert len(out) == 2


def test_unquantified_items_merge_into_one_line():
    out = merge_ingredients([Item("salt", None, ""), Item("salt", None, "")])
    assert len(out) == 1 and out[0].quantity is None


def test_unquantified_dropped_when_group_has_amounts():
    out = merge_ingredients([Item("lemon", None, ""), Item("lemon", D("2"), "")])
    assert [(i.name, i.quantity) for i in out] == [("lemon", D("2"))]


def test_merge_preserves_first_seen_order():
    out = merge_ingredients([Item("rice", D("1"), "cup"), Item("egg", D("2"), ""),
                             Item("rice", D("1"), "cup")])
    assert [i.name for i in out] == ["rice", "egg"]


def test_thirds_add_up_exactly():
    out = merge_ingredients([Item("milk", D("1") / 3, "cup"), Item("milk", D("2") / 3, "cup")])
    assert format_quantity(out[0].quantity) == "1"


@pytest.mark.parametrize("q,text", [
    (D("1.5"), "1 1/2"), (D("0.25"), "1/4"), (D("2"), "2"), (D("0.333"), "1/3"),
    (D("1.125"), "1 1/8"), (D("2.37"), "2.37"), (None, ""),
])
def test_format_quantity(q, text):
    assert format_quantity(q) == text


@pytest.mark.parametrize("name,aisle", [
    ("red onion", "Produce"), ("chicken thighs", "Meat & seafood"), ("parmesan", "Dairy & eggs"),
    ("soy sauce", "Pantry"), ("penne", "Pantry"), ("dragonfruit powder", "Other"),
])
def test_guess_aisle(name, aisle):
    assert guess_aisle(name) == aisle
