import { describe, it, expect } from "vitest";
import type { Feature } from "../../src/typescript/feature";
import type { MapPeriod, SliderPeriod, TimelineElementMarker } from "../../src/typescript/map";
import { getFeatureMapId } from "../../src/utils/featureHelpers";
import { toYear, isPeriodActiveAt } from "../../src/utils/dateUtils";
import { isTextFeature } from "../../src/utils/wordStyles";

type TimelineMarkerItem = TimelineElementMarker & {
  isCustom?: boolean;
};

/**
 * Reusable helper functions mirroring the logic in Map.vue
 */
function parseOptionalYear(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const num = Number(value);
  if (!Number.isFinite(num) || num <= 0) return null;
  return Math.trunc(num);
}

function getFeatureCustomYears(f: Feature): {
  startYear: number | null;
  endYear: number | null;
} {
  const startYear =
    parseOptionalYear(f.properties?.startYear) ??
    (f.properties?.startDate ? parseOptionalYear(toYear(f.properties.startDate)) : null);
  const endYear =
    parseOptionalYear(f.properties?.endYear) ??
    (f.properties?.endDate ? parseOptionalYear(toYear(f.properties.endDate)) : null);

  return { startYear, endYear };
}

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
    const { startYear, endYear } = getFeatureCustomYears(f);
    if (startYear != null) years.push(startYear);
    if (endYear != null) years.push(endYear);
  });
  return years;
}

function computeTimelineElementMarkers(
  features: Feature[],
  mapPeriods: MapPeriod[] = [],
): TimelineMarkerItem[] {
  const periodTitleById = new Map<string, string>(
    mapPeriods.map((p: MapPeriod) => [String(p.id), p.title]),
  );

  const list: TimelineMarkerItem[] = [];
  features.forEach((f: Feature) => {
    const { startYear, endYear } = getFeatureCustomYears(f);
    const effectiveStart = startYear ?? endYear;
    if (effectiveStart == null) return;

    const mapId = getFeatureMapId(f);
    list.push({
      id: String(f.id),
      name: f.properties?.labelText || f.properties?.name || "Élément",
      year: effectiveStart,
      endYear: endYear ?? effectiveStart,
      type: f.properties?.mapElementType || (isTextFeature(f) ? "Texte" : "Élément"),
      color: f.properties?.colorHex,
      mapId: mapId ?? null,
      mapTitle: mapId ? periodTitleById.get(String(mapId)) : undefined,
      isCustom: true,
    });
  });
  return list;
}

