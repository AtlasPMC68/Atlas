<template>
  <div class="relative h-full w-full z-0">
    <div id="map" style="height: 80vh; width: 100%"></div>
    <TimelineSlider v-model:year="selectedYear" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, watch, ref, computed } from "vue";
import L from "leaflet";
import "leaflet-geometryutil";
import "leaflet-arrowheads";
import TimelineSlider from "../components/TimelineSlider.vue";
import { useMapDrawing } from "../composables/useMapDrawing";
import { getFeatureRgbColor, getMapElementType } from "../utils/featureHelpers";
import {
  extractFeatureFromLayer,
  syncFeaturesFromLayerMap,
} from "../utils/mapDrawingFeature";
import { toArray } from "../utils/utils";
import type { Coordinate, Feature, Geometry } from "../typescript/feature";
import type { LayerWithFeature as LayerWithFeatureType } from "../typescript/mapLayers";

type FeatureId = string;

type LayerWithFeature = LayerWithFeatureType<Feature>;

interface GeoJsonFeatureWithGeometry {
  geometry: Geometry;
  [key: string]: unknown;
}

interface GeoJsonFeatureCollectionWithGeometry {
  features: GeoJsonFeatureWithGeometry[];
  [key: string]: unknown;
}

const props = defineProps<{
  features: Feature[];
  featureVisibility: Map<string, boolean>;
}>();

const emit = defineEmits<{
  (e: "features-loaded", features: Feature[]): void;
  (e: "draw-create", features: Feature[]): void;
  (e: "draw-update", features: Feature[]): void;
  (e: "draw-delete", features: Feature[]): void;
}>();

const selectedYear = ref(1740);
const previousFeatureIds = ref(new Set<FeatureId>());
const localFeaturesSnapshot = ref<Feature[]>([]);

function getYearSafeUTC(dateText: string): number {
  return new Date(dateText).getUTCFullYear();
}

const filteredFeatures = computed(() => {
  return props.features.filter(
    (feature: Feature) =>
      getYearSafeUTC(feature.properties.startDate) <=
        selectedYear.value &&
      (!feature.properties.endDate ||
        getYearSafeUTC(feature.properties.endDate) >=
          selectedYear.value),
  );
});

let map: L.Map | null = null;

const featureLayerManager = {
  layers: new Map<FeatureId, L.Layer>(),

  addFeatureLayer(featureId: string | number, layer: L.Layer) {
    const id = String(featureId);
    if (!map) return;

    if (this.layers.has(id)) {
      map.removeLayer(this.layers.get(id)!);
    }
    this.layers.set(id, layer);

    const isVisible = props.featureVisibility.get(id) ?? true;
    if (isVisible) {
      map.addLayer(layer);
    }
  },

  toggleFeature(featureId: string | number, visible: boolean) {
    const id = String(featureId);
    const layer = this.layers.get(id);
    if (!layer || !map) return;

    if (visible) {
      map.addLayer(layer);
    } else {
      map.removeLayer(layer);
    }
  },

  clearAllFeatures() {
    if (!map) return;
    this.layers.forEach((layer) => map!.removeLayer(layer));
    this.layers.clear();
  },
};

function featureIdAsString(featureOrId: Feature | string | number): string {
  if (typeof featureOrId === "object" && featureOrId !== null) {
    return String(featureOrId.id);
  }
  return String(featureOrId);
}

function upsertFeature(features: Feature[], feature: Feature): Feature[] {
  const targetId = featureIdAsString(feature);
  const next = [...features];
  const index = next.findIndex((f) => featureIdAsString(f) === targetId);

  if (index >= 0) {
    next[index] = feature;
    return next;
  }

  next.push(feature);
  return next;
}

