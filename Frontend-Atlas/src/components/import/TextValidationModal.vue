<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-[2000] flex items-center justify-center bg-black/60 backdrop-blur-xs p-3"
  >
    <div
      class="bg-base-100 rounded-2xl shadow-2xl w-full max-w-[96vw] h-[92vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200"
    >
      <!-- Header -->
      <div class="px-6 py-3 border-b border-base-200 flex items-center justify-between bg-base-100 shrink-0">
        <div class="flex items-center gap-6">
          <div class="flex items-center gap-2.5">
            <div class="w-8 h-8 rounded-lg bg-primary/10 text-primary flex items-center justify-center">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  stroke-width="2"
                  d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                />
              </svg>
            </div>
            <div>
              <h2 class="text-base font-bold text-black leading-tight">Validation des textes non reconnus</h2>
              <p class="text-xs text-black/70">
                Comparez avec l'image originale et validez les textes détectés.
              </p>
            </div>
          </div>

          <!-- Status legend -->
          <div class="hidden md:flex items-center gap-4 px-3 py-1 bg-base-200/50 rounded-lg border border-base-300 text-xs">
            <div class="flex items-center gap-1.5">
              <span class="w-2.5 h-2.5 rounded-full bg-blue-500 inline-block border border-blue-600" />
              <span class="font-medium text-black">Position estimée image</span>
            </div>
            <div class="flex items-center gap-1.5">
              <span class="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block border border-emerald-600" />
              <span class="font-medium text-black">Ville suggérée adoptée</span>
            </div>
            <div class="flex items-center gap-1.5">
              <span class="w-3.5 h-3.5 rounded-full bg-amber-500 text-white font-bold text-[9px] flex items-center justify-center border border-amber-600">!</span>
              <span class="font-medium text-black">Suggestion disponible (75 km)</span>
            </div>
          </div>
        </div>
        <button
          type="button"
          class="btn btn-ghost btn-sm btn-circle text-black hover:bg-base-200"
          :disabled="isSubmitting"
          @click="emit('cancel')"
        >
          ✕
        </button>
      </div>

      <!-- Main Body: 3 columns with draggable dividers -->
      <div
        class="flex-1 min-h-0 flex overflow-hidden select-none"
        :class="{ 'cursor-col-resize': isDraggingLeft || isDraggingRight }"
      >
        <!-- 1. Left: Original Image Viewer -->
        <div
          class="flex flex-col bg-gray-900 min-h-0 relative shrink-0 overflow-hidden"
          :style="{ width: `${leftColWidth}px` }"
        >
          <div class="px-3 py-2 bg-gray-800 text-white font-semibold flex items-center justify-between shrink-0 text-xs">
            <span class="flex items-center gap-1.5">
              <PhotoIcon class="w-4 h-4 text-gray-400" />
              Photo originale de l'image
            </span>
            <div class="flex items-center gap-1">
              <template v-if="displayImageUrl">
                <button
                  type="button"
                  class="btn btn-xs btn-ghost text-white px-1.5 min-h-0 h-6 text-xs"
                  title="Dézoomer"
                  @click="zoomImg(-0.1)"
                >
                  −
                </button>
                <button
                  type="button"
                  class="btn btn-xs btn-ghost text-white px-2 min-h-0 h-6 text-[11px]"
                  title="Réinitialiser"
                  @click="resetImgZoom"
                >
                  {{ Math.round(imgZoom * 100) }}%
                </button>
                <button
                  type="button"
                  class="btn btn-xs btn-ghost text-white px-1.5 min-h-0 h-6 text-xs"
                  title="Zoomer"
                  @click="zoomImg(0.1)"
                >
                  +
                </button>
              </template>

              <label
                class="btn btn-xs btn-ghost text-white px-1.5 min-h-0 h-6 text-[11px] cursor-pointer"
                title="Charger une image pour visualiser"
              >
                <ArrowUpTrayIcon class="w-3.5 h-3.5" />
                <span class="hidden sm:inline">Changer</span>
                <input
                  type="file"
                  accept="image/*"
                  class="hidden"
                  @change="onLocalImageSelected"
                />
              </label>
            </div>
          </div>

          <div class="flex-1 min-h-0 overflow-auto flex items-center justify-center p-2 bg-gray-950">
            <img
              v-if="displayImageUrl"
              :src="displayImageUrl"
              alt="Image de la carte pour visualisation"
              class="max-w-full max-h-full object-contain transition-transform duration-100 origin-center select-none will-change-transform"
              :style="{ transform: `scale(${imgZoom}) translateZ(0)` }"
            />
            <div v-else class="flex flex-col items-center justify-center p-6 text-center gap-3 max-w-sm">
              <PhotoIcon class="w-12 h-12 text-gray-500" />
              <div class="flex flex-col gap-1">
                <p class="text-xs text-gray-200 font-semibold">
                  Aucune image originale disponible pour cette carte.
                </p>
                <p class="text-[11px] text-gray-400">
                  Vous pouvez importer une image depuis votre ordinateur pour vous repérer pendant la validation.
                </p>
              </div>
              <label class="btn btn-primary btn-xs text-white cursor-pointer gap-1.5 font-medium shadow-xs mt-1">
                <ArrowUpTrayIcon class="w-3.5 h-3.5" />
                <span>Importer une image pour visualiser</span>
                <input
                  type="file"
                  accept="image/*"
                  class="hidden"
                  @change="onLocalImageSelected"
                />
              </label>
              <span class="text-[10px] text-gray-500 italic">
                (Visible uniquement pendant cette session)
              </span>
            </div>
          </div>
        </div>

        <!-- Left Resizer Divider -->
        <div
          class="w-1.5 bg-base-300 hover:bg-primary active:bg-primary transition-colors cursor-col-resize shrink-0 z-10"
          title="Glisser pour redimensionner la colonne"
          @mousedown="startColResize(true, $event)"
        />

        <!-- 2. Center: Leaflet Map -->
        <div class="flex-1 min-w-[200px] relative flex flex-col overflow-hidden" data-testid="map-container">
          <div class="px-3 py-2 bg-base-200/70 border-b border-base-300 text-xs shrink-0 flex items-center justify-between">
            <span class="text-black font-semibold">Positionnement géographique</span>
            <span class="text-[11px] text-primary font-medium">Glissez les points ou cliquez sur la carte pour ajuster leur position</span>
          </div>
          <div class="flex-1 min-h-0 relative">
            <div ref="mapContainer" class="w-full h-full bg-[#cfe8ff]" />
          </div>
        </div>

        <!-- Right Resizer Divider -->
        <div
          class="w-1.5 bg-base-300 hover:bg-primary active:bg-primary transition-colors cursor-col-resize shrink-0 z-10"
          title="Glisser pour redimensionner la colonne"
          @mousedown="startColResize(false, $event)"
        />

        <!-- 3. Right: Validation List -->
        <div
          class="shrink-0 flex flex-col bg-base-100 overflow-hidden border-l border-base-200"
          :style="{ width: `${rightColWidth}px` }"
        >
          <!-- List Header -->
          <div class="px-3.5 py-2.5 border-b border-base-200 shrink-0 bg-base-200/50 flex items-center justify-between text-sm">
            <span class="font-bold text-black flex items-center gap-1.5">
              <span>✕</span>
              <span>Non localisés</span>
            </span>
            <span class="badge badge-sm badge-neutral font-semibold text-black bg-base-300 border-0">
              {{ allItems.length }}
            </span>
          </div>

          <!-- Select All Controls -->
          <div class="px-3.5 py-2.5 border-b border-base-200 flex items-center justify-between shrink-0 bg-base-100 text-xs">
            <label class="flex items-center gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                data-testid="select-all-checkbox"
                class="checkbox checkbox-sm checkbox-primary rounded cursor-pointer"
                :checked="isAllSelected"
                :indeterminate.prop="isPartiallySelected"
                @change="onToggleSelectAll"
              />
              <span class="font-bold text-black text-sm">
                Tout sélectionner
              </span>
            </label>
            <span class="font-semibold text-black">
              {{ toKeepCount }} / {{ allItems.length }} conservé(s)
            </span>
          </div>

          <!-- Items list -->
          <div class="flex-1 overflow-y-auto p-2 flex flex-col gap-2">
            <div
              v-if="allItems.length === 0"
              class="text-xs text-black italic text-center py-8"
            >
              Aucun texte dans cette catégorie.
            </div>

            <div
              v-for="item in allItems"
              :key="item.id"
              class="flex flex-col p-2 gap-1.5 rounded-lg border transition-all cursor-pointer bg-base-100 hover:border-primary/50"
              :class="[
                item.id === highlightedId ? 'ring-2 ring-primary border-primary bg-primary/5' : '',
                itemBorderClass(item),
              ]"
              @click="focusItem(item)"
              @mouseenter="onItemHover(item)"
              @mouseleave="onItemLeave"
            >
              <!-- Checkbox + Input + Trash -->
              <div class="flex items-center gap-1.5">
                <input
                  type="checkbox"
                  data-testid="item-checkbox"
                  class="checkbox checkbox-sm checkbox-primary rounded shrink-0 cursor-pointer"
                  :checked="item.selected"
                  :title="item.selected ? 'Décocher pour ne pas conserver ce texte' : 'Cocher pour conserver ce texte'"
                  @click.stop
                  @change="toggleItemSelection(item)"
                />

                <div class="relative flex-1 flex items-center">
                  <input
                    v-model="item.text"
                    type="text"
                    class="input input-bordered input-sm w-full h-8 text-sm font-medium bg-base-100 text-black border-base-300 focus:border-primary placeholder:text-gray-400 px-2"
                    :placeholder="item.originalText"
                    @click.stop
                    @input="onTextInput(item)"
                  />
                  <!-- Amber badge if suggestion available -->
                  <span
                    v-if="item.suggestedCity && !item.useSuggestedCity"
                    class="absolute right-2 px-1.5 py-0.5 rounded-full bg-amber-500 text-white font-extrabold text-[10px] pointer-events-none shadow-xs"
                    title="Suggestion de ville à proximité disponible"
                  >
                    !
                  </span>
                </div>

                <button
                  type="button"
                  class="btn btn-ghost btn-xs btn-square w-7 h-7 text-error hover:bg-error/10 shrink-0"
                  title="Supprimer ce texte de la carte"
                  @click.stop="toggleSupprimer(item)"
                >
                  <TrashIcon class="w-4 h-4 text-error" />
                </button>
              </div>

              <!-- Suggested city pill button -->
              <div
                v-if="item.suggestedCity"
                class="flex items-center pt-0.5"
                @click.stop
              >
                <button
                  type="button"
                  class="btn btn-xs h-7 flex-1 justify-between normal-case font-medium transition-all text-xs text-black px-2"
                  :class="item.selected && item.useSuggestedCity
                    ? 'btn-success bg-emerald-600 hover:bg-emerald-700 text-white font-bold shadow-xs border-emerald-600'
                    : 'btn-outline border-emerald-400 text-black hover:bg-emerald-50 bg-base-100'"
                  @click="toggleSuggestion(item)"
                  :title="item.useSuggestedCity ? 'Cliquer pour revenir au texte libre' : `Accepter la suggestion ${item.suggestedCity}`"
                >
                  <span class="truncate">
                    Ville suggérée : <strong>{{ item.suggestedCity }}</strong>
                  </span>
                  <span class="font-semibold shrink-0 text-[11px] flex items-center gap-1">
                    <span v-if="item.useSuggestedCity" class="font-bold">✓ Adoptée</span>
                    <span v-else class="underline">Accepter la suggestion</span>
                  </span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <div class="px-6 py-3 border-t border-base-200 flex items-center justify-between bg-base-100 shrink-0">
        <div class="text-xs text-black font-medium">Carte sélectionnée : {{ mapTitle }}</div>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="btn btn-ghost btn-sm text-black hover:bg-base-200"
            :disabled="isSubmitting"
            @click="emit('cancel')"
          >
            Passer
          </button>
          <button
            type="button"
            class="btn btn-primary btn-sm text-white font-semibold shadow-xs"
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
import { TrashIcon, PhotoIcon, ArrowUpTrayIcon } from "@heroicons/vue/24/outline";
import type { TextValidationEntry } from "../../utils/textValidation";

