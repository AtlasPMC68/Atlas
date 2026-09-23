<template>
  <div
    class="bg-white rounded-[14px] h-full p-[18px] flex flex-col gap-3.5 shadow-[0_1px_4px_rgba(0,0,0,0.07)]"
  >
    <div class="flex justify-between items-center gap-3">
      <div class="flex items-center gap-3 min-w-0">
        <span class="text-[13px] font-semibold text-gray-700">Carte importée</span>
        <button
          v-if="canChangeMap"
          type="button"
          class="text-[11px] text-gray-400 hover:text-indigo-600 underline-offset-2 hover:underline"
          @click="emit('change-map')"
        >
          Changer de carte
        </button>
      </div>
      <span
        v-if="title"
        class="text-xs text-gray-400 bg-gray-50 border border-gray-100 px-2.5 py-0.5 rounded-md truncate"
      >
        {{ title }}
      </span>
    </div>

    <div
      ref="box"
      class="flex-1 min-h-0 rounded-[10px] overflow-hidden relative bg-gray-100"
    >
      <img
        :src="imageUrl"
        alt="Carte importée"
        class="absolute inset-0 w-full h-full object-contain select-none"
        @load="onImageLoad"
      />

      <!-- Overlays, in the image's own pixel space scaled to where it sits -->
      <div v-if="fit" class="absolute pointer-events-none" :style="layerStyle">
        <!-- Legend -->
        <div
          v-if="legend?.present"
          class="absolute border-2 border-green-600 rounded-md"
          :style="rectStyle(legend.bounds)"
        >
          <span
            class="absolute -top-5 left-0 whitespace-nowrap bg-white/95 text-green-600 text-[9px] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded"
          >
            ✓ Légende délimitée
          </span>
        </div>

        <!-- SIFT control points: a numbered dot centred on each point -->
        <span
          v-for="(point, index) in siftPoints"
          :key="`sift-${index}`"
          class="absolute w-4 h-4 rounded-full bg-blue-600/90 ring-2 ring-white text-white text-[8px] font-bold flex items-center justify-center shadow"
          :style="dotStyle(point.pixel.x, point.pixel.y)"
        >
          {{ index + 1 }}
        </span>

        <!-- City control points: pins -->
        <div
          v-for="(point, index) in cityPoints"
          :key="`city-${index}`"
          class="absolute flex flex-col items-center"
          :style="markerStyle(point.pixel.x, point.pixel.y)"
          :title="point.source === 'city' ? point.city.name : ''"
        >
          <MapPinIcon class="w-4 h-4 text-fuchsia-600 drop-shadow" />
        </div>
      </div>

      <!-- SIFT badge -->
      <span
        v-if="siftPoints.length > 0"
        class="absolute top-2 right-2 bg-blue-600/90 text-white text-[10px] font-semibold px-2 py-0.5 rounded flex items-center gap-1"
      >
        <CheckIcon class="w-2.5 h-2.5" />
        {{ siftPoints.length }} points SIFT
      </span>

      <!-- Extracted colours -->
      <div
        v-if="colors.length > 0"
        class="absolute bottom-0 inset-x-0 h-[26px] bg-gray-900/55 backdrop-blur-sm flex items-center px-2.5 gap-1.5"
      >
        <span class="text-[9px] text-white/70 font-semibold tracking-wide whitespace-nowrap">
          COULEURS EXTRAITES
        </span>
        <span
          v-for="(color, index) in colors"
          :key="`color-${index}`"
          class="w-4 h-3 rounded-[3px] border"
          :class="color.kind === 'water' ? 'border-sky-200 border-dashed' : 'border-white/30'"
          :style="{ backgroundColor: color.hex }"
          :title="color.kind === 'water' ? `${color.name} (eau)` : color.name"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { CheckIcon, MapPinIcon } from "@heroicons/vue/24/solid";
import { containRect } from "../../utils/imageFit";
import type { ControlPointInput, ImposedColor } from "../../typescript/georef";
import type { LegendAnswer, LegendBounds } from "../../typescript/legend";

withDefaults(
  defineProps<{
    imageUrl: string;
    title?: string;
    legend?: LegendAnswer | null;
    siftPoints?: ControlPointInput[];
    cityPoints?: ControlPointInput[];
    colors?: ImposedColor[];
    canChangeMap?: boolean;
  }>(),
  {
    title: "",
    legend: null,
    siftPoints: () => [],
    cityPoints: () => [],
    colors: () => [],
    canChangeMap: false,
  },
);

const emit = defineEmits<{ (e: "change-map"): void }>();

const box = ref<HTMLDivElement | null>(null);
const boxSize = ref({ width: 0, height: 0 });
const natural = ref({ width: 0, height: 0 });

const fit = computed(() =>
  containRect(
    boxSize.value.width,
    boxSize.value.height,
    natural.value.width,
    natural.value.height,
  ),
);

const layerStyle = computed(() => {
  const f = fit.value;
  if (!f) return {};
  return {
    left: `${f.offsetX}px`,
    top: `${f.offsetY}px`,
    width: `${f.width}px`,
    height: `${f.height}px`,
  };
});

function rectStyle(bounds: LegendBounds) {
  const scale = fit.value?.scale ?? 0;
  return {
    left: `${bounds.x * scale}px`,
    top: `${bounds.y * scale}px`,
    width: `${bounds.width * scale}px`,
    height: `${bounds.height * scale}px`,
  };
}

// Dots sit centred on their point.
function dotStyle(x: number, y: number) {
  const scale = fit.value?.scale ?? 0;
  return {
    left: `${x * scale}px`,
    top: `${y * scale}px`,
    transform: "translate(-50%, -50%)",
  };
}

// Pins stand on their point: centred horizontally, tip on the point.
function markerStyle(x: number, y: number) {
  const scale = fit.value?.scale ?? 0;
  return {
    left: `${x * scale}px`,
    top: `${y * scale}px`,
    transform: "translate(-50%, -100%)",
  };
}

function onImageLoad(event: Event) {
  const img = event.target as HTMLImageElement;
  natural.value = { width: img.naturalWidth, height: img.naturalHeight };
}

let observer: ResizeObserver | null = null;

onMounted(() => {
  if (!box.value) return;
  observer = new ResizeObserver(([entry]) => {
    boxSize.value = {
      width: entry.contentRect.width,
      height: entry.contentRect.height,
    };
  });
  observer.observe(box.value);
});

onBeforeUnmount(() => observer?.disconnect());
</script>
