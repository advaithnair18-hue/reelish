from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String, Table, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _now() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Video(Base):
    __tablename__ = "videos"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    storage_key: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255), default="")
    caption: Mapped[str] = mapped_column(Text, default="")
    # uploaded -> processing -> done | failed
    status: Mapped[str] = mapped_column(String(20), default="uploaded", index=True)
    transcript: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    recipe: Mapped["Recipe | None"] = relationship(back_populates="video", uselist=False)


class Recipe(Base):
    __tablename__ = "recipes"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    video_id: Mapped[int | None] = mapped_column(ForeignKey("videos.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(255))
    servings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    steps: Mapped[list] = mapped_column(JSON, default=list)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    video: Mapped[Video | None] = relationship(back_populates="recipe")
    ingredients: Mapped[list["Ingredient"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan", order_by="Ingredient.position"
    )


class Ingredient(Base):
    __tablename__ = "ingredients"
    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipes.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    unit: Mapped[str] = mapped_column(String(20), default="")
    raw_text: Mapped[str] = mapped_column(Text, default="")

    recipe: Mapped[Recipe] = relationship(back_populates="ingredients")


grocery_list_recipes = Table(
    "grocery_list_recipes",
    Base.metadata,
    Column("list_id", ForeignKey("grocery_lists.id", ondelete="CASCADE"), primary_key=True),
    Column("recipe_id", ForeignKey("recipes.id", ondelete="CASCADE"), primary_key=True),
)


class GroceryList(Base):
    __tablename__ = "grocery_lists"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    recipes: Mapped[list[Recipe]] = relationship(secondary=grocery_list_recipes)
    items: Mapped[list["GroceryItem"]] = relationship(
        back_populates="grocery_list", cascade="all, delete-orphan", order_by="GroceryItem.position"
    )


class GroceryItem(Base):
    __tablename__ = "grocery_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    list_id: Mapped[int] = mapped_column(ForeignKey("grocery_lists.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(10, 3), nullable=True)
    unit: Mapped[str] = mapped_column(String(20), default="")
    aisle: Mapped[str] = mapped_column(String(40), default="Other")
    checked: Mapped[bool] = mapped_column(Boolean, default=False)
    have_already: Mapped[bool] = mapped_column(Boolean, default=False)

    grocery_list: Mapped[GroceryList] = relationship(back_populates="items")