export type { TextValidationEntry };

const props = withDefaults(
  defineProps<{
    isOpen: boolean;
    mapId?: string | null;
    imageUrl?: string | null;
    mapTitle?: string;
    initialItems?: TextValidationEntry[];
    isSubmitting?: boolean;
  }>(),
  {
    mapId: null,
    imageUrl: null,
    mapTitle: "Carte sélectionnée",
    initialItems: () => [],
    isSubmitting: false,
  },
);

const emit = defineEmits<{
  (e: "confirm", items: TextValidationEntry[]): void;
  (e: "cancel"): void;
}>();

const mapContainer = ref<HTMLElement | null>(null);
const highlightedId = ref<string | null>(null);
const hoveredId = ref<string | null>(null);
const allItems = ref<TextValidationEntry[]>([]);

const leftColWidth = ref(420);
const rightColWidth = ref(380);
const isDraggingLeft = ref(false);
const isDraggingRight = ref(false);

const imgZoom = ref(1);
const localImageUrl = ref<string | null>(null);

let leafletMap: L.Map | null = null;
let landLayer: L.GeoJSON | null = null;
let cachedLeaflet: typeof import("leaflet") | null = null;
let cachedBasemapGeoJSON: GeoJSON.FeatureCollection | null = null;
const markerMap = new Map<string, L.Marker>();