function isFeatureVisibleAtYear(
  feature: Feature,
  selectedYear: number,
  periodByMapId: Map<string, SliderPeriod>,
  periodStartYears: Set<number>,
  mode: "specific" | "cumulative" | "global" = "specific",
): boolean {
  if (mode === "global") return true;

  const { startYear: featStartYear, endYear: featEndYear } = getFeatureCustomYears(feature);
  const hasCustomYears = featStartYear != null || featEndYear != null;

  let isCustomActive = false;
  if (hasCustomYears) {
    const sy = featStartYear ?? (featEndYear as number);
    const ey = featEndYear ?? sy;
    if (mode === "cumulative") {
      isCustomActive = sy <= selectedYear;
    } else {
      isCustomActive = isPeriodActiveAt(sy, ey, selectedYear, periodStartYears);
    }
  }

  const featureMapId = getFeatureMapId(feature);
  let isMapActive = false;
  if (featureMapId) {
    const period =
      periodByMapId.get(featureMapId) ??
      periodByMapId.get(String(featureMapId).trim().toLowerCase());
    if (!period || period.startYear == null || period.endYear == null) {
      isMapActive = true;
    } else if (mode === "cumulative") {
      isMapActive = period.startYear <= selectedYear;
    } else {
      isMapActive = isPeriodActiveAt(period.startYear, period.endYear, selectedYear, periodStartYears);
    }
  } else {
    isMapActive = !hasCustomYears;
  }

  if (hasCustomYears && featureMapId) {
    if (mode === "cumulative") {
      return isCustomActive;
    }
    return isCustomActive || isMapActive;
  }
  if (hasCustomYears) {
    return isCustomActive;
  }
  return isMapActive;
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

  it("extracts custom element markers for elements WITH or WITHOUT an associated map", () => {
    const albertaWithoutMap: Feature = {
      type: "Feature",
      id: "feat-alberta",
      projectId: "p1",
      mapId: null,
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

    const elementOnMapWithDate: Feature = {
      type: "Feature",
      id: "feat-on-map",
      projectId: "p1",
      mapId: "q1",
      name: "Fort Sevens",
      createdAt: "2026-01-01",
      updatedAt: "2026-01-01",
      geometry: { type: "Point", coordinates: [-71, 46] },
      properties: {
        name: "Fort Sevens",
        startYear: 1600,
        endYear: 1600,
      },
    };

    const customYears = computeCustomFeatureYears([
      featureOnQ1,
      albertaWithoutMap,
      elementOnMapWithDate,
    ]);
    expect(customYears).toContain(1900);
    expect(customYears).toContain(1600);

    const markers = computeTimelineElementMarkers(
      [featureOnQ1, albertaWithoutMap, elementOnMapWithDate],
      [mapQ1, mapQ2],
    );
    expect(markers).toHaveLength(2);

    const albertaMarker = markers.find((m) => m.id === "feat-alberta");
    expect(albertaMarker).toMatchObject({
      name: "ALBERTA",
      year: 1900,
      endYear: 1900,
      type: "label",
      mapId: null,
      mapTitle: undefined,
      isCustom: true,
    });

    const fortMarker = markers.find((m) => m.id === "feat-on-map");
    expect(fortMarker).toMatchObject({
      name: "Fort Sevens",
      year: 1600,
      endYear: 1600,
      mapId: "q1",
      mapTitle: "Carte q1",
      isCustom: true,
    });
  });

  it("removes elements from timeline when custom dates are cleared (null, empty string, or 0)", () => {
    const clearedEmptyString: Feature = {
      type: "Feature",
      id: "feat-empty",
      projectId: "p1",
      mapId: null,
      name: "PROVINCE DE QUÉBEC",
      createdAt: "2026-01-01",
      updatedAt: "2026-01-01",
      geometry: { type: "Point", coordinates: [-71, 46] },
      properties: {
        name: "PROVINCE DE QUÉBEC",
        startYear: "" as unknown as number,
        endYear: "" as unknown as number,
      },
    };

    const clearedZero: Feature = {
      type: "Feature",
      id: "feat-zero",
      projectId: "p1",
      mapId: "q1",
      name: "Élément remis à zéro",
      createdAt: "2026-01-01",
      updatedAt: "2026-01-01",
      geometry: { type: "Point", coordinates: [-71, 46] },
      properties: {
        name: "Élément remis à zéro",
        startYear: 0,
        endYear: 0,
      },
    };

    const clearedNull: Feature = {
      type: "Feature",
      id: "feat-null",
      projectId: "p1",
      mapId: "q1",
      name: "Élément sans date",
      createdAt: "2026-01-01",
      updatedAt: "2026-01-01",
      geometry: { type: "Point", coordinates: [-71, 46] },
      properties: {
        name: "Élément sans date",
        startYear: null,
        endYear: null,
      },
    };

    const features = [clearedEmptyString, clearedZero, clearedNull];

    expect(computeCustomFeatureYears(features)).toEqual([]);
    expect(computeTimelineElementMarkers(features, [mapQ1])).toEqual([]);

    // Visibility should fall back to map period (q1: 1500-1501) rather than year 0
    const periodMap = new Map<string, SliderPeriod>([
      ["q1", { ...mapQ1, startYear: 1500, endYear: 1501 }],
    ]);
    const periodStartYears = new Set([1500]);

    expect(isFeatureVisibleAtYear(clearedZero, 1500, periodMap, periodStartYears)).toBe(true);
    expect(isFeatureVisibleAtYear(clearedZero, 1600, periodMap, periodStartYears)).toBe(false);
    expect(isFeatureVisibleAtYear(clearedEmptyString, 1500, periodMap, periodStartYears)).toBe(true);
    expect(isFeatureVisibleAtYear(clearedEmptyString, 1800, periodMap, periodStartYears)).toBe(true);
  });

  it("supports custom multi-year ranges and endYear-only custom dates", () => {
    const rangedFeature: Feature = {
      type: "Feature",
      id: "feat-range",
      projectId: "p1",
      mapId: "q1",
      name: "Traité",
      createdAt: "2026-01-01",
      updatedAt: "2026-01-01",
      geometry: { type: "Point", coordinates: [-71, 46] },
      properties: {
        name: "Traité",
        startYear: 1600,
        endYear: 1650,
      },
    };

    const endYearOnlyFeature: Feature = {
      type: "Feature",
      id: "feat-end-only",
      projectId: "p1",
      mapId: null,
      name: "Fin seule",
      createdAt: "2026-01-01",
      updatedAt: "2026-01-01",
      geometry: { type: "Point", coordinates: [-71, 46] },
      properties: {
        name: "Fin seule",
        startYear: null,
        endYear: 1700,
      },
    };

    const customYears = computeCustomFeatureYears([rangedFeature, endYearOnlyFeature]);
    expect(customYears).toEqual([1600, 1650, 1700]);

    const markers = computeTimelineElementMarkers([rangedFeature, endYearOnlyFeature], [mapQ1]);
    expect(markers).toHaveLength(2);
    expect(markers[0]).toMatchObject({
      id: "feat-range",
      year: 1600,
      endYear: 1650,
      mapId: "q1",
      mapTitle: "Carte q1",
      isCustom: true,
    });
    expect(markers[1]).toMatchObject({
      id: "feat-end-only",
      year: 1700,
      endYear: 1700,
      mapId: null,
      isCustom: true,
    });
  });

  it("unions element custom years with map periods (rather than replacing them)", () => {
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

    // ALBERTA should be visible at 1900 (custom date)
    expect(isFeatureVisibleAtYear(albertaFeature, 1900, periodMap, periodStartYears)).toBe(true);

    // ALBERTA should also be visible at 1500 (union with associated map period 1500-1501)
    expect(isFeatureVisibleAtYear(albertaFeature, 1500, periodMap, periodStartYears)).toBe(true);

    // ALBERTA should NOT be visible at 1600 or 1800 (outside both periods)
    expect(isFeatureVisibleAtYear(albertaFeature, 1600, periodMap, periodStartYears)).toBe(false);
    expect(isFeatureVisibleAtYear(albertaFeature, 1800, periodMap, periodStartYears)).toBe(false);

    // Standard feature on q1 (no custom years) should be visible at 1500 and not at 1900
    expect(isFeatureVisibleAtYear(featureOnQ1, 1500, periodMap, periodStartYears)).toBe(true);
    expect(isFeatureVisibleAtYear(featureOnQ1, 1900, periodMap, periodStartYears)).toBe(false);
  });

  it("unions custom multi-year range with map period (1800-1850 map + 1800-2000 custom, or 1600-1601 map + 1800-2000 custom)", () => {
    const map1800: SliderPeriod = {
      id: "map-1800",
      title: "Carte 1800-1850",
      startDate: "1800",
      endDate: "1850",
      startYear: 1800,
      endYear: 1850,
      exactDate: false,
      color: "#0ea5e9",
    };
    const map1600: SliderPeriod = {
      id: "map-1600",
      title: "Carte 1600-1601",
      startDate: "1600",
      endDate: "1601",
      startYear: 1600,
      endYear: 1601,
      exactDate: false,
      color: "#10b981",
    };

    const periodMap = new Map<string, SliderPeriod>([
      ["map-1800", map1800],
      ["map-1600", map1600],
    ]);
    const periodStartYears = new Set([1600, 1800]);

    // Element on map 1800-1850 with custom range 1800-2000
    const elemOn1800: Feature = {
      type: "Feature",
      id: "elem-1",
      projectId: "p1",
      mapId: "map-1800",
      name: "Québec",
      createdAt: "2026-01-01",
      updatedAt: "2026-01-01",
      geometry: { type: "Point", coordinates: [-71, 46] },
      properties: {
        name: "Québec",
        startYear: 1800,
        endYear: 2000,
      },
    };

    // Visible throughout 1800-2000 without gap or duplicate
    expect(isFeatureVisibleAtYear(elemOn1800, 1800, periodMap, periodStartYears)).toBe(true);
    expect(isFeatureVisibleAtYear(elemOn1800, 1825, periodMap, periodStartYears)).toBe(true);
    expect(isFeatureVisibleAtYear(elemOn1800, 1850, periodMap, periodStartYears)).toBe(true);
    expect(isFeatureVisibleAtYear(elemOn1800, 1950, periodMap, periodStartYears)).toBe(true);
    expect(isFeatureVisibleAtYear(elemOn1800, 2000, periodMap, periodStartYears)).toBe(true);
    expect(isFeatureVisibleAtYear(elemOn1800, 1750, periodMap, periodStartYears)).toBe(false);
    expect(isFeatureVisibleAtYear(elemOn1800, 2001, periodMap, periodStartYears)).toBe(false);

    // Element on map 1600-1601 with custom range 1800-2000
    const elemOn1600: Feature = {
      type: "Feature",
      id: "elem-2",
      projectId: "p1",
      mapId: "map-1600",
      name: "Québec",
      createdAt: "2026-01-01",
      updatedAt: "2026-01-01",
      geometry: { type: "Point", coordinates: [-71, 46] },
      properties: {
        name: "Québec",
        startYear: 1800,
        endYear: 2000,
      },
    };

    // Visible in 1600-1601 (from map) and in 1800-2000 (from custom range)
    expect(isFeatureVisibleAtYear(elemOn1600, 1600, periodMap, periodStartYears)).toBe(true);
    expect(isFeatureVisibleAtYear(elemOn1600, 1601, periodMap, periodStartYears)).toBe(true);
    expect(isFeatureVisibleAtYear(elemOn1600, 1700, periodMap, periodStartYears)).toBe(false);
    expect(isFeatureVisibleAtYear(elemOn1600, 1800, periodMap, periodStartYears)).toBe(true);
    expect(isFeatureVisibleAtYear(elemOn1600, 1900, periodMap, periodStartYears)).toBe(true);
    expect(isFeatureVisibleAtYear(elemOn1600, 2000, periodMap, periodStartYears)).toBe(true);
    expect(isFeatureVisibleAtYear(elemOn1600, 2050, periodMap, periodStartYears)).toBe(false);
  });

  it("supports cumulative mode (features that appeared on or before selectedYear)", () => {
    const alberta1900: Feature = {
      type: "Feature",
      id: "feat-alberta",
      projectId: "p1",
      mapId: "q1",
      name: "ALBERTA",
      createdAt: "2026-01-01",
      updatedAt: "2026-01-01",
      geometry: { type: "Point", coordinates: [-114, 53] },
      properties: { name: "ALBERTA", startYear: 1900, endYear: 1900 },
    };

    const periodMap = new Map<string, SliderPeriod>([
      ["q1", { ...mapQ1, startYear: 1500, endYear: 1501 }],
    ]);
    const periodStartYears = new Set([1500, 1900]);

    // In cumulative mode at 1800:
    // mapQ1 (1500) has appeared -> featureOnQ1 is visible
    expect(isFeatureVisibleAtYear(featureOnQ1, 1800, periodMap, periodStartYears, "cumulative")).toBe(true);
    // ALBERTA (1900) has not appeared yet -> false
    expect(isFeatureVisibleAtYear(alberta1900, 1800, periodMap, periodStartYears, "cumulative")).toBe(false);

    // In cumulative mode at 1900: both are visible
    expect(isFeatureVisibleAtYear(featureOnQ1, 1900, periodMap, periodStartYears, "cumulative")).toBe(true);
    expect(isFeatureVisibleAtYear(alberta1900, 1900, periodMap, periodStartYears, "cumulative")).toBe(true);

    // Before 1500 (e.g. 1400): neither is visible
    expect(isFeatureVisibleAtYear(featureOnQ1, 1400, periodMap, periodStartYears, "cumulative")).toBe(false);
    expect(isFeatureVisibleAtYear(alberta1900, 1400, periodMap, periodStartYears, "cumulative")).toBe(false);
  });

  it("supports global mode (all features visible regardless of date)", () => {
    const alberta1900: Feature = {
      type: "Feature",
      id: "feat-alberta",
      projectId: "p1",
      mapId: "q1",
      name: "ALBERTA",
      createdAt: "2026-01-01",
      updatedAt: "2026-01-01",
      geometry: { type: "Point", coordinates: [-114, 53] },
      properties: { name: "ALBERTA", startYear: 1900, endYear: 1900 },
    };
    const periodMap = new Map<string, SliderPeriod>([
      ["q1", { ...mapQ1, startYear: 1500, endYear: 1501 }],
    ]);
    const periodStartYears = new Set([1500, 1900]);

    expect(isFeatureVisibleAtYear(featureOnQ1, 1000, periodMap, periodStartYears, "global")).toBe(true);
    expect(isFeatureVisibleAtYear(alberta1900, 1000, periodMap, periodStartYears, "global")).toBe(true);
  });
});