<template>
  <div class="timeline-container">
    <div class="slider-wrap">
      <div ref="axisRef" class="slider-axis">
        <!-- Discreet legend + Date filters -->
        <div
          v-if="!isZoomMode"
          class="flex items-center justify-start gap-4 pb-1.5 text-[11px] text-base-content opacity-70 select-none flex-wrap"
        >
          <span v-if="displayedPeriods.length > 0" class="inline-flex items-center gap-1.5">
            <span class="inline-block w-8 h-2 rounded-full bg-gradient-to-r from-sky-500 via-emerald-500 to-amber-500 shadow-xs"></span>
            <span>Cartes</span>
          </span>

          <!-- 3 Date filter buttons -->
          <div class="inline-flex items-center gap-2 ml-2 pl-2 border-l border-base-300 relative z-[7000] pointer-events-auto">
            <span class="text-xs font-semibold text-base-content/80 select-none">
              Filtrer par date :
            </span>
            <div class="join border border-base-300 rounded-lg overflow-visible bg-base-100 shadow-xs relative z-[7000]">
              <button
                type="button"
                class="join-item btn btn-xs px-2.5 font-medium transition-colors rounded-none rounded-l-lg border-0"
                :class="currentMode === 'specific' ? 'btn-primary' : 'btn-ghost text-base-content/70 hover:text-base-content'"
                data-testid="timeline-mode-specific"
                title="Uniquement les cartes de la période sélectionnée"
                @click="setMode('specific')"
              >
                Spécifique
              </button>
              <button
                type="button"
                class="join-item btn btn-xs px-2.5 font-medium transition-colors rounded-none border-0"
                :class="currentMode === 'cumulative' ? 'btn-primary' : 'btn-ghost text-base-content/70 hover:text-base-content'"
                data-testid="timeline-mode-cumulative"
                title="Toutes les cartes jusqu'à la date choisie (historique cumulé)"
                @click="setMode('cumulative')"
              >
                Cumulatif
              </button>
              <button
                type="button"
                class="join-item btn btn-xs px-2.5 font-medium transition-colors rounded-none rounded-r-lg border-0"
                :class="currentMode === 'global' ? 'btn-primary' : 'btn-ghost text-base-content/70 hover:text-base-content'"
                data-testid="timeline-mode-global"
                title="Toutes les cartes, sans filtre de date"
                @click="setMode('global')"
              >
                Global
              </button>
            </div>
          </div>
        </div>

        <!-- Period tracks - update based on view mode -->
        <div class="period-tracks" :style="periodTracksStyle">
          <div
            v-for="period in displayedPeriods"
            :key="period.id"
            class="period-track cursor-pointer"
            :style="
              isZoomMode
                ? getDayZoomPeriodStyle(period)
                : getPeriodStyle(period.startYear, period.endYear, period.color, period.row)
            "
            @click="onPeriodClick(period)"
            @mouseenter="hoveredPeriodId = period.id"
            @mouseleave="hoveredPeriodId = null"
            @dblclick.stop="emit('edit-map', period.id)"
          >
            <div
              v-if="hoveredPeriodId === period.id"
              class="period-track-popover absolute bottom-full mb-1.5 left-1/2 -translate-x-1/2 pointer-events-none rounded-xl border border-gray-300 bg-base-100 px-3 py-1.5 text-xs text-base-content shadow-lg whitespace-nowrap z-[6000]"
            >
              <div class="font-semibold text-center">{{ period.title }}</div>
              <div class="text-base-content opacity-70 text-center">
                {{
                  isZoomMode
                    ? `${period.startDate} - ${period.endDate}`
                    : `${period.startYear} - ${period.endYear}`
                }}
              </div>
            </div>
          </div>
        </div>

        <!-- Year-level slider (hidden during zoom) -->
        <template v-if="!isZoomMode">
          <input
            type="range"
            :min="min"
            :max="max"
            step="1"
            v-model.number="internalYear"
            @input="onSliderInput"
            class="timeline-year-range timeline-range w-full"
            :class="`timeline-range--${currentMode}`"
            :style="sliderTrackStyle"
          />

          <div class="ticks-row">
            <span
              v-for="tick in displayedTickMarks"
              :key="`tick-${tick}`"
              class="tick-mark"
              :style="getYearMarkerStyle(tick)"
              >|</span
            >
          </div>
          <div class="labels-row" :style="{ height: `${yearLabelLaneCount * 1.1}rem` }">
            <button
              v-for="label in yearLabels"
              :key="label.key"
              type="button"
              class="tick-label tick-label-button"
              :class="{
                'tick-label-active': isLabelActive(label),
              }"
              :style="label.style"
              :title="label.title"
              :aria-pressed="isLabelActive(label)"
              @click="selectYear(label.targetYear)"
            >
              {{ label.text }}
            </button>
          </div>
        </template>

        <!-- Day/month-level slider (shown during zoom) -->
        <template v-else>
          <input
            type="range"
            :min="0"
            :max="dayZoomSpanDays"
            step="1"
            v-model.number="dayZoomOffset"
            @input="onDayZoomInput"
            class="timeline-day-range timeline-range w-full"
            :class="`timeline-range--${currentMode}`"
            :style="sliderTrackStyle"
          />

          <div class="ticks-row">
            <span
              v-for="tick in dayTickValues"
              :key="`day-tick-${tick.date}`"
              class="tick-mark"
              :style="getDayMarkerStyle(tick.days)"
              >|</span
            >
          </div>
          <div class="labels-row day-labels-row">
            <span
              v-for="tick in dayTickValues"
              :key="`day-label-${tick.date}`"
              class="tick-label"
              :style="getDayLabelStyle(tick.days, tick.lane)"
              >{{ tick.label }}</span
            >
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { parseIsoDateUtc, toIsoDateUtc } from "../utils/dateUtils";
import type { DayTick, SliderPeriod, TimelineElementMarker } from "../typescript/map";

