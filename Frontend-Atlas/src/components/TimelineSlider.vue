<template>
  <div class="timeline-container">
    <div class="slider-wrap">
      <div class="slider-axis">
        <!-- Period tracks - update based on view mode -->
        <div class="period-tracks" :style="periodTracksStyle">
          <div
            v-for="period in displayedPeriods"
            :key="period.id"
            class="period-track tooltip tooltip-top"
            :class="{ 'tooltip-open': hoveredPeriodId === period.id }"
            :style="isZoomMode ? getDayZoomPeriodStyle(period) : getPeriodStyle(period.startYear, period.endYear, period.color, period.row)"
            :data-tip="`${period.title} (${isZoomMode ? period.startDate : period.startYear} - ${isZoomMode ? period.endDate : period.endYear})`"
            @mouseenter="hoveredPeriodId = period.id"
            @mouseleave="hoveredPeriodId = null"
          >
            <div
              class="tooltip-content pointer-events-auto rounded-box bg-base-100 px-3 py-2 text-xs text-base-content shadow-lg whitespace-nowrap"
              @mouseenter="hoveredPeriodId = period.id"
              @mouseleave="hoveredPeriodId = null"
            >
              <div class="font-semibold">{{ period.title }}</div>
              <div>{{ isZoomMode ? `${period.startDate} - ${period.endDate}` : `${period.startYear} - ${period.endYear}` }}</div>
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
            class="timeline-year-range range range-primary range-sm w-full"
          />

          <div class="ticks-row">
            <span
              v-for="tick in markerYears"
              :key="`tick-${tick}`"
              class="tick-mark"
              :style="getYearMarkerStyle(tick)"
              >|</span
            >
          </div>
          <div class="labels-row">
            <span
              v-for="tick in markerYears"
              :key="`label-${tick}`"
              class="tick-label"
              :style="getYearMarkerStyle(tick)"
              >{{ tick }}</span
            >
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
            class="timeline-day-range range range-primary range-sm w-full"
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
import { computed, ref, watch } from "vue";
import { parseIsoDateUtc, toIsoDateUtc } from "../utils/dateUtils";
import type { SliderPeriod } from "../typescript/map";

type DayTick = {
  date: string;
  label: string;
  days: number;
  lane: number;
  isExactDate: boolean;
};

const props = defineProps<{
  year: number;
  min: number;
  max: number;
  markerYears?: number[];
  currentExactDate?: string | null;
  mapPeriods?: SliderPeriod[];
}>();

const emit = defineEmits(["update:year", "exact-date-change"]);
const internalYear = ref(props.year || props.min);
const hoveredPeriodId = ref<string | null>(null);
const dayZoomOffset = ref(0);
const yearTraversalDirection = ref<"forward" | "backward">("forward");
const lastYearSelection = ref(props.year || props.min);

const markerYears = computed(() => {
  const values = (props.markerYears ?? []).filter(
    (v: number) => Number.isFinite(v) && v >= props.min && v <= props.max,
  );
  const merged = [...values, props.min, props.max];
  return [...new Set(merged)].sort((a, b) => a - b);
});

const PERIOD_ROW_HEIGHT_REM = 0.35;
const PERIOD_ROW_GAP_REM = 0.2;
const PERIOD_PADDING_REM = 0.35;

// Determine if we're in zoom mode (when day zoom window exists)
const isZoomMode = computed(() => dayZoomWindow.value != null);

const positionedPeriods = computed(() => {
  const sorted = [...(props.mapPeriods ?? [])].sort(
    (a, b) => a.startYear - b.startYear || a.endYear - b.endYear,
  );

  const rowEndYears: number[] = [];

  return sorted.map((period) => {
    // Reuse first row where the period starts after the row's last end year.
    let row = rowEndYears.findIndex((endYear) => period.startYear > endYear);

    if (row === -1) {
      row = rowEndYears.length;
      rowEndYears.push(period.endYear);
    } else {
      rowEndYears[row] = Math.max(rowEndYears[row], period.endYear);
    }

    return { ...period, row };
  });
});

