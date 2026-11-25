import { ref, computed, watch, nextTick, type Ref } from "vue";
import type { Feature } from "../typescript/feature";
import type { MapPeriod, SliderPeriod } from "../typescript/map";
import { toYear, isPeriodActiveAt } from "../utils/dateUtils";
import { getFeatureMapIds } from "../utils/featureHelpers";

export type TimelineFilterMode = "specific" | "cumulative" | "global";

const LEGACY_GLOBAL_MODE_KEY = "atlas_timeline_filter_mode";

function timelineStorageKey(projectId: string): string {
  return `atlas_timeline_${projectId}`;
}

function readTimelineStorage(projectId: string): {
  year?: number;
  exactDate?: string | null;
  mode?: TimelineFilterMode;
} {
  try {
    const raw = localStorage.getItem(timelineStorageKey(projectId));
    if (raw) {
      const parsed = JSON.parse(raw) as {
        year?: unknown;
        exactDate?: unknown;
        mode?: unknown;
      };
      return {
        year: typeof parsed.year === "number" ? parsed.year : Number(parsed.year),
        exactDate: typeof parsed.exactDate === "string" ? parsed.exactDate : null,
        mode:
          parsed.mode === "specific" ||
          parsed.mode === "cumulative" ||
          parsed.mode === "global"
            ? parsed.mode
            : undefined,
      };
    }
    const yearRaw = localStorage.getItem(`atlas_timeline_year_${projectId}`);
    const exactRaw = localStorage.getItem(`atlas_timeline_exact_date_${projectId}`);
    const modeRaw =
      localStorage.getItem(`atlas_timeline_filter_mode_${projectId}`) ??
      localStorage.getItem(LEGACY_GLOBAL_MODE_KEY);
    return {
      year: yearRaw !== null ? Number(yearRaw) : undefined,
      exactDate: exactRaw,
      mode:
        modeRaw === "specific" ||
        modeRaw === "cumulative" ||
        modeRaw === "global"
          ? modeRaw
          : undefined,
    };
  } catch {
    return {};
  }
}

function writeTimelineStorage(
  projectId: string,
  state: { year: number; exactDate: string | null; mode: TimelineFilterMode },
) {
  localStorage.setItem(timelineStorageKey(projectId), JSON.stringify(state));
  localStorage.removeItem(`atlas_timeline_year_${projectId}`);
  localStorage.removeItem(`atlas_timeline_exact_date_${projectId}`);
  localStorage.removeItem(`atlas_timeline_filter_mode_${projectId}`);
}

export interface TimelineMilestone {
  year: number;
  label: string;
  type: "map" | "element";
  id?: string;
}

export interface UseMapTimelineOptions {
  features: Ref<Feature[]>;
  mapPeriods: Ref<MapPeriod[]>;
  currentMapTitle: Ref<string | undefined>;
  projectId?: Ref<string | undefined>;
  onFitVisibleFeatures?: () => void;
}

