<template>
  <div class="relative h-full w-full z-0">
    <div id="test-map" style="height: 80vh; width: 100%"></div>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from "vue";
import L from "leaflet";
import "leaflet-geometryutil";
import "leaflet-arrowheads";

const props = defineProps({
  mapId: String,
  features: {
    type: Array,
    default: () => [],
  },
  featureVisibility: {
    type: Map,
    default: () => new Map(),
  },
});

const emit = defineEmits(["features-loaded"]);

let map = null;
let baseTileLayer = null;

const featureLayerManager = {
  layers: new Map(),

  addFeatureLayer(featureId, layer) {
    if (this.layers.has(featureId)) {
      map.removeLayer(this.layers.get(featureId));
    }
    this.layers.set(featureId, layer);

    const isVisible = props.featureVisibility.get(featureId) ?? true;
    if (isVisible) {
      map.addLayer(layer);
    }
  },

  toggleFeature(featureId, visible) {
    const layer = this.layers.get(featureId);
    if (layer) {
      if (visible) {
        map.addLayer(layer);
      } else {
        map.removeLayer(layer);
      }
    }
  },

  clearAllFeatures() {
    this.layers.forEach((layer) => map.removeLayer(layer));
    this.layers.clear();
  },
};

function renderZones(features) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach((feature) => {
    if (!feature.geometry || !Array.isArray(feature.geometry.coordinates)) {
      return;
    }

    const props = feature.properties || {};
    const rgb = Array.isArray(props.color_rgb) ? props.color_rgb : null;
    const colorFromRgb =
      rgb && rgb.length === 3 ? `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})` : null;
    const fillColor = feature.color || colorFromRgb || "#ccc";
    let targetGeometry = feature.geometry;

    if (props.is_normalized) {
      const fc = {
        type: "FeatureCollection",
        features: [feature],
      };

      const anchorLat = -80 + Math.random() * 160;
      const anchorLng = -170 + Math.random() * 340;
      const sizeMeters = 2_000_000;

      const worldFc = transformNormalizedToWorld(
        fc,
        anchorLat,
        anchorLng,
        sizeMeters,
      );

      if (
        worldFc &&
        Array.isArray(worldFc.features) &&
        worldFc.features[0]?.geometry
      ) {
        targetGeometry = worldFc.features[0].geometry;
      }
    }

    const layer = L.geoJSON(targetGeometry, {
      style: {
        fillColor,
        fillOpacity: 0.5,
        color: "#333",
        weight: 1,
      },
    });

    const name = props.name || feature.name;
    if (name) {
      layer.bindPopup(name);
    }

    featureLayerManager.addFeatureLayer(feature.id, layer);
  });
}

let previousFeatureIds = new Set();

function renderAllFeatures() {
  if (!map) return;

  const currentFeatures = (props.features || []).filter(
    (f) => f?.properties?.mapElementType === "zone",
  );

  const currentIds = new Set(currentFeatures.map((f) => f.id));

  previousFeatureIds.forEach((oldId) => {
    if (!currentIds.has(oldId)) {
      const layer = featureLayerManager.layers.get(oldId);
      if (layer) {
        map.removeLayer(layer);
        featureLayerManager.layers.delete(oldId);
      }
    }
  });

  const newFeatures = currentFeatures.filter((f) => !previousFeatureIds.has(f.id));

  featureLayerManager.clearAllFeatures();
  renderZones(newFeatures);

  previousFeatureIds = currentIds;

  emit("features-loaded", currentFeatures);
}

function transformNormalizedToWorld(geojson, anchorLat, anchorLng, sizeMeters) {
  const crs = L.CRS.EPSG3857;
  const center = crs.project(L.latLng(anchorLat, anchorLng));
  const halfSize = sizeMeters / 2;

  const transformCoord = ([x, y]) => {
    const nx = x - 0.5;
    const ny = y - 0.5;

    const mx = center.x + nx * 2 * halfSize;
    const my = center.y - ny * 2 * halfSize;

    const latlng = crs.unproject(L.point(mx, my));
    return [latlng.lng, latlng.lat];
  };

  const transformCoords = (coords) => {
    if (typeof coords[0] === "number") {
      return transformCoord(coords);
    }
    return coords.map(transformCoords);
  };

  return {
    ...geojson,
    features: geojson.features.map((f) => ({
      ...f,
      geometry: {
        ...f.geometry,
        coordinates: transformCoords(f.geometry.coordinates),
      },
    })),
  };
}

function toArray(maybeArray) {
  if (Array.isArray(maybeArray)) return maybeArray;
  if (maybeArray == null) return [];
  return [maybeArray];
}

onMounted(() => {
  map = L.map("test-map").setView([52.9399, -73.5491], 5);

  baseTileLayer = L.tileLayer(
    "https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png",
    {
      attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
      subdomains: "abcd",
      maxZoom: 19,
    },
  ).addTo(map);

  renderAllFeatures();
});

watch(
  () => props.features,
  () => {
    renderAllFeatures();
  },
  { deep: true },
);

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
