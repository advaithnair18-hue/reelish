"""Grocery lists are derived from their recipes, plus any items added by hand.

Whenever a list's recipes change (a recipe is added, edited or removed), the list is
rebuilt. Rebuilding keeps what the shopper already did: a ticked-off item stays ticked
as long as the same ingredient is still on the list.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import GroceryItem, GroceryList, Recipe, User
from .units import Item, guess_aisle, merge_ingredients, normalize_name

AISLE_ORDER = ["Produce", "Meat & seafood", "Dairy & eggs", "Bakery", "Pantry", "Frozen", "Other"]
DEFAULT_LIST_NAME = "My grocery list"


def get_default_list(db: Session, user: User | int) -> GroceryList:
    user_id = user if isinstance(user, int) else user.id
    gl = db.scalar(select(GroceryList).where(GroceryList.user_id == user_id,
                                             GroceryList.is_default.is_(True)))
    if gl is None:
        gl = GroceryList(user_id=user_id, name=DEFAULT_LIST_NAME, is_default=True)
        db.add(gl)
        db.flush()
    return gl


def rebuild_list(gl: GroceryList) -> None:
    previous = {normalize_name(it.name): it for it in gl.items if not it.custom}
    custom = [it for it in gl.items if it.custom]

    merged = merge_ingredients([Item(i.name, i.quantity, i.unit)
                                for r in gl.recipes for i in r.ingredients])
    fresh = []
    for m in merged:
        old = previous.get(normalize_name(m.name))
        fresh.append(GroceryItem(name=m.name, quantity=m.quantity, unit=m.unit,
                                 aisle=guess_aisle(m.name),
                                 checked=bool(old and old.checked),
                                 have_already=bool(old and old.have_already)))
    fresh.sort(key=lambda it: (AISLE_ORDER.index(it.aisle), it.name))
    gl.items = fresh + custom
    for pos, it in enumerate(gl.items):
        it.position = pos


def add_recipe(gl: GroceryList, recipe: Recipe) -> None:
    if recipe not in gl.recipes:
        gl.recipes.append(recipe)
    rebuild_list(gl)


def remove_recipe(gl: GroceryList, recipe: Recipe) -> None:
    if recipe in gl.recipes:
        gl.recipes.remove(recipe)
    rebuild_list(gl)


def rebuild_lists_for(recipe: Recipe) -> None:
    for gl in recipe.lists:
        rebuild_list(gl)
