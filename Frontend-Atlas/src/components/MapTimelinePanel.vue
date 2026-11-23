<template>
  <!-- Horizontal resize handle for timeline (Point 7) -->
  <div
    v-show="isTimelineVisible"
    role="separator"
    aria-label="Redimensionner l'échelle de temps"
    aria-orientation="horizontal"
    tabindex="0"
    class="h-1.5 w-full shrink-0 cursor-row-resize bg-base-300/50 hover:bg-primary/50 focus:bg-primary/50 transition-colors z-[1002]"
    data-testid="timeline-resize-handle"
    @mousedown.prevent="emit('start-resize', $event)"
    @keydown.up.prevent="emit('resize-by', 10)"
    @keydown.down.prevent="emit('resize-by', -10)"
  />

  <!-- Timeline panel with hide toggle and duplication button (Points 5, 6, 7) -->
  <div
    class="map-timeline-toolbar relative z-[2000] flex flex-col bg-base-100 border-t border-base-300 overflow-visible"
    :style="isTimelineVisible && timelineHeight ? { height: `${timelineHeight}px` } : {}"
  >
    <!-- Top bar with Filter Modes and Map Duplication -->
    <div
      class="map-timeline-topbar shrink-0 relative flex items-center justify-between px-3 py-1.5 border-b border-base-200 text-xs font-medium whitespace-nowrap bg-base-100 z-0"
    >
      <!-- Left section: Nom du projet -->
      <div class="flex items-center gap-2 min-w-0 pr-4">
        <span
          v-if="currentMapTitle"
          class="text-sm font-bold text-base-content select-none truncate max-w-xs md:max-w-sm"
          :title="currentMapTitle"
        >
          {{ currentMapTitle }}
        </span>
      </div>

      <!-- Center section: Flèches précédent / suivant parfaitement centrées sur toute la largeur -->
      <div
        v-if="sortedTimelineMilestones.length > 0"
        class="absolute left-1/2 -translate-x-1/2 inline-flex items-center rounded border border-base-300 bg-base-200/90 overflow-hidden shadow-xs pointer-events-auto"
      >
        <button
          type="button"
          class="px-2.5 py-1 text-base-content hover:bg-base-300 active:bg-base-300/80 disabled:opacity-30 disabled:pointer-events-none border-r border-base-300 transition-colors flex items-center justify-center"
          :disabled="!hasPrevMilestone"
          :title="
            prevMilestone
              ? `Précédent : ${prevMilestone.label} (${prevMilestone.year})`
              : 'Aucun jalon précédent'
          "
          aria-label="Jalon précédent"
          data-testid="prev-map-button"
          @click="emit('prev-milestone')"
        >
          <ChevronLeftIcon class="w-3.5 h-3.5 stroke-[2.5]" />
        </button>
        <button
          type="button"
          class="px-2.5 py-1 text-base-content hover:bg-base-300 active:bg-base-300/80 disabled:opacity-30 disabled:pointer-events-none transition-colors flex items-center justify-center"
          :disabled="!hasNextMilestone"
          :title="
            nextMilestone
              ? `Suivant : ${nextMilestone.label} (${nextMilestone.year})`
              : 'Aucun jalon suivant'
          "
          aria-label="Jalon suivant"
          data-testid="next-map-button"
          @click="emit('next-milestone')"
        >
          <ChevronRightIcon class="w-3.5 h-3.5 stroke-[2.5]" />
        </button>
      </div>

      <!-- Right section: Masquer la légende & Masquer la ligne du temps -->
      <div class="flex items-center gap-3 ml-auto">
        <button
          type="button"
          class="btn btn-ghost btn-xs text-base-content/70 hover:text-base-content gap-1"
          data-testid="hide-legend-button"
          :title="isLegendVisible ? 'Masquer la légende' : 'Afficher la légende'"
          @click="emit('toggle-legend')"
        >
          <EyeSlashIcon v-if="isLegendVisible" class="w-3.5 h-3.5" />
          <EyeIcon v-else class="w-3.5 h-3.5" />
          <span>{{ isLegendVisible ? "Masquer la légende" : "Afficher la légende" }}</span>
        </button>
        <button
          type="button"
          class="btn btn-ghost btn-xs text-base-content/70 hover:text-base-content gap-1"
          data-testid="hide-timeline-button"
          :title="isTimelineVisible ? 'Masquer la ligne du temps' : 'Afficher la ligne du temps'"
          @click="emit('toggle-timeline')"
        >
          <EyeSlashIcon v-if="isTimelineVisible" class="w-3.5 h-3.5" />
          <EyeIcon v-else class="w-3.5 h-3.5" />
          <span>{{ isTimelineVisible ? "Masquer la ligne du temps" : "Afficher la ligne du temps" }}</span>
        </button>
      </div>
    </div>

    <!-- Middle scrollable area containing the timeline tracks, ticks, labels, and legend -->
    <div
      v-show="isTimelineVisible"
      class="map-timeline-slider flex-1 min-h-0 w-full overflow-visible px-3 pt-3 pb-1 relative z-20"
    >
      <TimelineSlider
        :year="year"
        :mode="mode"
        :selected-feature-id="selectedFeatureId"
        :multi-selected-feature-ids="multiSelectedFeatureIds"
        :min="min"
        :max="max"
        :marker-years="markerYears"
        :map-periods="mapPeriods"
        :element-markers="elementMarkers"
        :current-exact-date="currentExactDate"
        @update:year="emit('update:year', $event)"
        @update:mode="emit('update:mode', $event)"
        @exact-date-change="emit('exact-date-change', $event)"
        @select-date="emit('select-date')"
        @select-map="emit('select-map', $event)"
        @edit-map="emit('edit-map', $event)"
        @edit-element="emit('edit-element', $event)"
        @select-element="emit('select-element', $event)"
        @select-elements="emit('select-elements', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ChevronLeftIcon, ChevronRightIcon, EyeIcon, EyeSlashIcon } from "@heroicons/vue/24/outline";
import TimelineSlider, { type TimelineMarkerItem } from "./TimelineSlider.vue";
import type { SliderPeriod } from "../typescript/map";
import type { TimelineMilestone, TimelineFilterMode } from "../composables/useMapTimeline";

defineProps<{
  isTimelineVisible: boolean;
  isLegendVisible: boolean;
  timelineHeight: number | null;
  currentMapTitle?: string;
  sortedTimelineMilestones: TimelineMilestone[];
  prevMilestone: TimelineMilestone | null;
  nextMilestone: TimelineMilestone | null;
  hasPrevMilestone: boolean;
  hasNextMilestone: boolean;
  year: number;
  mode: TimelineFilterMode;
  selectedFeatureId: string | null;
  multiSelectedFeatureIds: string[];
  min: number;
  max: number;
  markerYears: number[];
  mapPeriods: SliderPeriod[];
  elementMarkers: TimelineMarkerItem[];
  currentExactDate: string | null;
}>();

const emit = defineEmits<{
  (e: "update:year", value: number): void;
  (e: "update:mode", value: TimelineFilterMode): void;
  (e: "exact-date-change", date: string | null): void;
  (e: "select-date"): void;
  (e: "select-map", mapId: string): void;
  (e: "edit-map", mapId: string): void;
  (e: "edit-element", featureId: string): void;
  (e: "select-element", featureId: string): void;
  (e: "select-elements", ids: string[]): void;
  (e: "prev-milestone"): void;
  (e: "next-milestone"): void;
  (e: "toggle-legend"): void;
  (e: "toggle-timeline"): void;
  (e: "start-resize", event: MouseEvent): void;
  (e: "resize-by", delta: number): void;
}>();
</script>