export type TimelineMarkerItem = TimelineElementMarker & {
  isCustom?: boolean;
};

const props = defineProps<{
  year: number;
  min: number;
  max: number;
  markerYears?: number[];
  currentExactDate?: string | null;
  mapPeriods?: SliderPeriod[];
  elementMarkers?: TimelineMarkerItem[];
  filterByDate?: boolean;
  mode?: "specific" | "cumulative" | "global";
  selectedFeatureId?: string | null;
  multiSelectedFeatureIds?: string[];
}>();

const emit = defineEmits([
  "update:year",
  "update:mode",
  "exact-date-change",
  "edit-map",
  "select-map",
  "edit-element",
  "select-element",
  "select-elements",
  "select-date",
]);

function onPeriodClick(period: SliderPeriod) {
  if (period.exactDate && period.startDate) {
    emit("exact-date-change", period.startDate);
  } else {
    emit("exact-date-change", null);
  }
  selectYear(period.startYear);
  emit("select-map", period.id);
}

function setMode(newMode: "specific" | "cumulative" | "global") {
  emit("update:mode", newMode);
}

const currentMode = computed<"specific" | "cumulative" | "global">(() => {
  if (props.mode) return props.mode;
  if (props.filterByDate !== undefined) {
    return props.filterByDate ? "specific" : "global";
  }
  return "specific";
});

const internalYear = ref(props.year || props.min);
const hoveredPeriodId = ref<string | null>(null);
const dayZoomOffset = ref(0);
const yearTraversalDirection = ref<"forward" | "backward">("forward");
const lastYearSelection = ref(props.year || props.min);

const sliderProgressPct = computed(() => {
  const min = props.min;
  const max = props.max;
  if (max <= min) return 0;
  const val = isZoomMode.value ? dayZoomOffset.value : internalYear.value;
  const rangeMin = isZoomMode.value ? 0 : min;
  const rangeMax = isZoomMode.value ? dayZoomSpanDays.value : max;
  return Math.max(0, Math.min(100, ((val - rangeMin) / (rangeMax - rangeMin)) * 100));
});

