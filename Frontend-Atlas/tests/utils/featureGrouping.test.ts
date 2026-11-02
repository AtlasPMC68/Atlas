import { describe, it, expect } from "vitest";
import {
  groupFeaturesByType,
  groupFeaturesByMap,
  isVisibleInMainLayers,
} from "../../src/utils/featureGrouping";
import { ValidationStatus, type Feature } from "../../src/typescript/feature";
import type { MapPeriod } from "../../src/typescript/map";

describe("featureGrouping", () => {
  it("filters unrecognized and rejected OCR features from main layers", () => {
    const unrec = {
      type: "Feature",
      id: "f-unrec",
      geometry: { type: "Point", coordinates: [0, 0] },
      properties: { isOcrText: true, recognized: false, show: false },
    } as Feature;

    const rejected = {
      type: "Feature",
      id: "f-rej",
      geometry: { type: "Point", coordinates: [0, 0] },
      properties: { isOcrText: true, validationStatus: ValidationStatus.REJECTED },
    } as Feature;

    const accepted = {
      type: "Feature",
      id: "f-acc",
      geometry: { type: "Point", coordinates: [0, 0] },
      properties: { isOcrText: true, recognized: true, show: true },
    } as Feature;

    expect(isVisibleInMainLayers(unrec)).toBe(false);
    expect(isVisibleInMainLayers(rejected)).toBe(false);
    expect(isVisibleInMainLayers(accepted)).toBe(true);

    const groups = groupFeaturesByType([unrec, rejected, accepted]);
    const pointGroup = groups.find((g) => g.type === "point");
    expect(pointGroup?.features).toHaveLength(1);
    expect(pointGroup?.features[0].id).toBe("f-acc");
  });

  it("groupFeaturesByMap organizes and sorts features by period dates and name", () => {
    const mapPeriods: MapPeriod[] = [
      {
        id: "m-1",
        title: "Période 1900",
        description: "",
        startDate: "1900-01-01",
        endDate: "1910-01-01",
        visible: true,
        center: [0, 0],
        zoom: 5,
      },
      {
        id: "m-2",
        title: "Période 1800",
        description: "",
        startDate: "1800-01-01",
        endDate: "1810-01-01",
        visible: true,
        center: [0, 0],
        zoom: 5,
      },
    ];

    const f1 = {
      type: "Feature",
      id: "f-1",
      mapId: "m-1",
      geometry: { type: "Point", coordinates: [0, 0] },
      properties: { name: "B" },
    } as Feature;

    const f2 = {
      type: "Feature",
      id: "f-2",
      mapId: "m-1",
      geometry: { type: "Point", coordinates: [0, 0] },
      properties: { name: "A" },
    } as Feature;

    const f3 = {
      type: "Feature",
      id: "f-3",
      mapId: "m-2",
      geometry: { type: "Point", coordinates: [0, 0] },
      properties: { name: "C" },
    } as Feature;

    const grouped = groupFeaturesByMap([f1, f2, f3], mapPeriods);
    expect(grouped).toHaveLength(2);
    // 1800 comes before 1900
    expect(grouped[0].id).toBe("m-2");
    expect(grouped[1].id).toBe("m-1");
    // Features inside m-1 are sorted alphabetically (A then B)
    expect(grouped[1].features[0].id).toBe("f-2");
    expect(grouped[1].features[1].id).toBe("f-1");
  });
});
