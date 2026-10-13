from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..models import Ingredient, Recipe, User
from ..schemas import RecipeIn, RecipeOut, RecipeSummary
from ..services.lists import add_recipe, get_default_list, rebuild_list, rebuild_lists_for

router = APIRouter(prefix="/api/recipes", tags=["recipes"])


def _owned(db: Session, recipe_id: int, user: User) -> Recipe:
    recipe = db.get(Recipe, recipe_id)
    if recipe is None or recipe.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Recipe not found")
    return recipe


def _apply(recipe: Recipe, body: RecipeIn) -> None:
    recipe.title = body.title.strip()
    recipe.servings = body.servings
    recipe.steps = [s.strip() for s in body.steps if s.strip()]
    recipe.ingredients = [
        Ingredient(position=i, name=ing.name.strip(), quantity=ing.quantity, unit=ing.unit,
                   raw_text=ing.raw_text or ing.name)
        for i, ing in enumerate(body.ingredients)
    ]


@router.get("", response_model=list[RecipeSummary])
def list_recipes(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                 reviewed: bool | None = None,
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Recipe).where(Recipe.user_id == user.id)
    if reviewed is not None:
        q = q.where(Recipe.reviewed == reviewed)
    rows = db.scalars(q.order_by(Recipe.created_at.desc(), Recipe.id.desc()).limit(limit).offset(offset))
    return [RecipeSummary.from_model(r) for r in rows]


@router.post("", response_model=RecipeOut, status_code=status.HTTP_201_CREATED)
def create_recipe(body: RecipeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Add a recipe by hand (no video)."""
    recipe = Recipe(user_id=user.id, reviewed=True)
    _apply(recipe, body)
    db.add(recipe)
    db.flush()
    if user.auto_add and recipe.ingredients:
        add_recipe(get_default_list(db, user), recipe)
    db.commit()
    return RecipeOut.from_model(recipe)


@router.get("/{recipe_id}", response_model=RecipeOut)
def get_recipe(recipe_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return RecipeOut.from_model(_owned(db, recipe_id, user))


@router.put("/{recipe_id}", response_model=RecipeOut)
def update_recipe(recipe_id: int, body: RecipeIn, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    """Save the edit screen. Replaces ingredients wholesale and updates every list using the recipe."""
    recipe = _owned(db, recipe_id, user)
    _apply(recipe, body)
    recipe.reviewed = True
    db.flush()
    rebuild_lists_for(recipe)
    db.commit()
    db.refresh(recipe)
    return RecipeOut.from_model(recipe)


@router.delete("/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recipe(recipe_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    recipe = _owned(db, recipe_id, user)
    affected = list(recipe.lists)
    for gl in affected:
        gl.recipes.remove(recipe)
    db.delete(recipe)
    db.flush()
    for gl in affected:
        rebuild_list(gl)
    db.commit()