const sliderTrackStyle = computed<Record<string, string>>(() => {
  if (currentMode.value === "cumulative") {
    const pct = sliderProgressPct.value;
    return {
      background: `linear-gradient(to right, var(--color-primary) 0%, var(--color-primary) ${pct}%, #e2e8f0 ${pct}%, #e2e8f0 100%)`,
    };
  }
  if (currentMode.value === "global") {
    return {
      background: "var(--color-primary)",
    };
  }
  return {
    background: "#e2e8f0",
  };
});

const markerYears = computed(() => {
  const values = (props.markerYears ?? []).filter(
    (v: number) => Number.isFinite(v) && v >= props.min && v <= props.max,
  );
  const periodYears = (props.mapPeriods ?? [])
    .flatMap((p: SliderPeriod) => [p.startYear, p.endYear])
    .filter((v: number) => Number.isFinite(v) && v >= props.min && v <= props.max);
  const merged = [...values, ...periodYears, props.min, props.max];
  return [...new Set(merged)].sort((a, b) => a - b);
});

const displayedTickMarks = computed(() => markerYears.value);

const YEAR_LABEL_MIN_GAP_PX = 38;
const YEAR_LABEL_MAX_LANES = 4;
const YEAR_LABEL_FALLBACK_AXIS_WIDTH_PX = 900;

const axisRef = ref<HTMLElement | null>(null);
const axisWidthPx = ref(YEAR_LABEL_FALLBACK_AXIS_WIDTH_PX);
let axisResizeObserver: ResizeObserver | null = null;

function measureAxis() {
  const width = axisRef.value?.clientWidth ?? 0;
  if (width > 0) axisWidthPx.value = width;
}

onMounted(() => {
  measureAxis();
  if (typeof ResizeObserver === "undefined" || !axisRef.value) return;
  axisResizeObserver = new ResizeObserver(measureAxis);
  axisResizeObserver.observe(axisRef.value);
});

onBeforeUnmount(() => {
  axisResizeObserver?.disconnect();
  axisResizeObserver = null;
});

export interface YearLabelItem {
  key: string;
  text: string;
  title: string;
  startYear: number;
  endYear: number;
  targetYear: number;
  years: number[];
  lane: number;
  style: Record<string, string>;
}

function isLabelActive(label: YearLabelItem): boolean {
  return (
    label.years.includes(internalYear.value) ||
    (internalYear.value >= label.startYear && internalYear.value <= label.endYear)
  );
}