let radiusCircle: L.Circle | null = null;
let suggestionPreviewMarker: L.Marker | null = null;
let connectionLine: L.Polyline | null = null;

const displayImageUrl = computed(() => localImageUrl.value || props.imageUrl || null);

const toKeepCount = computed(() => allItems.value.filter((i) => i.selected).length);

const isAllSelected = computed(
  () => allItems.value.length > 0 && allItems.value.every((i) => i.selected),
);

const isPartiallySelected = computed(() => {
  const selectedCount = toKeepCount.value;
  return selectedCount > 0 && selectedCount < allItems.value.length;
});

function startColResize(isLeft: boolean, e: MouseEvent) {
  const isDragging = isLeft ? isDraggingLeft : isDraggingRight;
  const colWidth = isLeft ? leftColWidth : rightColWidth;
  const minWidth = isLeft ? 220 : 260;

  isDragging.value = true;
  const startX = e.clientX;
  const startW = colWidth.value;

  const onMouseMove = (ev: MouseEvent) => {
    if (!isDragging.value) return;
    const delta = isLeft ? ev.clientX - startX : startX - ev.clientX;
    colWidth.value = Math.max(minWidth, Math.min(800, startW + delta));
    leafletMap?.invalidateSize();
  };

  const onMouseUp = () => {
    isDragging.value = false;
    window.removeEventListener("mousemove", onMouseMove);
    window.removeEventListener("mouseup", onMouseUp);
    leafletMap?.invalidateSize();
  };

  window.addEventListener("mousemove", onMouseMove);
  window.addEventListener("mouseup", onMouseUp);
}

