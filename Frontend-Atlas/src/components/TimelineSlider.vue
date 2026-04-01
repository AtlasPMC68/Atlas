<template>
  <div class="timeline-container">
    <div class="slider-wrap">
      <div class="period-tracks" :style="periodTracksStyle">
          <div
            v-for="period in positionedPeriods"
            :key="period.id"
            class="period-track"
            :title="`${period.title} (${period.startYear} - ${period.endYear})`"
            :style="getPeriodStyle(period.startYear, period.endYear, period.color, period.row)"
          ></div>
        </div>
      <div class="slider-axis">
        <input
          type="range"
          :min="min"
          :max="max"
          step="1"
          v-model.number="internalYear"
          @input="onSliderInput"
          class="range range-primary range-sm w-full"
        />

        <div class="ticks-row">
          <span
            v-for="tick in tickValues"
            :key="`tick-${tick}`"
            class="tick-mark"
            :style="getMarkerStyle(tick)"
            >|</span
          >
        </div>
        <div class="labels-row">
          <span
            v-for="tick in tickValues"
            :key="`label-${tick}`"
            class="tick-label"
            :style="getMarkerStyle(tick)"
            >{{ tick }}</span
          >
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";

const props = defineProps<{
  year: number;
  min: number;
  max: number;
  markerYears?: number[];
  mapPeriods?: Array<{
    id: string;
    title: string;
    color: string;
    startYear: number;
    endYear: number;
  }>;
}>();

const emit = defineEmits(["update:year"]);
const internalYear = ref(props.year || props.min);
const inputValue = ref(String(internalYear.value));

const markerYears = computed(() => {
  const values = (props.markerYears ?? []).filter(
    (v: number) => Number.isFinite(v) && v >= props.min && v <= props.max,
  );
  const merged = [...values, props.min, props.max];
  return [...new Set(merged)].sort((a, b) => a - b);
});

const tickValues = computed(() => {
  return markerYears.value;
});

const mapPeriods = computed(() => props.mapPeriods ?? []);
const PERIOD_ROW_HEIGHT_REM = 0.35;
const PERIOD_ROW_GAP_REM = 0.2;
const PERIOD_PADDING_REM = 0.35;

const positionedPeriods = computed(() => {
  const sorted = [...mapPeriods.value].sort(
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

const rowCount = computed(() => {
  if (!positionedPeriods.value.length) return 1;
  return Math.max(...positionedPeriods.value.map((period) => period.row + 1));
});

const periodTracksStyle = computed(() => {
  const rows = rowCount.value;
  const height =
    rows * PERIOD_ROW_HEIGHT_REM +
    Math.max(0, rows - 1) * PERIOD_ROW_GAP_REM +
    PERIOD_PADDING_REM * 2;

  return { height: `${height}rem` };
});

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

function positionForYear(year: number): number {
  if (props.max <= props.min) return 0;
  const ratio = (year - props.min) / (props.max - props.min);
  return Math.min(100, Math.max(0, ratio * 100));
}

function getMarkerStyle(year: number) {
  const left = positionForYear(year);
  let transform = "translateX(-50%)";
  if (left <= 0) transform = "translateX(0)";
  if (left >= 100) transform = "translateX(-100%)";

  return {
    left: `${left}%`,
    transform,
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

watch(
  () => props.year,
  (val: number) => {
    if (val !== internalYear.value) {
      internalYear.value = snapToMarker(val);
      inputValue.value = String(internalYear.value);
    }
  },
);

watch(
  () => [props.min, props.max, props.markerYears],
  () => {
    internalYear.value = snapToMarker(internalYear.value);
    inputValue.value = String(internalYear.value);
  },
);

function onSliderInput() {
  internalYear.value = snapToMarker(internalYear.value);
  inputValue.value = String(internalYear.value);
  emit("update:year", internalYear.value);
}

function onInputChange() {
  const raw = parseInt(inputValue.value);
  const snapped = snapToMarker(raw || props.min);
  internalYear.value = snapped;
  inputValue.value = String(snapped);
  emit("update:year", snapped);
}
</script>

<style scoped>
.timeline-container {
  display: flex;
  align-items: flex-start;
  gap: 1rem;
  padding: 0.8rem 1.2rem;
  background: white;
  min-height: 6.5rem;
  width: 100%;
  box-sizing: border-box;
  border-top: 1px solid #ddd;
}

.slider-wrap {
  flex: 1;
}

.slider-axis {
  --axis-inset: 0.55rem;
  padding: 0 var(--axis-inset);
}

.ticks-row,
.labels-row {
  position: relative;
  margin-top: 0.2rem;
  font-size: 0.72rem;
  color: #6b7280;
}

.ticks-row {
  height: 0.8rem;
}

.labels-row {
  height: 1rem;
}

.tick-mark,
.tick-label {
  position: absolute;
  top: 0;
  white-space: nowrap;
}

.period-tracks {
  position: relative;
  margin-top: 0.4rem;
  border-radius: 0.25rem;
  background: #ffffff;
}

.period-track {
  position: absolute;
  border-radius: 999px;
  opacity: 0.95;
}
</style>
