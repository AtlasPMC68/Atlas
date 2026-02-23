<template>
  <div
    v-if="isOpen"
    class="fixed inset-0 z-50 flex items-start justify-center bg-black/60 overflow-y-auto"
  >
    <div class="bg-base-100 rounded-lg shadow-xl max-w-6xl w-full mx-4 my-6 p-6 flex flex-col gap-4">
      <div class="flex justify-between items-center mb-2">
        <h2 class="text-xl font-semibold">Sélectionner la zone sur le monde</h2>
        <button class="btn btn-ghost btn-sm" @click="emit('close')">✕</button>
      </div>

      <p class="text-sm text-base-content/70">
        Tracez un rectangle sur la carte du monde (à gauche) pour indiquer la zone couverte par votre carte.
        Utilisez la prévisualisation (à droite) pour vous aider.
      </p>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 flex-1 min-h-[360px]">
        <!-- World map -->
        <div class="border rounded-md overflow-hidden relative">
          <h3 class="px-3 py-2 text-sm font-medium bg-base-200 border-b">
            Monde (sélection de zone)
          </h3>

          <div class="absolute top-12 right-2 z-[1000] flex gap-2">
            <button
              type="button"
              class="btn btn-xs md:btn-sm btn-outline"
              @click="toggleSelectMode"
            >
              {{ isSelectMode ? 'Mode déplacement' : 'Mode sélection' }}
            </button>
            <button
              type="button"
              class="btn btn-xs md:btn-sm btn-ghost"
              @click="resetSelection"
              :disabled="!selectedBounds"
            >
              Réinitialiser
            </button>
          </div>

          <div ref="mapContainer" class="h-80 md:h-[28rem] w-full bg-[#cfe8ff]"></div>

          <div class="px-3 py-2 text-xs text-base-content/70 border-t bg-base-100">
            <div v-if="selectedBounds">
              Zone: W {{ selectedBounds.west.toFixed(4) }}, S {{ selectedBounds.south.toFixed(4) }},
              E {{ selectedBounds.east.toFixed(4) }}, N {{ selectedBounds.north.toFixed(4) }}
              <span class="ml-2">(zoom {{ selectedZoom }})</span>
            </div>
            <div v-else>
              Aucune zone sélectionnée.
            </div>
          </div>
        </div>

        <!-- User map preview -->
        <div class="border rounded-md overflow-hidden">
          <h3 class="px-3 py-2 text-sm font-medium bg-base-200 border-b">
            Votre carte (prévisualisation)
          </h3>

          <div class="h-80 md:h-[28rem] bg-base-200 flex items-center justify-center">
            <img
              v-if="imageUrl"
              :src="imageUrl"
              class="max-w-full max-h-full object-contain"
              alt="Carte importée"
            />
            <div v-else class="text-sm text-base-content/70">Aucune image</div>
          </div>
        </div>
      </div>

      <div class="flex justify-end gap-2 pt-2">
        <button class="btn btn-ghost" @click="emit('close')">Annuler</button>
        <button class="btn btn-primary" @click="onConfirm" :disabled="!selectedBounds">
          Confirmer la zone
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, nextTick, watch, ref } from "vue";
import L from "leaflet";
import type { WorldBounds, WorldAreaSelection } from "../../typescript/georef";

const props = withDefaults(
  defineProps<{
    isOpen: boolean;
    imageUrl: string;
    // Optional: allow parent to restore previous selection
    initialBounds: WorldBounds | null;
    initialZoom: number;
  }>(),
  {
    isOpen: false,
    initialBounds: null,
    initialZoom: 2,
  },
);

const emit = defineEmits<{
  (e: "close"): void;
  (e: "confirmed", payload: WorldAreaSelection): void;
}>();

const mapContainer = ref<HTMLDivElement | null>(null);
let map: L.Map | null = null;
let landLayer: L.GeoJSON | null = null;
let selectionRect: L.Rectangle | null = null;

// Match the GeoRef UX: start in move mode, user toggles into selection.
const isSelectMode = ref<boolean>(false);

const selectedBounds = ref<WorldBounds | null>(null); // { west, south, east, north }
const selectedZoom = ref<number | null>(null);

let isDraggingSelection = false;
let dragStartLatLng: L.LatLng | null = null;

