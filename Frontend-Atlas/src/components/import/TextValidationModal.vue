<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-3"
  >
    <div
      class="bg-white rounded-2xl shadow-2xl w-full max-w-[96vw] h-[92vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200"
    >
      <!-- Header -->
      <div class="px-6 py-3.5 border-b border-gray-100 flex items-center justify-between bg-gray-50/80 shrink-0">
        <div>
          <div class="flex items-center gap-2.5">
            <div class="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
            </div>
            <h2 class="text-lg font-bold text-gray-900">Validation des textes non reconnus</h2>
          </div>
          <p class="text-xs text-gray-500 mt-0.5">
            Comparez avec l'image originale à gauche et validez les textes détectés (localisés et non localisés) à conserver sur la carte.
          </p>
        </div>
        <button
          type="button"
          class="btn btn-ghost btn-sm btn-circle text-gray-400 hover:text-gray-600"
          :disabled="isSubmitting"
          @click="emit('cancel')"
        >
          ✕
        </button>
      </div>

      <!-- Main Body: 3 columns (Original image | Map | Text validation panel) -->
      <div class="flex-1 min-h-0 flex divide-x divide-gray-200">
        <!-- 1. Left: Original Image -->
        <div v-if="imageUrl" class="w-[30%] lg:w-[32%] flex flex-col bg-gray-900 min-h-0 relative shrink-0">
          <div class="px-3 py-2 bg-gray-800 text-white text-xs font-semibold flex items-center justify-between shrink-0">
            <span class="flex items-center gap-1.5">
              <svg class="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
              Photo originale de l'image
            </span>
            <div class="flex items-center gap-1">
              <button
                type="button"
                class="btn btn-xs btn-ghost text-white px-1.5 h-6 min-h-0"
                title="Dézoomer"
                @click="zoomImg(-0.25)"
              >
                −
              </button>
              <button
                type="button"
                class="btn btn-xs btn-ghost text-white px-2 h-6 min-h-0 text-[11px]"
                title="Réinitialiser"
                @click="resetImgZoom"
              >
                {{ Math.round(imgZoom * 100) }}%
              </button>
              <button
                type="button"
                class="btn btn-xs btn-ghost text-white px-1.5 h-6 min-h-0"
                title="Zoomer"
                @click="zoomImg(0.25)"
              >
                +
              </button>
            </div>
          </div>
          <div class="flex-1 min-h-0 overflow-auto flex items-center justify-center p-2 bg-gray-950">
            <img
              :src="imageUrl"
              alt="Image originale de la carte"
              class="max-w-none transition-transform duration-100 origin-center select-none"
              :style="{ transform: `scale(${imgZoom})` }"
            />
          </div>
        </div>

        <!-- 2. Center: Offline Leaflet Map -->
        <div class="flex-1 min-w-0 relative flex flex-col" data-testid="map-container">
          <div class="px-3 py-2 bg-gray-50 border-b border-gray-100 text-xs font-semibold text-gray-700 shrink-0 flex items-center justify-between">
            <span>Positionnement temporaire sur la carte</span>
            <span class="text-[11px] text-gray-400 font-normal">Basemap hors ligne</span>
          </div>
          <div class="flex-1 min-h-0 relative">
            <div ref="mapContainer" class="w-full h-full bg-[#cfe8ff]" />
            <!-- Map Legend -->
            <div class="absolute bottom-3 left-3 bg-white/95 rounded-lg shadow px-2.5 py-1.5 text-[11px] space-y-1 z-[1000] border border-gray-100">
              <div class="flex items-center gap-1.5">
                <span class="w-2.5 h-2.5 rounded-full bg-amber-400 inline-block border border-amber-600" />
                <span>Textes localisés (à valider)</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 3. Right: Validation List (Localisés & Non localisés only) -->
        <div class="w-[320px] lg:w-[350px] shrink-0 flex flex-col bg-white overflow-hidden">
          <!-- 2 Tabs: Localisés & Non localisés -->
          <div class="flex border-b border-gray-200 shrink-0 bg-gray-50">
            <button
              v-for="tab in TABS"
              :key="tab.key"
              type="button"
              class="flex-1 py-2.5 text-xs font-semibold transition-colors border-b-2 -mb-px"
              :class="
                activeTab === tab.key
                  ? `border-${tab.color}-500 text-${tab.color}-700 bg-white`
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              "
              @click="activeTab = tab.key"
            >
              <span>{{ tab.label }}</span>
              <span
                class="ml-1.5 badge badge-xs"
                :class="`bg-${tab.color}-100 text-${tab.color}-800 border-0`"
              >
                {{ countByTab(tab.key) }}
              </span>
            </button>
          </div>

          <!-- Section Action Header: Select All / Deselect All -->
          <div class="px-3 py-2 border-b border-gray-100 flex items-center justify-between shrink-0 bg-white text-xs">
            <span class="text-gray-500">
              {{ selectedInTab(activeTab) }} / {{ countByTab(activeTab) }} conservé(s)
            </span>
            <div class="flex items-center gap-2">
              <button
                type="button"
                class="text-indigo-600 hover:underline font-medium"
                @click="setAllInTab(activeTab, true)"
              >
                Tout sélectionner
              </button>
              <span class="text-gray-300">|</span>
              <button
                type="button"
                class="text-gray-500 hover:underline font-medium"
                @click="setAllInTab(activeTab, false)"
              >
                Tout désélectionner
              </button>
            </div>
          </div>

          <!-- List of items for active tab -->
          <div class="flex-1 overflow-y-auto p-2 space-y-1.5">
            <div
              v-if="itemsInTab(activeTab).length === 0"
              class="text-xs text-gray-400 italic text-center py-8"
            >
              Aucun texte dans cette catégorie.
            </div>

            <div
              v-for="item in itemsInTab(activeTab)"
              :key="item.id"
              class="flex items-center gap-2 p-2 rounded-lg border transition-all cursor-pointer"
              :class="[
                item.id === highlightedId ? 'ring-2 ring-indigo-400' : '',
                item.selected
                  ? categoryBorderClass(item.category)
                  : 'border-gray-200 opacity-60 bg-gray-50',
              ]"
              @click="onItemClick(item)"
            >
              <!-- Checkbox -->
              <input
                v-model="item.selected"
                type="checkbox"
                :class="categoryCheckboxClass(item.category)"
                class="checkbox checkbox-sm shrink-0"
                :aria-label="`Conserver ${item.text}`"
                @click.stop
              />

              <!-- Text input -->
              <div class="flex-1 min-w-0">
                <input
                  v-model="item.text"
                  type="text"
                  class="input input-bordered input-xs w-full text-sm font-medium"
                  :placeholder="item.originalText"
                  @click.stop
                  @input="refreshMarker(item)"
                />
              </div>

              <!-- Coords badge -->
              <div class="shrink-0 text-[10px]" @click.stop>
                <span
                  v-if="item.category === 'unrecognized_localized'"
                  class="badge badge-xs badge-outline border-amber-400 text-amber-700"
                >
                  georef: {{ fmtCoords(item.coordinates) }}
                </span>
                <span v-else class="badge badge-xs badge-ghost text-gray-400">
                  non localisé
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <div class="px-6 py-3 border-t border-gray-100 flex items-center justify-between bg-gray-50 shrink-0">
        <div class="text-xs text-gray-600">
          Sélectionné(s) à conserver :
          <span class="font-bold text-gray-900">{{ toKeepCount }}</span>
          sur {{ pendingValidationCount }} texte(s)
          <span v-if="recognizedCount > 0" class="text-gray-400 ml-1.5">
            (+ {{ recognizedCount }} reconnu(s) automatiquement conservé{{ recognizedCount > 1 ? 's' : '' }})
          </span>
        </div>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="btn btn-outline btn-sm"
            :disabled="isSubmitting"
            @click="emit('cancel')"
          >
            Passer
          </button>
          <button
            type="button"
            class="btn btn-primary btn-sm bg-indigo-600 hover:bg-indigo-700 text-white font-semibold"
            :disabled="isSubmitting"
            @click="onConfirm"
          >
            <span v-if="isSubmitting" class="loading loading-spinner loading-xs" />
            Confirmer et afficher sur la carte
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount, nextTick } from "vue";
import type L from "leaflet";

