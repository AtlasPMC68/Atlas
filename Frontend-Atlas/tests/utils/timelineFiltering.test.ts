import { describe, it, expect } from "vitest";
import type { Feature } from "../../src/typescript/feature";
import type { MapPeriod, SliderPeriod, TimelineElementMarker } from "../../src/typescript/map";
import { getFeatureMapId } from "../../src/utils/featureHelpers";
import { toYear, isPeriodActiveAt } from "../../src/utils/dateUtils";
import { isTextFeature } from "../../src/utils/wordStyles";

/**
 * Reusable helper functions mirroring the logic in Map.vue
 */
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

function computeCustomFeatureYears(features: Feature[]): number[] {
  const years: number[] = [];
  features.forEach((f: Feature) => {
    const sy =
      f.properties?.startYear != null
        ? Number(f.properties.startYear)
        : f.properties?.startDate
          ? toYear(f.properties.startDate)
          : null;
    const ey =
      f.properties?.endYear != null
        ? Number(f.properties.endYear)
        : f.properties?.endDate
          ? toYear(f.properties.endDate)
          : null;
    if (sy != null && !Number.isNaN(sy)) years.push(sy);
    if (ey != null && !Number.isNaN(ey)) years.push(ey);
  });
  return years;
}

function computeTimelineElementMarkers(features: Feature[]): TimelineElementMarker[] {
  const list: TimelineElementMarker[] = [];
  features.forEach((f: Feature) => {
    const sy =
      f.properties?.startYear != null
        ? Number(f.properties.startYear)
        : f.properties?.startDate
          ? toYear(f.properties.startDate)
          : null;
    const ey =
      f.properties?.endYear != null
        ? Number(f.properties.endYear)
        : f.properties?.endDate
          ? toYear(f.properties.endDate)
          : null;
    if (sy != null && !Number.isNaN(sy)) {
      list.push({
        id: String(f.id),
        name: f.properties?.labelText || f.properties?.name || "Élément",
        year: sy,
        endYear: ey,
        type: f.properties?.mapElementType || (isTextFeature(f) ? "Texte" : "Élément"),
        color: f.properties?.colorHex,
      });
    }
  });
  return list;
}

function isFeatureVisibleAtYear(
  feature: Feature,
  selectedYear: number,
  periodByMapId: Map<string, SliderPeriod>,
  periodStartYears: Set<number>,
): boolean {
  const featStartYear =
    feature.properties?.startYear != null
      ? Number(feature.properties.startYear)
      : feature.properties?.startDate
        ? toYear(feature.properties.startDate)
        : null;
  const featEndYear =
    feature.properties?.endYear != null
      ? Number(feature.properties.endYear)
      : feature.properties?.endDate
        ? toYear(feature.properties.endDate)
        : featStartYear;

  const hasCustomYears =
    (featStartYear != null && !Number.isNaN(featStartYear)) ||
    (featEndYear != null && !Number.isNaN(featEndYear));

  if (hasCustomYears) {
    const sy = featStartYear != null && !Number.isNaN(featStartYear) ? featStartYear : (featEndYear as number);
    const ey = featEndYear != null && !Number.isNaN(featEndYear) ? featEndYear : sy;
    return isPeriodActiveAt(sy, ey, selectedYear, periodStartYears);
  }

  const featureMapId = getFeatureMapId(feature);
  if (featureMapId) {
    const period = periodByMapId.get(featureMapId);
    if (!period || period.startYear == null || period.endYear == null) return true;
    return isPeriodActiveAt(period.startYear, period.endYear, selectedYear, periodStartYears);
  }

  return true;
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

  it("extracts custom element years even if associated with a map", () => {
    const albertaFeature: Feature = {
      type: "Feature",
      id: "feat-alberta",
      projectId: "p1",
      mapId: "q1",
      name: "ALBERTA",
      createdAt: "2026-01-01",
      updatedAt: "2026-01-01",
      geometry: { type: "Point", coordinates: [-114, 53] },
      properties: {
        name: "ALBERTA",
        startYear: 1900,
        endYear: 1900,
        mapElementType: "label",
      },
    };

    const customYears = computeCustomFeatureYears([featureOnQ1, albertaFeature]);
    expect(customYears).toContain(1900);

    const markers = computeTimelineElementMarkers([featureOnQ1, albertaFeature]);
    expect(markers).toHaveLength(1);
    expect(markers[0].name).toBe("ALBERTA");
    expect(markers[0].year).toBe(1900);
    expect(markers[0].type).toBe("label");
  });

  it("gives priority to element custom years over map period", () => {
    const albertaFeature: Feature = {
      type: "Feature",
      id: "feat-alberta",
      projectId: "p1",
      mapId: "q1", // Linked to q1 (1500-1501)
      name: "ALBERTA",
      createdAt: "2026-01-01",
      updatedAt: "2026-01-01",
      geometry: { type: "Point", coordinates: [-114, 53] },
      properties: {
        name: "ALBERTA",
        startYear: 1900,
        endYear: 1900,
      },
    };

    const periodMap = new Map<string, SliderPeriod>([
      ["q1", { ...mapQ1, startYear: 1500, endYear: 1501 }],
    ]);
    const periodStartYears = new Set([1500, 1900]);

    // ALBERTA should be visible at 1900
    expect(isFeatureVisibleAtYear(albertaFeature, 1900, periodMap, periodStartYears)).toBe(true);

    // ALBERTA should NOT be visible at 1500 even though it's linked to map q1
    expect(isFeatureVisibleAtYear(albertaFeature, 1500, periodMap, periodStartYears)).toBe(false);

    // Standard feature on q1 (no custom years) should be visible at 1500 and not at 1900
    expect(isFeatureVisibleAtYear(featureOnQ1, 1500, periodMap, periodStartYears)).toBe(true);
    expect(isFeatureVisibleAtYear(featureOnQ1, 1900, periodMap, periodStartYears)).toBe(false);
  });
});
