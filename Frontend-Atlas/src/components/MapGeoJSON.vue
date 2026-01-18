<template>
  <div class="relative h-full w-full z-0">
    <div id="map" style="height: 80vh; width: 100%"></div>
    <TimelineSlider v-model:year="selectedYear" />
  </div>
</template>

<script setup>
import { onMounted, ref, watch, computed } from "vue";
import L from "leaflet";
import "leaflet-geometryutil"; // ← requis pour que arrowheads fonctionne
import "leaflet-arrowheads"; // ← ajoute la méthode `arrowheads` aux polylines
import TimelineSlider from "../components/TimelineSlider.vue";

// Props reçues de la vue parent
const props = defineProps({
  mapId: String,
  features: Array,
  featureVisibility: Map,
});

// Émissions vers la vue parent
const emit = defineEmits(["features-loaded"]);

const selectedYear = ref(1740); // initial displayed year
const previousFeatureIds = ref(new Set());

// List of available years
const availableYears = [
  1400, 1500, 1530, 1600, 1650, 1700, 1715, 1783, 1800, 1815, 1880, 1900, 1914,
  1920, 1930, 1938, 1945, 1960, 1994, 2000, 2010,
];

let map = null;
let currentRegionsLayer = null;
let baseTileLayer = null;
let labelLayer = null;
const mockedCities = [
  { name: "Montréal", lat: 45.5017, lng: -73.5673, foundation_year: 1642 },
  { name: "Québec", lat: 46.8139, lng: -71.2082, foundation_year: 1608 },
  { name: "Trois-Rivières", lat: 46.343, lng: -72.5406, foundation_year: 1634 },
];

let citiesLayer = null;
let zonesLayer = null;
let arrowsLayer = null;

// Function to display the map
onMounted(() => {
  map = L.map("map").setView([52.9399, -73.5491], 5);

  // Background map
  baseTileLayer = L.tileLayer(
    "https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png",
    {
      attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
      subdomains: "abcd",
      maxZoom: 19,
    },
  ).addTo(map);

  loadRegionsForYear(selectedYear.value, true);

  // uncomment when link to db is done
  // loadTestNormalizedShape();

});

