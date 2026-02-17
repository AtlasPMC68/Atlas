<template>
  <div
    class="flex flex-col gap-4 h-full w-full overflow-auto md:flex-row md:items-stretch [&_.leaflet-draw-toolbar]:hidden"
  >
    <div
      class="w-full sticky top-4 self-start z-10 bg-white rounded-lg shadow-lg p-2 md:w-80 md:flex-none md:basis-80"
    >
      <div class="flex gap-2">
        <button
          v-for="mode in editModes"
          :key="mode.id"
          @click="setEditMode(mode.id)"
          :class="[
            'px-3 py-2 rounded text-sm font-medium transition-colors',
            activeMode === mode.id
              ? 'bg-blue-600 text-white'
              : 'bg-gray-100 text-gray-700 hover:bg-gray-200',
          ]"
        >
          <i :class="mode.icon" class="mr-1"></i>
          {{ mode.label }}
        </button>
      </div>

      <div class="flex gap-2 mt-2 pt-2 border-t border-gray-200">
        <button
          @click="saveChanges"
          class="px-3 py-2 bg-green-600 text-white rounded text-sm font-medium hover:bg-green-700 transition-colors"
          :disabled="!hasUnsavedChanges"
        >
          <i class="fas fa-save mr-1"></i>
          Sauvegarder
        </button>
        <button
          @click="cancelEdit"
          class="px-3 py-2 bg-red-600 text-white rounded text-sm font-medium hover:bg-red-700 transition-colors"
          :disabled="!activeMode"
        >
          <i class="fas fa-times mr-1"></i>
          Annuler
        </button>
      </div>
    </div>

    <div id="edit-map" class="flex-1 w-full min-h-[300px] md:min-h-0"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from "vue";
import type { PropType } from "vue";
import type { GeoJsonObject } from "geojson";
import L from "leaflet";
import "leaflet-draw";
import "leaflet-draw/dist/leaflet.draw.css";

type MapGeometry = {
  type?: string;
  coordinates?: number[] | number[][] | number[][][];
};

type MapFeature = {
  id?: string | number;
  map_id?: string;
  type: string;
  geometry?: MapGeometry;
  color?: string;
  opacity?: number;
  stroke_width?: number;
  z_index?: number;
};

type PendingFeature = MapFeature | { id?: string | number; action: "delete" };

const LDraw = L as unknown as {
  Control: { Draw: new (options: unknown) => L.Control };
  Draw: {
    Event: { CREATED: string; DELETED: string };
    Marker: new (map: L.Map, options: unknown) => { enable: () => void };
    Polyline: new (map: L.Map, options: unknown) => { enable: () => void };
    Polygon: new (map: L.Map, options: unknown) => { enable: () => void };
    Remove: new (map: L.Map) => { enable: () => void };
    Feature: new (...args: unknown[]) => { disable: () => void };
  };
};

const props = defineProps({
  mapId: String,
  features: { type: Array as PropType<MapFeature[]>, default: () => [] },
  featureVisibility: {
    type: Map as PropType<Map<string | number, boolean>>,
    required: true,
  },
});

const emit = defineEmits([
  "feature-created",
  "feature-updated",
  "feature-deleted",
  "features-updated",
]);

const editModes = [
  { id: "CREATE_POINT", label: "Point", icon: "fas fa-map-marker-alt" },
  { id: "CREATE_LINE", label: "Ligne", icon: "fas fa-minus" },
  { id: "CREATE_POLYGON", label: "Polygone", icon: "fas fa-draw-polygon" },
  { id: "MOVE_FEATURE", label: "Déplacer", icon: "fas fa-arrows-alt" },
  { id: "DELETE_FEATURE", label: "Supprimer", icon: "fas fa-trash" },
];

const activeMode = ref<string | null>(null);
const map = ref<L.Map | null>(null);
const drawControl = ref<L.Control | null>(null);
const drawnItems = ref<L.FeatureGroup | null>(null);
const hasUnsavedChanges = ref(false);
const unsavedFeatures = ref<PendingFeature[]>([]);

const isDeleteAction = (
  feature: PendingFeature,
): feature is { id?: string | number; action: "delete" } =>
  "action" in feature && feature.action === "delete";

onMounted(() => {
  initializeMap();
  initializeDrawControl();
  loadExistingFeatures();
});

onUnmounted(() => {
  if (map.value) {
    map.value.remove();
  }
});