// ─── Types ────────────────────────────────────────────────────────────────────

export type TextCategory =
  | "recognized"
  | "unrecognized_localized"
  | "unrecognized_unlocalized";

export interface TextValidationEntry {
  id: string;
  text: string;
  originalText: string;
  selected: boolean;
  recognized: boolean;
  category: TextCategory;
  matchedCity?: string;
  country?: string;
  coordinates?: [number, number]; // [lon, lat]
  confidence?: number;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function categorize(entry: Omit<TextValidationEntry, "category">): TextCategory {
  if (entry.recognized) return "recognized";
  const [lon, lat] = entry.coordinates ?? [0, 0];
  if (lon !== 0 || lat !== 0) return "unrecognized_localized";
  return "unrecognized_unlocalized";
}

function fmtCoords(coords?: [number, number]): string {
  if (!coords) return "?";
  return `${coords[1].toFixed(2)}°, ${coords[0].toFixed(2)}°`;
}

// ─── Constants: ONLY 2 tabs in the validation modal ──────────────────────────

const TABS = [
  {
    key: "unrecognized_localized" as TextCategory,
    label: "Localisés",
    icon: "◎",
    color: "amber",
  },
  {
    key: "unrecognized_unlocalized" as TextCategory,
    label: "Non localisés",
    icon: "✕",
    color: "red",
  },
] as const;

// ─── Props / Emits ────────────────────────────────────────────────────────────

const props = withDefaults(
  defineProps<{
    isOpen: boolean;
    imageUrl?: string | null;
    initialItems?: TextValidationEntry[];
    /** @deprecated use initialItems */
    initialRecognized?: TextValidationEntry[];
    /** @deprecated use initialItems */
    initialUnrecognized?: TextValidationEntry[];
    isSubmitting?: boolean;
  }>(),
  {
    imageUrl: null,
    initialItems: () => [],
    initialRecognized: () => [],
    initialUnrecognized: () => [],
    isSubmitting: false,
  },
);

const emit = defineEmits<{
  (e: "confirm", items: TextValidationEntry[]): void;
  (e: "cancel"): void;
}>();

// ─── State ────────────────────────────────────────────────────────────────────

const mapContainer = ref<HTMLElement | null>(null);
const activeTab = ref<TextCategory>("unrecognized_localized");
const highlightedId = ref<string | null>(null);
const allItems = ref<TextValidationEntry[]>([]);

// Original image zoom
const imgZoom = ref(1);
function zoomImg(delta: number) {
  imgZoom.value = Math.max(0.25, Math.min(4, imgZoom.value + delta));
}
function resetImgZoom() {
  imgZoom.value = 1;
}

let leafletMap: L.Map | null = null;
let landLayer: L.GeoJSON | null = null;
const markerMap = new Map<string, L.CircleMarker>();

// ─── Computed ─────────────────────────────────────────────────────────────────

// The items shown in the modal (only localized and unlocalized)
const pendingValidationItems = computed(() =>
  allItems.value.filter((i) => i.category !== "recognized"),
);

const recognizedCount = computed(
  () => allItems.value.filter((i) => i.category === "recognized").length,
);

const pendingValidationCount = computed(
  () => pendingValidationItems.value.length,
);

const toKeepCount = computed(
  () => pendingValidationItems.value.filter((i) => i.selected).length,
);

function itemsInTab(tab: TextCategory): TextValidationEntry[] {
  return pendingValidationItems.value.filter((i) => i.category === tab);
}

function countByTab(tab: TextCategory): number {
  return itemsInTab(tab).length;
}

function selectedInTab(tab: TextCategory): number {
  return itemsInTab(tab).filter((i) => i.selected).length;
}

// ─── Styling helpers ──────────────────────────────────────────────────────────

function categoryBorderClass(cat: TextCategory): string {
  if (cat === "unrecognized_localized") return "border-amber-200 bg-white shadow-sm";
  return "border-red-200 bg-white shadow-sm";
}

function categoryCheckboxClass(cat: TextCategory): string {
  if (cat === "unrecognized_localized") return "checkbox-warning";
  return "checkbox-error";
}

// ─── Item interactions ────────────────────────────────────────────────────────

function onItemClick(item: TextValidationEntry) {
  highlightedId.value = item.id;
  const marker = markerMap.get(item.id);
  if (marker && leafletMap) {
    leafletMap.setView(marker.getLatLng(), Math.max(leafletMap.getZoom(), 5), {
      animate: true,
    });
    marker.openTooltip();
  }
}

function setAllInTab(tab: TextCategory, selected: boolean) {
  for (const item of pendingValidationItems.value) {
    if (item.category === tab) {
      item.selected = selected;
      updateMarkerStyle(item);
    }
  }
}

function refreshMarker(item: TextValidationEntry) {
  const marker = markerMap.get(item.id);
  if (marker) marker.setTooltipContent(item.text);
}

// ─── Map management (100% offline via local GeoJSON) ─────────────────────────

function makeCircleMarker(
  L: typeof import("leaflet"),
  item: TextValidationEntry,
): L.CircleMarker {
  const [lon, lat] = item.coordinates ?? [0, 0];

  const marker = L.circleMarker([lat, lon], {
    radius: 9,
    fillColor: "#f59e0b",
    color: "#b45309",
    weight: 2,
    fillOpacity: item.selected ? 0.9 : 0.35,
  });

  marker.bindTooltip(item.text, {
    permanent: true,
    direction: "top",
    offset: [0, -10],
    className: "leaflet-tooltip-validation",
  });

  marker.on("click", () => {
    highlightedId.value = item.id;
    activeTab.value = item.category;
    item.selected = !item.selected;
    updateMarkerStyle(item);
  });

  return marker;
}

function updateMarkerStyle(item: TextValidationEntry) {
  const marker = markerMap.get(item.id);
  if (!marker) return;
  marker.setStyle({ fillOpacity: item.selected ? 0.9 : 0.35 });
}

async function initMap() {
  if (!mapContainer.value) return;

  const L = (await import("leaflet")).default;
  await import("leaflet/dist/leaflet.css");

  if (leafletMap) {
    leafletMap.remove();
    leafletMap = null;
  }
  if (landLayer) {
    landLayer = null;
  }
  markerMap.clear();

  const map = L.map(mapContainer.value, {
    center: [20, 0],
    zoom: 2,
    zoomControl: true,
    attributionControl: false,
    maxBoundsViscosity: 1.0,
  });

  // Offline basemap using local GeoJSON (no internet needed)
  try {
    const baseUrl =
      typeof window !== "undefined" && window.location?.origin
        ? window.location.origin
        : "http://localhost";
    const geojsonFiles = [
      "/geojson/ne_coastline.geojson",
      "/geojson/ne_50m_lakes.geojson",
    ];
    const responses = await Promise.all(
      geojsonFiles.map((f) => fetch(new URL(f, baseUrl).toString())),
    );
    const geojsonData = await Promise.all(
      responses.filter((r) => r.ok).map((r) => r.json()),
    );

    const combinedGeoJSON: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: geojsonData.flatMap((data: any) => data.features || []),
    };

    landLayer = L.geoJSON(combinedGeoJSON, {
      style: {
        fillColor: "#e5e7eb",
        fillOpacity: 0.9,
        color: "#9ca3af",
        weight: 1,
        opacity: 1,
      },
    }).addTo(map);
  } catch (err) {
    console.warn("Could not load local offline GeoJSON basemap:", err);
  }

