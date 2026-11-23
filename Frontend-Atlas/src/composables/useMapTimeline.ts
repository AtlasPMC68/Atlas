import { ref, computed, watch, nextTick, type Ref } from "vue";
import type { Feature } from "../typescript/feature";
import type { MapPeriod, SliderPeriod, TimelineElementMarker } from "../typescript/map";
import { toYear, isPeriodActiveAt } from "../utils/dateUtils";
import { getFeatureMapId, getFeatureMapIds } from "../utils/featureHelpers";
import { isTextFeature } from "../utils/wordStyles";
import { rgbToHex } from "../utils/utils";

export type TimelineFilterMode = "specific" | "cumulative" | "global";

export interface TimelineMilestone {
  year: number;
  label: string;
  type: "map" | "element";
  id?: string;
}

export type TimelineMarkerItem = TimelineElementMarker & {
  isCustom?: boolean;
};

export function getFeatureCustomYears(f: Feature): {
  startYear: number | null;
  endYear: number | null;
} {
  const startYear =
    toYear(f.properties?.startYear) ??
    (f.properties?.startDate ? toYear(f.properties.startDate) : null);
  const endYear =
    toYear(f.properties?.endYear) ??
    (f.properties?.endDate ? toYear(f.properties.endDate) : null);

  return { startYear, endYear };
}

export interface UseMapTimelineOptions {
  features: Ref<Feature[]>;
  mapPeriods: Ref<MapPeriod[]>;
  currentMapTitle: Ref<string | undefined>;
  onFitVisibleFeatures?: () => void;
}