function syncFeaturesFromMapLayers(): Feature[] {
  const mergedById = new Map<string, Feature>();

  const renderedFeatures = syncFeaturesFromLayerMap(
    featureLayerManager.layers,
    localFeaturesSnapshot.value,
    selectedYear.value
  );

  renderedFeatures.forEach((feature) => {
    mergedById.set(String(feature.id), feature);
  });

  drawing.drawnItems.value?.eachLayer((layer) => {
    const extracted = extractFeatureFromLayer(layer, selectedYear.value);
    if (!extracted?.id) return;
    mergedById.set(String(extracted.id), extracted);
  });

  return Array.from(mergedById.values());
}

function clearDraftLayers() {
  drawing.clearDrawnItems();
}

defineExpose({
  syncFeaturesFromMapLayers,
  clearDraftLayers,
});

const drawing = useMapDrawing((event, ...args) => {
  const payload = args[0] as Feature | string | number;
  const current = localFeaturesSnapshot.value;

  if (event === "feature-created") {
    const next = upsertFeature(current, payload as Feature);
    localFeaturesSnapshot.value = next;
    return;
  }

  if (event === "feature-updated") {
    const next = upsertFeature(current, payload as Feature);
    localFeaturesSnapshot.value = next;
    return;
  }

  if (event === "feature-deleted") {
    const deletedId = featureIdAsString(payload);
    const next = current.filter(
      (feature) => featureIdAsString(feature) !== deletedId,
    );
    localFeaturesSnapshot.value = next;
  }
});

function attachFeatureToLayer(layer: L.Layer, feature: Feature) {
  const layerWithFeature = layer as LayerWithFeature;
  layerWithFeature.feature = feature;

  if (typeof layerWithFeature.eachLayer === "function") {
    layerWithFeature.eachLayer((childLayer) => {
      (childLayer as LayerWithFeature).feature = feature;
    });
  }
}

function renderCities(features: Feature[]) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach((feature) => {
    if (!map || feature.geometry.type !== "Point") return;

    const [lng, lat] = feature.geometry.coordinates;
    const coord: L.LatLngTuple = [lat, lng];

    const colorFromRgb = getFeatureRgbColor(feature);
    const color = colorFromRgb || "#000";

    const point = L.circleMarker(coord, {
      radius: 6,
      fillColor: color,
      color,
      weight: 1,
      opacity: feature.opacity ?? 1,
      fillOpacity: feature.opacity ?? 1,
    });

    const featureProperties = feature.properties;
    const label = L.marker(coord, {
      icon: L.divIcon({
        className: "city-label-text",
        html: featureProperties.name || feature.name || "",
        iconSize: [100, 20],
        iconAnchor: [-8, 15],
      }),
      interactive: false,
    });

    attachFeatureToLayer(point, feature);
    attachFeatureToLayer(label, feature);

    const layerGroup = L.layerGroup([point, label]);
    attachFeatureToLayer(layerGroup, feature);
    featureLayerManager.addFeatureLayer(feature.id, layerGroup);
  });
}

function transformCoord(
  coord: Coordinate,
  anchorLat: number,
  anchorLng: number,
  sizeMeters: number,
): Coordinate {
  const [x, y] = coord;
  const crs = L.CRS.EPSG3857;
  const center = crs.project(L.latLng(anchorLat, anchorLng));
  const halfSize = sizeMeters / 2;

  const nx = x - 0.5;
  const ny = y - 0.5;

  const mx = center.x + nx * 2 * halfSize;
  const my = center.y - ny * 2 * halfSize;

  const latLng = crs.unproject(L.point(mx, my));
  return [latLng.lng, latLng.lat];
}

function transformCoordinates(
  coordinates: Geometry["coordinates"],
  anchorLat: number,
  anchorLng: number,
  sizeMeters: number,
): Geometry["coordinates"] {
  if (!Array.isArray(coordinates)) return coordinates;

  if (
    coordinates.length > 0 &&
    typeof coordinates[0] === "number" &&
    typeof coordinates[1] === "number"
  ) {
    return transformCoord(
      coordinates as Coordinate,
      anchorLat,
      anchorLng,
      sizeMeters,
    );
  }

  return (coordinates as Array<Geometry["coordinates"]>).map((nested) =>
    transformCoordinates(nested, anchorLat, anchorLng, sizeMeters),
  ) as Geometry["coordinates"];
}

