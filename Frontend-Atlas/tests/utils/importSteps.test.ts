import { describe, expect, it } from "vitest";
import {
  applyInputsPatch,
  canStartExtraction,
  casePartCount,
  deriveStepStates,
  missingRequiredSteps,
  pickCaseInputs,
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

  it("treats check points like control points: locked until framed, dropped on a new frame", () => {
    const check = { ...city };
    expect(deriveStepStates({}).checks.status).toBe("locked");
    expect(deriveStepStates({ frameBounds: FRAME }).checks.status).toBe("available");

    const withChecks = { ...complete, checkPoints: [check] };
    expect(deriveStepStates(withChecks).checks.status).toBe("done");
    expect(deriveStepStates(withChecks).checks.required).toBe(false);
    expect(zoneRedoResetsPoints({ frameBounds: FRAME, checkPoints: [check] })).toBe(true);

    const moved = applyInputsPatch(withChecks, { frameBounds: { ...FRAME, west: -90 } });
    expect(moved.checkPoints).toBeUndefined();
    expect(applyInputsPatch(withChecks, { colors: [] }).checkPoints).toHaveLength(1);
  });

  it("keeps the points when a case is framed for the first time", () => {
    const unframed = { ...complete, frameBounds: undefined };
    expect(zoneRedoResetsPoints(unframed)).toBe(false);

    const framed = applyInputsPatch(unframed, { frameBounds: FRAME });
    expect(framed.frameBounds).toEqual(FRAME);
    expect(framed.controlPoints).toHaveLength(4);
  });

  it("clears a key on null", () => {
    expect(applyInputsPatch(complete, { legend: null }).legend).toBeUndefined();
  });
});

describe("pickCaseInputs", () => {
  const water: ImposedColor = { ...zone, name: "eau", kind: "water" };
  const check: ControlPointInput = { ...city, pixel: { x: 9, y: 9 } };
  const source: ImportInputs = {
    ...complete,
    controlPoints: [sift(0), sift(1), sift(2), sift(3), city],
    checkPoints: [check],
    colors: [zone, water],
  };

  it("counts each part of a case", () => {
    expect(casePartCount(source, "sift")).toBe(4);
    expect(casePartCount(source, "cities")).toBe(1);
    expect(casePartCount(source, "checks")).toBe(1);
    expect(casePartCount(source, "zoneColors")).toBe(1);
    expect(casePartCount(source, "waterColors")).toBe(1);
    expect(casePartCount({}, "frame")).toBe(0);
  });

  it("takes only the parts asked for", () => {
    const picked = pickCaseInputs(source, ["frame", "sift", "waterColors"]);
    expect(picked.frameBounds).toEqual(FRAME);
    expect(picked.legend).toBeUndefined();
    expect(picked.controlPoints).toEqual([sift(0), sift(1), sift(2), sift(3)]);
    expect(picked.checkPoints).toBeUndefined();
    expect(picked.colors).toEqual([water]);
  });

  it("takes no points without the frame they were matched in", () => {
    const picked = pickCaseInputs(source, ["legend", "sift", "cities", "checks", "zoneColors"]);
    expect(picked.frameBounds).toBeUndefined();
    expect(picked.controlPoints).toBeUndefined();
    expect(picked.checkPoints).toBeUndefined();
    expect(picked.legend).toEqual(source.legend);
    expect(picked.colors).toEqual([zone]);
  });

  it("omits keys that end up empty, so their step reads as not done", () => {
    const picked = pickCaseInputs({ frameBounds: FRAME }, ["frame", "sift", "zoneColors"]);
    expect(Object.keys(picked)).toEqual(["frameBounds"]);
  });
});
