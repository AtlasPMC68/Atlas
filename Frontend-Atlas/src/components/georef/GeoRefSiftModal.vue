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
        Pour reprendre un point déjà apparié, recliquez simplement sur son cercle
        (sur la carte du monde ou sur l'image), puis cliquez à nouveau sur l'image
        à l'endroit souhaité.
      </p>

      <div
        v-if="totalPoints > 0"
        class="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-base-content/70 mb-2"
      >
        <span>
          Points appariés : {{ matchedCount }} / {{ totalPoints }}
          <span v-if="activeIndex < totalPoints"> — Point courant #{{ activeIndex + 1 }}</span>
        </span>
        <!-- Key to the markers drawn by both maps. -->
        <span class="flex items-center gap-1">
          <span class="status status-lg bg-red-600" aria-hidden="true" /> courant
        </span>
        <span class="flex items-center gap-1">
          <span class="status status-lg bg-blue-200 ring-1 ring-blue-600" aria-hidden="true" />
          à apparier
        </span>
        <span class="flex items-center gap-1">
          <span class="status status-lg bg-blue-600" aria-hidden="true" /> apparié
        </span>
        <span v-if="allowCheckPoints" class="flex items-center gap-1">
          <span class="status status-lg bg-green-600" aria-hidden="true" /> vérification
        </span>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 flex-1 min-h-[360px]">
        <div class="border rounded-md overflow-hidden">
          <h3 class="px-3 py-2 text-sm font-medium bg-base-200 border-b">
            Carte du monde (points SIFT)
          </h3>
          <GeoRefWorldMap
            class="h-80 md:h-[28rem]"
            :world-bounds="worldBounds"
            :points="worldPoints"
            :active-index="activeIndex"
            :matched-points="matchedWorldPoints"
            :used-lakes="usedLakes"
            numbered
            @select-point="onSelectWorldKeypoint"
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
            :matched-points="matchedImagePoints"
            numbered
            v-model:point="currentImagePoint"
            @select-match="onSelectImageMatch"
          />
        </div>
      </div>

      <!-- Dev-test only: any matched pair can be held out of the fit as a
           check point, measured against the transform after the run. -->
      <fieldset
        v-if="allowCheckPoints && matches.length > 0"
        class="fieldset border border-base-300 rounded-box px-3 pb-3"
      >
        <legend class="fieldset-legend">Points de vérification (test)</legend>
        <p class="text-xs text-base-content/70">
          Un point coché n'est jamais utilisé pour le calage ; après chaque run,
          on mesure à quelle distance la transformation le place de sa vraie
          position.
        </p>
        <div class="flex flex-wrap gap-x-4 gap-y-1">
          <label v-for="m in sortedMatches" :key="m.index" class="label text-xs">
            <input
              type="checkbox"
              class="checkbox checkbox-xs"
              :checked="!!m.check"
              @change="toggleCheck(m.index, ($event.target as HTMLInputElement).checked)"
            />
            <span
              class="status"
              :class="m.check ? 'bg-green-600' : 'bg-blue-600'"
              aria-hidden="true"
            />
            #{{ m.index + 1 }} vérification
          </label>
        </div>
      </fieldset>

      <div class="flex justify-between items-center pt-2">
        <div class="text-xs text-base-content/60">
          Il est recommandé d'avoir au moins {{ minPairs }} paires de points
          <span v-if="allowCheckPoints">utilisées pour le calage (hors vérification)</span>
          pour un bon géoréférencement.
        </div>
        <div class="flex gap-2">
          <button class="btn btn-ghost btn-sm" @click="resetMatching">Réinitialiser</button>
          <button
            class="btn btn-primary btn-sm"
            :disabled="!canConfirm"
            @click="onConfirm"
          >
            Confirmer les {{ fitCount }} points<span v-if="checkCount > 0">
              + {{ checkCount }} de vérification</span
            >
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from "vue";
import GeoRefWorldMap from "./GeoRefWorldMap.vue";
import GeoRefImageMap from "./GeoRefImageMap.vue";
import type {
  WorldBounds,
  XYTuple,
  CoastlineKeypoint,
  ControlPointInput,
  GeorefMatch,
  MatchedWorldPointSummary,
  MatchedImagePoint,
  WorldMapPoint,
} from "../../typescript/georef";

const props = withDefaults(
  defineProps<{
    isOpen: boolean;
    imageUrl: string;
    worldBounds: WorldBounds | null;
    keypoints: CoastlineKeypoint[];
    usedLakes?: boolean;
    minPairs?: number;
    // Pairs confirmed earlier, restored when the user comes back to this step
    initialPoints?: ControlPointInput[];
    // Dev-test only: pairs can be marked as check points, held out of the fit.
    allowCheckPoints?: boolean;
    // SIFT check points confirmed earlier, restored ticked.
    initialCheckPoints?: ControlPointInput[];
  }>(),
  {
    isOpen: false,
    worldBounds: null,
    keypoints: () => [],
    usedLakes: false,
    minPairs: 4,
    initialPoints: () => [],
    allowCheckPoints: false,
    initialCheckPoints: () => [],
  },
);

const emit = defineEmits<{
  (e: "close"): void;
  // checks: the pairs ticked as check points (always empty outside dev-test).
  (e: "confirmed", points: ControlPointInput[], checks: ControlPointInput[]): void;
}>();

const imageMapRef = ref<InstanceType<typeof GeoRefImageMap> | null>(null);
const activeIndex = ref<number>(0);
const currentImagePoint = ref<XYTuple | null>(null); // [x, y] of last click on image
// Matches between world keypoints (by index) and the clicked image points.
const matches = ref<GeorefMatch[]>([]);

function sameGeo(kp: CoastlineKeypoint, point: ControlPointInput): boolean {
  return (
    Math.abs(kp.geo.lat - point.geo.lat) < 1e-9 && Math.abs(kp.geo.lng - point.geo.lon) < 1e-9
  );
}

// A world point for a stored pair whose keypoint the frame no longer offers:
// one clicked before the case had this frame, or before the keypoint finder
// changed. It is still a valid pair, so it is shown, kept, and can be retaken
// like any other. It has no raster position and no SIFT response.
function keypointForStoredPair(point: ControlPointInput, id: number): CoastlineKeypoint {
  return {
    id,
    pixel: { x: 0, y: 0 },
    geo: { lat: point.geo.lat, lng: point.geo.lon },
    response: 0,
  };
}

// The keypoints offered for the frame, then the stored pairs they no longer
// offer, numbered after them. Built once: the modal is mounted per opening,
// with the keypoints of the current frame.
const worldKeypoints: CoastlineKeypoint[] = [...props.keypoints];
for (const point of [...props.initialPoints, ...props.initialCheckPoints]) {
  if (point.source !== "sift" || worldKeypoints.some((kp) => sameGeo(kp, point))) continue;
  worldKeypoints.push(keypointForStoredPair(point, -worldKeypoints.length - 1));
}

// A stored point carries its keypoint's coordinates, not its index: find the
// keypoint again by position.
function matchesFromPoints(points: ControlPointInput[], check = false): GeorefMatch[] {
  const restored: GeorefMatch[] = [];
  for (const point of points) {
    if (point.source !== "sift") continue;
    const index = worldKeypoints.findIndex((kp) => sameGeo(kp, point));
    if (index < 0 || restored.some((m) => m.index === index)) continue;
    restored.push({
      index,
      world: [point.geo.lat, point.geo.lon],
      image: [point.pixel.x, point.pixel.y],
      check,
    });
  }
  return restored;
}

const restoredFit = matchesFromPoints(props.initialPoints);
matches.value = [
  ...restoredFit,
  ...matchesFromPoints(props.initialCheckPoints, true).filter(
    (c) => !restoredFit.some((m) => m.index === c.index),
  ),
];
// Start on a free keypoint, so the first click does not replace a restored pair.
activeIndex.value = Math.max(
  0,
  worldKeypoints.findIndex((_, i) => !matches.value.some((m) => m.index === i)),
);

const totalPoints = worldKeypoints.length;
const matchedCount = computed<number>(() => matches.value.length);

const checkCount = computed<number>(() => matches.value.filter((m) => m.check).length);
const fitCount = computed<number>(() => matchedCount.value - checkCount.value);
const sortedMatches = computed(() => [...matches.value].sort((a, b) => a.index - b.index));

// Only the pairs used for the fit count towards the minimum.
const canConfirm = computed<boolean>(() => fitCount.value >= props.minPairs);

function toggleCheck(index: number, checked: boolean): void {
  matches.value = matches.value.map((m) => (m.index === index ? { ...m, check: checked } : m));
}

const currentWorldKeypoint = computed<CoastlineKeypoint | null>(() => {
  if (activeIndex.value < 0 || activeIndex.value >= totalPoints) return null;
  return worldKeypoints[activeIndex.value];
});

const worldPoints: WorldMapPoint[] = worldKeypoints.map((kp) => ({
  lat: kp.geo.lat,
  lng: kp.geo.lng,
}));

const matchedWorldPoints = computed<MatchedWorldPointSummary[]>(() =>
  matches.value.map((m) => ({ index: m.index, check: !!m.check })),
);

const matchedImagePoints = computed<MatchedImagePoint[]>(() =>
  matches.value.map((m) => ({
    index: m.index,
    x: m.image[0],
    y: m.image[1],
    check: !!m.check,
  })),
);

function resetMatching(): void {
  matches.value = [];
  activeIndex.value = 0;
  currentImagePoint.value = null;
}

function onSelectWorldKeypoint(index: number): void {
  if (index < 0 || index >= totalPoints) return;
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
  // Focus the pair whose marker was clicked on the image.
  if (index < 0 || index >= totalPoints) return;
  activeIndex.value = index;
  currentImagePoint.value = null;

  // Clicking a matched circle on the image also means "retake".
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

  const toPoint = (m: GeorefMatch): ControlPointInput => ({
    source: "sift",
    pixel: { x: m.image[0], y: m.image[1] },
    geo: { lon: m.world[1], lat: m.world[0] },
  });

  emit(
    "confirmed",
    matches.value.filter((m) => !m.check).map(toPoint),
    matches.value.filter((m) => m.check).map(toPoint),
  );
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
    // can reassign it by clicking a different location on the image. A
    // re-placed pair keeps its check-point tick.
    const wasCheck = matches.value.some((m) => m.index === kpIndex && m.check);
    matches.value = matches.value.filter((m) => m.index !== kpIndex);

    matches.value.push({
      index: kpIndex,
      world: [kp.geo.lat, kp.geo.lng],
      image: val,
      check: wasCheck,
    });

    // After matching, move focus to the next UNMATCHED keypoint.
    // This avoids jumping back to an already-matched point when
    // redoing earlier pairs.
    const total = totalPoints;
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