const yearLabels = computed<YearLabelItem[]>(() => {
  if (markerYears.value.length === 0) return [];

  const minGapPercent = (YEAR_LABEL_MIN_GAP_PX / axisWidthPx.value) * 100;

  // 1. Initialize with distinct entry per year
  let entries: {
    startYear: number;
    endYear: number;
    years: number[];
  }[] = markerYears.value.map((y: number) => ({
    startYear: y,
    endYear: y,
    years: [y],
  }));

  // 2. Collision detection: if labels saturate all 4 lanes at a given location,
  // merge all colliding entries in that zone into a single overall interval (e.g. 1600 - 1605)
  let maxPasses = 50;
  while (maxPasses-- > 0) {
    const laneEnds: number[] = new Array(YEAR_LABEL_MAX_LANES).fill(-Infinity);
    let collisionIndex = -1;

    for (let i = 0; i < entries.length; i++) {
      const entry = entries[i];
      const startPos = positionForYear(entry.startYear);
      const endPos = positionForYear(entry.endYear);
      const centerPos = (startPos + endPos) / 2;
      const isRange = entry.startYear !== entry.endYear;
      const requiredGapPercent = isRange ? minGapPercent * 1.4 : minGapPercent;

      let bestLane = -1;
      for (let l = 0; l < YEAR_LABEL_MAX_LANES; l++) {
        if (centerPos - laneEnds[l] >= minGapPercent) {
          bestLane = l;
          break;
        }
      }

      if (bestLane === -1) {
        // None of the 4 lanes is free at this spot: collision!
        collisionIndex = i;
        break;
      }

      laneEnds[bestLane] = centerPos + (isRange ? requiredGapPercent * 0.4 : 0);
    }

    if (collisionIndex === -1) {
      // All dates fit across the 4 lanes without overlap
      break;
    }

    // When no space is left across the 4 lanes and collision occurs,
    // identify the contiguous group of items in that space
    // to merge the entire cluster into one complete interval (e.g. 1600 - 1605)
    let startIdx = collisionIndex;
    while (startIdx > 0) {
      const curPos = positionForYear(entries[startIdx].startYear);
      const prevEndPos = positionForYear(entries[startIdx - 1].endYear);
      if (curPos - prevEndPos < minGapPercent) {
        startIdx--;
      } else {
        break;
      }
    }

    let endIdx = collisionIndex;
    while (endIdx < entries.length - 1) {
      const curEndPos = positionForYear(entries[endIdx].endYear);
      const nextPos = positionForYear(entries[endIdx + 1].startYear);
      if (nextPos - curEndPos < minGapPercent) {
        endIdx++;
      } else {
        break;
      }
    }

    if (startIdx === endIdx) {
      if (startIdx > 0) startIdx--;
      else if (endIdx < entries.length - 1) endIdx++;
    }

    const mergedYears: number[] = [];
    for (let k = startIdx; k <= endIdx; k++) {
      mergedYears.push(...entries[k].years);
    }

    const merged = {
      startYear: entries[startIdx].startYear,
      endYear: entries[endIdx].endYear,
      years: [...new Set(mergedYears)].sort((a, b) => a - b),
    };
    entries.splice(startIdx, endIdx - startIdx + 1, merged);
  }

  // 3. Final lane assignment for resolved labels
  const laneEnds: number[] = new Array(YEAR_LABEL_MAX_LANES).fill(-Infinity);
  return entries.map((entry) => {
    const startPos = positionForYear(entry.startYear);
    const endPos = positionForYear(entry.endYear);
    const centerPos = (startPos + endPos) / 2;
    const isRange = entry.startYear !== entry.endYear;
    const text = isRange ? `${entry.startYear} - ${entry.endYear}` : `${entry.startYear}`;

    let lane = -1;
    for (let l = 0; l < YEAR_LABEL_MAX_LANES; l++) {
      if (centerPos - laneEnds[l] >= minGapPercent) {
        lane = l;
        break;
      }
    }
    if (lane === -1) {
      lane = laneEnds.indexOf(Math.min(...laneEnds));
    }
    laneEnds[lane] = centerPos + (isRange ? minGapPercent * 0.7 : 0);

    const targetYear = entry.years.includes(internalYear.value)
      ? internalYear.value
      : entry.startYear;

    return {
      key: `label-${entry.startYear}-${entry.endYear}`,
      text,
      title: isRange
        ? `Aller à ${entry.startYear} - ${entry.endYear}`
        : `Aller à ${entry.startYear}`,
      startYear: entry.startYear,
      endYear: entry.endYear,
      targetYear,
      years: entry.years,
      lane,
      style: {
        ...markerStyleFromPercent(centerPos),
        top: `${lane * 1.05}rem`,
      },
    };
  });
});

const yearLabelLaneCount = computed(() =>
  Math.max(1, ...yearLabels.value.map((label: YearLabelItem) => label.lane + 1)),
);

const PERIOD_ROW_HEIGHT_REM = 0.22;
const PERIOD_ROW_GAP_REM = 0.12;
const PERIOD_PADDING_REM = 0.2;

const isZoomMode = computed(() => dayZoomWindow.value != null);

const positionedPeriods = computed(() => {
  const sorted = [...(props.mapPeriods ?? [])].sort(
    (a, b) => a.startYear - b.startYear || a.endYear - b.endYear,
  );

  return sorted.map((period, index) => ({
    ...period,
    row: index,
  }));
});

