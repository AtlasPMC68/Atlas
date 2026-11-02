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
});
