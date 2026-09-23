<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-50 flex items-start justify-center bg-black/60 overflow-y-auto"
  >
    <div class="bg-base-100 rounded-lg shadow-xl max-w-6xl w-full mx-4 my-6 p-6 flex flex-col gap-4">
      <div class="flex justify-between items-center mb-2">
        <h2 class="text-xl font-semibold">Villes de la carte (optionnel)</h2>
        <button class="btn btn-ghost btn-sm" @click="emit('close')">✕</button>
      </div>

      <p class="text-sm text-base-content/70">
        Tapez le nom d'une ville que votre carte montre, choisissez-la dans la
        liste, puis cliquez à l'endroit où votre carte la place (à droite).
        Seules les villes de la zone choisie sur le monde sont proposées.
      </p>
      <p class="text-xs text-base-content/60">
        Pour reprendre une ville, recliquez sur son marqueur (sur la carte du
        monde ou sur l'image) ou sur son nom dans la liste. Les points SIFT déjà
        placés apparaissent en gris.
      </p>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <!-- Search -->
        <div class="space-y-2">
          <div class="relative">
            <input
              v-model="query"
              type="search"
              class="input input-bordered input-sm w-full"
              placeholder="Nom de ville (ex. Montréal, Trois-Rivières, Kebek)"
              @keydown.enter.prevent="pickFirstCandidate"
            />
            <span
              v-if="isSearching"
              class="loading loading-spinner loading-xs absolute right-3 top-2"
            />
          </div>

          <ul
            v-if="candidates.length > 0"
            class="menu menu-xs bg-base-200 rounded-box max-h-48 overflow-y-auto flex-nowrap"
          >
            <li v-for="c in candidates" :key="c.id">
              <button type="button" class="flex justify-between gap-2" @click="pickCandidate(c)">
                <span>
                  {{ c.name }}
                  <span v-if="c.matchedName !== c.name" class="text-base-content/60">
                    (« {{ c.matchedName }} »)
                  </span>
                  <span v-if="c.match === 'fuzzy'" class="badge badge-ghost badge-xs ml-1">
                    proche
                  </span>
                </span>
                <span class="text-base-content/60 whitespace-nowrap">
                  {{ c.country }} · {{ formatPopulation(c.population) }}
                </span>
              </button>
            </li>
          </ul>
          <p
            v-else-if="query.trim() && !isSearching && hasSearched"
            class="text-xs text-base-content/60"
          >
            Aucune ville de ce nom dans la zone choisie.
          </p>
          <p v-if="searchError" class="text-xs text-error">{{ searchError }}</p>
          <p v-if="notice" class="text-xs text-warning">{{ notice }}</p>
        </div>

        <!-- Chosen cities -->
        <div class="space-y-1">
          <p class="text-xs font-semibold text-base-content/70">
            Villes choisies : {{ placedCount }} placée{{ placedCount > 1 ? "s" : "" }}
            sur {{ entries.length }}
          </p>
          <p v-if="entries.length === 0" class="text-xs text-base-content/60">
            Aucune ville pour l'instant. Cette étape est facultative.
          </p>
          <ul v-else class="max-h-48 overflow-y-auto space-y-1">
            <li
              v-for="(entry, index) in entries"
              :key="entry.city.id"
              class="flex items-center gap-2 text-sm rounded px-2 py-1 cursor-pointer"
              :class="index === activeIndex ? 'bg-primary/15' : 'hover:bg-base-200'"
              @click="activate(index)"
            >
              <span
                class="inline-block w-3 h-3 rounded-full shrink-0"
                :style="{ backgroundColor: colorFor(index) }"
              />
              <span class="flex-1 min-w-0 truncate">{{ entry.city.name }}</span>
              <span
                class="text-xs"
                :class="entry.image ? 'text-success' : 'text-base-content/60'"
              >
                {{
                  entry.image
                    ? "placée"
                    : index === activeIndex
                      ? "cliquez sur l'image"
                      : "à placer"
                }}
              </span>
              <button
                type="button"
                class="btn btn-ghost btn-xs px-1"
                title="Retirer"
                @click.stop="remove(index)"
              >
                ✕
              </button>
            </li>
          </ul>
        </div>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 flex-1 min-h-[360px]">
        <div class="border rounded-md overflow-hidden">
          <h3 class="px-3 py-2 text-sm font-medium bg-base-200 border-b">
            Carte du monde (villes choisies)
          </h3>
          <GeoRefWorldMap
            class="h-80 md:h-[28rem]"
            :world-bounds="worldBounds"
            :points="worldPoints"
            :active-index="activeIndex"
            :matched-points="matchedWorldPoints"
            :context-points="contextWorldPoints"
            :used-lakes="usedLakes"
            @select-point="onSelectWorldPoint"
          />
        </div>

        <div class="border rounded-md overflow-hidden">
          <h3 class="px-3 py-2 text-sm font-medium bg-base-200 border-b">
            Image importée
            <span v-if="activeEntry" class="font-normal text-base-content/70">
              — cliquez sur {{ activeEntry.city.name }}
            </span>
          </h3>
          <GeoRefImageMap
            ref="imageMapRef"
            class="h-80 md:h-[28rem]"
            :image-url="imageUrl"
            :matched-points="matchedImagePoints"
            :context-points="contextImagePoints"
            v-model:point="currentImagePoint"
            @select-match="onSelectImageMatch"
          />
        </div>
      </div>

      <div class="flex justify-between items-center pt-2">
        <div class="text-xs text-base-content/60">
          <span v-if="unplacedCount > 0">
            {{ unplacedCount }} ville{{ unplacedCount > 1 ? "s" : "" }} non
            placée{{ unplacedCount > 1 ? "s" : "" }} ne sera pas utilisée{{
              unplacedCount > 1 ? "s" : ""
            }}.
          </span>
        </div>
        <div class="flex gap-2">
          <button class="btn btn-ghost btn-sm" @click="resetCities">Réinitialiser</button>
          <button class="btn btn-primary btn-sm" @click="onConfirm">
            {{
              placedCount > 0
                ? `Confirmer ${placedCount} ville${placedCount > 1 ? "s" : ""}`
                : "Continuer sans ville"
            }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import GeoRefWorldMap from "./GeoRefWorldMap.vue";
import GeoRefImageMap from "./GeoRefImageMap.vue";
import { useCityCandidates } from "../../composables/useCityCandidates";
import type {
  CityCandidate,
  ControlPointInput,
  MatchedImagePoint,
  MatchedWorldPointSummary,
  WorldBounds,
  WorldMapPoint,
  XYTuple,
} from "../../typescript/georef";

// One chosen city, and where the user clicked it on their map (null until placed).
type CityEntry = { city: CityCandidate; image: XYTuple | null };

const props = withDefaults(
  defineProps<{
    isOpen: boolean;
    imageUrl: string;
    worldBounds: WorldBounds;
    // SIFT points from the previous step, shown greyed for context
    siftPoints?: ControlPointInput[];
    // Cities confirmed earlier, restored when the user comes back to this step
    initialCities?: ControlPointInput[];
    usedLakes?: boolean;
  }>(),
  {
    isOpen: false,
    siftPoints: () => [],
    initialCities: () => [],
    usedLakes: false,
  },
);

const emit = defineEmits<{
  (e: "close"): void;
  (e: "confirmed", cities: ControlPointInput[]): void;
}>();

const PAIR_COLORS = [
  "#a855f7",
  "#e11d48",
  "#0ea5e9",
  "#f97316",
  "#22c55e",
  "#14b8a6",
  "#6366f1",
  "#facc15",
  "#ef4444",
  "#3b82f6",
];

const { candidates, isSearching, searchError, searchCities, clearCandidates } =
  useCityCandidates();

const imageMapRef = ref<InstanceType<typeof GeoRefImageMap> | null>(null);
const query = ref("");
const hasSearched = ref(false);
const notice = ref<string | null>(null);
const entries = ref<CityEntry[]>(entriesFromPoints(props.initialCities));
const activeIndex = ref<number>(-1);
const currentImagePoint = ref<XYTuple | null>(null);

function entriesFromPoints(points: ControlPointInput[]): CityEntry[] {
  return points.flatMap((p) =>
    p.source === "city"
      ? [
          {
            city: {
              id: p.city.id,
              name: p.city.name,
              lat: p.geo.lat,
              lon: p.geo.lon,
              country: "",
              population: 0,
              matchedName: p.city.name,
              match: "exact" as const,
            },
            image: [p.pixel.x, p.pixel.y] as XYTuple,
          },
        ]
      : [],
  );
}

const activeEntry = computed<CityEntry | null>(
  () => entries.value[activeIndex.value] ?? null,
);
const placedCount = computed(() => entries.value.filter((e) => e.image).length);
const unplacedCount = computed(() => entries.value.length - placedCount.value);

function colorFor(index: number): string {
  return PAIR_COLORS[index % PAIR_COLORS.length];
}

const worldPoints = computed<WorldMapPoint[]>(() =>
  entries.value.map((e) => ({ lat: e.city.lat, lng: e.city.lon, label: e.city.name })),
);

const matchedWorldPoints = computed<MatchedWorldPointSummary[]>(() =>
  entries.value.flatMap((e, index) => (e.image ? [{ index, color: colorFor(index) }] : [])),
);

const matchedImagePoints = computed<MatchedImagePoint[]>(() =>
  entries.value.flatMap((e, index) =>
    e.image ? [{ index, x: e.image[0], y: e.image[1], color: colorFor(index) }] : [],
  ),
);

const contextWorldPoints = computed<WorldMapPoint[]>(() =>
  props.siftPoints.map((p) => ({ lat: p.geo.lat, lng: p.geo.lon })),
);
const contextImagePoints = computed(() => props.siftPoints.map((p) => p.pixel));

function formatPopulation(population: number): string {
  return population > 0
    ? `${population.toLocaleString("fr-CA")} hab.`
    : "population inconnue";
}

// --- search ------------------------------------------------------------------

let searchTimer: ReturnType<typeof setTimeout> | null = null;

watch(query, (value) => {
  if (searchTimer) clearTimeout(searchTimer);
  // Typing again dismisses a notice; the reset after a pick must not.
  if (value.trim()) notice.value = null;
  if (!value.trim()) {
    hasSearched.value = false;
    clearCandidates();
    return;
  }
  searchTimer = setTimeout(async () => {
    await searchCities(value, props.worldBounds);
    hasSearched.value = true;
  }, 250);
});

onBeforeUnmount(() => {
  if (searchTimer) clearTimeout(searchTimer);
});

function pickCandidate(candidate: CityCandidate): void {
  const existing = entries.value.findIndex((e) => e.city.id === candidate.id);
  if (existing >= 0) {
    // Two spellings of one city ("Quebec", "Kebek") resolve to the same id.
    notice.value = `${candidate.name} est déjà dans la liste.`;
  } else {
    entries.value.push({ city: candidate, image: null });
    activeIndex.value = entries.value.length - 1;
    imageMapRef.value?.focusClickMode();
  }
  query.value = "";
  hasSearched.value = false;
  clearCandidates();
}

function pickFirstCandidate(): void {
  const first = candidates.value[0];
  if (first) pickCandidate(first);
}

// --- matching ----------------------------------------------------------------

// Selecting a city means "place (or re-place) this one": drop its click so the
// next click on the image sets it again.
function activate(index: number): void {
  if (index < 0 || index >= entries.value.length) return;
  activeIndex.value = index;
  currentImagePoint.value = null;
  entries.value[index].image = null;
  imageMapRef.value?.focusClickMode();
}

function onSelectWorldPoint(index: number): void {
  activate(index);
}

function onSelectImageMatch(index: number): void {
  activate(index);
}

function remove(index: number): void {
  entries.value.splice(index, 1);
  if (activeIndex.value === index) activeIndex.value = -1;
  else if (activeIndex.value > index) activeIndex.value -= 1;
}

function nextUnplaced(from: number): number {
  const n = entries.value.length;
  for (let step = 1; step <= n; step += 1) {
    const i = (from + step) % n;
    if (!entries.value[i].image) return i;
  }
  return -1;
}

watch(currentImagePoint, (point) => {
  if (!point) return;
  const index = activeIndex.value;
  if (index < 0 || index >= entries.value.length) {
    notice.value = "Choisissez d'abord une ville dans la liste.";
    currentImagePoint.value = null;
    return;
  }
  entries.value[index].image = point;
  activeIndex.value = nextUnplaced(index);
  currentImagePoint.value = null;
});

function resetCities(): void {
  entries.value = [];
  activeIndex.value = -1;
  currentImagePoint.value = null;
  query.value = "";
  notice.value = null;
  clearCandidates();
}

function onConfirm(): void {
  const cities: ControlPointInput[] = entries.value.flatMap((e) =>
    e.image
      ? [
          {
            source: "city" as const,
            pixel: { x: e.image[0], y: e.image[1] },
            geo: { lon: e.city.lon, lat: e.city.lat },
            city: { id: e.city.id, name: e.city.name },
          },
        ]
      : [],
  );
  emit("confirmed", cities);
}
</script>
