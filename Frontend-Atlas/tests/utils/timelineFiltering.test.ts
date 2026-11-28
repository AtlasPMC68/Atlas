import { describe, it, expect } from "vitest";
import type { Feature } from "../../src/typescript/feature";
import type { MapPeriod, SliderPeriod } from "../../src/typescript/map";
import { getFeatureMapId } from "../../src/utils/featureHelpers";
import { toYear, isPeriodActiveAt } from "../../src/utils/dateUtils";

function computeEnrichedPeriods(
  mapPeriods: MapPeriod[],
  features: Feature[],
): SliderPeriod[] {
  const mapIdsWithFeatures = new Set<string>();
  for (const f of features) {
    const mid = getFeatureMapId(f);
    if (mid) mapIdsWithFeatures.add(mid.toLowerCase());
  }

  const periods: SliderPeriod[] = [];
  for (const p of mapPeriods) {
    if (
      mapIdsWithFeatures.size > 0 &&
      !mapIdsWithFeatures.has(String(p.id).trim().toLowerCase())
    ) {
      continue;
    }
    const startYear = toYear(p.startDate);
    const endYear = toYear(p.endDate);
    if (startYear != null && endYear != null) {
      periods.push({
        ...p,
        startYear,
        endYear,
      });
    }
  }
  return periods;
}

function isFeatureVisibleAtYear(
  feature: Feature,
  selectedYear: number,
  periodByMapId: Map<string, SliderPeriod>,
  periodStartYears: Set<number>,
  mode: "specific" | "cumulative" | "global" = "specific",
): boolean {
  if (mode === "global") return true;

  const featureMapId = getFeatureMapId(feature);
  if (!featureMapId) return true;

  const period =
    periodByMapId.get(featureMapId) ??
    periodByMapId.get(String(featureMapId).trim().toLowerCase());
  if (!period || period.startYear == null || period.endYear == null) {
    return false;
  }
  if (mode === "cumulative") {
    return period.startYear <= selectedYear;
  }
  return isPeriodActiveAt(period.startYear, period.endYear, selectedYear, periodStartYears);
}

describe("Timeline filtering & empty map exclusion", () => {
  const mapQ1: MapPeriod = {
    id: "q1",
    title: "Carte q1",
    startDate: "1500",
    endDate: "1501",
    exactDate: false,
    color: "#0ea5e9",
  };

  const mapQ2: MapPeriod = {
    id: "q2",
    title: "Carte q2",
    startDate: "1509",
    endDate: "1509",
    exactDate: false,
    color: "#10b981",
  };

  const map1800: MapPeriod = {
    id: "map-1800",
    title: "Carte 1800",
    startDate: "1800",
    endDate: "1850",
    exactDate: false,
    color: "#f59e0b",
  };

  const featureOnQ1: Feature = {
    type: "Feature",
    id: "feat-1",
    projectId: "p1",
    mapId: "q1",
    name: "Ville 1500",
    createdAt: "2026-01-01",
    updatedAt: "2026-01-01",
    geometry: { type: "Point", coordinates: [-71, 46] },
    properties: { name: "Ville 1500" },
  };

  const featureOn1800: Feature = {
    type: "Feature",
    id: "feat-1800",
    projectId: "p1",
    mapId: "map-1800",
    name: "Ville 1800",
    createdAt: "2026-01-01",
    updatedAt: "2026-01-01",
    geometry: { type: "Point", coordinates: [-71, 46] },
    properties: { name: "Ville 1800" },
  };

  it("filters out empty map q2 when q1 has features", () => {
    const enriched = computeEnrichedPeriods([mapQ1, mapQ2], [featureOnQ1]);
    expect(enriched).toHaveLength(1);
    expect(enriched[0].id).toBe("q1");
    expect(enriched[0].startYear).toBe(1500);
    expect(enriched[0].endYear).toBe(1501);
  });

  it("keeps maps when the project has no features at all yet", () => {
    const enriched = computeEnrichedPeriods([mapQ1, mapQ2], []);
    expect(enriched).toHaveLength(2);
  });

  it("filters features correctly in specific mode based on active map period", () => {
    const periodMap = new Map<string, SliderPeriod>([
      ["q1", { ...mapQ1, startYear: 1500, endYear: 1501 }],
      ["map-1800", { ...map1800, startYear: 1800, endYear: 1850 }],
    ]);
    const periodStartYears = new Set([1500, 1800]);

    // Visible at 1500-1501 for q1
    expect(isFeatureVisibleAtYear(featureOnQ1, 1500, periodMap, periodStartYears)).toBe(true);
    expect(isFeatureVisibleAtYear(featureOnQ1, 1501, periodMap, periodStartYears)).toBe(true);
    expect(isFeatureVisibleAtYear(featureOnQ1, 1600, periodMap, periodStartYears)).toBe(false);
    expect(isFeatureVisibleAtYear(featureOnQ1, 1800, periodMap, periodStartYears)).toBe(false);

    // Visible at 1800-1850 for map-1800
    expect(isFeatureVisibleAtYear(featureOn1800, 1800, periodMap, periodStartYears)).toBe(true);
    expect(isFeatureVisibleAtYear(featureOn1800, 1825, periodMap, periodStartYears)).toBe(true);
    expect(isFeatureVisibleAtYear(featureOn1800, 1500, periodMap, periodStartYears)).toBe(false);
  });

  it("supports cumulative mode (features on maps that started on or before selectedYear)", () => {
    const periodMap = new Map<string, SliderPeriod>([
      ["q1", { ...mapQ1, startYear: 1500, endYear: 1501 }],
      ["map-1800", { ...map1800, startYear: 1800, endYear: 1850 }],
    ]);
    const periodStartYears = new Set([1500, 1800]);

    // At 1400: neither has appeared
    expect(isFeatureVisibleAtYear(featureOnQ1, 1400, periodMap, periodStartYears, "cumulative")).toBe(false);
    expect(isFeatureVisibleAtYear(featureOn1800, 1400, periodMap, periodStartYears, "cumulative")).toBe(false);

    // At 1550: q1 has appeared, map-1800 has not
    expect(isFeatureVisibleAtYear(featureOnQ1, 1550, periodMap, periodStartYears, "cumulative")).toBe(true);
    expect(isFeatureVisibleAtYear(featureOn1800, 1550, periodMap, periodStartYears, "cumulative")).toBe(false);

    // At 1850: both maps have appeared
    expect(isFeatureVisibleAtYear(featureOnQ1, 1850, periodMap, periodStartYears, "cumulative")).toBe(true);
    expect(isFeatureVisibleAtYear(featureOn1800, 1850, periodMap, periodStartYears, "cumulative")).toBe(true);
  });

  it("supports global mode (all features visible regardless of date)", () => {
    const periodMap = new Map<string, SliderPeriod>([
      ["q1", { ...mapQ1, startYear: 1500, endYear: 1501 }],
      ["map-1800", { ...map1800, startYear: 1800, endYear: 1850 }],
    ]);
    const periodStartYears = new Set([1500, 1800]);

    expect(isFeatureVisibleAtYear(featureOnQ1, 1000, periodMap, periodStartYears, "global")).toBe(true);
    expect(isFeatureVisibleAtYear(featureOn1800, 1000, periodMap, periodStartYears, "global")).toBe(true);
  });
});
