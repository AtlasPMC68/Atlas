<template>
  <div class="timeline-container">
    <div class="slider-wrap">
      <div ref="axisRef" class="slider-axis">
        <!-- Period tracks - update based on view mode -->
        <div class="period-tracks" :style="periodTracksStyle">
          <div
            v-for="period in displayedPeriods"
            :key="period.id"
            class="period-track tooltip tooltip-top cursor-pointer"
            :class="{ 'tooltip-open': hoveredPeriodId === period.id }"
            :style="isZoomMode ? getDayZoomPeriodStyle(period) : getPeriodStyle(period.startYear, period.endYear, period.color, period.row)"
            :data-tip="`${period.title} (${isZoomMode ? period.startDate : period.startYear} - ${isZoomMode ? period.endDate : period.endYear})`"
            @mouseenter="hoveredPeriodId = period.id"
            @mouseleave="hoveredPeriodId = null"
            @dblclick.stop="emit('edit-map', period.id)"
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

        <!-- Element markers row (pins / puces d'éléments) - Year mode -->
        <div
          v-if="!isZoomMode && groupedElementMarkers.length > 0"
          class="element-markers-row"
          data-testid="timeline-element-markers-row"
        >
          <!-- Mini-segments colorés (Suggestion 3 : amplitude des éléments multi-périodes) -->
          <div
            v-for="marker in groupedElementMarkers.filter((m) => m.isRange && m.rangeStyle)"
            :key="`element-range-${marker.year}-${marker.maxEndYear}`"
            class="element-marker-range-track"
            :class="{
              'element-marker-range-active':
                internalYear >= marker.year &&
                marker.maxEndYear != null &&
                internalYear <= marker.maxEndYear,
            }"
            :style="marker.rangeStyle"
            @click="selectYear(marker.year)"
            @dblclick.stop="onMarkerDblClick(marker)"
          />

          <div
            v-for="marker in groupedElementMarkers"
            :key="`element-marker-${marker.year}`"
            role="button"
            tabindex="0"
            class="element-marker-pin"
            :class="{
              'element-marker-active': marker.year === internalYear,
              'element-marker-is-range': marker.isRange,
            }"
            :style="marker.style"
            :data-tip="marker.tooltip"
            :aria-label="marker.tooltip"
            data-testid="timeline-element-marker"
            @click="selectYear(marker.year)"
            @dblclick.stop="onMarkerDblClick(marker)"
            @mouseenter="onMarkerMouseEnter(marker.year)"
            @mouseleave="onMarkerMouseLeave"
            @keydown.enter="selectYear(marker.year)"
            @keydown.space.prevent="selectYear(marker.year)"
          >
            <span
              class="element-marker-badge"
              :class="{
                'element-marker-badge-range': marker.isRange,
                'element-marker-badge-single': marker.items.length === 1,
                'element-marker-badge-multiple': marker.items.length > 1,
              }"
            >
              <span class="element-marker-exclamation-icon">!</span>
              <span class="element-marker-count">{{ marker.items.length }}</span>
              <span class="sr-only">{{ marker.label }}</span>
            </span>

            <!-- Popover élégant (fiche moderne agrandie avec séparation par carte) -->
            <div
              v-if="hoveredMarkerYear === marker.year"
              class="element-marker-popover absolute bottom-full mb-2 bg-base-100 text-base-content shadow-2xl rounded-2xl border border-base-300 p-3.5 z-[2100] w-80 sm:w-96 min-w-[20rem] max-w-[28rem] pointer-events-auto text-left"
              :style="getPopoverStyle(marker.year)"
              @mouseenter="onMarkerMouseEnter(marker.year)"
              @mouseleave="onMarkerMouseLeave"
              @click.stop
            >
              <div class="flex items-center justify-between gap-2 pb-2 border-b border-base-200">
                <div class="flex items-center gap-2 text-xs font-bold min-w-0 truncate">
                  <span
                    v-if="marker.items.length > 1"
                    class="inline-flex items-center justify-center w-5 h-5 rounded-full bg-warning/20 text-warning-content font-black text-xs leading-none shrink-0"
                  >
                    !
                  </span>
                  <span v-else class="text-sm">{{ marker.isRange ? '↔️' : '📌' }}</span>
                  <span class="text-sm font-bold">{{ marker.items.length }} élément{{ marker.items.length > 1 ? 's' : '' }}</span>
                  <span class="text-base-content/50 font-normal">({{ marker.year }}{{ marker.isRange && marker.maxEndYear ? ` - ${marker.maxEndYear}` : '' }})</span>
                </div>
                <span class="text-xs text-base-content/70 bg-base-200 px-2 py-0.5 rounded-md font-mono font-semibold shrink-0">
                  {{ marker.year }}
                </span>
              </div>

              <!-- Groupes d'éléments séparés par carte -->
              <div class="flex flex-col gap-2.5 mt-2.5 max-h-72 overflow-y-auto pr-1">
                <div
                  v-for="mapGroup in getItemsByMap(marker.items)"
                  :key="mapGroup.mapId || 'general'"
                  class="flex flex-col gap-1 rounded-xl bg-base-200/50 p-2 border border-base-200"
                >
                  <!-- En-tête de la carte dans un encadré plus foncé (sans icône) -->
                  <div class="flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-lg bg-base-300/80 text-xs font-bold text-base-content shadow-xs">
                    <span class="truncate">{{ mapGroup.mapTitle }}</span>
                    <span class="badge badge-xs badge-neutral font-mono shrink-0">
                      {{ mapGroup.items.length }}
                    </span>
                  </div>

                  <!-- Liste des éléments de cette carte -->
                  <div class="flex flex-col gap-1 pt-1">
                    <div
                      v-for="item in mapGroup.items"
                      :key="item.id"
                      class="flex items-center justify-between gap-2 px-2 py-1.5 rounded-lg bg-base-100 hover:bg-base-200/80 cursor-pointer transition-all group text-xs select-none border border-base-200/60 hover:border-primary/40 shadow-xs"
                      @click.stop="onPopoverItemClick(item, marker.year)"
                    >
                      <div class="flex items-center gap-2 min-w-0 flex-1">
                        <span
                          class="w-2.5 h-2.5 rounded-full shrink-0 border border-black/15 shadow-xs"
                          :style="{ backgroundColor: item.color || (marker.isRange ? '#6366f1' : '#f59e0b') }"
                        />
                        <span class="font-medium truncate text-base-content group-hover:text-primary transition-colors">
                          {{ toNaturalCase(item.name) }}
                        </span>
                      </div>
                      <div class="flex items-center gap-1.5 shrink-0">
                        <span class="text-[10px] font-semibold tracking-wide bg-primary/10 text-primary border border-primary/20 px-2 py-0.5 rounded-full">
                          {{ formatElementType(item.type) }}
                        </span>
                        <button
                          type="button"
                          class="btn btn-ghost btn-xs btn-circle text-primary opacity-75 group-hover:opacity-100 hover:bg-primary/10"
                          title="Modifier cet élément"
                          @click.stop="onPopoverItemClick(item, marker.year)"
                        >
                          ✏️
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Bas de la fiche : message conservé sans le bouton bleu -->
              <div class="mt-2.5 pt-2 border-t border-base-200 flex items-center justify-center text-xs text-center">
                <span class="text-[11px] text-base-content/60 italic">
                  {{ marker.items.length > 1 ? 'Cliquer sur un élément pour le modifier' : 'Cliquer pour modifier' }}
                </span>
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
          <div class="labels-row" :style="{ height: `${yearLabelLaneCount}rem` }">
            <button
              v-for="label in yearLabels"
              :key="`label-${label.year}`"
              type="button"
              class="tick-label tick-label-button"
              :class="{
                'tick-label-active': label.year === internalYear,
                'tick-label-element': elementYearsSet.has(label.year),
              }"
              :style="label.style"
              :title="elementYearsSet.has(label.year) ? `Aller à ${label.year} (Éléments présents)` : `Aller à ${label.year}`"
              :aria-pressed="label.year === internalYear"
              @click="selectYear(label.year)"
            >
              {{ label.year }}
              <span
                v-if="elementYearsSet.has(label.year)"
                class="element-dot"
                title="Éléments présents"
              ></span>
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
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { parseIsoDateUtc, toIsoDateUtc } from "../utils/dateUtils";
import type { DayTick, SliderPeriod, TimelineElementMarker } from "../typescript/map";

