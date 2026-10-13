from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..models import GroceryItem, GroceryList, Recipe, User
from ..schemas import GroceryItemIn, GroceryItemOut, GroceryItemPatch, GroceryListIn, GroceryListOut, ListRecipeIn
from ..services.lists import add_recipe, get_default_list, rebuild_list, remove_recipe
from ..services.units import guess_aisle

router = APIRouter(prefix="/api/lists", tags=["grocery lists"])


def _owned(db: Session, list_id: int, user: User) -> GroceryList:
    gl = db.get(GroceryList, list_id)
    if gl is None or gl.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "List not found")
    return gl


def _owned_recipe(db: Session, recipe_id: int, user: User) -> Recipe:
    recipe = db.get(Recipe, recipe_id)
    if recipe is None or recipe.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recipe not found")
    return recipe


def _owned_item(db: Session, gl: GroceryList, item_id: int) -> GroceryItem:
    item = db.get(GroceryItem, item_id)
    if item is None or item.list_id != gl.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
    return item


@router.get("/default", response_model=GroceryListOut)
def default_list(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """The list shared recipes flow into. Created on first use."""
    gl = get_default_list(db, user)
    db.commit()
    return GroceryListOut.from_model(gl)


@router.post("", response_model=GroceryListOut, status_code=status.HTTP_201_CREATED)
def create_list(body: GroceryListIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ids = list(dict.fromkeys(body.recipe_ids))
    recipes = db.scalars(select(Recipe).where(Recipe.id.in_(ids), Recipe.user_id == user.id)).all()
    if len(recipes) != len(ids):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "One or more recipes not found")
    gl = GroceryList(user_id=user.id, name=body.name.strip(), recipes=list(recipes))
    db.add(gl)
    rebuild_list(gl)
    db.commit()
    return GroceryListOut.from_model(gl)


@router.get("", response_model=list[GroceryListOut])
def list_lists(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(GroceryList).where(GroceryList.user_id == user.id)
                      .order_by(GroceryList.is_default.desc(), GroceryList.created_at.desc(),
                                GroceryList.id.desc()))
    return [GroceryListOut.from_model(gl) for gl in rows]


@router.get("/{list_id}", response_model=GroceryListOut)
def get_list(list_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return GroceryListOut.from_model(_owned(db, list_id, user))


@router.post("/{list_id}/recipes", response_model=GroceryListOut)
def add_recipe_to_list(list_id: int, body: ListRecipeIn, user: User = Depends(current_user),
                       db: Session = Depends(get_db)):
    gl = _owned(db, list_id, user)
    add_recipe(gl, _owned_recipe(db, body.recipe_id, user))
    db.commit()
    return GroceryListOut.from_model(gl)


@router.delete("/{list_id}/recipes/{recipe_id}", response_model=GroceryListOut)
def remove_recipe_from_list(list_id: int, recipe_id: int, user: User = Depends(current_user),
                            db: Session = Depends(get_db)):
    gl = _owned(db, list_id, user)
    remove_recipe(gl, _owned_recipe(db, recipe_id, user))
    db.commit()
    return GroceryListOut.from_model(gl)


@router.post("/{list_id}/items", response_model=GroceryItemOut, status_code=status.HTTP_201_CREATED)
def add_item(list_id: int, body: GroceryItemIn, user: User = Depends(current_user),
             db: Session = Depends(get_db)):
    """Add something not from a recipe (paper towels, coffee)."""
    gl = _owned(db, list_id, user)
    item = GroceryItem(name=body.name.strip(), quantity=body.quantity, unit=body.unit,
                       aisle=guess_aisle(body.name), position=len(gl.items), custom=True)
    gl.items.append(item)
    db.commit()
    return GroceryItemOut.from_model(item)


@router.patch("/{list_id}/items/{item_id}", response_model=GroceryItemOut)
def update_item(list_id: int, item_id: int, body: GroceryItemPatch,
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    item = _owned_item(db, _owned(db, list_id, user), item_id)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(item, field, value)
    db.commit()
    return GroceryItemOut.from_model(item)


@router.delete("/{list_id}/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(list_id: int, item_id: int, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    item = _owned_item(db, _owned(db, list_id, user), item_id)
    if not item.custom:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "This item comes from a recipe. Remove the recipe from the list instead.")
    db.delete(item)
    db.commit()


@router.post("/{list_id}/reset", response_model=GroceryListOut)
def reset_list(list_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Start a new shop: untick everything."""
    gl = _owned(db, list_id, user)
    for item in gl.items:
        item.checked = False
    db.commit()
    return GroceryListOut.from_model(gl)


@router.post("/{list_id}/clear", response_model=GroceryListOut)
def clear_list(list_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Done shopping: empty the list (recipes stay saved)."""
    gl = _owned(db, list_id, user)
    gl.recipes = []
    gl.items = []
    db.commit()
    return GroceryListOut.from_model(gl)


@router.delete("/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_list(list_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    gl = _owned(db, list_id, user)
    if gl.is_default:
        raise HTTPException(status.HTTP_409_CONFLICT, "Your main list can be cleared but not deleted")
    db.delete(gl)
    db.commit()