async function initMap(): Promise<void> {
  if (!mapContainer.value || map) return;

  map = L.map(mapContainer.value, {
    maxBoundsViscosity: 1.0,
  }).setView([20, 0], props.initialZoom);

  // Load a lightweight basemap layer for context.
  // Served from Frontend-Atlas/public/geojson/
  try {
    const res = await fetch("/geojson/ne_coastline.geojson");
    if (!res.ok) throw new Error(`Failed to load coastline geojson: ${res.status}`);
    const geojson = await res.json();

    landLayer = L.geoJSON(geojson, {
      // Coastlines are typically LineString/MultiLineString; land is Polygon/MultiPolygon.
      // Style both in a way that's visible on the blue ocean background.
      style: (feature) => {
        const type = feature?.geometry?.type;
        const isLine = type === "LineString" || type === "MultiLineString";
        const isPolygon = type === "Polygon" || type === "MultiPolygon";

        if (isLine) {
          return {
            color: "#111827",
            weight: 2,
            opacity: 0.9,
          };
        }

        if (isPolygon) {
          return {
            fillColor: "#e5e7eb",
            fillOpacity: 0.9,
            color: "#6b7280",
            weight: 1,
            opacity: 1,
          };
        }

        return {
          color: "#111827",
          weight: 2,
          opacity: 0.9,
        };
      },
    }).addTo(map);

    const bounds = landLayer.getBounds();
    if (bounds.isValid()) {
      // Add some margin so the initial view isn't overly zoomed-in.
      const padded = bounds.pad(0.2);
      map.setMaxBounds(padded);

      // If no initial bounds are provided, fit to world
      if (!props.initialBounds) {
        // Cap maxZoom so we don't zoom in too much on load.
        map.fitBounds(padded, { padding: [10, 10], maxZoom: 2 });

        // Allow a little more zoom-out than the fitted view.
        // (Lower zoom number = more zoomed out in Leaflet.)
        map.setMinZoom(Math.max(map.getZoom() - 1, 0));
      }
    }
  } catch (e) {
    console.error("Failed to load Natural Earth land layer", e);
  }

  // Restore previous selection if provided
  if (props.initialBounds) {
    const b = L.latLngBounds(
      [props.initialBounds.south, props.initialBounds.west],
      [props.initialBounds.north, props.initialBounds.east],
    );
    setSelectionFromBounds(b);
    map.fitBounds(b.pad(0.15), { padding: [10, 10] });
  }

  map.on("mousedown", onMapMouseDown);
  map.on("mousemove", onMapMouseMove);
  map.on("mouseup", onMapMouseUp);
  map.on("mouseout", onMapMouseUp);

  applyInteractionMode();
}

async function ensureMapLifecycle(open: boolean): Promise<void> {
  if (open) {
    // Wait until the modal is rendered so Leaflet can measure the container.
    await nextTick();
    await initMap();
    if (map) {
      // Leaflet often needs this when mounted in a modal.
      const currentMap = map;
      setTimeout(() => currentMap.invalidateSize(), 0);
    }
  } else {
    resetSelection();
    destroyMap();
  }
}

function destroyMap(): void {
  if (!map) return;

  map.off("mousedown", onMapMouseDown);
  map.off("mousemove", onMapMouseMove);
  map.off("mouseup", onMapMouseUp);
  map.off("mouseout", onMapMouseUp);

  if (selectionRect) {
    map.removeLayer(selectionRect);
    selectionRect = null;
  }

  if (landLayer) {
    map.removeLayer(landLayer);
    landLayer = null;
  }

  map.remove();
  map = null;
}

function applyInteractionMode(): void {
  if (!map) return;
  if (isSelectMode.value) {
    // Selection mode: allow zooming, but disable dragging so mouse-drag draws the rectangle.
    map.dragging.disable();
    map.scrollWheelZoom.enable();
    map.doubleClickZoom.enable();
    map.touchZoom.enable();
    map.keyboard.enable();

    // Keep Leaflet's boxZoom off so it doesn't conflict with our drag selection.
    map.boxZoom.disable();
  } else {
    map.dragging.enable();
    map.scrollWheelZoom.enable();
    map.doubleClickZoom.enable();
    map.touchZoom.enable();
    map.boxZoom.enable();
    map.keyboard.enable();
  }
}

function toggleSelectMode(): void {
  isSelectMode.value = !isSelectMode.value;
  isDraggingSelection = false;
  dragStartLatLng = null;
  applyInteractionMode();
}

function resetSelection(): void {
  selectedBounds.value = null;
  selectedZoom.value = null;

  if (map && selectionRect) {
    map.removeLayer(selectionRect);
    selectionRect = null;
  }
}

function onMapMouseDown(e: L.LeafletMouseEvent): void {
  if (!map || !isSelectMode.value) return;

  isDraggingSelection = true;
  dragStartLatLng = e.latlng;

  const bounds = L.latLngBounds(dragStartLatLng, dragStartLatLng);

  if (!selectionRect) {
    selectionRect = L.rectangle(bounds, {
      color: "#2563eb",
      weight: 2,
      fillColor: "#2563eb",
      fillOpacity: 0.1,
    }).addTo(map);
  } else {
    selectionRect.setBounds(bounds);
  }

  setSelectionFromBounds(bounds);
}

function onMapMouseMove(e: L.LeafletMouseEvent): void {
  if (!map || !isSelectMode.value || !isDraggingSelection || !dragStartLatLng) return;

  const bounds = L.latLngBounds(dragStartLatLng, e.latlng);
  if (selectionRect) selectionRect.setBounds(bounds);
  setSelectionFromBounds(bounds);
}

function onMapMouseUp(): void {
  isDraggingSelection = false;
  dragStartLatLng = null;

  if (map) {
    selectedZoom.value = map.getZoom();
  }
}

function setSelectionFromBounds(bounds: L.LatLngBounds): void {
  const sw = bounds.getSouthWest();
  const ne = bounds.getNorthEast();

  selectedBounds.value = {
    west: sw.lng,
    south: sw.lat,
    east: ne.lng,
    north: ne.lat,
  };

  if (map) {
    selectedZoom.value = map.getZoom();
  }
}

function onConfirm(): void {
  if (!selectedBounds.value) return;
  const zoom = selectedZoom.value ?? (map ? map.getZoom() : props.initialZoom);
  emit("confirmed", {
    bounds: selectedBounds.value,
    zoom,
  });
}

watch(
  () => props.isOpen,
  async (open: boolean) => {
    await ensureMapLifecycle(open);
  },
  { immediate: true },
);

onMounted(async () => {
  // In case the component is created with isOpen=true via v-if,
  // ensure the map is initialized.
  await ensureMapLifecycle(props.isOpen);
});

onBeforeUnmount(() => {
  destroyMap();
});
</script>