function normalizeGeometryToWorld(
  geometry: Geometry,
  sizeMeters: number,
): Geometry {
  const anchorLat = -80 + Math.random() * 160;
  const anchorLng = -170 + Math.random() * 340;

  return {
    ...geometry,
    coordinates: transformCoordinates(
      geometry.coordinates,
      anchorLat,
      anchorLng,
      sizeMeters,
    ),
  } as Geometry;
}

function transformNormalizedToWorld(
  geojson: GeoJsonFeatureCollectionWithGeometry,
  anchorLat: number,
  anchorLng: number,
  sizeMeters: number,
): GeoJsonFeatureCollectionWithGeometry {
  // Use the same projected CRS as the basemap (Web Mercator).
  const crs = L.CRS.EPSG3857;
  const center = crs.project(L.latLng(anchorLat, anchorLng));
  const halfSize = sizeMeters / 2;

  // Transform a single coordinate [x, y] in [0,1]x[0,1] into [lng, lat]
  const transformCoord = (coord: Coordinate): Coordinate => {
    const [x, y] = coord;

    // Center the shape around (0,0) in its local space
    const nx = x - 0.5;
    const ny = y - 0.5;

    // Work in projected meters with a uniform scale so aspect ratio is preserved
    const mx = center.x + nx * 2 * halfSize;
    const my = center.y - ny * 2 * halfSize;

    const latlng = crs.unproject(L.point(mx, my));
    return [latlng.lng, latlng.lat];
  };

  const transformCoords = (
    coords: Geometry["coordinates"],
  ): Geometry["coordinates"] => {
    if (!Array.isArray(coords)) return coords;

    if (typeof coords[0] === "number") {
      return transformCoord(coords as Coordinate);
    }

    return (coords as Array<Geometry["coordinates"]>).map(
      transformCoords,
    ) as Geometry["coordinates"];
  };

  return {
    ...geojson,
    features: geojson.features.map((feature) => ({
      ...feature,
      geometry: {
        ...feature.geometry,
        coordinates: transformCoords(feature.geometry.coordinates),
      } as Geometry,
    })),
  };
}

void normalizeGeometryToWorld;
void transformNormalizedToWorld;

function renderZones(features: Feature[]) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach((feature) => {
    if (!map) return;
    if (
      feature.geometry.type !== "Polygon" &&
      feature.geometry.type !== "MultiPolygon"
    ) {
      return;
    }

    const featureProperties = feature.properties;
    const colorFromRgb = getFeatureRgbColor(feature);
    const fillColor = colorFromRgb || "#ccc";

    const layer = L.geoJSON(feature.geometry, {
      style: {
        fillColor,
        fillOpacity: 0.5,
        color: "#333",
        weight: 1,
      },
    });
    attachFeatureToLayer(layer, feature);

    const name = featureProperties.name || feature.name;
    if (name) {
      layer.bindPopup(name);
    }

    featureLayerManager.addFeatureLayer(feature.id, layer);
  });
}

function renderArrows(features: Feature[]) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach((feature) => {
    if (!map || feature.geometry.type !== "LineString") return;

    const latLngs = feature.geometry.coordinates.map(
      ([lng, lat]) => [lat, lng] as L.LatLngTuple,
    );

    const colorFromRgb = getFeatureRgbColor(feature);
    const color = colorFromRgb || "#000";

    const line = L.polyline(latLngs, {
      color,
      weight: feature.strokeWidth ?? 2,
      opacity: feature.opacity ?? 1,
    });
    attachFeatureToLayer(line, feature);

    line.addTo(map);
    line.arrowheads({
      size: "10px",
      frequency: "endonly",
      fill: true,
    });

    const featureProperties = feature.properties;
    const name = featureProperties.name || feature.name;
    if (name) {
      line.bindPopup(name);
    }

    featureLayerManager.addFeatureLayer(feature.id, line);
  });
}

