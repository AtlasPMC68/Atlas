<template>
  <BasePickerModal
    :is-open="isOpen"
    :title="modalTitle"
    :description="modalDescription"
    :confirm-label="modalConfirmLabel"
    :is-confirm-disabled="false"
    :show-skip="false"
    @close="emit('close')"
    @confirm="onConfirmModal"
  >
    <!-- Controls Area: Selection Mode Switcher -->
    <template #controls-area>
      <div class="flex items-center justify-between gap-3 flex-wrap">
        <div class="join">
          <button
            type="button"
            class="btn btn-sm join-item"
            :class="activeMode === 'legend' ? 'btn-primary' : 'btn-outline'"
            @click="activeMode = 'legend'"
          >
            <span class="inline-block w-2 h-2 rounded-full bg-emerald-500 mr-1" />
            Légende
          </button>
          <button
            type="button"
            class="btn btn-sm join-item"
            :class="activeMode === 'exclusion' ? 'btn-primary' : 'btn-outline'"
            @click="activeMode = 'exclusion'"
          >
            <span class="inline-block w-2 h-2 rounded-full bg-amber-500 mr-1" />
            Zones de texte à ignorer
          </button>
        </div>
      </div>
    </template>

    <!-- Image Area: Interactive canvas / viewer with persistent overlays -->
    <template #image-area>
      <div class="px-3 py-2 text-xs font-medium bg-base-200 border-b flex items-center justify-between">
        <span>Cliquez et glissez sur l'image pour tracer un rectangle</span>
      </div>

      <div
        ref="container"
        class="relative h-[28rem] bg-base-200 select-none cursor-crosshair overflow-hidden"
        @mousedown="onMouseDown"
      >
        <img
          v-if="imageUrl"
          ref="imageEl"
          :src="imageUrl"
          class="w-full h-full object-contain pointer-events-none select-none"
          alt="Carte importée"
          @load="onImageLoad"
        />

        <!-- Legend overlay (Green) -->
        <div
          v-if="legendStyle && !(isDrawing && activeMode === 'legend')"
          class="absolute border-2 border-emerald-500 bg-emerald-500/20 pointer-events-none transition-all"
          :style="legendStyle"
        >
          <div
            class="absolute px-2 py-0.5 text-[11px] font-bold bg-emerald-600 text-white rounded shadow flex items-center gap-1 whitespace-nowrap"
            :class="isNearTop(legendBounds) ? 'top-1 left-1' : '-top-6 left-0'"
          >
            <span>Légende</span>
          </div>
        </div>

        <!-- All Exclusion zones (Amber/Orange) -->
        <template v-for="(zone, index) in exclusionZoneStyles" :key="`zone-${index}`">
          <div
            v-if="zone"
            class="absolute border-2 border-amber-500 bg-amber-500/20 pointer-events-none transition-all"
            :style="zone"
          >
            <div
              class="absolute px-2 py-0.5 text-[11px] font-bold bg-amber-600 text-white rounded shadow flex items-center gap-1 whitespace-nowrap"
              :class="isNearTop(exclusionZones[index]) ? 'top-1 left-1' : '-top-6 left-0'"
            >
              <span>Zone #{{ index + 1 }}</span>
            </div>
          </div>
        </template>

        <!-- Active drawing selection rectangle -->
        <div
          v-if="isDrawing && currentDrawingStyle"
          class="absolute border-2 pointer-events-none shadow-sm"
          :class="
            activeMode === 'legend'
              ? 'border-emerald-500 bg-emerald-500/25'
              : 'border-amber-500 bg-amber-500/25'
          "
          :style="currentDrawingStyle"
        >
        </div>
      </div>
    </template>

