from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..models import GroceryItem, GroceryList, Recipe, User
from ..schemas import GroceryItemIn, GroceryItemOut, GroceryItemPatch, GroceryListIn, GroceryListOut
from ..services.units import Item, guess_aisle, merge_ingredients

router = APIRouter(prefix="/api/lists", tags=["grocery lists"])

AISLE_ORDER = ["Produce", "Meat & seafood", "Dairy & eggs", "Bakery", "Pantry", "Frozen", "Other"]


def _owned(db: Session, list_id: int, user: User) -> GroceryList:
    gl = db.get(GroceryList, list_id)
    if gl is None or gl.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "List not found")
    return gl


def build_items(recipes: list[Recipe]) -> list[GroceryItem]:
    merged = merge_ingredients([Item(i.name, i.quantity, i.unit)
                                for r in recipes for i in r.ingredients])
    items = [GroceryItem(name=m.name, quantity=m.quantity, unit=m.unit, aisle=guess_aisle(m.name))
             for m in merged]
    items.sort(key=lambda it: (AISLE_ORDER.index(it.aisle), it.name))
    for pos, it in enumerate(items):
        it.position = pos
    return items


@router.post("", response_model=GroceryListOut, status_code=status.HTTP_201_CREATED)
def create_list(body: GroceryListIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    ids = list(dict.fromkeys(body.recipe_ids))
    recipes = db.scalars(select(Recipe).where(Recipe.id.in_(ids), Recipe.user_id == user.id)).all()
    if len(recipes) != len(ids):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "One or more recipes not found")
    gl = GroceryList(user_id=user.id, name=body.name.strip(), recipes=list(recipes),
                     items=build_items(list(recipes)))
    db.add(gl)
    db.commit()
    return GroceryListOut.from_model(gl)


@router.get("", response_model=list[GroceryListOut])
def list_lists(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(GroceryList).where(GroceryList.user_id == user.id)
                      .order_by(GroceryList.created_at.desc(), GroceryList.id.desc()))
    return [GroceryListOut.from_model(gl) for gl in rows]


@router.get("/{list_id}", response_model=GroceryListOut)
def get_list(list_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return GroceryListOut.from_model(_owned(db, list_id, user))


@router.post("/{list_id}/items", response_model=GroceryItemOut, status_code=status.HTTP_201_CREATED)
def add_item(list_id: int, body: GroceryItemIn, user: User = Depends(current_user),
             db: Session = Depends(get_db)):
    """Add something not from a recipe (paper towels, coffee)."""
    gl = _owned(db, list_id, user)
    item = GroceryItem(name=body.name.strip(), quantity=body.quantity, unit=body.unit,
                       aisle=guess_aisle(body.name), position=len(gl.items))
    gl.items.append(item)
    db.commit()
    return GroceryItemOut.from_model(item)


@router.patch("/{list_id}/items/{item_id}", response_model=GroceryItemOut)
def update_item(list_id: int, item_id: int, body: GroceryItemPatch,
                user: User = Depends(current_user), db: Session = Depends(get_db)):
    gl = _owned(db, list_id, user)
    item = db.get(GroceryItem, item_id)
    if item is None or item.list_id != gl.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(item, field, value)
    db.commit()
    return GroceryItemOut.from_model(item)


@router.delete("/{list_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_list(list_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(_owned(db, list_id, user))
    db.commit()