function initializeMap() {
  map.value = L.map("edit-map").setView([52.9399, -73.5491], 5);
  const mapInstance = map.value as L.Map;

  // Base map tiles
  L.tileLayer(
    "https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png",
    {
      attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
      subdomains: "abcd",
      maxZoom: 19,
    },
  ).addTo(mapInstance);

  // Layer for drawn features
  drawnItems.value = new L.FeatureGroup();
  mapInstance.addLayer(drawnItems.value as unknown as L.Layer);
}

function initializeDrawControl() {
  if (!map.value || !drawnItems.value) return;

  const drawOptions = {
    position: "topright",
    draw: {
      polyline: false,
      polygon: false,
      circle: false,
      rectangle: false,
      marker: false,
      circlemarker: false,
    },
    edit: {
      featureGroup: drawnItems.value,
      remove: false,
      edit: false,
    },
  };

  drawControl.value = new LDraw.Control.Draw(drawOptions);
  map.value.addControl(drawControl.value);
}

function loadExistingFeatures() {
  const drawnItemsInstance = drawnItems.value;
  if (!drawnItemsInstance) return;

  props.features.forEach((feature) => {
    if (feature.geometry) {
      const layer = createLayerFromFeature(feature);
      if (layer) {
        drawnItemsInstance.addLayer(layer);
        const layerWithId = layer as L.Layer & { featureId?: string | number };
        layerWithId.featureId = feature.id; // Keep id for updates
      }
    }
  });
}

function createLayerFromFeature(feature: MapFeature) {
  const geom = feature.geometry;

  if (!geom || !geom.coordinates) return null;

  switch (feature.type) {
    case "point": {
      const coords = geom.coordinates as [number, number];
      return L.circleMarker([coords[1], coords[0]], {
        radius: 6,
        fillColor: feature.color || "#000",
        color: feature.color || "#000",
        weight: 1,
        opacity: feature.opacity ?? 1,
        fillOpacity: feature.opacity ?? 1,
      });
    }

    case "polyline":
    case "arrow":
      const latlngs = (geom.coordinates as [number, number][]).map(
        (coord) => [coord[1], coord[0]] as L.LatLngTuple,
      );
      return L.polyline(latlngs, {
        color: feature.color || "#000",
        weight: feature.stroke_width ?? 2,
        opacity: feature.opacity ?? 1,
      });

    case "polygon":
    case "zone":
      return L.geoJSON(geom as GeoJsonObject, {
        style: {
          fillColor: feature.color || "#ccc",
          fillOpacity: 0.5,
          color: "#333",
          weight: 1,
        },
      });

    default:
      return null;
  }
}

function setEditMode(modeId: string) {
  if (activeMode.value === modeId) {
    activeMode.value = null;
    disableDrawMode();
    return;
  }

  activeMode.value = modeId;
  enableDrawMode(modeId);
}

function enableDrawMode(modeId: string) {
  if (!map.value || !drawnItems.value) return;
  const mapInstance = map.value as L.Map;

  disableDrawMode();

  switch (modeId) {
    case "CREATE_POINT":
      new LDraw.Draw.Marker(mapInstance, {
        icon: new L.Icon.Default(),
      }).enable();
      break;

    case "CREATE_LINE":
      new LDraw.Draw.Polyline(mapInstance, {
        shapeOptions: {
          color: "#000",
          weight: 2,
        },
      }).enable();
      break;

    case "CREATE_POLYGON":
      new LDraw.Draw.Polygon(mapInstance, {
        shapeOptions: {
          color: "#000",
          fillColor: "#ccc",
          fillOpacity: 0.5,
        },
      }).enable();
      break;

    case "MOVE_FEATURE":
      drawnItems.value.eachLayer(
        (layer: L.Layer & { editing?: { enable: () => void } }) => {
          layer.editing?.enable();
        },
      );
      break;

    case "DELETE_FEATURE":
      new LDraw.Draw.Remove(mapInstance).enable();
      break;
  }
}

function disableDrawMode() {
  if (!map.value || !drawnItems.value) return;

  map.value.eachLayer((layer: L.Layer) => {
    const disableTarget = layer as L.Layer & { disable?: () => void };
    if (layer instanceof LDraw.Draw.Feature) {
      disableTarget.disable?.();
      return;
    }
    disableTarget.disable?.();
  });

  drawnItems.value.eachLayer(
    (layer: L.Layer & { editing?: { disable: () => void } }) => {
      layer.editing?.disable();
    },
  );
}