<!-- List Area: Side-by-side management for legend and all ignored zones -->
<template #list-area>
  <div class="flex flex-col gap-4 p-3 bg-base-100 rounded-lg border border-base-200 h-full max-h-[30rem] overflow-y-auto">
    <!-- Section 1: Legend -->
    <div class="flex flex-col gap-2 pb-3 border-b border-base-200">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2">
          <span class="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block" />
          <h4 class="text-sm font-semibold text-base-content">Légende</h4>
        </div>
        <button
          v-if="legendBounds"
          type="button"
          class="btn btn-ghost btn-xs text-error"
          @click="clearLegend"
        >
          Supprimer
        </button>
      </div>

      <div
        v-if="legendBounds"
        class="flex items-center justify-between p-2.5 bg-base-200 rounded-lg border border-base-300 text-xs"
      >
        <div class="flex flex-col gap-0.5">
          <span class="font-semibold text-emerald-700 flex items-center gap-1">
            <span>✓</span> Délimitée
          </span>
          <span class="font-mono text-base-content/60 text-[11px]">
            {{ Math.round(legendBounds.width) }} × {{ Math.round(legendBounds.height) }} px (x: {{ Math.round(legendBounds.x) }}, y: {{ Math.round(legendBounds.y) }})
          </span>
        </div>
        <button
          type="button"
          class="btn btn-xs btn-outline"
          @click="activeMode = 'legend'"
        >
          Retracer
        </button>
      </div>

      <div
        v-else
        class="p-3 bg-base-200/50 border border-dashed border-base-300 rounded-lg text-xs text-base-content/60 text-center"
      >
        Aucune légende délimitée (optionnelle).
      </div>
    </div>

    <!-- Section 2: Ignored Areas (Exclusion zones) -->
    <div class="flex flex-col flex-1 min-h-0 gap-2">
      <div class="flex items-start justify-between gap-2">
        <div class="flex flex-col gap-0.5 min-w-0">
          <div class="flex items-center gap-2">
            <span class="w-2.5 h-2.5 rounded-full bg-amber-500 inline-block shrink-0" />
            <h4 class="text-sm font-semibold text-base-content">
              Zones de texte à ignorer
            </h4>
            <span
              v-if="exclusionZones.length > 0"
              class="inline-flex items-center justify-center min-w-[1.25rem] h-5 px-1.5 text-xs font-semibold rounded-full bg-base-300 border border-base-content/20 text-base-content"
            >
              {{ exclusionZones.length }}
            </span>
          </div>
          <p class="text-xs text-base-content/60 pl-4">
            Ex. : logo, titre, échelle du temps, boussole
          </p>
        </div>
        <button
          v-if="exclusionZones.length > 0"
          type="button"
          class="btn btn-ghost btn-xs text-error shrink-0"
          @click="clearAllExclusionZones"
        >
          Tout effacer
        </button>
      </div>

      <div
        v-if="exclusionZones.length === 0"
        class="p-3 bg-base-200/50 border border-dashed border-base-300 rounded-lg text-xs text-base-content/60 text-center"
      >
        Aucune zone d'exclusion tracée.
      </div>

      <div v-else class="flex flex-col gap-2 max-h-[16rem] overflow-y-auto pr-1">
        <div
          v-for="(zone, index) in exclusionZones"
          :key="`list-zone-${index}`"
          class="flex items-center justify-between p-2 rounded-lg bg-base-200 border border-base-300 text-xs hover:border-base-content/20 transition-colors"
        >
          <div class="flex items-center gap-2">
            <span class="text-xs font-semibold text-base-content">Zone #{{ index + 1 }}</span>
            <span class="font-mono text-base-content/70 text-[11px]">
              {{ Math.round(zone.width) }}×{{ Math.round(zone.height) }} px
              <span class="text-base-content/50 ml-1">(x: {{ Math.round(zone.x) }}, y: {{ Math.round(zone.y) }})</span>
            </span>
          </div>
          <button
            type="button"
            class="btn btn-circle btn-ghost btn-xs text-error hover:bg-error/10"
            title="Supprimer cette zone"
            aria-label="Supprimer cette zone"
            @click="removeExclusionZone(index)"
          >
            <TrashIcon class="w-4 h-4 text-error" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
