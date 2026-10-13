import { describe, expect, it } from "vitest";
import type { GroceryItem } from "./api";
import { formatAmount, groupByAisle, progress } from "./grocery";

const item = (over: Partial<GroceryItem>): GroceryItem => ({
  id: 1, name: "x", quantity: 1, quantity_display: "1", unit: "", aisle: "Other",
  checked: false, have_already: false, custom: false, ...over,
});

describe("formatAmount", () => {
  it("pluralizes count units", () => {
    expect(formatAmount(item({ quantity: 6, quantity_display: "6", unit: "clove" }))).toBe("6 cloves");
    expect(formatAmount(item({ quantity: 1.5, quantity_display: "1 1/2", unit: "cup" }))).toBe("1 1/2 cups");
  });
  it("leaves abbreviations and singulars alone", () => {
    expect(formatAmount(item({ quantity: 3, quantity_display: "3", unit: "tbsp" }))).toBe("3 tbsp");
    expect(formatAmount(item({ quantity: 1, quantity_display: "1", unit: "can" }))).toBe("1 can");
  });
  it("handles no quantity and no unit", () => {
    expect(formatAmount(item({ quantity: null, quantity_display: "" }))).toBe("");
    expect(formatAmount(item({ quantity: 2, quantity_display: "2" }))).toBe("2");
  });
});

describe("groupByAisle", () => {
  const items = [
    item({ id: 1, aisle: "Pantry" }),
    item({ id: 2, aisle: "Produce", have_already: true }),
    item({ id: 3, aisle: "Produce" }),
    item({ id: 4, aisle: "Mystery" }),
  ];
  it("orders aisles like a store walk and puts have-already items last", () => {
    const groups = groupByAisle(items, false);
    expect(groups.map((g) => g.aisle)).toEqual(["Produce", "Pantry", "Other"]);
    expect(groups[0].items.map((i) => i.id)).toEqual([3, 2]);
  });
  it("can hide items you already have", () => {
    expect(groupByAisle(items, true)[0].items.map((i) => i.id)).toEqual([3]);
  });
});

it("progress ignores items you already have", () => {
  expect(progress([item({ checked: true }), item({}), item({ have_already: true })])).toEqual({ done: 1, total: 2 });
});