// Gestionnaire de layers par feature
const featureLayerManager = {
  layers: new Map(),

  addFeatureLayer(featureId, layer) {
    if (this.layers.has(featureId)) {
      map.removeLayer(this.layers.get(featureId));
    }
    this.layers.set(featureId, layer);

    // Ajouter seulement si visible
    if (props.featureVisibility.get(featureId)) {
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

const filteredFeatures = computed(() => {
  return props.features.filter(
    (feature) =>
      new Date(feature.start_date).getFullYear() <= selectedYear.value &&
      (!feature.end_date ||
        new Date(feature.end_date).getFullYear() >= selectedYear.value),
  );
});

async function fetchFeaturesAndRender(year) {
  const mapId = "11111111-1111-1111-1111-111111111111";

  try {
    const res = await fetch(`http://localhost:8000/maps/features/${mapId}`);
    if (!res.ok) throw new Error("Failed to fetch features");

    const allFeatures = await res.json();

    // Filtrer par année
    const features = allFeatures.filter(
      (f) => new Date(f.start_date).getFullYear() <= year,
    );

    // Dispatcher selon le type
    const cities = features.filter(
      (f) => f.properties?.mapElementType === "point",
    );
    const zones = features.filter(
      (f) => f.properties?.mapElementType === "zone",
    );
    const arrows = features.filter(
      (f) => f.properties?.mapElementType === "arrow",
    );

    renderCities(cities);
    renderZones(zones);
    renderArrows(arrows);
  } catch (err) {
    console.warn("Erreur fetch features:", err);
  }
}
// Returns the closest available year that is less than or equal to the requested year
function getClosestAvailableYear(year) {
  const sorted = [...availableYears].sort((a, b) => a - b);
  for (let i = sorted.length - 1; i >= 0; i--) {
    if (year >= sorted[i]) return sorted[i];
  }
  return sorted[0]; // default to the earliest year
}

let lastCurrentYear;
// Loads the GeoJSON file named world_(year) and displays its content on the map
function loadRegionsForYear(year, isFirstTime = false) {
  const closestYear = getClosestAvailableYear(year);

  if (isFirstTime) {
    lastCurrentYear = closestYear;
  } else {
    if (lastCurrentYear == closestYear) {
      return;
    }
  }

  lastCurrentYear = closestYear;
  const filename = `/geojson/world_${closestYear}.geojson`;

  return fetch(filename)
    .then((res) => {
      if (!res.ok) throw new Error("File not found: " + filename);
      return res.json();
    })
    .then((data) => {
      if (currentRegionsLayer) {
        map.removeLayer(currentRegionsLayer);
        currentRegionsLayer = null;
      }
      currentRegionsLayer = L.geoJSON(data, {
        style: {
          color: "#444",
          weight: 2,
          fill: false,
        },
        onEachFeature: (feature, layer) => {
          layer.bindPopup(feature.properties.name || "Unnamed");
        },
      }).addTo(map);
    })
    .catch((err) => {
      console.warn(err.message);
    });
}

function renderCities(features) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach((feature) => {
    // Defensive check
    if (!feature.geometry || !Array.isArray(feature.geometry.coordinates)) {
      return;
    }

    const [lng, lat] = feature.geometry.coordinates;
    const coord = [lat, lng];

    const props = feature.properties || {};
    const rgb = Array.isArray(props.color_rgb) ? props.color_rgb : null;
    const colorFromRgb =
      rgb && rgb.length === 3
        ? `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`
        : null;
    const color = feature.color || colorFromRgb || "#000";

    const point = L.circleMarker(coord, {
      radius: 6,
      fillColor: color,
      color,
      weight: 1,
      opacity: feature.opacity ?? 1,
      fillOpacity: feature.opacity ?? 1,
    });

    const label = L.marker(coord, {
      icon: L.divIcon({
        className: "city-label-text",
        html: props.name || feature.name || "",
        iconSize: [100, 20],
        iconAnchor: [-8, 15],
      }),
      interactive: false,
    });

    const layerGroup = L.layerGroup([point, label]);
    featureLayerManager.addFeatureLayer(feature.id, layerGroup);
  });
}

function renderZones(features) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach((feature) => {
    if (!feature.geometry || !Array.isArray(feature.geometry.coordinates)) {
      return;
    }

    const props = feature.properties || {};
    const rgb = Array.isArray(props.color_rgb) ? props.color_rgb : null;
    const colorFromRgb =
      rgb && rgb.length === 3
        ? `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`
        : null;
    const fillColor = feature.color || colorFromRgb || "#ccc";

    const layer = L.geoJSON(feature.geometry, {
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

function renderArrows(features) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach((feature) => {
    if (!feature.geometry || !Array.isArray(feature.geometry.coordinates)) {
      return;
    }
    // Convert GeoJSON [lng, lat] → Leaflet [lat, lng]
    const latLngs = feature.geometry.coordinates.map(([lng, lat]) => [
      lat,
      lng,
    ]);

    const props = feature.properties || {};
    const rgb = Array.isArray(props.color_rgb) ? props.color_rgb : null;
    const colorFromRgb =
      rgb && rgb.length === 3
        ? `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})`
        : null;
    const color = feature.color || colorFromRgb || "#000";

    const line = L.polyline(latLngs, {
      color,
      weight: feature.stroke_width ?? 2,
      opacity: feature.opacity ?? 1,
    });

    line.addTo(map);

    // Apply arrowheads (after addTo(map))
    line.arrowheads({
      size: "10px",
      frequency: "endonly",
      fill: true,
    });

    const name = props.name || feature.name;
    if (name) {
      line.bindPopup(name);
    }

    featureLayerManager.addFeatureLayer(feature.id, line);
  });
}

function renderAllFeatures() {
  const currentFeatures = filteredFeatures.value;
  const currentIds = new Set(currentFeatures.map((f) => f.id));
  const previousIds = previousFeatureIds.value;

  previousIds.forEach((oldId) => {
    if (!currentIds.has(oldId)) {
      const layer = featureLayerManager.layers.get(oldId);
      if (layer) {
        map.removeLayer(layer);
        featureLayerManager.layers.delete(oldId);
      }
    }
  });

  const newFeatures = currentFeatures.filter((f) => !previousIds.has(f.id));
  const featuresByType = {
    point: newFeatures.filter(
      (f) => f.properties?.mapElementType === "point",
    ),
    polygon: newFeatures.filter(
      (f) => f.properties?.mapElementType === "zone",
    ),
    arrow: newFeatures.filter(
      (f) => f.properties?.mapElementType === "arrow",
    ),
  };

  renderCities(featuresByType.point);
  renderZones(featuresByType.polygon);
  renderArrows(featuresByType.arrow);

  previousFeatureIds.value = currentIds;

  emit("features-loaded", currentFeatures);
}

function removeGeoJSONLayers() {
  if (currentRegionsLayer) {
    map.removeLayer(currentRegionsLayer);
    currentRegionsLayer = null;
  }
}

// Loads all necessary layers for the given year
let isLoading = false;

async function loadAllLayersForYear(year) {
  if (isLoading) return;
  isLoading = true;

  try {
    await loadRegionsForYear(year); // <-- ici on attend le chargement complet
    renderAllFeatures();
  } catch (e) {
    console.warn("Error loading layers:", e);
  } finally {
    isLoading = false;
  }
}
// Creates a delay between map updates to prevent issues caused by rapid year changes
function debounce(fn, delay) {
  let timeout;
  return (...args) => {
    clearTimeout(timeout);
    timeout = setTimeout(() => fn(...args), delay);
  };
}

function transformNormalizedToWorld(geojson, anchorLat, anchorLng, sizeMeters) {
  // Use the same projected CRS as the basemap (Web Mercator).
  const crs = L.CRS.EPSG3857;
  const center = crs.project(L.latLng(anchorLat, anchorLng)); // { x, y } in meters
  const halfSize = sizeMeters / 2;

  // Transform a single coordinate [x, y] in [0,1]×[0,1] into [lng, lat]
  const transformCoord = ([x, y]) => {
    // Center the shape around (0,0) in its local space
    const nx = x - 0.5;
    const ny = y - 0.5;

    // Work in projected meters with a uniform scale so aspect ratio is preserved
    const mx = center.x + nx * 2 * halfSize;
    const my = center.y - ny * 2 * halfSize; // minus because y grows downward

    const latlng = crs.unproject(L.point(mx, my));
    return [latlng.lng, latlng.lat]; // GeoJSON order = [lng, lat]
  };

  const transformCoords = (coords) => {
    if (typeof coords[0] === "number") {
      // [x, y]
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

async function loadTestNormalizedShape() {
  // file doesnt exist in project, in future code we will access
  // geojson with the db but code rest of code can be reused so its best to
  // keep it imo
  const url = "/geojson/blue_normalized.geojson";

  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error("File not found: " + url);
    const normalized = await res.json();

    // Arbitrary anchor somewhere in central Canada
    const anchorLat = 56;
    const anchorLng = -100;

    // Choose a base size in meters for the projected shape
    // (e.g. 1,000,000 m ≈ 1000 km across). Adjust to taste.
    const sizeMeters = 1_000_000;

    const worldGeojson = transformNormalizedToWorld(
      normalized,
      anchorLat,
      anchorLng,
      sizeMeters,
    );

    const layer = L.geoJSON(worldGeojson, {
      // Use the color provided in GeoJSON properties when available
      style: (feature) => ({
        color: feature?.properties?.color_hex || "#ff0000",
        fillColor: feature?.properties?.color_hex || "#ff0000",
        weight: 2,
        fillOpacity: 0.5,
      }),
    }).addTo(map);

    // Optionally zoom the map to this test shape
    const bounds = layer.getBounds();
    if (bounds.isValid()) {
      map.fitBounds(bounds);
      // Zoom in a bit more so the shape appears larger
      map.zoomIn(1);
    }
  } catch (err) {
    console.warn("Error loading normalized test shape:", err);
  }
}

function toArray(maybeArray) {
  if (Array.isArray(maybeArray)) return maybeArray;
  if (maybeArray == null) return []; // null or undefined
  return [maybeArray]; // wrap single object
}

// Uses debounce to load GeoJSON layers
const debouncedUpdate = debounce((year) => {
  loadAllLayersForYear(year);
}, 100);

// Watchers
watch(selectedYear, (newYear) => {
  debouncedUpdate(newYear);
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
  transform: rotate(0deg); /* statique pour l’instant */
}
</style>