export function useMapTimeline({
  features,
  mapPeriods,
  currentMapTitle,
  onFitVisibleFeatures,
}: UseMapTimelineOptions) {
  const selectedYear = ref(-1);
  const selectedExactDate = ref<string | null>(null);

  const storedTimelineMode =
    typeof window !== "undefined"
      ? localStorage.getItem("atlas_timeline_filter_mode")
      : null;
  const timelineMode = ref<TimelineFilterMode>(
    storedTimelineMode === "specific" ||
      storedTimelineMode === "cumulative" ||
      storedTimelineMode === "global"
      ? storedTimelineMode
      : "specific",
  );

  watch(timelineMode, (mode: TimelineFilterMode) => {
    try {
      localStorage.setItem("atlas_timeline_filter_mode", mode);
    } catch {
      // Ignore storage errors in restricted contexts
    }
  });

  const enrichedPeriods = computed<SliderPeriod[]>(() => {
    const mapIdsWithFeatures = new Set<string>();
    for (const f of features.value) {
      const mid = getFeatureMapId(f);
      if (mid) mapIdsWithFeatures.add(mid.toLowerCase());
      const mapTitle =
        ("mapTitle" in f ? (f as { mapTitle?: string }).mapTitle : undefined) ||
        f.properties?.mapTitle;
      if (mapTitle) mapIdsWithFeatures.add(String(mapTitle).trim().toLowerCase());
    }

    const periods: SliderPeriod[] = [];
    for (const p of mapPeriods.value) {
      const pIdNorm = String(p.id).trim().toLowerCase();
      const pTitleNorm = p.title ? p.title.trim().toLowerCase() : "";
      if (
        mapIdsWithFeatures.size > 0 &&
        !mapIdsWithFeatures.has(pIdNorm) &&
        (!pTitleNorm || !mapIdsWithFeatures.has(pTitleNorm))
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
  });

  const periodByMapId = computed(() => {
    const map = new Map<string, SliderPeriod>();
    for (const p of mapPeriods.value) {
      const startYear = toYear(p.startDate);
      const endYear = toYear(p.endDate);
      if (startYear != null && endYear != null) {
        const enriched: SliderPeriod = {
          ...p,
          startYear,
          endYear,
        };
        map.set(p.id, enriched);
        map.set(String(p.id).trim().toLowerCase(), enriched);
        if (p.title) {
          map.set(p.title, enriched);
          map.set(p.title.trim().toLowerCase(), enriched);
        }
      }
    }
    return map;
  });

  const customFeatureYears = computed<number[]>(() => {
    const years: number[] = [];
    features.value.forEach((f: Feature) => {
      const { startYear, endYear } = getFeatureCustomYears(f);
      if (startYear != null) years.push(startYear);
      if (endYear != null) years.push(endYear);
    });
    return years;
  });

  const timelineElementMarkers = computed<TimelineMarkerItem[]>(() => {
    const list: TimelineMarkerItem[] = [];

    features.value.forEach((f: Feature) => {
      const { startYear, endYear } = getFeatureCustomYears(f);
      const effectiveStart = startYear ?? endYear;
      if (effectiveStart == null) return;

      const rawName =
        f.properties?.name?.trim() ||
        f.name?.trim() ||
        f.properties?.labelText?.trim();
      const hasName = Boolean(rawName);
      const effectiveName = hasName && rawName ? rawName : "Nom manquant";

      list.push({
        id: String(
          f.id ??
            f.properties?.id ??
            f.properties?.name ??
            f.properties?.labelText ??
            "",
        ),
        name: effectiveName,
        isNameMissing: !hasName,
        year: effectiveStart,
        startYear: startYear != null ? startYear : effectiveStart,
        endYear: endYear != null ? endYear : null,
        type:
          f.properties?.mapElementType ||
          (isTextFeature(f) ? "Texte" : "Élément"),
        color:
          f.properties?.colorHex ||
          (f.properties?.colorRgb ? rgbToHex(f.properties.colorRgb) : undefined),
        mapId: null,
        mapTitle: "Éléments généraux",
        isCustom: true,
      });
    });

    return list;
  });

  const sortedTimelineMilestones = computed<TimelineMilestone[]>(() => {
    const list: TimelineMilestone[] = [];
    const seen = new Set<string>();

    for (const p of enrichedPeriods.value) {
      const key = `map-${p.id}-${p.startYear}`;
      if (!seen.has(key)) {
        seen.add(key);
        list.push({
          year: p.startYear,
          label: p.title || `Carte (${p.startYear})`,
          type: "map",
          id: String(p.id),
        });
      }
    }

    for (const item of timelineElementMarkers.value) {
      const key = `element-${item.id}-${item.year}`;
      if (!seen.has(key)) {
        seen.add(key);
        list.push({
          year: item.year,
          label: item.name || `Élément (${item.year})`,
          type: "element",
          id: String(item.id),
        });
      }
    }

    return list.sort(
      (a: TimelineMilestone, b: TimelineMilestone) =>
        a.year - b.year || (a.type === "map" ? -1 : 1),
    );
  });

  const prevMilestone = computed<TimelineMilestone | null>(() => {
    const currentY = selectedYear.value;
    const earlier = sortedTimelineMilestones.value.filter(
      (m: TimelineMilestone) => m.year < currentY,
    );
    return earlier.length > 0 ? earlier[earlier.length - 1] : null;
  });

  const nextMilestone = computed<TimelineMilestone | null>(() => {
    const currentY = selectedYear.value;
    const later = sortedTimelineMilestones.value.filter(
      (m: TimelineMilestone) => m.year > currentY,
    );
    return later.length > 0 ? later[0] : null;
  });

  const hasPrevMilestone = computed<boolean>(() => prevMilestone.value != null);
  const hasNextMilestone = computed<boolean>(() => nextMilestone.value != null);

  function goToPrevMilestone() {
    if (!prevMilestone.value) return;
    selectedExactDate.value = null;
    selectedYear.value = prevMilestone.value.year;
    nextTick(() => {
      onFitVisibleFeatures?.();
    });
  }

  function goToNextMilestone() {
    if (!nextMilestone.value) return;
    selectedExactDate.value = null;
    selectedYear.value = nextMilestone.value.year;
    nextTick(() => {
      onFitVisibleFeatures?.();
    });
  }

  function onTimelineDateSelect() {
    nextTick(() => {
      onFitVisibleFeatures?.();
    });
  }

  const allTimelineStartYears = computed(() => {
    const years = enrichedPeriods.value.map((p: SliderPeriod) => p.startYear);
    return [...years, ...customFeatureYears.value];
  });

  const allTimelineEndYears = computed(() => {
    const years = enrichedPeriods.value.map((p: SliderPeriod) => p.endYear);
    return [...years, ...customFeatureYears.value];
  });

  const timelineMinYear = computed(() =>
    allTimelineStartYears.value.length
      ? Math.min(...allTimelineStartYears.value)
      : 1400,
  );

  const timelineMaxYear = computed(() =>
    allTimelineEndYears.value.length
      ? Math.max(...allTimelineEndYears.value)
      : new Date().getFullYear(),
  );

  const timelineMarkerYears = computed(() => {
    const markers = new Set<number>([
      timelineMinYear.value,
      timelineMaxYear.value,
    ]);
    enrichedPeriods.value.forEach((p: SliderPeriod) => {
      markers.add(p.startYear);
      markers.add(p.endYear);
    });
    customFeatureYears.value.forEach((y: number) => markers.add(y));
    return [...markers].sort((a: number, b: number) => a - b);
  });

  const periodStartYears = computed(() => {
    const years = new Set<number>(
      enrichedPeriods.value.map((p: SliderPeriod) => p.startYear),
    );
    features.value.forEach((f: Feature) => {
      const { startYear, endYear } = getFeatureCustomYears(f);
      const effectiveStart = startYear ?? endYear;
      if (effectiveStart != null) years.add(effectiveStart);
    });
    return years;
  });

  const periodStartDates = computed(() => {
    const dates = new Set<string>(
      enrichedPeriods.value
        .map((p: SliderPeriod) => p.startDate)
        .filter((date: string | null): date is string => Boolean(date)),
    );
    features.value.forEach((f: Feature) => {
      if (f.properties?.startDate) dates.add(f.properties.startDate);
    });
    return dates;
  });

  const activeMapPeriod = computed<SliderPeriod | null>(() => {
    if (selectedYear.value == null || selectedYear.value < 0) return null;
    if (selectedExactDate.value) {
      const match = enrichedPeriods.value.find(
        (p: SliderPeriod) =>
          p.startDate &&
          p.endDate &&
          isPeriodActiveAt(
            p.startDate,
            p.endDate,
            selectedExactDate.value!,
            periodStartDates.value,
          ),
      );
      if (match) return match;
    }
    const match = enrichedPeriods.value.find(
      (p: SliderPeriod) =>
        p.startYear != null &&
        p.endYear != null &&
        isPeriodActiveAt(
          p.startYear,
          p.endYear,
          selectedYear.value,
          periodStartYears.value,
        ),
    );
    return match ?? null;
  });

  watch(
    activeMapPeriod,
    (newPeriod: SliderPeriod | null) => {
      if (newPeriod?.title) {
        currentMapTitle.value = newPeriod.title;
      }
    },
    { immediate: true },
  );

  const filteredFeatures = computed(() => {
    return features.value.filter((feature: Feature) => {
      if (timelineMode.value === "global") return true;

      const { startYear: featStartYear, endYear: featEndYear } =
        getFeatureCustomYears(feature);
      const hasCustomYears = featStartYear != null || featEndYear != null;

      let isCustomActive = false;
      if (hasCustomYears) {
        const sy = featStartYear ?? (featEndYear as number);
        const ey = featEndYear ?? sy;

        if (timelineMode.value === "cumulative") {
          isCustomActive = sy <= selectedYear.value;
        } else if (
          selectedExactDate.value &&
          feature.properties?.startDate &&
          feature.properties?.endDate
        ) {
          isCustomActive = isPeriodActiveAt(
            feature.properties.startDate,
            feature.properties.endDate,
            selectedExactDate.value,
            periodStartDates.value,
          );
        } else {
          isCustomActive = isPeriodActiveAt(
            sy,
            ey,
            selectedYear.value,
            periodStartYears.value,
          );
        }
      }

      if (hasCustomYears) {
        return isCustomActive;
      }

      const featureMapIds = getFeatureMapIds(feature);
      const featureMapTitle =
        ("mapTitle" in feature ? (feature as { mapTitle?: string }).mapTitle : undefined) ||
        feature.properties?.mapTitle;
      const targetMapKeys =
        featureMapIds.length > 0
          ? featureMapIds
          : featureMapTitle
            ? [featureMapTitle]
            : [];

      if (targetMapKeys.length > 0) {
        return targetMapKeys.some((effectiveMapKey: string) => {
          const normalizedMapId = String(effectiveMapKey).trim().toLowerCase();
          const period =
            periodByMapId.value.get(effectiveMapKey) ??
            periodByMapId.value.get(normalizedMapId) ??
            enrichedPeriods.value.find(
              (p: SliderPeriod) =>
                String(p.id).trim().toLowerCase() === normalizedMapId ||
                p.title?.trim().toLowerCase() === normalizedMapId,
            );

          if (!period) return true;
          if (timelineMode.value === "cumulative") {
            return (
              period.startYear == null || period.startYear <= selectedYear.value
            );
          } else if (
            selectedExactDate.value &&
            period.startDate &&
            period.endDate
          ) {
            return isPeriodActiveAt(
              period.startDate,
              period.endDate,
              selectedExactDate.value,
              periodStartDates.value,
            );
          } else if (period.startYear == null || period.endYear == null) {
            return true;
          } else {
            return isPeriodActiveAt(
              period.startYear,
              period.endYear,
              selectedYear.value,
              periodStartYears.value,
            );
          }
        });
      }

      return true;
    });
  });

  function onExactDateChange(nextDate: string | null) {
    selectedExactDate.value = nextDate;
    nextTick(() => {
      onFitVisibleFeatures?.();
    });
  }

  return {
    selectedYear,
    selectedExactDate,
    timelineMode,
    enrichedPeriods,
    periodByMapId,
    customFeatureYears,
    timelineElementMarkers,
    sortedTimelineMilestones,
    prevMilestone,
    nextMilestone,
    hasPrevMilestone,
    hasNextMilestone,
    goToPrevMilestone,
    goToNextMilestone,
    onTimelineDateSelect,
    allTimelineStartYears,
    allTimelineEndYears,
    timelineMinYear,
    timelineMaxYear,
    timelineMarkerYears,
    periodStartYears,
    periodStartDates,
    activeMapPeriod,
    filteredFeatures,
    onExactDateChange,
  };
}
