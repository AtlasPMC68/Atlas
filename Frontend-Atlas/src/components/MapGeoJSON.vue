<template>
  <div class="relative h-full w-full z-0">
    <div id="map" style="height: 80vh; width: 100%"></div>
      <div class="map-timeline-toolbar flex flex-col gap-2 px-4 py-2 bg-base-100 border-t border-base-300">
        <div class="map-timeline-slider w-full min-w-0">
          <TimelineSlider
            v-model:year="selectedYear"
            @exact-date-change="onExactDateChange"
            :min="timelineMinYear"
            :max="timelineMaxYear"
            :marker-years="timelineMarkerYears"
            :map-periods="sliderMapPeriods"
            :current-exact-date="selectedExactDate"
          />
        </div>
        <div class="map-timeline-filter flex flex-row gap-1 items-center text-sm font-medium whitespace-nowrap">
          <span>Filtrer par date</span>
          <input
            v-model="useTimelineFilter"
            type="checkbox"
            aria-label="Filtrer par date"
            class="timeline-filter-toggle toggle toggle-sm"
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
import { getFeatureRgbColor, getMapElementType } from "../utils/featureHelpers";
import { toArray, toImageSrc } from "../utils/utils";
import type { Coordinate, Feature, Geometry } from "../typescript/feature";
import type { LayerWithFeature as LayerWithFeatureType } from "../typescript/mapLayers";
import type { MapFeatureId } from "../typescript/mapDrawing";

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
  mapPeriods: Array<{
    id: string;
    title: string;
    startDate: string | null;
    endDate: string | null;
    exactDate: boolean;
    color: string;
  }>;
}>();

const emit = defineEmits<{
  (e: "features-loaded", features: Feature[]): void;
  (e: "draw-create", features: Feature[]): void;
  (e: "draw-update", features: Feature[]): void;
  (e: "draw-delete", features: Feature[]): void;
  (e: "map-ready", map: L.Map): void;
}>();

const selectedYear = ref(-1);
const selectedExactDate = ref<string | null>(null);
const useTimelineFilter = ref(false);
const previousFeatureIds = ref(new Set<MapFeatureId>());
const localFeaturesSnapshot = ref<Feature[]>([]);

function toYear(value: string | null | undefined): number | null {
  if (!value) return null;
  const match = /^(\d{4})-\d{2}-\d{2}$/.exec(value);
  if (!match) return null;

  const year = Number(match[1]);
  return Number.isFinite(year) ? year : null;
}

const periodYears = computed(() => {
  const years: number[] = [];
  props.mapPeriods.forEach((period) => {
    const s = toYear(period.startDate);
    const e = toYear(period.endDate);
    if (s != null) years.push(s);
    if (e != null) years.push(e);
  });
  return years;
});

const timelineMinYear = computed(() => {
  const years = [...periodYears.value];
  if (!years.length) return 1400;
  return Math.min(...years);
});

const timelineMaxYear = computed(() => {
  const years = [...periodYears.value];
  if (!years.length) return new Date().getFullYear();
  return Math.max(...years);
});

const mapPeriodsByMapId = computed(() => {
  const periods = new Map<
    string,
    {
      startYear: number | null;
      endYear: number | null;
      startDate: string | null;
      endDate: string | null;
    }
  >();
  props.mapPeriods.forEach((period) => {
    periods.set(period.id, {
      startYear: toYear(period.startDate),
      endYear: toYear(period.endDate),
      startDate: period.startDate,
      endDate: period.endDate,
    });
  });
  return periods;
});

const sliderMapPeriods = computed(() => {
  return props.mapPeriods
    .map((period) => ({
      id: period.id,
      title: period.title,
      color: period.color,
      startYear: toYear(period.startDate),
      endYear: toYear(period.endDate),
      startDate: period.startDate,
      endDate: period.endDate,
      exactDate: period.exactDate,
    }))
    .filter((period) => period.startYear != null && period.endYear != null)
    .map((period) => ({
      id: period.id,
      title: period.title,
      color: period.color,
      startYear: period.startYear as number,
      endYear: period.endYear as number,
      startDate: period.startDate,
      endDate: period.endDate,
      exactDate: period.exactDate,
    }));
});

const timelineMarkerYears = computed(() => {
  const markers = new Set<number>();
  markers.add(timelineMinYear.value);
  markers.add(timelineMaxYear.value);

  sliderMapPeriods.value.forEach((period) => {
    markers.add(period.startYear);
    markers.add(period.endYear);
  });

  return [...markers].sort((a, b) => a - b);
});

const filteredFeatures = computed(() => {
  return props.features.filter((feature: Feature) => {
    if (!useTimelineFilter.value) return true;

    const period = mapPeriodsByMapId.value.get(feature.mapId);
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
  layers: new Map<MapFeatureId, L.Layer>(),

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

const drawing = useMapDrawing((...args) => {
  const [event, payload] = args;
  const current = localFeaturesSnapshot.value;

  if (event === "feature-created") {
    const next = upsertFeature(current, payload);
    localFeaturesSnapshot.value = next;
    emit("draw-create", next);
    return;
  }

  if (event === "feature-updated") {
    const next = upsertFeature(current, payload);
    localFeaturesSnapshot.value = next;
    emit("draw-update", next);
    return;
  }

  if (event === "feature-deleted") {
    const next = current.filter((feature) => feature.id !== payload);
    localFeaturesSnapshot.value = next;
    emit("draw-delete", next);
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
        renderer: vectorRenderer ?? undefined,
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
      renderer: vectorRenderer ?? undefined,
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
        renderer: vectorRenderer ?? undefined,
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

function renderImages(features: Feature[]) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach((feature) => {
    if (!map || !feature.image) return;

    const bounds = feature.properties?.bounds as [[0, 0], [0, 0]] | undefined;

    if (!bounds) return;

    const src = toImageSrc(feature.image);
    const overlay = L.imageOverlay(src, bounds, {
      opacity: feature.opacity ?? 1,
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
    arrow: currentFeatures.filter((f) => getMapElementType(f) === "arrow"),
    shape: currentFeatures.filter((f) => getMapElementType(f) === "shape"),
    polyline: currentFeatures.filter(
      (f) => getMapElementType(f) === "polyline",
    ),
    image: currentFeatures.filter((f) => getMapElementType(f) === "image"),
  };

  renderCities(featuresByType.point);
  renderZones(featuresByType.zone);
  renderArrows([...featuresByType.arrow, ...featuresByType.polyline]);
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
  background-color: var(--color-base-300) !important;
  border-color: var(--color-base-300) !important;
}

.timeline-filter-toggle::before {
  background-color: var(--color-primary-content) !important;
}

.timeline-filter-toggle:checked {
  background-color: var(--color-primary) !important;
  border-color: var(--color-primary) !important;
}

.timeline-filter-toggle:checked::before {
  background-color: var(--color-primary-content) !important;
}
</style>