export function useMapTimeline({
  features,
  mapPeriods,
  currentMapTitle,
  projectId,
  onFitVisibleFeatures,
}: UseMapTimelineOptions) {
  const isValidTimelineMode = (m: string | null): m is TimelineFilterMode =>
    m === "specific" || m === "cumulative" || m === "global";

  const selectedYear = ref(-1);
  const selectedExactDate = ref<string | null>(null);
  const timelineMode = ref<TimelineFilterMode>("specific");
  const isRestoringPosition = ref(false);

  function beginTimelineRestore() {
    isRestoringPosition.value = true;
  }

  function clampYearToTimelineRange(year: number): number {
    const min = timelineMinYear.value;
    const max = timelineMaxYear.value;
    if (year < min) return min;
    if (year > max) return max;
    return year;
  }

  async function restoreTimelinePosition(id?: string) {
    const targetId = id ?? projectId?.value;
    if (!targetId || typeof window === "undefined") {
      isRestoringPosition.value = false;
      return;
    }
    isRestoringPosition.value = true;
    try {
      const stored = readTimelineStorage(targetId);
      if (stored.year !== undefined && Number.isFinite(stored.year) && stored.year >= 0) {
        selectedYear.value = clampYearToTimelineRange(stored.year);
        selectedExactDate.value = stored.exactDate || null;
      }
      const storedMode = stored.mode;
      timelineMode.value = isValidTimelineMode(storedMode ?? null)
        ? storedMode
        : "specific";
      await nextTick();
    } catch {
      // Ignore storage errors in restricted contexts
    } finally {
      isRestoringPosition.value = false;
    }
  }

  watch([selectedYear, selectedExactDate, timelineMode], ([year, exactDate, mode]) => {
    if (isRestoringPosition.value || !projectId?.value || year < 0) return;
    try {
      writeTimelineStorage(projectId.value, {
        year,
        exactDate: exactDate ?? null,
        mode,
      });
    } catch {
      // Ignore storage errors in restricted contexts
    }
  });

  const enrichedPeriods = computed<SliderPeriod[]>(() => {
    const mapIdsWithFeatures = new Set<string>();
    for (const f of features.value) {
      for (const mid of getFeatureMapIds(f)) {
        mapIdsWithFeatures.add(mid.toLowerCase());
      }
    }

    const periods: SliderPeriod[] = [];
    for (const p of mapPeriods.value) {
      const pIdNorm = String(p.id).trim().toLowerCase();
      if (mapIdsWithFeatures.size > 0 && !mapIdsWithFeatures.has(pIdNorm)) {
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
      }
    }
    return map;
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

    return list.sort(
      (a: TimelineMilestone, b: TimelineMilestone) => a.year - b.year,
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
    return enrichedPeriods.value.map((p: SliderPeriod) => p.startYear);
  });

  const allTimelineEndYears = computed(() => {
    return enrichedPeriods.value.map((p: SliderPeriod) => p.endYear);
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
    return [...markers].sort((a: number, b: number) => a - b);
  });

  const periodStartYears = computed(() => {
    return new Set<number>(
      enrichedPeriods.value.map((p: SliderPeriod) => p.startYear),
    );
  });

  const periodStartDates = computed(() => {
    return new Set<string>(
      enrichedPeriods.value
        .map((p: SliderPeriod) => p.startDate)
        .filter((date: string | null): date is string => Boolean(date)),
    );
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

  function resolvePeriodForKey(effectiveMapKey: string): SliderPeriod | undefined {
    const normalizedMapId = String(effectiveMapKey).trim().toLowerCase();
    return (
      periodByMapId.value.get(effectiveMapKey) ??
      periodByMapId.value.get(normalizedMapId) ??
      enrichedPeriods.value.find(
        (p: SliderPeriod) =>
          String(p.id).trim().toLowerCase() === normalizedMapId,
      )
    );
  }

  function isPeriodVisibleAtCurrentDate(period: SliderPeriod): boolean {
    if (timelineMode.value === "global") return true;

    if (timelineMode.value === "cumulative") {
      return period.startYear == null || period.startYear <= selectedYear.value;
    }

    if (selectedExactDate.value && period.startDate && period.endDate) {
      return isPeriodActiveAt(
        period.startDate,
        period.endDate,
        selectedExactDate.value,
        periodStartDates.value,
      );
    }

    if (period.startYear == null || period.endYear == null) {
      return true;
    }

    return isPeriodActiveAt(
      period.startYear,
      period.endYear,
      selectedYear.value,
      periodStartYears.value,
    );
  }

  /**
   * Whether `feature` is already visible at the current timeline position and mode.
   * Dates come from maps only: no mapId → all periods; with mapId → that map's dates.
   */
  function isFeatureVisibleOnTimeline(feature: Feature): boolean {
    if (timelineMode.value === "global") return true;

    const keys = getFeatureMapIds(feature);
    if (keys.length === 0) return true;

    return keys.some((effectiveMapKey: string) => {
      const period = resolvePeriodForKey(effectiveMapKey);
      if (!period) return false;
      return isPeriodVisibleAtCurrentDate(period);
    });
  }

  /**
   * Moves the timeline only when `feature` is not already visible at the current date.
   * Returns true if the timeline position changed.
   */
  function revealFeatureOnTimeline(feature: Feature): boolean {
    if (timelineMode.value === "global") return false;
    if (isFeatureVisibleOnTimeline(feature)) return false;

    const keys = getFeatureMapIds(feature);
    if (keys.length === 0) return false;

    const candidatePeriods = keys
      .map((key) => resolvePeriodForKey(key))
      .filter((period): period is SliderPeriod => period != null);

    if (candidatePeriods.length === 0) return false;

    const sortedCandidates = [...candidatePeriods].sort((a, b) => {
      const aYear = a.startYear ?? toYear(a.startDate) ?? 0;
      const bYear = b.startYear ?? toYear(b.startDate) ?? 0;
      if (aYear !== bYear) return aYear - bYear;
      return (a.startDate ?? "").localeCompare(b.startDate ?? "");
    });

    const targetPeriod = sortedCandidates[0];
    const targetYear = targetPeriod.startYear ?? toYear(targetPeriod.startDate);
    if (targetYear == null) return false;

    const targetExactDate =
      targetPeriod.exactDate && targetPeriod.startDate
        ? targetPeriod.startDate
        : null;

    const changed =
      targetYear !== selectedYear.value ||
      targetExactDate !== selectedExactDate.value;

    if (targetYear !== selectedYear.value) {
      selectedYear.value = targetYear;
    }
    selectedExactDate.value = targetExactDate;

    if (targetPeriod.title) {
      currentMapTitle.value = targetPeriod.title;
    }

    return changed;
  }

  const filteredFeatures = computed(() => {
    return features.value.filter(isFeatureVisibleOnTimeline);
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
    isFeatureVisibleOnTimeline,
    revealFeatureOnTimeline,
    onExactDateChange,
    beginTimelineRestore,
    restoreTimelinePosition,
    isRestoringPosition,
  };
}
