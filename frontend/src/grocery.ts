import type { GroceryItem } from "./api";

export const AISLE_ORDER = ["Produce", "Meat & seafood", "Dairy & eggs", "Bakery", "Pantry", "Frozen", "Other"];

/** "1 1/2 cup" -> "1 1/2 cups"; countable items get no unit. */
export function formatAmount(item: Pick<GroceryItem, "quantity" | "quantity_display" | "unit">): string {
  if (item.quantity == null) return "";
  const unit = item.unit && item.quantity > 1 && !["g", "kg", "ml", "l", "oz", "lb", "tsp", "tbsp"].includes(item.unit)
    ? pluralize(item.unit)
    : item.unit;
  return [item.quantity_display, unit].filter(Boolean).join(" ");
}

function pluralize(unit: string): string {
  if (unit === "pinch") return "pinches";
  if (unit === "bunch") return "bunches";
  return `${unit}s`;
}

export interface AisleGroup {
  aisle: string;
  items: GroceryItem[];
}

/** Group items by aisle in store-walking order. Items you already have go last. */
export function groupByAisle(items: GroceryItem[], hideHave: boolean): AisleGroup[] {
  const visible = hideHave ? items.filter((i) => !i.have_already) : items;
  const groups = new Map<string, GroceryItem[]>();
  for (const item of visible) {
    const aisle = AISLE_ORDER.includes(item.aisle) ? item.aisle : "Other";
    groups.set(aisle, [...(groups.get(aisle) ?? []), item]);
  }
  return AISLE_ORDER.filter((a) => groups.has(a)).map((aisle) => ({
    aisle,
    items: [...groups.get(aisle)!].sort((a, b) => Number(a.have_already) - Number(b.have_already)),
  }));
}

export function progress(items: GroceryItem[]): { done: number; total: number } {
  const needed = items.filter((i) => !i.have_already);
  return { done: needed.filter((i) => i.checked).length, total: needed.length };
}