function zoomImg(delta: number) {
  imgZoom.value = Math.max(0.2, Math.min(4, Number((imgZoom.value + delta).toFixed(2))));
}

function resetImgZoom() {
  imgZoom.value = 1;
}

function onLocalImageSelected(event: Event) {
  const target = event.target as HTMLInputElement;
  const file = target.files?.[0];
  if (!file) return;

  if (localImageUrl.value && localImageUrl.value.startsWith("blob:")) {
    URL.revokeObjectURL(localImageUrl.value);
  }

  localImageUrl.value = URL.createObjectURL(file);
  imgZoom.value = 1;
}

function itemBorderClass(item: TextValidationEntry): string {
  if (item.useSuggestedCity) {
    return "border-emerald-500 bg-emerald-50/30 ring-1 ring-emerald-400";
  }
  if (item.suggestedCity) {
    return "border-amber-300 bg-amber-50/20";
  }
  return "border-base-200";
}

function getItemCoords(item: TextValidationEntry): [number, number] | undefined {
  return item.useSuggestedCity && item.suggestedCoords
    ? item.suggestedCoords
    : item.coordinates;
}

function focusItem(item: TextValidationEntry, minZoom = 5) {
  highlightedId.value = item.id;
  const marker = markerMap.get(item.id);
  if (marker && leafletMap) {
    leafletMap.setView(marker.getLatLng(), Math.max(leafletMap.getZoom(), minZoom), {
      animate: true,
    });
    marker.openTooltip();
  }
  showToleranceRadius(item);
}