</BasePickerModal>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from "vue";
import { TrashIcon } from "@heroicons/vue/24/outline";
import BasePickerModal from "../import/BasePickerModal.vue";
import type { LegendBounds } from "../../typescript/legend";
import { containRect } from "../../utils/imageFit";

export type DrawingMode = "legend" | "exclusion";

const props = withDefaults(
  defineProps<{
    isOpen: boolean;
    imageUrl: string;
    initialBounds?: LegendBounds | null;
    initialIgnoredAreas?: LegendBounds[] | null;
  }>(),
  {
    isOpen: false,
    initialBounds: null,
    initialIgnoredAreas: () => [],
  },
);

const emit = defineEmits<{
  (e: "close"): void;
  (
    e: "confirmed",
    payload: { legend: LegendBounds | null; ignoredAreas: LegendBounds[] },
  ): void;
}>();

const activeMode = ref<DrawingMode>("legend");
const container = ref<HTMLDivElement | null>(null);
const imageEl = ref<HTMLImageElement | null>(null);

const imageNaturalWidth = ref<number>(0);
const imageNaturalHeight = ref<number>(0);

const isDrawing = ref<boolean>(false);
const dragStart = ref<{ x: number; y: number } | null>(null);
const currentDrawingBounds = ref<LegendBounds | null>(null);

const legendBounds = ref<LegendBounds | null>(
  props.initialBounds ? { ...props.initialBounds } : null,
);
const exclusionZones = ref<LegendBounds[]>(
  props.initialIgnoredAreas ? [...props.initialIgnoredAreas] : [],
);

watch(
  () => props.isOpen,
  (opened: any) => {
    if (opened) {
      activeMode.value = props.initialBounds ? "exclusion" : "legend";
      legendBounds.value = props.initialBounds ? { ...props.initialBounds } : null;
      exclusionZones.value = props.initialIgnoredAreas
        ? [...props.initialIgnoredAreas]
        : [];
      isDrawing.value = false;
      dragStart.value = null;
      currentDrawingBounds.value = null;
    }
  },
  { immediate: true },
);

const displayRect = computed(() => {
  if (
    !container.value ||
    !imageNaturalWidth.value ||
    !imageNaturalHeight.value
  ) {
    return null;
  }

  const rect = container.value.getBoundingClientRect();
  const fit = containRect(
    rect.width,
    rect.height,
    imageNaturalWidth.value,
    imageNaturalHeight.value,
  );
  if (!fit) return null;

  return {
    offsetX: fit.offsetX,
    offsetY: fit.offsetY,
    displayW: fit.width,
    displayH: fit.height,
    baseScale: fit.scale,
  };
});

function getRectStyle(bounds: LegendBounds | null) {
  if (!bounds || !displayRect.value) return null;
  const { offsetX, offsetY, baseScale } = displayRect.value;

  return {
    left: `${offsetX + bounds.x * baseScale}px`,
    top: `${offsetY + bounds.y * baseScale}px`,
    width: `${bounds.width * baseScale}px`,
    height: `${bounds.height * baseScale}px`,
  };
}

function isNearTop(bounds: LegendBounds | null): boolean {
  if (!bounds || !displayRect.value) return false;
  const { offsetY, baseScale } = displayRect.value;
  const topPx = offsetY + bounds.y * baseScale;
  return topPx < 26;
}

const legendStyle = computed(() => getRectStyle(legendBounds.value));
const currentDrawingStyle = computed(() => getRectStyle(currentDrawingBounds.value));

const exclusionZoneStyles = computed(() => {
  return exclusionZones.value.map((zone: LegendBounds | null) => getRectStyle(zone));
});

const modalTitle = computed(() => "Légende et zones de texte à ignorer");

