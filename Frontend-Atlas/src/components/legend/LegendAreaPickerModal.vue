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
      <div class="flex flex-wrap items-center justify-between gap-3 p-3 bg-base-200/60 rounded-xl border border-base-300">
        <div class="flex items-center gap-2">
          <span class="text-xs font-semibold text-base-content/70">Mode de traçage :</span>
          <div class="join">
            <button
              type="button"
              class="btn btn-sm join-item gap-1.5 transition-all"
              :class="activeMode === 'legend' ? 'btn-success text-white shadow-sm' : 'btn-ghost border border-base-300 bg-base-100'"
              @click="activeMode = 'legend'"
            >
              <span class="inline-block w-2.5 h-2.5 rounded-full bg-green-500 ring-2 ring-white" />
              Légende
              <span v-if="legendBounds" class="badge badge-xs badge-neutral ml-1">1</span>
            </button>
            <button
              type="button"
              class="btn btn-sm join-item gap-1.5 transition-all"
              :class="activeMode === 'exclusion' ? 'btn-warning text-amber-950 shadow-sm' : 'btn-ghost border border-base-300 bg-base-100'"
              @click="activeMode = 'exclusion'"
            >
              <span class="inline-block w-2.5 h-2.5 rounded-full bg-amber-500 ring-2 ring-white" />
              Zones à ignorer (OCR)
              <span v-if="exclusionZones.length > 0" class="badge badge-xs badge-warning ml-1">
                {{ exclusionZones.length }}
              </span>
            </button>
          </div>
        </div>

        <div class="flex items-center gap-2 text-xs text-base-content/70">
          <span>Mode actif :</span>
          <span
            class="font-medium px-2 py-0.5 rounded-full"
            :class="activeMode === 'legend' ? 'bg-green-100 text-green-800' : 'bg-amber-100 text-amber-900'"
          >
            {{ activeMode === 'legend' ? 'Traçage de la légende' : 'Traçage des zones à ignorer' }}
          </span>
        </div>
      </div>
    </template>

    <!-- Image Area: Interactive canvas / viewer with persistent overlays -->
    <template #image-area>
      <div class="px-3 py-2 text-xs font-medium bg-base-200 border-b flex items-center justify-between">
        <span class="flex items-center gap-1.5">
          <span>Cliquez et glissez sur l'image pour tracer un rectangle</span>
          <span class="text-base-content/50">•</span>
          <span :class="activeMode === 'legend' ? 'text-green-700 font-semibold' : 'text-amber-800 font-semibold'">
            {{ activeMode === 'legend' ? 'Zone de légende' : 'Zone à ignorer' }}
          </span>
        </span>
        <span class="text-base-content/60">
          {{ legendBounds ? '1 légende' : '0 légende' }}, {{ exclusionZones.length }} zone{{ exclusionZones.length > 1 ? 's' : '' }} à ignorer
        </span>
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
          class="absolute border-2 border-green-600 bg-green-600/20 pointer-events-none transition-all"
          :style="legendStyle"
        >
          <div
            class="absolute -top-6 left-0 px-2 py-0.5 text-[11px] font-bold bg-green-700 text-white rounded shadow flex items-center gap-1 whitespace-nowrap"
          >
            <span>🏷️ Légende</span>
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
              class="absolute -top-6 left-0 px-2 py-0.5 text-[11px] font-bold bg-amber-600 text-white rounded shadow flex items-center gap-1 whitespace-nowrap"
            >
              <span>🚫 Zone #{{ index + 1 }}</span>
            </div>
          </div>
        </template>

        <!-- Active drawing selection rectangle -->
        <div
          v-if="isDrawing && currentDrawingStyle"
          class="absolute border-2 pointer-events-none shadow-sm"
          :class="
            activeMode === 'legend'
              ? 'border-green-600 bg-green-600/25'
              : 'border-amber-500 bg-amber-500/25'
          "
          :style="currentDrawingStyle"
        >
          <span
            class="absolute -top-6 left-0 px-2 py-0.5 text-[10px] font-bold text-white rounded shadow whitespace-nowrap"
            :class="activeMode === 'legend' ? 'bg-green-700' : 'bg-amber-600'"
          >
            {{ activeMode === 'legend' ? 'Nouvelle Légende...' : 'Nouvelle Zone...' }}
          </span>
        </div>
      </div>
    </template>

    <!-- List Area: Side-by-side management for legend and all ignored zones -->
    <template #list-area>
      <div class="flex flex-col gap-4 p-4 bg-base-100 rounded-xl border border-base-200 h-full max-h-[34rem] overflow-y-auto">
        <!-- Section 1: Legend -->
        <div class="border-b border-base-200 pb-4">
          <div class="flex items-center justify-between mb-1.5">
            <div class="flex items-center gap-2">
              <span class="w-3 h-3 rounded-full bg-green-500 inline-block" />
              <h4 class="text-sm font-bold text-base-content">Légende</h4>
            </div>
            <button
              v-if="legendBounds"
              type="button"
              class="btn btn-ghost btn-xs text-error hover:bg-error/10"
              @click="clearLegend"
            >
              Supprimer
            </button>
          </div>
          <p class="text-xs text-base-content/70 mb-2.5">
            Zone de référence pour l'extraction des couleurs. Elle est également exclue de l'OCR des noms de lieux.
          </p>

          <div
            v-if="legendBounds"
            class="p-2.5 bg-green-50/80 border border-green-200 rounded-lg text-xs flex items-center justify-between"
          >
            <div class="font-mono text-green-950 flex flex-col gap-0.5">
              <span class="font-bold flex items-center gap-1 text-green-800">
                <span>✓</span> Délimitée
              </span>
              <span class="text-[11px] text-green-900/80">
                {{ Math.round(legendBounds.width) }} × {{ Math.round(legendBounds.height) }} px (x: {{ Math.round(legendBounds.x) }}, y: {{ Math.round(legendBounds.y) }})
              </span>
            </div>
            <button
              type="button"
              class="btn btn-xs btn-outline btn-success"
              @click="activeMode = 'legend'"
            >
              Retracer
            </button>
          </div>

          <div
            v-else
            class="p-3 bg-base-200/70 border border-dashed border-base-300 rounded-lg text-xs text-base-content/70 flex flex-col gap-2"
          >
            <span>Aucune légende délimitée (optionnelle).</span>
            <button
              type="button"
              class="btn btn-xs btn-success text-white w-fit"
              @click="activeMode = 'legend'"
            >
              + Tracer la légende
            </button>
          </div>
        </div>

        <!-- Section 2: Ignored Areas (Exclusion zones) -->
        <div class="flex flex-col flex-1 min-h-0">
          <div class="flex items-center justify-between mb-1.5">
            <div class="flex items-center gap-2">
              <span class="w-3 h-3 rounded-full bg-amber-500 inline-block" />
              <h4 class="text-sm font-bold text-base-content">
                Zones à ignorer (OCR)
              </h4>
              <span class="badge badge-sm badge-warning font-semibold">
                {{ exclusionZones.length }}
              </span>
            </div>
            <button
              v-if="exclusionZones.length > 0"
              type="button"
              class="btn btn-ghost btn-xs text-error hover:bg-error/10"
              @click="clearAllExclusionZones"
            >
              Tout effacer
            </button>
          </div>

          <p class="text-xs text-base-content/70 mb-2.5">
            Tracez autant de rectangles que désiré pour masquer le texte inutile (titre, échelle, boussole, encadrés, mentions légales...).
          </p>

          <div class="flex items-center justify-between mb-2">
            <button
              type="button"
              class="btn btn-xs btn-warning text-amber-950 font-semibold"
              @click="activeMode = 'exclusion'"
            >
              + Ajouter une zone à ignorer
            </button>
          </div>

          <div
            v-if="exclusionZones.length === 0"
            class="p-3 bg-base-200/70 border border-dashed border-base-300 rounded-lg text-xs text-base-content/60 text-center"
          >
            Aucune zone d'exclusion tracée.<br />
            Basculez en mode « Zones à ignorer » et dessinez des rectangles sur la carte.
          </div>

          <div v-else class="flex flex-col gap-2 max-h-[14rem] overflow-y-auto pr-1">
            <div
              v-for="(zone, index) in exclusionZones"
              :key="`list-zone-${index}`"
              class="flex items-center justify-between p-2 rounded-lg bg-amber-50 border border-amber-200 text-xs hover:border-amber-400 transition-colors"
            >
              <div class="flex items-center gap-2">
                <span class="badge badge-warning badge-sm font-bold">#{{ index + 1 }}</span>
                <div class="font-mono text-gray-800">
                  <span class="font-semibold">{{ Math.round(zone.width) }}×{{ Math.round(zone.height) }} px</span>
                  <span class="text-gray-500 text-[11px] ml-1.5">(x: {{ Math.round(zone.x) }}, y: {{ Math.round(zone.y) }})</span>
                </div>
              </div>
              <button
                type="button"
                class="btn btn-circle btn-ghost btn-xs text-error hover:bg-error/15"
                title="Supprimer cette zone"
                @click="removeExclusionZone(index)"
              >
                ✕
              </button>
            </div>
          </div>
        </div>

        <!-- Help notice -->
        <div class="mt-auto pt-3 border-t text-[11px] text-base-content/60 flex items-start gap-1.5">
          <span class="text-base-content/80 font-bold">💡</span>
          <span>Vous pouvez alterner librement entre le traçage de la légende et l'ajout d'autant de zones à ignorer que vous le désirez sur la même carte.</span>
        </div>
      </div>
    </template>
  </BasePickerModal>