function onItemHover(item: TextValidationEntry) {
  hoveredId.value = item.id;
  showToleranceRadius(item);
}

function onItemLeave() {
  hoveredId.value = null;
  if (highlightedId.value) {
    const activeItem = allItems.value.find((i) => i.id === highlightedId.value);
    if (activeItem) {
      showToleranceRadius(activeItem);
      return;
    }
  }
  hideToleranceRadius();
}

function onToggleSelectAll(e: Event) {
  const target = e.target as HTMLInputElement;
  setAll(target.checked);
}

function setAll(selected: boolean) {
  for (const item of allItems.value) {
    item.selected = selected;
    updateMarkerStyle(item);
  }
}

function toggleItemSelection(item: TextValidationEntry) {
  item.selected = !item.selected;
  updateMarkerStyle(item);
}

function onTextInput(item: TextValidationEntry) {
  item.useSuggestedCity = false;
  item.selected = true;
  updateMarkerStyle(item);
  showToleranceRadius(item);
}

function toggleSuggestion(item: TextValidationEntry) {
  if (item.useSuggestedCity) {
    item.useSuggestedCity = false;
    item.text = item.originalText;
  } else {
    item.useSuggestedCity = true;
    item.selected = true;
    if (item.suggestedCity) {
      item.text = item.suggestedCity;
    }
  }
  updateMarkerStyle(item);
  focusItem(item, 4);
  adjustTooltipsAntiCollision();
}

function toggleSupprimer(item: TextValidationEntry) {
  item.selected = !item.selected;
  updateMarkerStyle(item);
}

function setItemCoordinates(item: TextValidationEntry, lon: number, lat: number) {
  item.coordinates = [lon, lat];
  item.useSuggestedCity = false;
  item.suggestedCity = undefined;
  item.suggestedCoords = undefined;
  item.selected = true;

  hideToleranceRadius();
  updateMarkerStyle(item);
  adjustTooltipsAntiCollision();
}

function getMarkerHtml(item: TextValidationEntry): string {
  const isSuggested = Boolean(item.useSuggestedCity);
  const fillColor = isSuggested ? "#059669" : "#2563eb";
  const strokeColor = isSuggested ? "#047857" : "#1d4ed8";
  const opacity = item.selected ? "1" : "0.45";

  const hasSuggestion = Boolean(item.suggestedCity) && !item.useSuggestedCity;
  const badgeHtml = hasSuggestion
    ? `<div style="position: absolute; top: -7px; right: -7px; width: 14px; height: 14px; border-radius: 50%; background-color: #f59e0b; color: #ffffff; font-size: 10px; font-weight: 800; display: flex; align-items: center; justify-content: center; border: 1.5px solid #ffffff; box-shadow: 0 1px 3px rgba(0,0,0,0.35); pointer-events: none;">!</div>`
    : "";

  return `<div class="relative validation-point-dot" style="width: 18px; height: 18px; border-radius: 50%; background-color: ${fillColor}; border: 2px solid ${strokeColor}; opacity: ${opacity}; box-shadow: 0 2px 5px rgba(0,0,0,0.35); cursor: grab; transition: transform 0.1s ease;">${badgeHtml}</div>`;
}