const displayedPeriods = computed(() => {
  if (!isZoomMode.value) {
    return positionedPeriods.value;
  }

  const year = internalYear.value;
  return positionedPeriods.value.filter(
    (period: SliderPeriod) =>
      period.startYear <= year && period.endYear >= year,
  );
});

const rowCount = computed(() => {
  if (!displayedPeriods.value.length) return 1;
  return Math.max(
    ...displayedPeriods.value.map((period: { row: number }) => period.row + 1),
  );
});

const periodTracksStyle = computed(() => {
  const rows = rowCount.value;
  const height =
    rows * PERIOD_ROW_HEIGHT_REM +
    Math.max(0, rows - 1) * PERIOD_ROW_GAP_REM +
    PERIOD_PADDING_REM * 2;

  return { height: `${height}rem` };
});

const exactDatesForYear = computed(() => {
  const year = internalYear.value;
  const exactDateSet = new Set<string>();

  (props.mapPeriods ?? []).forEach((period: SliderPeriod) => {
    if (!period.exactDate) return;

    if (period.startYear === year) {
      const d = parseIsoDateUtc(period.startDate);
      if (d) exactDateSet.add(toIsoDateUtc(d));
    }

    if (period.endYear === year) {
      const d = parseIsoDateUtc(period.endDate);
      if (d) exactDateSet.add(toIsoDateUtc(d));
    }
  });

  return [...exactDateSet]
    .map((iso) => parseIsoDateUtc(iso))
    .filter((d): d is Date => !!d)
    .sort((a, b) => a.getTime() - b.getTime());
});

const dayTickValues = computed(() => {
  const window = dayZoomWindow.value;
  if (!window) return [];

  const ticks: DayTick[] = [];

  ticks.push({
    date: toIsoDateUtc(window.minDate),
    label: String(props.min),
    days: 0,
    lane: 0,
    isExactDate: false,
  });

  let prevPercent = -100;
  let prevLane = 0;

  exactDatesForYear.value.forEach((date: Date) => {
    const iso = toIsoDateUtc(date);
    const days = Math.round(
      (date.getTime() - window.minDate.getTime()) / 86_400_000,
    );
    if (days < 0 || days > window.spanDays) return;

    const percent = positionForDay(days);
    const tooClose = percent - prevPercent < 10;
    const lane = tooClose ? (prevLane === 0 ? 1 : 0) : 0;

    ticks.push({
      date: iso,
      label: `${date.getUTCDate()} ${getMonthName(date.getUTCMonth())} ${date.getUTCFullYear()}`,
      days,
      lane,
      isExactDate: true,
    });

    prevPercent = percent;
    prevLane = lane;
  });

  if (window.spanDays > 0) {
    ticks.push({
      date: toIsoDateUtc(window.maxDate),
      label: String(props.max),
      days: window.spanDays,
      lane: 0,
      isExactDate: false,
    });
  }

  return ticks;
});

function getMonthName(monthIndex: number): string {
  const names = [
    "Janvier",
    "Février",
    "Mars",
    "Avril",
    "Mai",
    "Juin",
    "Juillet",
    "Août",
    "Septembre",
    "Octobre",
    "Novembre",
    "Décembre",
  ];
  return names[monthIndex] || "";
}

const dayZoomWindow = computed(() => {
  if (exactDatesForYear.value.length < 2) return null;

  const minDate = exactDatesForYear.value[0];
  const maxDate = exactDatesForYear.value[exactDatesForYear.value.length - 1];

  const expandedMin = new Date(
    Date.UTC(minDate.getUTCFullYear(), minDate.getUTCMonth() - 1, 1),
  );
  const expandedMax = new Date(
    Date.UTC(maxDate.getUTCFullYear(), maxDate.getUTCMonth() + 2, 0),
  );

  const spanDays = Math.round(
    (expandedMax.getTime() - expandedMin.getTime()) / 86_400_000,
  );
  if (spanDays <= 0) return null;

  return { minDate: expandedMin, maxDate: expandedMax, spanDays };
});