</template>

<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from "vue";
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
  (e: "no-legend"): void;
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

const legendBounds = ref<LegendBounds | null>(props.initialBounds);
const exclusionZones = ref<LegendBounds[]>(
  props.initialIgnoredAreas ? [...props.initialIgnoredAreas] : [],
);

watch(
  () => props.initialBounds,
  (value) => {
    legendBounds.value = value ? { ...value } : null;
  },
);

watch(
  () => props.initialIgnoredAreas,
  (value) => {
    exclusionZones.value = value ? [...value] : [];
  },
);

watch(
  () => props.isOpen,
  (opened) => {
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

const legendStyle = computed(() => getRectStyle(legendBounds.value));
const currentDrawingStyle = computed(() => getRectStyle(currentDrawingBounds.value));

const exclusionZoneStyles = computed(() => {
  return exclusionZones.value.map((zone) => getRectStyle(zone));
});

const modalTitle = computed(() => "Légende et zones à ignorer");

const modalDescription = computed(() =>
  "Délimitez la légende (pour l'extraction de couleurs) et tracez autant de zones d'exclusion que vous le souhaitez pour masquer le texte inutile (titres, boussoles, cartouches, etc.).",
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
      } else {
        exclusionZones.value.push({ ...currentDrawingBounds.value });
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