function createMarkerIcon(L: typeof import("leaflet"), item: TextValidationEntry) {
  return L.divIcon({
    className: "custom-validation-marker",
    html: getMarkerHtml(item),
    iconSize: [18, 18],
    iconAnchor: [9, 9],
  });
}

function showToleranceRadius(item: TextValidationEntry) {
  if (!leafletMap || !cachedLeaflet || !item.suggestedCity || !item.suggestedCoords) return;
  hideToleranceRadius();

  const coords = getItemCoords(item);
  if (!coords || (coords[0] === 0 && coords[1] === 0)) return;
  const [lon, lat] = coords;
  const [sLon, sLat] = item.suggestedCoords;

  radiusCircle = cachedLeaflet.circle([lat, lon], {
    radius: 75000,
    color: "#2563eb",
    weight: 1.5,
    dashArray: "5, 5",
    fillColor: "#3b82f6",
    fillOpacity: 0.12,
  }).addTo(leafletMap);

  const previewIcon = cachedLeaflet.divIcon({
    className: "custom-suggestion-preview-marker",
    html: `<div style="width: 16px; height: 16px; border-radius: 50%; background-color: #059669; border: 2px solid #ffffff; box-shadow: 0 2px 6px rgba(0,0,0,0.4);"></div>`,
    iconSize: [16, 16],
    iconAnchor: [8, 8],
  });

  suggestionPreviewMarker = cachedLeaflet.marker([sLat, sLon], { icon: previewIcon }).addTo(leafletMap);
  suggestionPreviewMarker.bindTooltip(`<strong>${item.suggestedCity}</strong> (Suggestion)`, {
    permanent: true,
    direction: "top",
    offset: [0, -10],
    className: "leaflet-tooltip-suggestion",
  });

  connectionLine = cachedLeaflet.polyline([[lat, lon], [sLat, sLon]], {
    color: "#059669",
    weight: 1.5,
    dashArray: "3, 3",
    opacity: 0.75,
  }).addTo(leafletMap);
}

function hideToleranceRadius() {
  if (!leafletMap) return;
  if (radiusCircle) {
    leafletMap.removeLayer(radiusCircle);
    radiusCircle = null;
  }
  if (suggestionPreviewMarker) {
    leafletMap.removeLayer(suggestionPreviewMarker);
    suggestionPreviewMarker = null;
  }
  if (connectionLine) {
    leafletMap.removeLayer(connectionLine);
    connectionLine = null;
  }
}

function makeDraggableMarker(
  L: typeof import("leaflet"),
  item: TextValidationEntry,
): L.Marker {
  const [lon, lat] = getItemCoords(item) ?? [0, 0];

  const marker = L.marker([lat, lon], {
    draggable: true,
    icon: createMarkerIcon(L, item),
  });

  marker.bindTooltip(item.text, {
    permanent: true,
    direction: "top",
    offset: [0, -12],
    className: "leaflet-tooltip-validation",
  });

  marker.on("click", () => focusItem(item));
  marker.on("mouseover", () => showToleranceRadius(item));
  marker.on("mouseout", () => {
    if (highlightedId.value !== item.id) {
      const active = allItems.value.find((i) => i.id === highlightedId.value);
      if (active) showToleranceRadius(active);
      else hideToleranceRadius();
    }
  });

  marker.on("dragstart", () => {
    highlightedId.value = item.id;
    hideToleranceRadius();
  });

  marker.on("dragend", (event: any) => {
    const latlng = event.target.getLatLng();
    setItemCoordinates(
      item,
      Number(latlng.lng.toFixed(5)),
      Number(latlng.lat.toFixed(5)),
    );
  });

  return marker;
}

