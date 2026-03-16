<template>
  <div class="relative h-full w-full z-0">
    <div id="map" style="height: 80vh; width: 100%"></div>
    <TimelineSlider v-model:year="selectedYear" />
  </div>
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, watch, computed, ref } from "vue";
import L from "leaflet";
import "leaflet-geometryutil";
import "leaflet-arrowheads";
import TimelineSlider from "../components/TimelineSlider.vue";
import { useMapDrawing } from "../composables/useMapDrawing";
import { getMapElementType } from "../utils/featureHelpers";
import type { Feature, Geometry, Coordinate } from "../typescript/feature";
import type { LayerWithFeature as LayerWithFeatureType } from "../typescript/mapLayers";

type FeatureId = string;

type FeatureLike = Feature & {
  properties?: Feature["properties"] & {
    color_rgb?: [number, number, number];
    is_normalized?: boolean;
    isNormalized?: boolean;
    start_date?: string;
    end_date?: string;
  };
  stroke_width?: number;
};

type LayerWithFeature = LayerWithFeatureType<FeatureLike>;

const props = defineProps<{
  features: FeatureLike[];
  featureVisibility: Map<string, boolean>;
}>();

const emit = defineEmits<{
  (e: "features-loaded", features: FeatureLike[]): void;
  (e: "draw-create", features: FeatureLike[]): void;
  (e: "draw-update", features: FeatureLike[]): void;
  (e: "draw-delete", features: FeatureLike[]): void;
}>();

const selectedYear = ref(1740);
const previousFeatureIds = ref(new Set<FeatureId>());
const localFeaturesSnapshot = ref<FeatureLike[]>([]);

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

function featureIdAsString(featureOrId: FeatureLike | string | number): string {
  if (typeof featureOrId === "object" && featureOrId !== null) {
    return String(featureOrId.id);
  }
  return String(featureOrId);
}

function upsertFeature(
  features: FeatureLike[],
  feature: FeatureLike,
): FeatureLike[] {
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

const drawing = useMapDrawing((event, ...args) => {
  const payload = args[0] as FeatureLike | string | number;
  const current = localFeaturesSnapshot.value;

  if (event === "feature-created") {
    const next = upsertFeature(current, payload as FeatureLike);
    localFeaturesSnapshot.value = next;
    emit("draw-create", next);
    return;
  }

  if (event === "feature-updated") {
    const next = upsertFeature(current, payload as FeatureLike);
    localFeaturesSnapshot.value = next;
    emit("draw-update", next);
    return;
  }

  if (event === "feature-deleted") {
    const deletedId = featureIdAsString(payload);
    const next = current.filter(
      (feature) => featureIdAsString(feature) !== deletedId,
    );
    localFeaturesSnapshot.value = next;
    emit("draw-delete", next);
  }
});

const filteredFeatures = computed(() => {
  return props.features.filter((feature) => {
    const featureProperties =
      feature.properties || ({} as FeatureLike["properties"]);
    const startRaw =
      featureProperties.startDate || featureProperties.start_date;
    const endRaw = featureProperties.endDate || featureProperties.end_date;

    const startYear = startRaw ? new Date(startRaw).getFullYear() : -Infinity;
    const endYear = endRaw ? new Date(endRaw).getFullYear() : Infinity;

    return startYear <= selectedYear.value && endYear >= selectedYear.value;
  });
});

function getRgbColor(feature: FeatureLike): string | null {
  const featureProperties =
    feature.properties || ({} as FeatureLike["properties"]);
  const rgb = Array.isArray(featureProperties.colorRgb)
    ? featureProperties.colorRgb
    : Array.isArray(featureProperties.color_rgb)
      ? featureProperties.color_rgb
      : null;
  return rgb && rgb.length === 3
    ? `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`
    : null;
}

function attachFeatureToLayer(layer: L.Layer, feature: FeatureLike) {
  const layerWithFeature = layer as LayerWithFeature;
  layerWithFeature.feature = feature;

  if (typeof layerWithFeature.eachLayer === "function") {
    layerWithFeature.eachLayer((childLayer) => {
      (childLayer as LayerWithFeature).feature = feature;
    });
  }
}

function renderCities(features: FeatureLike[]) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach((feature) => {
    if (!map || feature.geometry.type !== "Point") return;

    const [lng, lat] = feature.geometry.coordinates;
    const coord: L.LatLngTuple = [lat, lng];

    const colorFromRgb = getRgbColor(feature);
    const color = feature.color || colorFromRgb || "#000";

    const point = L.circleMarker(coord, {
      radius: 6,
      fillColor: color,
      color,
      weight: 1,
      opacity: feature.opacity ?? 1,
      fillOpacity: feature.opacity ?? 1,
    });

    const featureProperties =
      feature.properties || ({} as FeatureLike["properties"]);
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

function renderZones(features: FeatureLike[]) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach((feature) => {
    if (!map) return;
    if (
      feature.geometry.type !== "Polygon" &&
      feature.geometry.type !== "MultiPolygon"
    ) {
      return;
    }

    const featureProperties =
      feature.properties || ({} as FeatureLike["properties"]);
    const colorFromRgb = getRgbColor(feature);
    const fillColor = feature.color || colorFromRgb || "#ccc";
    const isNormalized = Boolean(
      featureProperties.isNormalized ?? featureProperties.is_normalized,
    );
    const targetGeometry = isNormalized
      ? normalizeGeometryToWorld(feature.geometry, 2_000_000)
      : feature.geometry;

    const layer = L.geoJSON(targetGeometry, {
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

function renderArrows(features: FeatureLike[]) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach((feature) => {
    if (!map || feature.geometry.type !== "LineString") return;

    const latLngs = feature.geometry.coordinates.map(
      ([lng, lat]) => [lat, lng] as L.LatLngTuple,
    );

    const colorFromRgb = getRgbColor(feature);
    const color = feature.color || colorFromRgb || "#000";

    const line = L.polyline(latLngs, {
      color,
      weight: feature.strokeWidth ?? feature.stroke_width ?? 2,
      opacity: feature.opacity ?? 1,
    });
    attachFeatureToLayer(line, feature);

    line.addTo(map);
    line.arrowheads({
      size: "10px",
      frequency: "endonly",
      fill: true,
    });

    const featureProperties =
      feature.properties || ({} as FeatureLike["properties"]);
    const name = featureProperties.name || feature.name;
    if (name) {
      line.bindPopup(name);
    }

    featureLayerManager.addFeatureLayer(feature.id, line);
  });
}

function renderShapes(features: FeatureLike[]) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach((feature) => {
    if (!map) return;
    if (
      feature.geometry.type !== "Polygon" &&
      feature.geometry.type !== "MultiPolygon"
    ) {
      return;
    }

    const featureProperties =
      feature.properties || ({} as FeatureLike["properties"]);
    const colorFromRgb = getRgbColor(feature);
    const fillColor = feature.color || colorFromRgb || "#ccc";
    const isNormalized = Boolean(
      featureProperties.isNormalized ?? featureProperties.is_normalized,
    );
    const targetGeometry = isNormalized
      ? normalizeGeometryToWorld(feature.geometry, 1_000_000)
      : feature.geometry;

    const layer = L.geoJSON(targetGeometry, {
      style: {
        fillColor,
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

function toArray<T>(maybeArray: T[] | T | null | undefined): T[] {
  if (Array.isArray(maybeArray)) return maybeArray;
  if (maybeArray == null) return [];
  return [maybeArray];
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
