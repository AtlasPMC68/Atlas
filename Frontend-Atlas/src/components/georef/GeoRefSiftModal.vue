<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-50 flex items-start justify-center bg-black/60 overflow-y-auto"
  >
    <div class="bg-base-100 rounded-lg shadow-xl max-w-6xl w-full mx-4 my-6 p-6 flex flex-col gap-4">
      <div class="flex justify-between items-center mb-2">
        <h2 class="text-xl font-semibold">Géoréférencement avec points SIFT</h2>
        <button class="btn btn-ghost btn-sm" @click="emit('close')">✕</button>
      </div>

      <p class="text-sm text-base-content/70 mb-2">
        Pour chaque point détecté sur la carte du monde (à gauche),
        cliquez à l'endroit correspondant sur votre image (à droite).
        Nous utiliserons ces paires de points pour géoréférencer la carte.
      </p>

      <p class="text-xs text-base-content/60 mb-1">
        Pour reprendre un point déjà apparié, recliquez simplement sur son triangle
        (sur la carte du monde ou sur l'image), puis cliquez à nouveau sur l'image
        à l'endroit souhaité.
      </p>

      <div class="text-xs text-base-content/70 mb-2" v-if="totalPoints > 0">
        Points appariés : {{ matchedCount }} / {{ totalPoints }}
        <span v-if="activeIndex < totalPoints"> — Point courant #{{ activeIndex + 1 }}</span>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 flex-1 min-h-[360px]">
        <div class="border rounded-md overflow-hidden">
          <h3 class="px-3 py-2 text-sm font-medium bg-base-200 border-b">
            Carte du monde (points SIFT)
          </h3>
          <GeoRefSiftWorldMap
            class="h-80 md:h-[28rem]"
            :world-bounds="worldBounds"
            :keypoints="keypoints"
            :active-index="activeIndex"
            :matched-points="matchedWorldPoints"
            @select-keypoint="onSelectWorldKeypoint"
          />
        </div>

        <div class="border rounded-md overflow-hidden">
          <h3 class="px-3 py-2 text-sm font-medium bg-base-200 border-b">
            Image importée (cliquez pour placer le point)
          </h3>
          <GeoRefImageMap
            ref="imageMapRef"
            class="h-80 md:h-[28rem]"
            :image-url="imageUrl"
            drawing-mode="point"
            :matched-points="matchedImagePoints"
            v-model:point="currentImagePoint"
            @select-match="onSelectImageMatch"
          />
        </div>
      </div>

      <div class="flex justify-between items-center pt-2">
        <div class="text-xs text-base-content/60">
          Il est recommandé d'avoir au moins {{ minPairs }} paires de points
          pour un bon géoréférencement.
        </div>
        <div class="flex gap-2">
          <button class="btn btn-ghost btn-sm" @click="resetMatching">Réinitialiser</button>
          <button
            class="btn btn-primary btn-sm"
            :disabled="!canConfirm"
            @click="onConfirm"
          >
            Confirmer les {{ matchedCount }} points
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import GeoRefSiftWorldMap from "./GeoRefSiftWorldMap.vue";
import GeoRefImageMap from "./GeoRefImageMap.vue";
import type {
  WorldBounds,
  LatLngTuple,
  XYTuple,
  CoastlineKeypoint,
  GeorefMatch,
  MatchedWorldPointSummary,
  MatchedImagePoint,
} from "../../typescript/georef";

const props = withDefaults(
  defineProps<{
    isOpen: boolean;
    imageUrl: string;
    worldBounds: WorldBounds | null;
    keypoints: CoastlineKeypoint[];
    minPairs?: number;
  }>(),
  {
    isOpen: false,
    worldBounds: null,
    keypoints: () => [],
    minPairs: 4,
  },
);

const emit = defineEmits<{
  (e: "close"): void;
  (e: "confirmed", payload: { worldPoints: LatLngTuple[]; imagePoints: XYTuple[] }): void;
}>();

const imageMapRef = ref<InstanceType<typeof GeoRefImageMap> | null>(null);
const activeIndex = ref<number>(0);
const currentImagePoint = ref<XYTuple | null>(null); // [x, y] of last click on image
// Matches between world keypoints and image points:
// { index, world: [lat,lng], image: [x,y], color }
const matches = ref<GeorefMatch[]>([]);

// Simple color palette for matched pairs
const PAIR_COLORS = [
  "#ef4444",
  "#22c55e",
  "#3b82f6",
  "#f97316",
  "#a855f7",
  "#14b8a6",
  "#e11d48",
  "#0ea5e9",
  "#facc15",
  "#6366f1",
];

const totalPoints = computed<number>(() => props.keypoints?.length || 0);
const matchedCount = computed<number>(() => matches.value.length);

const canConfirm = computed<boolean>(
  () => matchedCount.value >= props.minPairs,
);

const currentWorldKeypoint = computed<CoastlineKeypoint | null>(() => {
  if (!props.keypoints || props.keypoints.length === 0) return null;
  if (activeIndex.value < 0 || activeIndex.value >= props.keypoints.length) return null;
  return props.keypoints[activeIndex.value];
});

const matchedWorldPoints = computed<MatchedWorldPointSummary[]>(() =>
  matches.value.map((m) => ({ index: m.index, color: m.color })),
);

const matchedImagePoints = computed<MatchedImagePoint[]>(() =>
  matches.value.map((m) => ({
    index: m.index,
    x: m.image[0],
    y: m.image[1],
    color: m.color,
  })),
);

function resetMatching(): void {
  matches.value = [];
  activeIndex.value = 0;
  currentImagePoint.value = null;
}

function onSelectWorldKeypoint(index: number): void {
  if (index < 0 || index >= totalPoints.value) return;
  // Change the currently selected world keypoint.
  // If it was already matched, entering here means "retake" that pair:
  // drop the existing match and put the image map back in click mode.
  activeIndex.value = index;
  currentImagePoint.value = null;

  const hadMatch = matches.value.some((m) => m.index === index);
  if (hadMatch) {
    matches.value = matches.value.filter((m) => m.index !== index);
    if (imageMapRef.value?.focusClickMode) {
      imageMapRef.value.focusClickMode();
    }
  }
}

function onSelectImageMatch(index: number): void {
  // Focus the pair corresponding to the clicked triangle on the image.
  if (index < 0 || index >= totalPoints.value) return;
  activeIndex.value = index;
  currentImagePoint.value = null;

  // Clicking a matched triangle on the image also means "retake".
  const hadMatch = matches.value.some((m) => m.index === index);
  if (hadMatch) {
    matches.value = matches.value.filter((m) => m.index !== index);
  }
  if (imageMapRef.value?.focusClickMode) {
    imageMapRef.value.focusClickMode();
  }
}

function onConfirm(): void {
  if (!canConfirm.value || matches.value.length === 0) return;

  const worldPoints = matches.value.map((m) => m.world);
  const imagePoints = matches.value.map((m) => m.image);

  emit("confirmed", { worldPoints, imagePoints });
}

// Whenever the user clicks on the image, record a match
watch(
  () => currentImagePoint.value,
  (val: XYTuple | null) => {
    if (!val) return;
    const kp = currentWorldKeypoint.value;
    if (!kp) return;

    const kpIndex = activeIndex.value;

    // Remove any previous match for this world keypoint so the user
    // can reassign it by clicking a different location on the image.
    matches.value = matches.value.filter((m) => m.index !== kpIndex);

    // Give each keypoint index a stable color, independent of how many
    // matches currently exist. This avoids color "shifting" when
    // intermediate points are removed and re-matched.
    const color = PAIR_COLORS[kpIndex % PAIR_COLORS.length];

    matches.value.push({
      index: kpIndex,
      world: [kp.geo.lat, kp.geo.lng],
      image: val,
      color,
    });

    // After matching, move focus to the next UNMATCHED keypoint.
    // This avoids jumping back to an already-matched point when
    // redoing earlier pairs.
    const total = totalPoints.value;
    if (total > 0) {
      const matchedIndices = new Set(matches.value.map((m) => m.index));

      let nextIndex = kpIndex;
      // Search forward from current index
      for (let i = kpIndex + 1; i < total; i += 1) {
        if (!matchedIndices.has(i)) {
          nextIndex = i;
          break;
        }
      }
      // If everything after is matched, wrap from start
      if (nextIndex === kpIndex) {
        for (let i = 0; i < total; i += 1) {
          if (!matchedIndices.has(i)) {
            nextIndex = i;
            break;
          }
        }
      }

      activeIndex.value = nextIndex;
      currentImagePoint.value = null;
    }
  },
);

watch(
  () => props.isOpen,
  (open: boolean) => {
    if (!open) {
      resetMatching();
    }
  },
);
</script>
