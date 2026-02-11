<template>
  <div v-if="isOpen" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
    <div class="bg-base-100 rounded-lg shadow-xl max-w-6xl w-full mx-4 p-6 flex flex-col gap-4">
      <div class="flex justify-between items-center mb-2">
        <h2 class="text-xl font-semibold">Géoréférencement avec points SIFT</h2>
        <button class="btn btn-ghost btn-sm" @click="emit('close')">✕</button>
      </div>

      <p class="text-sm text-base-content/70 mb-2">
        Pour chaque point détecté sur la carte du monde (à gauche),
        cliquez à l'endroit correspondant sur votre image (à droite).
        Nous utiliserons ces paires de points pour géoréférencer la carte.
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
            class="h-80 md:h-[28rem]"
            :image-url="imageUrl"
            drawing-mode="point"
            :matched-points="matchedImagePoints"
            v-model:point="currentImagePoint"
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

<script setup>
import { computed, ref, watch } from "vue";
import GeoRefSiftWorldMap from "./GeoRefSiftWorldMap.vue";
import GeoRefImageMap from "./GeoRefImageMap.vue";

const props = defineProps({
  isOpen: { type: Boolean, default: false },
  imageUrl: { type: String, required: true },
  worldBounds: {
    type: Object,
    default: null, // { west, south, east, north }
  },
  keypoints: {
    type: Array,
    default: () => [], // CoastlineKeypoint[]
  },
  minPairs: {
    type: Number,
    default: 4,
  },
});

const emit = defineEmits(["close", "confirmed"]);

const activeIndex = ref(0);
const currentImagePoint = ref(null); // [x, y] of last click on image
// Matches between world keypoints and image points:
// { index, world: [lat,lng], image: [x,y], color }
const matches = ref([]);

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
];

const totalPoints = computed(() => props.keypoints?.length || 0);
const matchedCount = computed(() => matches.value.length);

const canConfirm = computed(
  () => matchedCount.value >= props.minPairs,
);

const currentWorldKeypoint = computed(() => {
  if (!props.keypoints || props.keypoints.length === 0) return null;
  if (activeIndex.value < 0 || activeIndex.value >= props.keypoints.length) return null;
  return props.keypoints[activeIndex.value];
});

const matchedWorldPoints = computed(() =>
  matches.value.map((m) => ({ index: m.index, color: m.color })),
);

const matchedImagePoints = computed(() =>
  matches.value.map((m) => ({
    index: m.index,
    x: m.image[0],
    y: m.image[1],
    color: m.color,
  })),
);

function resetMatching() {
  matches.value = [];
  activeIndex.value = 0;
  currentImagePoint.value = null;
}

function onSelectWorldKeypoint(index) {
  if (index < 0 || index >= totalPoints.value) return;
  // Change the currently selected world keypoint; the next image click
  // will create or update the match for this point.
  activeIndex.value = index;
  currentImagePoint.value = null;
}

function onConfirm() {
  if (!canConfirm.value || matches.value.length === 0) return;

  const worldPoints = matches.value.map((m) => m.world);
  const imagePoints = matches.value.map((m) => m.image);

  emit("confirmed", { worldPoints, imagePoints });
}

// Whenever the user clicks on the image, record a match
watch(
  () => currentImagePoint.value,
  (val) => {
    if (!val) return;
    const kp = currentWorldKeypoint.value;
    if (!kp) return;

    const kpIndex = activeIndex.value;

    // Preserve existing color if rematching this keypoint
    const existing = matches.value.find((m) => m.index === kpIndex);
    const existingColor = existing?.color;

    // Remove any previous match for this world keypoint so the user
    // can reassign it by clicking a different location on the image.
    matches.value = matches.value.filter((m) => m.index !== kpIndex);

    const color =
      existingColor ||
      PAIR_COLORS[matches.value.length % PAIR_COLORS.length];

    matches.value.push({
      index: kpIndex,
      world: [kp.geo.lat, kp.geo.lng],
      image: val,
      color,
    });

    // Advance to next keypoint if available
    if (activeIndex.value < totalPoints.value - 1) {
      activeIndex.value += 1;
      currentImagePoint.value = null;
    }
  },
);

watch(
  () => props.isOpen,
  (open) => {
    if (!open) {
      resetMatching();
    }
  },
);
</script>