export interface GroupedElementMarker {
  year: number;
  endYear?: number | null;
  items: TimelineElementMarker[];
  label: string;
  tooltip: string;
  style: Record<string, string>;
  isRange: boolean;
  maxEndYear?: number | null;
  rangeStyle?: Record<string, string>;
}

const props = defineProps<{
  year: number;
  min: number;
  max: number;
  markerYears?: number[];
  currentExactDate?: string | null;
  mapPeriods?: SliderPeriod[];
  elementMarkers?: TimelineElementMarker[];
}>();

const emit = defineEmits(["update:year", "exact-date-change", "edit-map", "edit-element"]);

const hoveredMarkerYear = ref<number | null>(null);
let popoverTimeout: ReturnType<typeof setTimeout> | null = null;

function onMarkerMouseEnter(year: number) {
  if (popoverTimeout) clearTimeout(popoverTimeout);
  hoveredMarkerYear.value = year;
}

function onMarkerMouseLeave() {
  popoverTimeout = setTimeout(() => {
    hoveredMarkerYear.value = null;
  }, 180);
}

function onPopoverItemClick(item: TimelineElementMarker, year: number) {
  selectYear(year);
  emit("edit-element", item.id);
  hoveredMarkerYear.value = null;
}

function toNaturalCase(str: string): string {
  if (!str) return "";
  const letters = str.replace(/[^a-zA-ZÀ-ÿ]/g, "");
  if (letters.length > 0 && letters === letters.toUpperCase()) {
    return str
      .toLowerCase()
      .split(/([\s\-_',]+)/)
      .map((part) =>
        part.length > 0 ? part.charAt(0).toUpperCase() + part.slice(1) : part
      )
      .join("");
  }
  return str;
}

const ELEMENT_TYPE_TRANSLATIONS: Record<string, string> = {
  label: "Texte",
  text: "Texte",
  texte: "Texte",
  point: "Point",
  zone: "Zone",
  shape: "Forme",
  forme: "Forme",
  image: "Image",
  polyline: "Tracé",
  drawing: "Dessin",
  dessin: "Dessin",
  arrow: "Flèche",
  fleche: "Flèche",
};

function formatElementType(type?: string | null): string {
  if (!type) return "Texte";
  const normalized = type.trim().toLowerCase();
  return ELEMENT_TYPE_TRANSLATIONS[normalized] || (type.charAt(0).toUpperCase() + type.slice(1));
}

interface MarkerMapGroup {
  mapId: string | null;
  mapTitle: string;
  items: TimelineElementMarker[];
}

function getItemsByMap(items: TimelineElementMarker[]): MarkerMapGroup[] {
  const groups = new Map<string, MarkerMapGroup>();
  for (const item of items) {
    const key = item.mapId ? String(item.mapId) : "general";
    const title = item.mapTitle || (item.mapId ? `Carte ${item.mapId}` : "Éléments généraux");
    if (!groups.has(key)) {
      groups.set(key, { mapId: item.mapId ?? null, mapTitle: title, items: [] });
    }
    groups.get(key)!.items.push(item);
  }
  return Array.from(groups.values());
}

function getPopoverStyle(year: number): Record<string, string> {
  const percent = positionForYear(year);
  if (percent < 18) {
    return { left: "0%", transform: "translateX(0)" };
  }
  if (percent > 82) {
    return { right: "0%", left: "auto", transform: "translateX(0)" };
  }
  return { left: "50%", transform: "translateX(-50%)" };
}

function onMarkerDblClick(marker: GroupedElementMarker) {
  selectYear(marker.year);
  if (marker.items.length > 0) {
    emit("edit-element", marker.items[0].id);
  }
}
const internalYear = ref(props.year || props.min);
const hoveredPeriodId = ref<string | null>(null);
const dayZoomOffset = ref(0);
const yearTraversalDirection = ref<"forward" | "backward">("forward");
const lastYearSelection = ref(props.year || props.min);

const elementYearsSet = computed(() => {
  return new Set((props.elementMarkers ?? []).map((m: TimelineElementMarker) => m.year));
});

const groupedElementMarkers = computed<GroupedElementMarker[]>(() => {
  if (isZoomMode.value || !props.elementMarkers || props.elementMarkers.length === 0) {
    return [];
  }
  const map = new Map<number, TimelineElementMarker[]>();
  for (const m of props.elementMarkers) {
    if (m.year >= props.min && m.year <= props.max) {
      if (!map.has(m.year)) map.set(m.year, []);
      map.get(m.year)!.push(m);
    }
  }
  const groups: GroupedElementMarker[] = [];
  for (const [year, items] of map.entries()) {
    const percent = positionForYear(year);
    const hasRange = items.some(
      (item) => item.endYear != null && item.endYear > year,
    );
    const maxEndYear = hasRange
      ? Math.max(
          ...items
            .map((item) => (item.endYear != null && item.endYear > year ? item.endYear : year))
            .filter(Boolean),
        )
      : null;

    let tooltip: string;
    if (items.length === 1) {
      const item = items[0];
      const isRangeItem = item.endYear != null && item.endYear > year;
      const periodStr = isRangeItem
        ? ` (${year} - ${item.endYear})`
        : ` (${year})`;
      const icon = isRangeItem ? "↔️" : "📌";
      tooltip = `${icon} ${item.name}${periodStr} - ${item.type || "Texte"}`;
    } else {
      const names = items.map((i) => i.name).slice(0, 3).join(", ");
      const extra = items.length > 3 ? ` et ${items.length - 3} autre(s)` : "";
      const icon = hasRange ? "↔️" : "📌";
      const periodStr = hasRange ? ` (${year} - ${maxEndYear})` : ` (${year})`;
      tooltip = `${icon} ${items.length} éléments${periodStr} : ${names}${extra}`;
    }

    let rangeStyle: Record<string, string> | undefined = undefined;
    if (hasRange && maxEndYear != null) {
      const left = positionForYear(year);
      const right = positionForYear(Math.min(props.max, maxEndYear));
      const width = Math.max(0.8, right - left);
      rangeStyle = {
        left: `${left}%`,
        width: `${width}%`,
      };
    }

    groups.push({
      year,
      endYear: maxEndYear,
      items,
      label: items.length === 1 ? items[0].name : `${items.length} éléments`,
      tooltip,
      style: markerStyleFromPercent(percent),
      isRange: hasRange,
      maxEndYear,
      rangeStyle,
    });
  }
  return groups.sort((a, b) => a.year - b.year);
});

const markerYears = computed(() => {
  const values = (props.markerYears ?? []).filter(
    (v: number) => Number.isFinite(v) && v >= props.min && v <= props.max,
  );
  const elementYears = (props.elementMarkers ?? [])
    .map((m: TimelineElementMarker) => m.year)
    .filter((v: number) => Number.isFinite(v) && v >= props.min && v <= props.max);
  const merged = [...values, ...elementYears, props.min, props.max];
  return [...new Set(merged)].sort((a, b) => a - b);
});

// Year labels closer than this would print over one another ("1899" and
// "1900" read as "18990"), so the later one drops to the next lane.
const YEAR_LABEL_MIN_GAP_PX = 36;
const YEAR_LABEL_MAX_LANES = 3;
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

const yearLabels = computed(() => {
  const minGapPercent = (YEAR_LABEL_MIN_GAP_PX / axisWidthPx.value) * 100;
  // Position of the last label placed on each lane.
  const laneEnds: number[] = [];

  return markerYears.value.map((year: number) => {
    const percent = positionForYear(year);
    let lane = laneEnds.findIndex((end: number) => percent - end >= minGapPercent);
    if (lane === -1) {
      lane =
        laneEnds.length < YEAR_LABEL_MAX_LANES
          ? laneEnds.length
          : laneEnds.indexOf(Math.min(...laneEnds));
    }
    laneEnds[lane] = percent;
    return {
      year,
      lane,
      style: { ...markerStyleFromPercent(percent), top: `${lane}rem` },
    };
  });
});

const yearLabelLaneCount = computed(() =>
  Math.max(1, ...yearLabels.value.map((label: { lane: number }) => label.lane + 1)),
);

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
  const names = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"];
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

// Two markers a year apart sit under the same pixel of the slider; their labels
// are the reliable way to pick one.
function selectYear(year: number) {
  internalYear.value = year;
  onSliderInput();
}

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