const dayZoomSpanDays = computed(() => dayZoomWindow.value?.spanDays ?? 0);

const dayStepOffsets = computed(() =>
  dayTickValues.value.map((tick: { days: number }) => tick.days),
);

const dayStepInitialOffset = computed(() => {
  const exactTicks = dayTickValues.value.filter(
    (tick: { days: number; isExactDate: boolean }) => tick.isExactDate,
  );

  if (!exactTicks.length) return 0;

  const currentExactDate = parseIsoDateUtc(props.currentExactDate);
  if (currentExactDate) {
    const currentExactIso = toIsoDateUtc(currentExactDate);
    const matched = exactTicks.find(
      (tick: { date: string; days: number; lane: number; isExactDate: boolean }) =>
        tick.date === currentExactIso,
    );
    if (matched) return matched.days;
  }

  if (yearTraversalDirection.value === "backward") {
    return exactTicks[exactTicks.length - 1].days;
  }

  return exactTicks[0].days;
});

const dayZoomCurrentDate = computed(() => {
  const window = dayZoomWindow.value;
  if (!window) return null;
  const offset = Math.min(Math.max(dayZoomOffset.value, 0), window.spanDays);
  return new Date(window.minDate.getTime() + offset * 86_400_000);
});

function snapDayZoomOffset(value: number): number {
  if (!dayStepOffsets.value.length) return value;

  let bestOffset = dayStepOffsets.value[0];
  let bestDiff = Math.abs(value - bestOffset);

  for (let i = 1; i < dayStepOffsets.value.length; i++) {
    const candidate = dayStepOffsets.value[i];
    const diff = Math.abs(value - candidate);
    if (diff < bestDiff) {
      bestOffset = candidate;
      bestDiff = diff;
    }
  }

  return bestOffset;
}

function isBoundaryOffset(value: number): boolean {
  const window = dayZoomWindow.value;
  if (!window) return false;
  return value <= 0 || value >= window.spanDays;
}

function exitToYearModeAtBoundary(value: number) {
  const window = dayZoomWindow.value;
  if (!window) return;

  const boundaryYear = value <= 0 ? props.min : props.max;
  emit("update:year", boundaryYear);
  emit("exact-date-change", null);
}

function clampToRange(value: number): number {
  return Math.min(Math.max(value, props.min), props.max);
}

function snapToMarker(value: number): number {
  const clamped = clampToRange(value);
  const markers = markerYears.value;
  if (!markers.length) return clamped;

  let best = markers[0];
  let bestDiff = Math.abs(clamped - best);

  for (let i = 1; i < markers.length; i++) {
    const candidate = markers[i];
    const diff = Math.abs(clamped - candidate);
    if (diff < bestDiff) {
      best = candidate;
      bestDiff = diff;
    }
  }

  return best;
}

function markerStyleFromPercent(left: number) {
  return {
    left: `calc(0.425rem + (100% - 0.85rem) * ${left / 100})`,
    transform: "translateX(-50%)",
  };
}

function positionForYear(year: number): number {
  if (props.max <= props.min) return 0;
  const ratio = (year - props.min) / (props.max - props.min);
  return Math.min(100, Math.max(0, ratio * 100));
}

function getYearMarkerStyle(year: number) {
  return markerStyleFromPercent(positionForYear(year));
}

function positionForDay(days: number): number {
  const span = dayZoomSpanDays.value;
  if (span <= 0) return 0;
  const ratio = days / span;
  return Math.min(100, Math.max(0, ratio * 100));
}

function getDayMarkerStyle(days: number) {
  return markerStyleFromPercent(positionForDay(days));
}

function getDayLabelStyle(days: number, lane: number) {
  const base = getDayMarkerStyle(days);
  return {
    ...base,
    top: lane === 1 ? "0.9rem" : "0",
  };
}

