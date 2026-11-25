import { describe, it, expect, beforeEach } from "vitest";
import { ref } from "vue";
import { useMapTimeline } from "../../src/composables/useMapTimeline";
import type { Feature } from "../../src/typescript/feature";
import type { MapPeriod } from "../../src/typescript/map";

function makeFeature(
  id: string,
  mapId: string | null,
  mapIds?: string[],
): Feature {
  return {
    type: "Feature",
    id,
    projectId: "proj-1",
    mapId,
    ...(mapIds ? { mapIds } : {}),
    name: `Feature ${id}`,
    createdAt: "2026-01-01",
    updatedAt: "2026-01-01",
    geometry: {
      type: "Polygon",
      coordinates: [
        [
          [-71, 46],
          [-70, 46],
          [-70, 47],
          [-71, 47],
          [-71, 46],
        ],
      ],
    },
    properties: {
      name: `Feature ${id}`,
      mapElementType: "shape",
      mapId,
      ...(mapIds ? { mapIds } : {}),
    },
  };
}

describe("useMapTimeline - revealFeatureOnTimeline", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  const period1800: MapPeriod = {
    id: "map-1800",
    title: "Carte 1800",
    startDate: "1800-01-01",
    endDate: "1850-12-31",
    exactDate: false,
    color: "#0ea5e9",
  };

  const period1850: MapPeriod = {
    id: "map-1850",
    title: "Carte 1850",
    startDate: "1850-01-01",
    endDate: "1900-12-31",
    exactDate: false,
    color: "#10b981",
  };

  const period1875Mid: MapPeriod = {
    id: "map-1875",
    title: "Carte 1875",
    startDate: "1875-01-01",
    endDate: "1885-12-31",
    exactDate: false,
    color: "#8b5cf6",
  };

  const period1900: MapPeriod = {
    id: "map-1900",
    title: "Carte 1900",
    startDate: "1900-01-01",
    endDate: "1925-12-31",
    exactDate: false,
    color: "#f59e0b",
  };

  const period1900Jan: MapPeriod = {
    id: "map-1900-jan",
    title: "Carte Janvier 1900",
    startDate: "1900-01-15",
    endDate: "1900-01-15",
    exactDate: true,
    color: "#ef4444",
  };

  const period1900Jun: MapPeriod = {
    id: "map-1900-jun",
    title: "Carte Juin 1900",
    startDate: "1900-06-20",
    endDate: "1900-06-20",
    exactDate: true,
    color: "#14b8a6",
  };

  function setupTimeline(
    periods: MapPeriod[],
    featList: Feature[],
    initialYear: number,
    mode: "specific" | "cumulative" | "global",
    initialExactDate: string | null = null,
  ) {
    const features = ref<Feature[]>(featList);
    const mapPeriods = ref<MapPeriod[]>(periods);
    const currentMapTitle = ref<string | undefined>(undefined);
    const timeline = useMapTimeline({
      features,
      mapPeriods,
      currentMapTitle,
    });
    timeline.timelineMode.value = mode;
    timeline.selectedYear.value = initialYear;
    timeline.selectedExactDate.value = initialExactDate;
    return { ...timeline, currentMapTitle };
  }

  describe("cumulative mode", () => {
    it("stays at 1900 when selecting an already-visible feature from 1850", () => {
      const f1850 = makeFeature("f-1850", "map-1850");
      const f1900 = makeFeature("f-1900", "map-1900");
      const {
        selectedYear,
        selectedExactDate,
        isFeatureVisibleOnTimeline,
        revealFeatureOnTimeline,
      } = setupTimeline([period1850, period1900], [f1850, f1900], 1900, "cumulative");

      expect(isFeatureVisibleOnTimeline(f1850)).toBe(true);
      expect(revealFeatureOnTimeline(f1850)).toBe(false);
      expect(selectedYear.value).toBe(1900);
      expect(selectedExactDate.value).toBeNull();
    });

    it("advances from 1850 to 1900 when selecting a non-visible feature from 1900", () => {
      const f1850 = makeFeature("f-1850", "map-1850");
      const f1900 = makeFeature("f-1900", "map-1900");
      const {
        selectedYear,
        selectedExactDate,
        currentMapTitle,
        isFeatureVisibleOnTimeline,
        revealFeatureOnTimeline,
      } = setupTimeline([period1850, period1900], [f1850, f1900], 1850, "cumulative");

      expect(isFeatureVisibleOnTimeline(f1900)).toBe(false);
      expect(revealFeatureOnTimeline(f1900)).toBe(true);
      expect(selectedYear.value).toBe(1900);
      expect(selectedExactDate.value).toBeNull();
      expect(currentMapTitle.value).toBe("Carte 1900");
    });

    it("advances to the earliest period for shared multi-map features when not yet visible", () => {
      const f1800 = makeFeature("f-1800", "map-1800");
      const fShared = makeFeature("f-shared", "map-1900", ["map-1900", "map-1850"]);
      const { selectedYear, revealFeatureOnTimeline } = setupTimeline(
        [period1800, period1850, period1900],
        [f1800, fShared],
        1800,
        "cumulative",
      );

      expect(revealFeatureOnTimeline(fShared)).toBe(true);
      expect(selectedYear.value).toBe(1850);
    });
  });

  describe("specific mode", () => {
    it("stays in place when selecting a feature already visible in the middle of its period", () => {
      const f1850 = makeFeature("f-1850", "map-1850");
      const f1875 = makeFeature("f-1875", "map-1875");
      const {
        selectedYear,
        isFeatureVisibleOnTimeline,
        revealFeatureOnTimeline,
      } = setupTimeline([period1850, period1875], [f1850, f1875], 1875, "specific");

      expect(isFeatureVisibleOnTimeline(f1850)).toBe(true);
      expect(revealFeatureOnTimeline(f1850)).toBe(false);
      expect(selectedYear.value).toBe(1875);
    });

    it("jumps to the feature's period when it is not visible at the current year", () => {
      const f1850 = makeFeature("f-1850", "map-1850");
      const f1900 = makeFeature("f-1900", "map-1900");
      const {
        selectedYear,
        currentMapTitle,
        isFeatureVisibleOnTimeline,
        revealFeatureOnTimeline,
      } = setupTimeline([period1850, period1900], [f1850, f1900], 1850, "specific");

      expect(isFeatureVisibleOnTimeline(f1900)).toBe(false);
      expect(revealFeatureOnTimeline(f1900)).toBe(true);
      expect(selectedYear.value).toBe(1900);
      expect(currentMapTitle.value).toBe("Carte 1900");
    });

    it("respects half-open shared period bounds [start, end[ when deciding visibility", () => {
      // period1800 (1800-1850) meets period1850 (1850-1900) at 1850; 1850 belongs to period1850
      const f1800 = makeFeature("f-1800", "map-1800");
      const f1850 = makeFeature("f-1850", "map-1850");
      const {
        selectedYear,
        isFeatureVisibleOnTimeline,
        revealFeatureOnTimeline,
      } = setupTimeline([period1800, period1850], [f1800, f1850], 1850, "specific");

      expect(isFeatureVisibleOnTimeline(f1850)).toBe(true);
      expect(revealFeatureOnTimeline(f1850)).toBe(false);
      expect(selectedYear.value).toBe(1850);

      expect(isFeatureVisibleOnTimeline(f1800)).toBe(false);
      expect(revealFeatureOnTimeline(f1800)).toBe(true);
      expect(selectedYear.value).toBe(1800);
    });

    it("handles exactDate periods: stays when active and jumps to exactDate when hidden", () => {
      const fJan = makeFeature("f-jan", "map-1900-jan");
      const fJun = makeFeature("f-jun", "map-1900-jun");
      const {
        selectedYear,
        selectedExactDate,
        isFeatureVisibleOnTimeline,
        revealFeatureOnTimeline,
      } = setupTimeline(
        [period1900Jan, period1900Jun],
        [fJan, fJun],
        1900,
        "specific",
        "1900-01-15",
      );

      expect(isFeatureVisibleOnTimeline(fJan)).toBe(true);
      expect(revealFeatureOnTimeline(fJan)).toBe(false);
      expect(selectedExactDate.value).toBe("1900-01-15");

      expect(isFeatureVisibleOnTimeline(fJun)).toBe(false);
      expect(revealFeatureOnTimeline(fJun)).toBe(true);
      expect(selectedYear.value).toBe(1900);
      expect(selectedExactDate.value).toBe("1900-06-20");
    });

    it("stays in place for shared features already visible via a later map", () => {
      const fShared = makeFeature("f-shared", "map-1800", ["map-1800", "map-1900"]);
      const { selectedYear, isFeatureVisibleOnTimeline, revealFeatureOnTimeline } =
        setupTimeline([period1800, period1900], [fShared], 1900, "specific");

      expect(isFeatureVisibleOnTimeline(fShared)).toBe(true);
      expect(revealFeatureOnTimeline(fShared)).toBe(false);
      expect(selectedYear.value).toBe(1900);
    });
  });

  describe("global mode and general elements", () => {
    it("never moves the timeline in global mode", () => {
      const f1800 = makeFeature("f-1800", "map-1800");
      const f1900 = makeFeature("f-1900", "map-1900");
      const {
        selectedYear,
        selectedExactDate,
        isFeatureVisibleOnTimeline,
        revealFeatureOnTimeline,
      } = setupTimeline(
        [period1800, period1900],
        [f1800, f1900],
        1850,
        "global",
        "1850-05-01",
      );

      expect(isFeatureVisibleOnTimeline(f1800)).toBe(true);
      expect(isFeatureVisibleOnTimeline(f1900)).toBe(true);
      expect(revealFeatureOnTimeline(f1800)).toBe(false);
      expect(revealFeatureOnTimeline(f1900)).toBe(false);
      expect(selectedYear.value).toBe(1850);
      expect(selectedExactDate.value).toBe("1850-05-01");
    });

    it("never moves the timeline for general features with no mapId", () => {
      const fGeneral = makeFeature("f-gen", null);
      const { selectedYear, isFeatureVisibleOnTimeline, revealFeatureOnTimeline } =
        setupTimeline([period1800, period1900], [fGeneral], 1850, "specific");

      expect(isFeatureVisibleOnTimeline(fGeneral)).toBe(true);
      expect(revealFeatureOnTimeline(fGeneral)).toBe(false);
      expect(selectedYear.value).toBe(1850);
    });
  });
});