function renderShapes(features: Feature[]) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach((feature) => {
    if (!map) return;
    if (
      feature.geometry.type !== "Polygon" &&
      feature.geometry.type !== "MultiPolygon"
    ) {
      return;
    }

    const featureProperties = feature.properties;
    const colorFromRgb = getFeatureRgbColor(feature);
    const fillColor = colorFromRgb || "#ccc";

    const layer = L.geoJSON(feature.geometry, {
      style: {
        fillColor: fillColor,
        opacity: feature.opacity ?? 1,
        fillOpacity: feature.opacity ?? 0.5,
        color: fillColor,
        weight: 3,
      },
    });
    attachFeatureToLayer(layer, feature);

    const name = featureProperties.name || feature.name || "Detected shape";
    if (name) {
      layer.bindPopup(name);
    }

    featureLayerManager.addFeatureLayer(feature.id, layer);
  });
}

function renderAllFeatures() {
  if (!map) return;

  const currentFeatures = filteredFeatures.value;
  const currentIds = new Set(currentFeatures.map((f) => String(f.id)));
  const previousIds = previousFeatureIds.value;

  previousIds.forEach((oldId) => {
    if (!currentIds.has(oldId)) {
      const layer = featureLayerManager.layers.get(oldId);
      if (layer) {
        map!.removeLayer(layer);
        featureLayerManager.layers.delete(oldId);
      }
    }
  });

  const featuresByType = {
    point: currentFeatures.filter((f) => getMapElementType(f) === "point"),
    zone: currentFeatures.filter((f) => getMapElementType(f) === "zone"),
    arrow: currentFeatures.filter((f) => getMapElementType(f) === "arrow"),
    shape: currentFeatures.filter((f) => getMapElementType(f) === "shape"),
    polyline: currentFeatures.filter(
      (f) => getMapElementType(f) === "polyline",
    ),
  };

  renderCities(featuresByType.point);
  renderZones(featuresByType.zone);
  renderArrows([...featuresByType.arrow, ...featuresByType.polyline]);
  renderShapes(featuresByType.shape);

  previousFeatureIds.value = currentIds;
  emit("features-loaded", currentFeatures);
}

onMounted(() => {
  map = L.map("map").setView([52.9399, -73.5491], 5);

  L.tileLayer(
    "https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png",
    {
      attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
      subdomains: "abcd",
      maxZoom: 19,
    },
  ).addTo(map);

  drawing.initializeDrawing(map);
  drawing.setSelectedYear(selectedYear.value);
  renderAllFeatures();
});

onBeforeUnmount(() => {
  if (map) {
    featureLayerManager.clearAllFeatures();
    map.remove();
    map = null;
  }
});

watch(selectedYear, (newYear) => {
  drawing.setSelectedYear(newYear);
  void newYear;
  if (!map) return;
  renderAllFeatures();
});

watch(
  () => props.features,
  (newFeatures) => {
    localFeaturesSnapshot.value = [...newFeatures];
    if (!map) return;
    renderAllFeatures();
  },
  { deep: true },
);

localFeaturesSnapshot.value = [...props.features];

watch(
  () => props.featureVisibility,
  (newVisibility) => {
    newVisibility.forEach((visible, featureId) => {
      featureLayerManager.toggleFeature(featureId, visible);
    });
  },
  { deep: true },
);
</script>

<style>
.city-label-text {
  font-size: 12px;
  font-weight: bold;
  color: black;
  background: transparent;
  padding: 2px 4px;
  border-radius: 3px;
  border: transparent;
}

.arrow-head {
  font-size: 20px;
  color: black;
  transform: rotate(0deg);
}
</style>