function getPeriodStyle(
  startYear: number,
  endYear: number,
  color: string,
  index: number,
) {
  const left = positionForYear(startYear);
  const right = positionForYear(endYear);
  const width = Math.max(0.8, right - left);
  const bottom =
    PERIOD_PADDING_REM +
    index * (PERIOD_ROW_HEIGHT_REM + PERIOD_ROW_GAP_REM);

  return {
    left: `${left}%`,
    width: `${width}%`,
    backgroundColor: color,
    bottom: `${bottom}rem`,
    height: `${PERIOD_ROW_HEIGHT_REM}rem`,
  };
}

function getDayZoomPeriodStyle(period: {
  startDate?: string | null;
  endDate?: string | null;
  color: string;
  row: number;
}) {
  const window = dayZoomWindow.value;
  if (!window) return getPeriodStyle(0, 0, period.color, period.row);

  const startDate = parseIsoDateUtc(period.startDate);
  const endDate = parseIsoDateUtc(period.endDate);

  if (!startDate || !endDate) {
    return getPeriodStyle(0, 0, period.color, period.row);
  }

  const startDays = Math.max(
    0,
    Math.round((startDate.getTime() - window.minDate.getTime()) / 86_400_000),
  );
  const endDays = Math.max(
    0,
    Math.round((endDate.getTime() - window.minDate.getTime()) / 86_400_000),
  );

  const left = positionForDay(startDays);
  const right = positionForDay(endDays);
  const width = Math.max(0.8, right - left);
  const bottom =
    PERIOD_PADDING_REM +
    period.row * (PERIOD_ROW_HEIGHT_REM + PERIOD_ROW_GAP_REM);

  return {
    left: `${left}%`,
    width: `${width}%`,
    backgroundColor: period.color,
    bottom: `${bottom}rem`,
    height: `${PERIOD_ROW_HEIGHT_REM}rem`,
  };
}

watch(
  () => props.year,
  (val: number, oldVal: number | undefined) => {
    if (val !== internalYear.value) {
      if (typeof oldVal === "number") {
        yearTraversalDirection.value = val >= oldVal ? "forward" : "backward";
      }
      internalYear.value = snapToMarker(val);
      lastYearSelection.value = internalYear.value;
    }
  },
);

watch([() => props.min, () => props.max], () => {
  const clamped = clampToRange(internalYear.value);
  if (clamped !== internalYear.value) {
    internalYear.value = clamped;
    emit("update:year", clamped);
  }
});

watch(markerYears, () => {
  const nextSnapped = snapToMarker(internalYear.value);
  if (nextSnapped !== internalYear.value) {
    internalYear.value = nextSnapped;
    emit("update:year", nextSnapped);
  }
});

function selectYear(year: number) {
  internalYear.value = year;
  onSliderInput();
  emit("select-date", year);
}

function onSliderInput() {
  yearTraversalDirection.value =
    internalYear.value >= lastYearSelection.value ? "forward" : "backward";
  lastYearSelection.value = internalYear.value;
  internalYear.value = snapToMarker(internalYear.value);
  emit("update:year", internalYear.value);
}

function onDayZoomInput() {
  dayZoomOffset.value = snapDayZoomOffset(dayZoomOffset.value);
  if (isBoundaryOffset(dayZoomOffset.value)) {
    exitToYearModeAtBoundary(dayZoomOffset.value);
    return;
  }

  const d = dayZoomCurrentDate.value;
  emit("exact-date-change", d ? toIsoDateUtc(d) : null);
}

watch(
  dayZoomWindow,
  (window: { minDate: Date; maxDate: Date; spanDays: number } | null) => {
    if (!window) {
      dayZoomOffset.value = 0;
      emit("exact-date-change", null);
      return;
    }

    dayZoomOffset.value = dayStepInitialOffset.value;
    const current = dayZoomCurrentDate.value;
    emit("exact-date-change", current ? toIsoDateUtc(current) : null);
  },
);
</script>