function updateMarkerStyle(item: TextValidationEntry) {
  const marker = markerMap.get(item.id);
  if (!marker || !cachedLeaflet) return;

  const coords = getItemCoords(item);
  if (coords && (coords[0] !== 0 || coords[1] !== 0)) {
    marker.setLatLng([coords[1], coords[0]]);
  }

  marker.setIcon(createMarkerIcon(cachedLeaflet, item));
  marker.setTooltipContent(item.text);
}

function renderMapMarkers() {
  if (!leafletMap || !cachedLeaflet) return;

  for (const marker of markerMap.values()) {
    leafletMap.removeLayer(marker);
  }
  markerMap.clear();

  const bounds: [number, number][] = [];

  for (const item of allItems.value) {
    const coords = getItemCoords(item);
    if (!coords) continue;
    const [lon, lat] = coords;
    if (lon === 0 && lat === 0) continue;

    const marker = makeDraggableMarker(cachedLeaflet, item);
    marker.addTo(leafletMap);
    markerMap.set(item.id, marker);
    bounds.push([lat, lon]);
  }

  if (bounds.length > 0) {
    leafletMap.fitBounds(bounds as L.LatLngBoundsExpression, {
      padding: [40, 40],
      maxZoom: 8,
    });
  }
  nextTick(() => adjustTooltipsAntiCollision());
}

function adjustTooltipsAntiCollision() {
  const currentMap = leafletMap;
  if (!currentMap || !cachedLeaflet) return;

  const entries = allItems.value
    .map((item) => {
      const marker = markerMap.get(item.id);
      const latlng = marker?.getLatLng();
      if (!marker || !latlng || (latlng.lat === 0 && latlng.lng === 0)) return null;
      try {
        return { id: item.id, marker, pt: currentMap.latLngToContainerPoint(latlng) };
      } catch {
        return null;
      }
    })
    .filter(Boolean) as { id: string; marker: L.Marker; pt: L.Point }[];

  const directions: ("top" | "bottom" | "right" | "left")[] = ["top", "bottom", "right", "left"];
  const assigned = new Set<string>();

  for (let i = 0; i < entries.length; i++) {
    const curr = entries[i];
    if (assigned.has(curr.id)) continue;

    const cluster = [curr];
    assigned.add(curr.id);

    for (let j = i + 1; j < entries.length; j++) {
      const other = entries[j];
      if (!assigned.has(other.id) && Math.hypot(curr.pt.x - other.pt.x, curr.pt.y - other.pt.y) < 70) {
        cluster.push(other);
        assigned.add(other.id);
      }
    }

    cluster.forEach((entry, idx) => {
      const dir = directions[idx % directions.length];
      const offset: [number, number] =
        dir === "top" ? [0, -12] : dir === "bottom" ? [0, 12] : dir === "right" ? [14, 0] : [-14, 0];
      const tooltip = entry.marker.getTooltip();
      if (tooltip && cachedLeaflet) {
        tooltip.options.direction = dir;
        tooltip.options.offset = cachedLeaflet.point(offset[0], offset[1]);
        if (entry.marker.isTooltipOpen?.()) {
          entry.marker.closeTooltip();
          entry.marker.openTooltip();
        }
      }
    });
  }
}

