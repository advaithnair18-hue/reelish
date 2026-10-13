from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .services.units import format_quantity, normalize_unit, parse_quantity


class Credentials(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    auto_add: bool


class UserPatch(BaseModel):
    auto_add: bool | None = None


class LinkIn(BaseModel):
    # Raw share-sheet text is fine: "Check this out! https://vm.tiktok.com/abc"
    url: str = Field(min_length=8, max_length=2000)
    caption: str = Field(default="", max_length=10000)


class VideoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    source_url: str
    platform: str
    author: str
    thumbnail_url: str
    original_filename: str
    caption: str
    status: str
    transcript: str
    error: str
    created_at: datetime
    recipe_id: int | None = None


class _QuantityFields(BaseModel):
    # Accepts 2, 0.5, "1/2", "1 1/2" or "½" so the review form can be typed naturally.
    quantity: Decimal | None = None
    unit: str = ""

    @field_validator("quantity", mode="before")
    @classmethod
    def _parse_qty(cls, v):
        if v is None or v == "":
            return None
        if isinstance(v, (int, float, Decimal)):
            if v <= 0:
                raise ValueError("quantity must be positive")
            return Decimal(str(v))
        parsed = parse_quantity(str(v))
        if parsed is None:
            raise ValueError(f"can't read quantity {v!r}")
        return parsed

    @field_validator("unit")
    @classmethod
    def _unit(cls, v: str) -> str:
        return normalize_unit(v)


class IngredientIn(_QuantityFields):
    name: str = Field(min_length=1, max_length=255)
    raw_text: str = ""


class IngredientOut(BaseModel):
    id: int
    name: str
    quantity: float | None
    quantity_display: str = ""
    unit: str
    raw_text: str

    @classmethod
    def from_model(cls, ing) -> IngredientOut:
        return cls(id=ing.id, name=ing.name,
                   quantity=float(ing.quantity) if ing.quantity is not None else None,
                   quantity_display=format_quantity(ing.quantity), unit=ing.unit,
                   raw_text=ing.raw_text)


class RecipeIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    servings: int | None = Field(default=None, ge=1, le=100)
    steps: list[str] = []
    ingredients: list[IngredientIn] = Field(default=[], max_length=100)


class RecipeSummary(BaseModel):
    id: int
    title: str
    reviewed: bool
    estimated: bool
    source_url: str
    platform: str
    author: str
    thumbnail_url: str
    created_at: datetime
    ingredient_count: int
    in_default_list: bool

    @staticmethod
    def _fields(r) -> dict:
        return dict(id=r.id, title=r.title, reviewed=r.reviewed, estimated=bool(r.estimated),
                    source_url=r.source_url or "", platform=r.platform or "", author=r.author or "",
                    thumbnail_url=r.thumbnail_url or "", created_at=r.created_at,
                    ingredient_count=len(r.ingredients),
                    in_default_list=any(gl.is_default for gl in r.lists))

    @classmethod
    def from_model(cls, r) -> RecipeSummary:
        return cls(**cls._fields(r))


class RecipeOut(RecipeSummary):
    servings: int | None
    steps: list[str]
    video_id: int | None
    ingredients: list[IngredientOut]

    @classmethod
    def from_model(cls, r) -> RecipeOut:
        return cls(**cls._fields(r), servings=r.servings, steps=r.steps or [], video_id=r.video_id,
                   ingredients=[IngredientOut.from_model(i) for i in r.ingredients])


class GroceryListIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    recipe_ids: list[int] = Field(min_length=1, max_length=50)


class ListRecipeIn(BaseModel):
    recipe_id: int


class GroceryItemIn(_QuantityFields):
    name: str = Field(min_length=1, max_length=255)


class GroceryItemPatch(BaseModel):
    checked: bool | None = None
    have_already: bool | None = None


class GroceryItemOut(BaseModel):
    id: int
    name: str
    quantity: float | None
    quantity_display: str
    unit: str
    aisle: str
    checked: bool
    have_already: bool
    custom: bool

    @classmethod
    def from_model(cls, it) -> GroceryItemOut:
        return cls(id=it.id, name=it.name,
                   quantity=float(it.quantity) if it.quantity is not None else None,
                   quantity_display=format_quantity(it.quantity), unit=it.unit, aisle=it.aisle,
                   checked=it.checked, have_already=it.have_already, custom=bool(it.custom))


class GroceryListOut(BaseModel):
    id: int
    name: str
    is_default: bool
    created_at: datetime
    recipes: list[RecipeSummary]
    items: list[GroceryItemOut]

    @classmethod
    def from_model(cls, gl) -> GroceryListOut:
        return cls(id=gl.id, name=gl.name, is_default=bool(gl.is_default), created_at=gl.created_at,
                   recipes=[RecipeSummary.from_model(r) for r in gl.recipes],
                   items=[GroceryItemOut.from_model(i) for i in gl.items])