onMounted(() => {
  if (!map.value || !drawnItems.value) {
    return;
  }

  const mapInstance = map.value;
  const drawnItemsInstance = drawnItems.value;

  mapInstance.on(LDraw.Draw.Event.CREATED, (event: any) => {
    const layer = event.layer;
    drawnItemsInstance.addLayer(layer);

    const feature = createFeatureFromLayer(layer, event.layerType);
    if (feature) {
      unsavedFeatures.value.push(feature);
      hasUnsavedChanges.value = true;

      layer.isUnsaved = true;
      layer.featureData = feature;
    }
  });

  mapInstance.on(LDraw.Draw.Event.DELETED, (event: any) => {
    event.layers.eachLayer(
      (
        layer: L.Layer & {
          isUnsaved?: boolean;
          featureData?: MapFeature;
          featureId?: string | number;
        },
      ) => {
        if (layer.isUnsaved) {
          const index = unsavedFeatures.value.findIndex(
            (f) => f === layer.featureData,
          );
          if (index > -1) {
            unsavedFeatures.value.splice(index, 1);
          }
        } else {
          unsavedFeatures.value.push({
            id: layer.featureId,
            action: "delete",
          });
        }
      },
    );
    hasUnsavedChanges.value = true;
  });
});

function createFeatureFromLayer(
  layer: L.Layer,
  layerType: string,
): MapFeature | null {
  const mapId = props.mapId;

  switch (layerType) {
    case "marker":
      const latlng = (layer as L.CircleMarker).getLatLng();
      return {
        map_id: mapId,
        type: "point",
        geometry: {
          type: "Point",
          coordinates: [latlng.lng, latlng.lat],
        },
        color: "#000000",
        opacity: 1.0,
        z_index: 1,
      };

    case "polyline":
      const latlngs = (layer as L.Polyline).getLatLngs() as L.LatLng[];
      return {
        map_id: mapId,
        type: "polyline",
        geometry: {
          type: "LineString",
          coordinates: latlngs.map((ll) => [ll.lng, ll.lat]),
        },
        color: "#000000",
        stroke_width: 2,
        opacity: 1.0,
        z_index: 1,
      };

    case "polygon":
      const polygonLatlngs = (layer as L.Polygon).getLatLngs()[0] as L.LatLng[];
      return {
        map_id: mapId,
        type: "polygon",
        geometry: {
          type: "Polygon",
          coordinates: [polygonLatlngs.map((ll) => [ll.lng, ll.lat])],
        },
        color: "#cccccc",
        opacity: 0.5,
        z_index: 1,
      };

    default:
      return null;
  }
}

async function saveChanges() {
  try {
    for (const feature of unsavedFeatures.value) {
      if (isDeleteAction(feature)) {
        await deleteFeature(feature.id);
      } else if (feature.id) {
        await updateFeature(feature);
      } else {
        await createFeature(feature);
      }
    }

    unsavedFeatures.value = [];
    hasUnsavedChanges.value = false;

    emit("features-updated");
  } catch (error) {
    console.error("Failed to save changes:", error);
  }
}

function cancelEdit() {
  loadExistingFeatures();
  unsavedFeatures.value = [];
  hasUnsavedChanges.value = false;
  activeMode.value = null;
  disableDrawMode();
}

// API calls
async function createFeature(featureData: MapFeature) { //TODO: Ajouter vérification de l'utilisateur
  const response = await fetch(
    `${import.meta.env.VITE_API_URL}/maps/features`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(featureData),
    },
  );

  if (!response.ok) {
    throw new Error("Failed to create feature");
  }

  return response.json();
}

async function updateFeature(featureData: MapFeature) { //TODO: Ajouter vérification de l'utilisateur
  const response = await fetch(
    `${import.meta.env.VITE_API_URL}/maps/features/${featureData.id}`,
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(featureData),
    },
  );

  if (!response.ok) {
    throw new Error("Failed to update feature");
  }

  return response.json();
}

async function deleteFeature(featureId: string | number | undefined) { //!IMPORTANT! TODO: Ajouter vérification de l'utilisateur
  if (!featureId) return;
  const response = await fetch(
    `${import.meta.env.VITE_API_URL}/maps/features/${featureId}`,
    {
      method: "DELETE",
    },
  );

  if (!response.ok) {
    throw new Error("Failed to delete feature");
  }
}
</script>