  leafletMap = map;

  // Add markers ONLY for localized items to validate (not the already recognized ones)
  const bounds: [number, number][] = [];

  for (const item of itemsInTab("unrecognized_localized")) {
    if (!item.coordinates) continue;
    const [lon, lat] = item.coordinates;
    if (lon === 0 && lat === 0) continue;

    const marker = makeCircleMarker(L, item);
    marker.addTo(map);
    markerMap.set(item.id, marker);
    bounds.push([lat, lon]);
  }

  if (bounds.length > 0) {
    map.fitBounds(bounds as L.LatLngBoundsExpression, {
      padding: [40, 40],
      maxZoom: 8,
    });
  }
}

function destroyMap() {
  if (landLayer && leafletMap) {
    leafletMap.removeLayer(landLayer);
    landLayer = null;
  }
  if (leafletMap) {
    leafletMap.remove();
    leafletMap = null;
  }
  markerMap.clear();
}

// ─── Watch ────────────────────────────────────────────────────────────────────

watch(
  () =>
    [
      props.isOpen,
      props.initialItems,
      props.initialRecognized,
      props.initialUnrecognized,
    ] as const,
  ([open, items, rec, unrec]) => {
    if (!open) {
      destroyMap();
      return;
    }

    const source: TextValidationEntry[] =
      items && items.length > 0
        ? items
        : [...(rec || []), ...(unrec || [])];

    allItems.value = source.map((item) => {
      const cat = item.category ?? categorize(item);
      return {
        ...item,
        category: cat,
        // Recognized are always kept. Localized and unlocalized default to false so user selects what to keep.
        selected: item.selected ?? (cat === "recognized"),
      };
    });

    // Auto-select tab: if no localized items, switch to unlocalized
    const locCount = allItems.value.filter(
      (i) => i.category === "unrecognized_localized",
    ).length;
    if (locCount === 0) {
      activeTab.value = "unrecognized_unlocalized";
    } else {
      activeTab.value = "unrecognized_localized";
    }

    nextTick(() => initMap());
  },
  { immediate: true, deep: true },
);

watch(
  allItems,
  (items) => {
    for (const item of items) {
      updateMarkerStyle(item);
    }
  },
  { deep: true },
);

onBeforeUnmount(() => destroyMap());

// ─── Confirm ──────────────────────────────────────────────────────────────────

function onConfirm() {
  // Confirm emits all items: recognized (always kept) + user's selection for localized/unlocalized
  emit("confirm", allItems.value);
}
</script>

<style>
.leaflet-tooltip-validation {
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  color: #1f2937;
  padding: 2px 6px;
  white-space: nowrap;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15);
}
.leaflet-tooltip-validation::before {
  border-top-color: #d1d5db;
}
</style>
