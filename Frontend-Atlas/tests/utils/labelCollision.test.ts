import { describe, expect, it } from "vitest";
import { selectVisibleLabels, type LabelCollisionCandidate } from "../../src/utils/labelCollision";

const bounds = { left: 0, right: 100, top: 0, bottom: 100, width: 100, height: 100 };

function label(
  id: string,
  priority: number,
  minZoom: number,
  rectangle = { left: 10, right: 30, top: 10, bottom: 30, width: 20, height: 20 },
): LabelCollisionCandidate {
  return { id, text: id, priority, minZoom, rectangle };
}

describe("map label collision selection", () => {
  it("keeps the higher-priority label when two labels are stacked", () => {
    const visible = selectVisibleLabels(
      [label("low", 10, 0), label("high", 90, 0)],
      bounds,
      5,
      null,
    );
    expect(visible).toEqual(new Set(["high"]));
  });

  it("keeps the selected label visible at low zoom despite collisions", () => {
    const visible = selectVisibleLabels(
      [label("selected", 10, 8), label("high", 90, 0)],
      bounds,
      3,
      "selected",
    );
    expect(visible).toEqual(new Set(["high", "selected"]));
  });

  it("filters labels below their minimum zoom and outside the map viewport", () => {
    const visible = selectVisibleLabels(
      [
        label("too-small", 90, 6),
        label("offscreen", 80, 0, {
          left: 110,
          right: 130,
          top: 10,
          bottom: 30,
          width: 20,
          height: 20,
        }),
        label("visible", 10, 0, {
          left: 40,
          right: 60,
          top: 40,
          bottom: 60,
          width: 20,
          height: 20,
        }),
      ],
      bounds,
      4,
      null,
    );
    expect(visible).toEqual(new Set(["visible"]));
  });

  it("keeps collision results correct for large labels and many separated labels", () => {
    const largeBounds = {
      left: 0,
      right: 5000,
      top: 0,
      bottom: 5000,
      width: 5000,
      height: 5000,
    };
    const separated = Array.from({ length: 400 }, (_, index) => {
      const left = (index % 20) * 200;
      const top = Math.floor(index / 20) * 200;
      return label(`separated-${index}`, 1, 0, {
        left,
        right: left + 40,
        top,
        bottom: top + 20,
        width: 40,
        height: 20,
      });
    });
    const large = label("large", 100, 0, {
      left: 1000,
      right: 2000,
      top: 1000,
      bottom: 2000,
      width: 1000,
      height: 1000,
    });
    const overlapped = label("overlapped", 10, 0, {
      left: 1100,
      right: 1900,
      top: 1100,
      bottom: 1900,
      width: 800,
      height: 800,
    });

    const separatedVisible = selectVisibleLabels(
      separated,
      largeBounds,
      5,
      null,
    );
    const largeLabelVisible = selectVisibleLabels(
      [overlapped, large],
      largeBounds,
      5,
      null,
    );

    expect(separatedVisible.size).toBe(separated.length);
    expect(largeLabelVisible).toEqual(new Set(["large"]));
  });
});
