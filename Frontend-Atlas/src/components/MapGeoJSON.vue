<template>
  <div class="relative h-full w-full z-0 flex flex-col min-h-0">
    <div id="map" class="flex-1 min-h-0 w-full"></div>
    <div class="map-timeline-toolbar flex flex-col gap-1 px-3 py-1.5 bg-base-100 border-t border-base-300">
      <div class="map-timeline-slider w-full min-w-0">
        <TimelineSlider
          v-model:year="selectedYear"
          @exact-date-change="onExactDateChange"
          :min="timelineMinYear"
          :max="timelineMaxYear"
          :marker-years="timelineMarkerYears"
          :map-periods="enrichedPeriods"
          :current-exact-date="selectedExactDate"
        />
      </div>
      <div class="map-timeline-filter flex flex-row gap-1 items-center text-xs font-medium whitespace-nowrap">
        <span>Filtrer par date</span>
        <input
          v-model="useTimelineFilter"
          type="checkbox"
          aria-label="Filtrer par date"
          role="switch"
          class="timeline-filter-toggle"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, watch, ref, computed } from "vue";
import L from "leaflet";
import "leaflet-geometryutil";
import "leaflet-arrowheads";
import TimelineSlider from "../components/TimelineSlider.vue";
import { useMapDrawing } from "../composables/useMapDrawing";
import { colorRgbToCss, getMapElementType } from "../utils/featureHelpers";
import {
  extractFeatureFromLayer,
  syncFeaturesFromLayerMap,
} from "../utils/mapDrawingFeature";
import {
  attachFeatureToLayer,
  bindRenderedFeatureEvents,
} from "../utils/mapLayersFeature";
import { toArray, toImageSrc } from "../utils/utils";
import { toYear } from "../utils/dateUtils";
import type {
  Coordinate,
  Feature,
  Geometry,
  FeatureId,
} from "../typescript/feature";
import type { MapPeriod, SliderPeriod } from "../typescript/map";
import type { AtlasRuntimeLayer } from "../typescript/mapLayers";
import { showAlert } from "../composables/useAlert";

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
  mapPeriods: MapPeriod[];
}>();

const emit = defineEmits<{
  (e: "features-loaded", features: Feature[]): void;
  (e: "draw-create", features: Feature[]): void;
  (e: "draw-update", features: Feature[]): void;
  (
    e: "draw-delete-id",
    featureId: string,
    callbacks: { onSuccess: () => void; onError: (message: string) => void },
  ): void;
  (e: "map-ready", map: L.Map): void;
}>();

const selectedYear = ref(-1);
const selectedExactDate = ref<string | null>(null);
const useTimelineFilter = ref(false);
const previousFeatureIds = ref(new Set<FeatureId>());
const localFeaturesSnapshot = ref<Feature[]>([]);

// Enrich MapPeriod with parsed startYear/endYear, filtering out periods with invalid dates.
const enrichedPeriods = computed((): SliderPeriod[] =>
  props.mapPeriods
    .map((p) => ({ ...p, startYear: toYear(p.startDate), endYear: toYear(p.endDate) }))
    .filter((p): p is SliderPeriod => p.startYear != null && p.endYear != null),
);

// Keyed by map id for O(1) feature filtering.
const periodByMapId = computed(() => new Map(enrichedPeriods.value.map((p) => [p.id, p])));

const timelineMinYear = computed(() =>
  enrichedPeriods.value.length ? Math.min(...enrichedPeriods.value.map((p) => p.startYear)) : 1400,
);

const timelineMaxYear = computed(() =>
  enrichedPeriods.value.length ? Math.max(...enrichedPeriods.value.map((p) => p.endYear)) : new Date().getFullYear(),
);

const timelineMarkerYears = computed(() => {
  const markers = new Set<number>([timelineMinYear.value, timelineMaxYear.value]);
  enrichedPeriods.value.forEach((p) => { markers.add(p.startYear); markers.add(p.endYear); });
  return [...markers].sort((a, b) => a - b);
});

const filteredFeatures = computed(() => {
  return props.features.filter((feature: Feature) => {
    if (!useTimelineFilter.value) return true;

    // Project-level features without a map are always visible in timeline mode.
    if (!feature.mapId) return true;

    const period = periodByMapId.value.get(feature.mapId);
    if (!period) return true;

    if (selectedExactDate.value && period.startDate && period.endDate) {
      return (
        period.startDate <= selectedExactDate.value &&
        period.endDate >= selectedExactDate.value
      );
    }

    if (period.startYear == null || period.endYear == null) return true;
    return (
      period.startYear <= selectedYear.value &&
      period.endYear >= selectedYear.value
    );
  });
});

function onExactDateChange(nextDate: string | null) {
  selectedExactDate.value = nextDate;
}

let map: L.Map | null = null;
let vectorRenderer: L.Canvas | null = null;

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

function upsertFeature(features: Feature[], feature: Feature): Feature[] {
  const targetId = feature.id;
  const next = [...features];
  const index = next.findIndex((f) => f.id === targetId);

  if (index >= 0) {
    next[index] = feature;
    return next;
  }

  next.push(feature);
  return next;
}