async function initMap() {
  if (!mapContainer.value || leafletMap) return;

  const L = await import("leaflet");
  await import("leaflet/dist/leaflet.css");
  cachedLeaflet = L;

  const map = L.map(mapContainer.value, {
    center: [20, 0],
    zoom: 2,
    zoomControl: true,
    attributionControl: false,
    maxBoundsViscosity: 1.0,
  });

  map.on("zoomend", () => adjustTooltipsAntiCollision());
  map.on("moveend", () => adjustTooltipsAntiCollision());

  map.on("click", (e: any) => {
    if (!highlightedId.value) return;
    const item = allItems.value.find((i) => i.id === highlightedId.value);
    if (!item) return;

    const lon = Number(e.latlng.lng.toFixed(5));
    const lat = Number(e.latlng.lat.toFixed(5));

    let marker = markerMap.get(item.id);
    if (!marker && cachedLeaflet && leafletMap) {
      marker = makeDraggableMarker(cachedLeaflet, item);
      marker.addTo(leafletMap);
      markerMap.set(item.id, marker);
    }
    setItemCoordinates(item, lon, lat);
  });

  // Offline basemap using local GeoJSON (cached in memory)
  try {
    if (!cachedBasemapGeoJSON && typeof fetch === "function") {
      const baseUrl =
        typeof window !== "undefined" && window.location?.origin
          ? window.location.origin
          : "http://localhost";
      const geojsonFiles = [
        "/geojson/ne_coastline.geojson",
        "/geojson/ne_50m_lakes.geojson",
      ];
      const responses = await Promise.all(
        geojsonFiles.map((f) => fetch(new URL(f, baseUrl).toString()).catch(() => null)),
      );
      const geojsonData = await Promise.all(
        responses.filter((r): r is Response => Boolean(r && r.ok)).map((r) => r.json().catch(() => null)),
      );

      const validData = geojsonData.filter(Boolean);
      if (validData.length > 0) {
        cachedBasemapGeoJSON = {
          type: "FeatureCollection",
          features: validData.flatMap((data: any) => data.features || []),
        };
      }
    }

    if (cachedBasemapGeoJSON) {
      landLayer = L.geoJSON(cachedBasemapGeoJSON, {
        style: {
          fillColor: "#e5e7eb",
          fillOpacity: 0.9,
          color: "#9ca3af",
          weight: 1,
          opacity: 1,
        },
      }).addTo(map);
    }
  } catch {
    // Basemap is optional visual context
  }

  leafletMap = map;
  renderMapMarkers();
}

function destroyMap() {
  hideToleranceRadius();
  if (landLayer && leafletMap) {
    leafletMap.removeLayer(landLayer);
    landLayer = null;
  }
  if (leafletMap) {
    leafletMap.remove();
    leafletMap = null;
  }
  markerMap.clear();
  cachedLeaflet = null;
}

function mapInitialItems(items?: TextValidationEntry[]): TextValidationEntry[] {
  return (items || []).map((item) => ({
    ...item,
    selected: item.selected ?? true,
    useSuggestedCity: item.useSuggestedCity ?? false,
  }));
}

watch(
  () => props.isOpen,
  (open) => {
    if (!open) {
      destroyMap();
      if (localImageUrl.value && localImageUrl.value.startsWith("blob:")) {
        URL.revokeObjectURL(localImageUrl.value);
        localImageUrl.value = null;
      }
      return;
    }
    imgZoom.value = 1;
    allItems.value = mapInitialItems(props.initialItems);
    nextTick(() => initMap());
  },
  { immediate: true },
);

watch(
  () => props.initialItems,
  (newItems) => {
    if (props.isOpen && (!allItems.value || allItems.value.length === 0)) {
      allItems.value = mapInitialItems(newItems);
      renderMapMarkers();
    }
  },
);

onBeforeUnmount(() => {
  destroyMap();
  if (localImageUrl.value && localImageUrl.value.startsWith("blob:")) {
    URL.revokeObjectURL(localImageUrl.value);
    localImageUrl.value = null;
  }
});

function onConfirm() {
  emit("confirm", allItems.value);
}

defineExpose({
  allItems,
  setItemCoordinates,
});
</script>

<style>
.custom-validation-marker {
  background: transparent !important;
  border: none !important;
}
.custom-suggestion-preview-marker {
  background: transparent !important;
  border: none !important;
}
.leaflet-tooltip-validation {
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  color: #000000 !important;
  padding: 2px 6px;
  white-space: nowrap;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15);
  pointer-events: none;
}
.leaflet-tooltip-validation::before {
  border-top-color: #d1d5db;
}
.leaflet-tooltip-suggestion {
  background: #ecfdf5;
  border: 1px solid #10b981;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  color: #065f46 !important;
  padding: 2px 6px;
  white-space: nowrap;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15);
  pointer-events: none;
}
.leaflet-tooltip-suggestion::before {
  border-top-color: #10b981;
}
</style>
