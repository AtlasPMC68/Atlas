import { describe, it, expect } from "vitest";
import {
  getContinuousRangeSelection,
  isRangeSelectModifier,
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

describe("selectionUtils - isRangeSelectModifier", () => {
  it("returns true for ctrlKey", () => {
    expect(isRangeSelectModifier({ ctrlKey: true })).toBe(true);
  });

  it("returns true for metaKey (Mac Cmd)", () => {
    expect(isRangeSelectModifier({ metaKey: true })).toBe(true);
  });

  it("returns true for shiftKey", () => {
    expect(isRangeSelectModifier({ shiftKey: true })).toBe(true);
  });

  it("returns false when no modifier is pressed or event is null/undefined", () => {
    expect(isRangeSelectModifier(null)).toBe(false);
    expect(isRangeSelectModifier(undefined)).toBe(false);
    expect(isRangeSelectModifier({})).toBe(false);
    expect(isRangeSelectModifier({ ctrlKey: false, metaKey: false, shiftKey: false })).toBe(false);
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

  it("deduplicates features with identical geometry and mapElementType", () => {
    const list = [
      { id: "f1", geometry: { type: "Polygon", coordinates: [[[0, 0], [1, 1], [0, 1], [0, 0]]] }, properties: { mapElementType: "zone" } },
      { id: "f2", geometry: { type: "Polygon", coordinates: [[[0, 0], [1, 1], [0, 1], [0, 0]]] }, properties: { mapElementType: "zone" } },
      { id: "f3", geometry: { type: "Polygon", coordinates: [[[5, 5], [6, 6], [5, 6], [5, 5]]] }, properties: { mapElementType: "zone" } },
    ];
    const res = deduplicateFeatures(list);
    expect(res).toHaveLength(2);
    expect(res.map((f) => f.id)).toEqual(["f1", "f3"]);
  });

  it("preserves distinct features with different coordinates or IDs", () => {
    const list = [
      { id: "f1", geometry: { type: "Point", coordinates: [1, 1] } },
      { id: "f2", geometry: { type: "Point", coordinates: [2, 2] } },
      { id: "f3", geometry: { type: "Point", coordinates: [3, 3] } },
    ];
    expect(deduplicateFeatures(list)).toHaveLength(3);
  });
});