function applyLayerUpdate(layer: L.Layer) {
  const runtimeLayer = layer as AtlasRuntimeLayer;

  if (runtimeLayer.__atlasApplyingSync) return;
  runtimeLayer.__atlasApplyingSync = true;

  try {
    const extracted = extractFeatureFromLayer(layer, selectedYear.value);
    if (!extracted) return;

    attachFeatureToLayer(layer, extracted);

    const next = upsertFeature(localFeaturesSnapshot.value, extracted);
    localFeaturesSnapshot.value = next;
    emit("draw-update", next);
  } finally {
    runtimeLayer.__atlasApplyingSync = false;
  }
}

function syncFeaturesFromMapLayers(): Feature[] {
  const mergedById = new Map<string, Feature>();

  const renderedFeatures = syncFeaturesFromLayerMap(
    featureLayerManager.layers,
    localFeaturesSnapshot.value,
    selectedYear.value,
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
  const current = localFeaturesSnapshot.value;

  if (event === "feature-created") {
    const payload = args[0] as Feature;
    const next = upsertFeature(current, payload);
    localFeaturesSnapshot.value = next;
    emit("draw-create", next);
    return;
  }

  if (event === "feature-updated") {
    const payload = args[0] as Feature;
    const next = upsertFeature(current, payload);
    localFeaturesSnapshot.value = next;
    emit("draw-update", next);
    return;
  }

  if (event === "feature-deleted") {
    const deletedId = String(args[0]);
    const next = current.filter((feature) => String(feature.id) !== deletedId);
    localFeaturesSnapshot.value = next;

    emit("draw-delete-id", deletedId);

    return;
  }
});