// Filter periods based on view mode
const displayedPeriods = computed(() => {
  if (!isZoomMode.value) {
    return positionedPeriods.value;
  }

  // In zoom mode, show only periods that overlap the current zoomed year
  const year = internalYear.value;
  return positionedPeriods.value.filter(
    (period: SliderPeriod) =>
      period.startYear <= year && period.endYear >= year,
  );
});

const rowCount = computed(() => {
  if (!displayedPeriods.value.length) return 1;
  return Math.max(...displayedPeriods.value.map((period: { row: number }) => period.row + 1));
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

// Generate exact start/end date ticks for the day zoom view.
const dayTickValues = computed(() => {
  const window = dayZoomWindow.value;
  if (!window) return [];

  const ticks: DayTick[] = [];

  // Add the two edge stops so the thumb can escape back to year mode.
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
    const days = Math.round((date.getTime() - window.minDate.getTime()) / 86_400_000);
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
  const names = ["Janvier", "Fevrier", "Mars", "Avril", "Mai", "Juin", "Juillet", "Aout", "Septembre", "Octobre", "Novembre", "Decembre"];
  return names[monthIndex] || "";
}

const dayZoomWindow = computed(() => {
  if (exactDatesForYear.value.length < 2) return null;

  const minDate = exactDatesForYear.value[0];
  const maxDate = exactDatesForYear.value[exactDatesForYear.value.length - 1];

  // Expand range to full months: start of previous month to end of next month
  const expandedMin = new Date(Date.UTC(minDate.getUTCFullYear(), minDate.getUTCMonth() - 1, 1));
  const expandedMax = new Date(Date.UTC(maxDate.getUTCFullYear(), maxDate.getUTCMonth() + 2, 0)); // Last day of next month

  const spanDays = Math.round((expandedMax.getTime() - expandedMin.getTime()) / 86_400_000);
  if (spanDays <= 0) return null;

  return { minDate: expandedMin, maxDate: expandedMax, spanDays };
});

const dayZoomSpanDays = computed(() => dayZoomWindow.value?.spanDays ?? 0);

const dayStepOffsets = computed(() => dayTickValues.value.map((tick: { days: number }) => tick.days));

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
  let transform = "translateX(-50%)";
  if (left <= 0) transform = "translateX(0)";
  if (left >= 100) transform = "translateX(-100%)";

  return {
    left: `${left}%`,
    transform,
  };
}

// Year-level positioning
function positionForYear(year: number): number {
  if (props.max <= props.min) return 0;
  const ratio = (year - props.min) / (props.max - props.min);
  return Math.min(100, Math.max(0, ratio * 100));
}

function getYearMarkerStyle(year: number) {
  return markerStyleFromPercent(positionForYear(year));
}

// Day-level positioning
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

// Day-level period styling (when in zoom mode)
function getDayZoomPeriodStyle(period: { startDate?: string | null; endDate?: string | null; color: string; row: number }) {
  const window = dayZoomWindow.value;
  if (!window) return getPeriodStyle(0, 0, period.color, period.row);

  const startDate = parseIsoDateUtc(period.startDate);
  const endDate = parseIsoDateUtc(period.endDate);

  if (!startDate || !endDate) {
    return getPeriodStyle(0, 0, period.color, period.row);
  }

  // Calculate offset in days from window min
  const startDays = Math.max(0, Math.round((startDate.getTime() - window.minDate.getTime()) / 86_400_000));
  const endDays = Math.max(0, Math.round((endDate.getTime() - window.minDate.getTime()) / 86_400_000));

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

watch(
  markerYears,
  () => {
    internalYear.value = snapToMarker(internalYear.value);
  },
);

function onSliderInput() {
  yearTraversalDirection.value = internalYear.value >= lastYearSelection.value ? "forward" : "backward";
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

watch(dayZoomWindow, (window: { minDate: Date; maxDate: Date; spanDays: number } | null) => {
  if (!window) {
    dayZoomOffset.value = 0;
    emit("exact-date-change", null);
    return;
  }

  // Start at the first real exact date, not the boundary escape stop.
  dayZoomOffset.value = dayStepInitialOffset.value;
  const current = dayZoomCurrentDate.value;
  emit("exact-date-change", current ? toIsoDateUtc(current) : null);
});

</script>
