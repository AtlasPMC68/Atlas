import { describe, it, expect } from "vitest";
import {
  getContinuousRangeSelection,
  isRangeSelectModifier,
  isToggleSelectModifier,
  isMultiSelectModifier,
  deduplicateFeatures,
} from "../../src/utils/selectionUtils";

describe("selectionUtils - getContinuousRangeSelection", () => {
  const orderedList = ["elem-1", "elem-2", "elem-3", "elem-4", "elem-5"];

  it("returns [targetId] when anchorId is null or undefined", () => {
    expect(getContinuousRangeSelection(orderedList, null, "elem-3")).toEqual(["elem-3"]);
    expect(getContinuousRangeSelection(orderedList, undefined, "elem-2")).toEqual(["elem-2"]);
    expect(getContinuousRangeSelection(orderedList, "", "elem-1")).toEqual(["elem-1"]);
  });

  it("returns empty array when targetId is null, undefined, or empty", () => {
    expect(getContinuousRangeSelection(orderedList, "elem-1", null)).toEqual([]);
    expect(getContinuousRangeSelection(orderedList, "elem-1", undefined)).toEqual([]);
    expect(getContinuousRangeSelection(orderedList, "elem-1", "")).toEqual([]);
  });

  it("returns single item when anchorId and targetId are the same", () => {
    expect(getContinuousRangeSelection(orderedList, "elem-3", "elem-3")).toEqual(["elem-3"]);
  });

  it("selects range downwards (anchor at lower index, target at higher index)", () => {
    const result = getContinuousRangeSelection(orderedList, "elem-2", "elem-4");
    expect(result).toEqual(["elem-2", "elem-3", "elem-4"]);
  });

  it("selects range upwards (anchor at higher index, target at lower index)", () => {
    const result = getContinuousRangeSelection(orderedList, "elem-4", "elem-2");
    expect(result).toEqual(["elem-2", "elem-3", "elem-4"]);
  });

  it("selects entire list when anchor is first and target is last", () => {
    const result = getContinuousRangeSelection(orderedList, "elem-1", "elem-5");
    expect(result).toEqual(orderedList);
  });

  it("falls back to [targetId] when anchorId is not in orderedIds", () => {
    const result = getContinuousRangeSelection(orderedList, "non-existent-anchor", "elem-3");
    expect(result).toEqual(["elem-3"]);
  });

  it("falls back to [targetId] when targetId is not in orderedIds", () => {
    const result = getContinuousRangeSelection(orderedList, "elem-2", "non-existent-target");
    expect(result).toEqual(["non-existent-target"]);
  });

  it("handles whitespace in IDs and number types gracefully", () => {
    const numericList = [10, 20, 30, 40];
    expect(getContinuousRangeSelection(numericList, 20, 40)).toEqual(["20", "30", "40"]);

    const untrimmedList = ["  a ", " b ", " c "];
    expect(getContinuousRangeSelection(untrimmedList, "a", "c")).toEqual(["a", "b", "c"]);
  });

  it("returns [targetId] when orderedList is empty", () => {
    expect(getContinuousRangeSelection([], "elem-1", "elem-2")).toEqual(["elem-2"]);
  });
});

describe("selectionUtils - modifier helpers", () => {
  it("isRangeSelectModifier checks Shift key only", () => {
    expect(isRangeSelectModifier({ shiftKey: true })).toBe(true);
    expect(isRangeSelectModifier({ ctrlKey: true })).toBe(false);
    expect(isRangeSelectModifier({ metaKey: true })).toBe(false);
    expect(isRangeSelectModifier(null)).toBe(false);
  });

  it("isToggleSelectModifier checks Ctrl and Meta keys", () => {
    expect(isToggleSelectModifier({ ctrlKey: true })).toBe(true);
    expect(isToggleSelectModifier({ metaKey: true })).toBe(true);
    expect(isToggleSelectModifier({ shiftKey: true })).toBe(false);
    expect(isToggleSelectModifier(null)).toBe(false);
  });

  it("isMultiSelectModifier checks any modifier", () => {
    expect(isMultiSelectModifier({ ctrlKey: true })).toBe(true);
    expect(isMultiSelectModifier({ metaKey: true })).toBe(true);
    expect(isMultiSelectModifier({ shiftKey: true })).toBe(true);
    expect(isMultiSelectModifier({})).toBe(false);
  });
});

describe("selectionUtils - deduplicateFeatures", () => {
  it("deduplicates features with identical IDs keeping the first occurrence", () => {
    const list = [
      { id: "feat-1", geometry: { type: "Point", coordinates: [10, 20] } },
      { id: "feat-1", geometry: { type: "Point", coordinates: [10, 20] } },
      { id: "feat-2", geometry: { type: "Point", coordinates: [30, 40] } },
    ];
    const res = deduplicateFeatures(list);
    expect(res).toHaveLength(2);
    expect(res.map((f) => f.id)).toEqual(["feat-1", "feat-2"]);
  });

  it("preserves distinct features even if they share identical geometry or coordinates", () => {
    const list = [
      { id: "f1", geometry: { type: "Polygon", coordinates: [[[0, 0], [1, 1], [0, 1], [0, 0]]] }, properties: { mapElementType: "zone" } },
      { id: "f2", geometry: { type: "Polygon", coordinates: [[[0, 0], [1, 1], [0, 1], [0, 0]]] }, properties: { mapElementType: "zone" } },
      { id: "f3", geometry: { type: "Polygon", coordinates: [[[5, 5], [6, 6], [5, 6], [5, 5]]] }, properties: { mapElementType: "zone" } },
    ];
    const res = deduplicateFeatures(list);
    expect(res).toHaveLength(3);
    expect(res.map((f) => f.id)).toEqual(["f1", "f2", "f3"]);
  });

  it("supports ID located in properties if direct ID is omitted", () => {
    const list = [
      { properties: { id: "p-1" } },
      { properties: { id: "p-1" } },
      { properties: { id: "p-2" } },
    ];
    const res = deduplicateFeatures(list);
    expect(res).toHaveLength(2);
  });
});