function renderCities(features: Feature[]) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach((feature) => {
    if (!map || feature.geometry.type !== "Point") return;

    const [lng, lat] = feature.geometry.coordinates;
    const coord: L.LatLngTuple = [lat, lng];

    const fillColor = colorRgbToCss(feature.properties.colorRgb) || "#000000";
    const strokeColor =
      colorRgbToCss(feature.properties.strokeColor) || fillColor;

    const point = L.circleMarker(coord, {
      radius: 6,
      fillColor: fillColor,
      color: strokeColor,
      weight: feature.properties.strokeWidth ?? 1,
      opacity: feature.properties.strokeOpacity ?? 1,
      fillOpacity: feature.properties.opacity ?? 0.5,
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
    bindRenderedFeatureEvents(point, applyLayerUpdate);

    attachFeatureToLayer(label, feature);

    const layerGroup = L.layerGroup([point, label]);
    attachFeatureToLayer(layerGroup, feature);
    featureLayerManager.addFeatureLayer(feature.id, layerGroup);
  });
}

function renderLabels(features: Feature[]) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach((feature) => {
    if (!map || feature.geometry.type !== "Point") return;

    const [lng, lat] = feature.geometry.coordinates;
    const coord: L.LatLngTuple = [lat, lng];

    const labelText = feature.properties.labelText || "";

    const label = L.marker(coord, {
      icon: L.divIcon({
        className: "city-label-text geoman-text-label",
        html: labelText,
        iconSize: [120, 20],
        iconAnchor: [0, 10],
      }),
    });

    const textMarker = label as L.Marker & {
      options: L.MarkerOptions & { text: string; textMarker?: boolean };
    };
    textMarker.options.text = labelText;
    textMarker.options.textMarker = true;

    attachFeatureToLayer(label, feature);
    bindRenderedFeatureEvents(label, applyLayerUpdate);
    featureLayerManager.addFeatureLayer(feature.id, label);
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
    const fillColor = colorRgbToCss(feature.properties.colorRgb) || "#000000";
    const strokeColor =
      colorRgbToCss(feature.properties.strokeColor) || fillColor;

    const layer = L.geoJSON(feature.geometry, {
      style: {
        renderer: vectorRenderer ?? undefined,
        fillColor,
        fillOpacity: 0.5,
        color: strokeColor || fillColor,
        weight: featureProperties.strokeWidth || 1,
        opacity: featureProperties.strokeOpacity ?? 1,
      },
    });

    attachFeatureToLayer(layer, feature);
    bindRenderedFeatureEvents(layer, applyLayerUpdate);

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

    const fillColor = colorRgbToCss(feature.properties.colorRgb) || "#000000";
    const strokeColor =
      colorRgbToCss(feature.properties.strokeColor) || fillColor;

    const line = L.polyline(latLngs, {
      renderer: vectorRenderer ?? undefined,
      color: strokeColor,
      weight: feature.properties.strokeWidth ?? 2,
      opacity: feature.properties.strokeOpacity ?? 1,
    });

    attachFeatureToLayer(line, feature);
    bindRenderedFeatureEvents(line, applyLayerUpdate);

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

function renderPolylines(features: Feature[]) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach((feature) => {
    if (!map || feature.geometry.type !== "LineString") return;

    const latLngs = feature.geometry.coordinates.map(
      ([lng, lat]) => [lat, lng] as L.LatLngTuple,
    );

    const fillColor = colorRgbToCss(feature.properties.colorRgb) || "#000000";
    const strokeColor =
      colorRgbToCss(feature.properties.strokeColor) || fillColor;

    const line = L.polyline(latLngs, {
      color: strokeColor,
      weight: feature.properties.strokeWidth ?? 2,
      opacity: feature.properties.strokeOpacity ?? 1,
    });

    attachFeatureToLayer(line, feature);
    bindRenderedFeatureEvents(line, applyLayerUpdate);

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
    const fillColor = colorRgbToCss(feature.properties.colorRgb) || "#000000";
    const strokeColor =
      colorRgbToCss(feature.properties.strokeColor) || fillColor;

    const layer = L.geoJSON(feature.geometry, {
      style: {
        renderer: vectorRenderer ?? undefined,
        fillColor: fillColor,
        opacity: feature.properties.strokeOpacity ?? 1,
        fillOpacity: feature.properties.strokeOpacity ?? 1,
        color: strokeColor,
        weight: feature.properties.strokeWidth || 1,
      },
    });

    attachFeatureToLayer(layer, feature);
    bindRenderedFeatureEvents(layer, applyLayerUpdate);

    const name = featureProperties.name || feature.name || "Detected shape";
    if (name) {
      layer.bindPopup(name);
    }

    featureLayerManager.addFeatureLayer(feature.id, layer);
  });
}

function renderImages(features: Feature[]) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach((feature) => {
    if (!map || !feature.image) return;

    const bounds = feature.properties?.bounds as [[0, 0], [0, 0]] | undefined;

    if (!bounds) return;

    const src = toImageSrc(feature.image);
    const overlay = L.imageOverlay(src, bounds, {
      opacity: feature.properties.opacity ?? 1,
      interactive: true,
    });

    attachFeatureToLayer(overlay, feature);
    featureLayerManager.addFeatureLayer(feature.id, overlay);
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
    shape: currentFeatures.filter((f) => getMapElementType(f) === "shape"),
    label: currentFeatures.filter((f) => getMapElementType(f) === "label"),
    polyline: currentFeatures.filter(
      (f) => getMapElementType(f) === "polyline",
    ),
    arrow: currentFeatures.filter((f) => getMapElementType(f) === "arrow"),
    image: currentFeatures.filter((f) => getMapElementType(f) === "image"),
  };

  renderCities(featuresByType.point);
  renderLabels(featuresByType.label);
  renderZones(featuresByType.zone);
  renderArrows(featuresByType.arrow);
  renderPolylines(featuresByType.polyline);
  renderShapes(featuresByType.shape);
  renderImages(featuresByType.image);

  previousFeatureIds.value = currentIds;
  emit("features-loaded", currentFeatures);
}

onMounted(() => {
  map = L.map("map", { zoomControl: false, preferCanvas: true }).setView(
    [52.9399, -73.5491],
    5,
  );
  vectorRenderer = L.canvas({ padding: 0.5 });

  L.tileLayer(
    "https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png",
    {
      attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
      subdomains: "abcd",
      maxZoom: 19,
    },
  ).addTo(map);

  drawing.initializeDrawing(map);

  L.control
    .scale({ position: "bottomright", metric: true, imperial: false })
    .addTo(map);

  L.control.zoom({ position: "topleft" }).addTo(map);

  drawing.setSelectedYear(selectedYear.value);
  emit("map-ready", map);
  renderAllFeatures();
});

onBeforeUnmount(() => {
  if (map) {
    featureLayerManager.clearAllFeatures();
    map.remove();
    map = null;
  }
});

watch([selectedYear, useTimelineFilter, selectedExactDate], () => {
  if (!map) return;
  renderAllFeatures();
});

watch([timelineMinYear, timelineMaxYear], () => {
  if (selectedYear.value < timelineMinYear.value) {
    selectedYear.value = timelineMinYear.value;
  }
  if (selectedYear.value > timelineMaxYear.value) {
    selectedYear.value = timelineMaxYear.value;
  }
});

watch(
  timelineMarkerYears,
  (markers) => {
    if (!markers.length) return;
    if (!markers.includes(selectedYear.value)) {
      selectedYear.value = markers[0];
    }
  },
  { immediate: true },
);

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

.timeline-filter-toggle {
  appearance: none;
  width: 2.25rem;
  height: 1.25rem;
  border-radius: 9999px;
  border: 1px solid var(--color-base-300);
  background-color: var(--color-base-300);
  position: relative;
  cursor: pointer;
  transition: background-color 150ms ease, border-color 150ms ease;
}

.timeline-filter-toggle::before {
  content: "";
  position: absolute;
  top: 50%;
  left: 2px;
  width: 0.9rem;
  height: 0.9rem;
  border-radius: 9999px;
  background-color: var(--color-primary-content);
  transform: translate(0, -50%);
  transition: transform 150ms ease, background-color 150ms ease;
}

.timeline-filter-toggle:checked {
  background-color: var(--color-primary);
  border-color: var(--color-primary);
}

.timeline-filter-toggle:checked::before {
  background-color: var(--color-primary-content);
  transform: translate(1rem, -50%);
}

.timeline-filter-toggle:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}
</style>
