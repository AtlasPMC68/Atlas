import { describe, expect, it } from "vitest";
import {
  applyInputsPatch,
  canStartExtraction,
  deriveStepStates,
  missingRequiredSteps,
  zoneRedoResetsPoints,
} from "../../src/utils/importSteps";
import type { ControlPointInput, ImposedColor } from "../../src/typescript/georef";
import type { ImportInputs } from "../../src/typescript/importSession";

const FRAME = { west: -80, south: 40, east: -60, north: 60 };

const sift = (i: number): ControlPointInput => ({
  source: "sift",
  pixel: { x: i, y: i },
  geo: { lon: -70 + i, lat: 45 },
});
const city: ControlPointInput = {
  source: "city",
  pixel: { x: 5, y: 5 },
  geo: { lon: -71.2, lat: 46.8 },
  city: { id: 1, name: "Québec" },
};
const zone: ImposedColor = {
  x: 0.2,
  y: 0.2,
  name: "Nouvelle-France",
  radius: 20,
  kind: "zone",
  hex: "#aabbcc",
};

const complete: ImportInputs = {
  frameBounds: FRAME,
  legend: { present: false, bounds: null },
  controlPoints: [sift(0), sift(1), sift(2), sift(3)],
  colors: [zone],
};

describe("deriveStepStates", () => {
  it("unlocks zone, legend and colours at once, and points only after the zone", () => {
    const steps = deriveStepStates({});
    expect(steps.zone.status).toBe("available");
    expect(steps.legend.status).toBe("available");
    expect(steps.colors.status).toBe("available");
    expect(steps.sift.status).toBe("locked");
    expect(steps.cities.status).toBe("locked");

    const framed = deriveStepStates({ frameBounds: FRAME });
    expect(framed.zone.status).toBe("done");
    expect(framed.sift.status).toBe("available");
    expect(framed.cities.status).toBe("available");
  });

  it("counts 'no legend' as a completed legend step", () => {
    const steps = deriveStepStates({ legend: { present: false, bounds: null } });
    expect(steps.legend.status).toBe("done");
  });

  it("needs three SIFT points and one zone colour, not water", () => {
    const partial = deriveStepStates({
      frameBounds: FRAME,
      controlPoints: [sift(0), sift(1), city],
      colors: [{ ...zone, kind: "water" }],
    });
    expect(partial.sift.status).toBe("available");
    expect(partial.cities.status).toBe("done");
    expect(partial.colors.status).toBe("available");
  });
});

describe("canStartExtraction", () => {
  it("requires zone, legend, SIFT and colours; cities are optional", () => {
    expect(canStartExtraction(complete)).toBe(true);
    expect(missingRequiredSteps({})).toEqual(["zone", "legend", "sift", "colors"]);
    expect(missingRequiredSteps({ ...complete, legend: undefined })).toEqual(["legend"]);
  });
});

describe("zone redo", () => {
  it("warns only when points would be lost", () => {
    expect(zoneRedoResetsPoints({ frameBounds: FRAME })).toBe(false);
    expect(zoneRedoResetsPoints(complete)).toBe(true);
  });

  it("drops the points when the frame changes, keeps them otherwise", () => {
    const moved = applyInputsPatch(complete, { frameBounds: { ...FRAME, west: -90 } });
    expect(moved.controlPoints).toBeUndefined();

    const same = applyInputsPatch(complete, { frameBounds: { ...FRAME } });
    expect(same.controlPoints).toHaveLength(4);

    const colours = applyInputsPatch(complete, { colors: [] });
    expect(colours.controlPoints).toHaveLength(4);
  });

  it("clears a key on null", () => {
    expect(applyInputsPatch(complete, { legend: null }).legend).toBeUndefined();
  });
});
