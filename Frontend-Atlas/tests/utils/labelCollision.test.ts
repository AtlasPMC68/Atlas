import { describe, expect, it } from "vitest";
import { selectVisibleLabels, type LabelCollisionCandidate } from "../../src/utils/labelCollision";

const bounds = { left: 0, right: 100, top: 0, bottom: 100, width: 100, height: 100 };

function label(
  id: string,
  sizePx: number,
  rectangle = { left: 10, right: 30, top: 10, bottom: 30, width: 20, height: 20 },
): LabelCollisionCandidate {
  return { id, text: id, sizePx, rectangle };
}

describe("map label collision selection", () => {
  it("keeps the larger word when two labels are stacked", () => {
    const visible = selectVisibleLabels(
      [label("small", 10), label("large", 18)],
      bounds,
      null,
    );
    expect(visible).toEqual(new Set(["large"]));
  });

  it("keeps the selected label visible despite collisions", () => {
    const visible = selectVisibleLabels(
      [label("selected", 10), label("large", 18)],
      bounds,
      "selected",
    );
    expect(visible).toEqual(new Set(["large", "selected"]));
  });

  it("hides only off-screen labels, not words that are merely at a low zoom", () => {
    const visible = selectVisibleLabels(
      [
        label("on-screen-small", 10),
        label("offscreen", 18, {
          left: 110,
          right: 130,
          top: 10,
          bottom: 30,
          width: 20,
          height: 20,
        }),
        label("visible", 12, {
          left: 40,
          right: 60,
          top: 40,
          bottom: 60,
          width: 20,
          height: 20,
        }),
      ],
      bounds,
      null,
    );
    expect(visible).toEqual(new Set(["on-screen-small", "visible"]));
  });

  it("keeps every non-overlapping word even when there are many of them", () => {
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
      return label(`separated-${index}`, 12, {
        left,
        right: left + 40,
        top,
        bottom: top + 20,
        width: 40,
        height: 20,
      });
    });
    const large = label("large", 24, {
      left: 1000,
      right: 2000,
      top: 1000,
      bottom: 2000,
      width: 1000,
      height: 1000,
    });
    const overlapped = label("overlapped", 10, {
      left: 1100,
      right: 1900,
      top: 1100,
      bottom: 1900,
      width: 800,
      height: 800,
    });

    const separatedVisible = selectVisibleLabels(separated, largeBounds, null);
    const largeLabelVisible = selectVisibleLabels(
      [overlapped, large],
      largeBounds,
      null,
    );

    expect(separatedVisible.size).toBe(separated.length);
    expect(largeLabelVisible).toEqual(new Set(["large"]));
  });

  it("hides a word once half of its box overlaps a larger label", () => {
    const large = label("large", 18, {
      left: 0,
      right: 40,
      top: 0,
      bottom: 20,
      width: 40,
      height: 20,
    });
    const halfCovered = label("half", 10, {
      left: 20,
      right: 60,
      top: 0,
      bottom: 20,
      width: 40,
      height: 20,
    });
    const lessThanHalf = label("kept", 10, {
      left: 32,
      right: 72,
      top: 0,
      bottom: 20,
      width: 40,
      height: 20,
    });

    expect(selectVisibleLabels([large, halfCovered], bounds, null)).toEqual(
      new Set(["large"]),
    );
    expect(selectVisibleLabels([large, lessThanHalf], bounds, null)).toEqual(
      new Set(["large", "kept"]),
    );
  });

  it("breaks size ties with a stable per-word order", () => {
    const visible = selectVisibleLabels(
      [label("beta", 12), label("alpha", 12)],
      bounds,
      null,
    );
    expect(visible).toEqual(new Set(["alpha"]));
  });
});