const modalDescription = computed(() =>
  "Délimitez la légende et tracez des zones d'exclusion pour masquer le texte inutile (titres, boussoles, encadrés).",
);

const modalConfirmLabel = computed(() => {
  const parts: string[] = [];
  if (legendBounds.value) parts.push("1 légende");
  if (exclusionZones.value.length > 0) {
    parts.push(`${exclusionZones.value.length} zone${exclusionZones.value.length > 1 ? "s" : ""} à ignorer`);
  }
  if (parts.length === 0) {
    return "Confirmer (aucune sélection)";
  }
  return `Confirmer (${parts.join(", ")})`;
});

function onImageLoad(): void {
  if (!imageEl.value) return;
  imageNaturalWidth.value = imageEl.value.naturalWidth || 0;
  imageNaturalHeight.value = imageEl.value.naturalHeight || 0;
}

function getImageClampedPoint(
  event: MouseEvent,
): { x: number; y: number } | null {
  if (!container.value || !displayRect.value) return null;

  const containerRect = container.value.getBoundingClientRect();
  const px = event.clientX - containerRect.left;
  const py = event.clientY - containerRect.top;

  const { offsetX, offsetY, displayW, displayH, baseScale } = displayRect.value;
  if (baseScale <= 0 || displayW <= 0 || displayH <= 0) return null;

  // Clamp strictly within the visible image boundary
  const ix = Math.max(0, Math.min(px - offsetX, displayW));
  const iy = Math.max(0, Math.min(py - offsetY, displayH));

  return {
    x: ix / baseScale,
    y: iy / baseScale,
  };
}

function onMouseDown(event: MouseEvent): void {
  if (event.button !== 0) return;

  const point = getImageClampedPoint(event);
  if (!point) return;

  isDrawing.value = true;
  dragStart.value = point;
  currentDrawingBounds.value = {
    x: point.x,
    y: point.y,
    width: 0,
    height: 0,
  };

  window.addEventListener("mousemove", onWindowMouseMove);
  window.addEventListener("mouseup", onWindowMouseUp);
}

function onWindowMouseMove(event: MouseEvent): void {
  if (!isDrawing.value || !dragStart.value) return;

  const point = getImageClampedPoint(event);
  if (!point) return;

  const x1 = Math.min(dragStart.value.x, point.x);
  const y1 = Math.min(dragStart.value.y, point.y);
  const x2 = Math.max(dragStart.value.x, point.x);
  const y2 = Math.max(dragStart.value.y, point.y);

  currentDrawingBounds.value = {
    x: x1,
    y: y1,
    width: x2 - x1,
    height: y2 - y1,
  };
}

function onWindowMouseUp(): void {
  if (!isDrawing.value) return;

  window.removeEventListener("mousemove", onWindowMouseMove);
  window.removeEventListener("mouseup", onWindowMouseUp);

  isDrawing.value = false;

  if (currentDrawingBounds.value) {
    const { width, height } = currentDrawingBounds.value;
    if (width >= 2 && height >= 2) {
      if (activeMode.value === "legend") {
        legendBounds.value = { ...currentDrawingBounds.value };
        activeMode.value = "exclusion";
      } else {
        exclusionZones.value = [...exclusionZones.value, { ...currentDrawingBounds.value }];
      }
    }
  }

  dragStart.value = null;
  currentDrawingBounds.value = null;
}

onUnmounted(() => {
  window.removeEventListener("mousemove", onWindowMouseMove);
  window.removeEventListener("mouseup", onWindowMouseUp);
});

function clearLegend(): void {
  legendBounds.value = null;
}

function removeExclusionZone(index: number): void {
  exclusionZones.value.splice(index, 1);
}

function clearAllExclusionZones(): void {
  exclusionZones.value = [];
}

function onConfirmModal(): void {
  emit("confirmed", {
    legend: legendBounds.value,
    ignoredAreas: [...exclusionZones.value],
  });
}
</script>
