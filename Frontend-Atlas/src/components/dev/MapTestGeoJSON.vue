<template>
  <div class="relative h-full w-full z-0">
    <div ref="mapEl" style="height: 80vh; width: 100%"></div>
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, ref, watch } from "vue";
import L from "leaflet";

const mapEl = ref(null);

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
  // Create-zone mode control
  isCreateMode: {
    type: Boolean,
    default: false,
  },
  resetCreateKey: {
    type: Number,
    default: 0,
  },
  isFrontierMode: {
    type: Boolean,
    default: false,
  },
  isGeoBorderMode: {
    type: Boolean,
    default: false,
  },
  undoCreateKey: {
    type: Number,
    default: 0,
  },
  subGeometries: {
    type: Array,
    default: () => [],
  },
});

const emit = defineEmits(["features-loaded", "zone-click", "create-updated"]);

let map = null;
let baseTileLayer = null;
let isUnmounted = false;

// Multi-stroke create-zone drawing state
let strokes = [];
let currentStroke = [];
let createStrokeLayer = null;
let createPolygonLayer = null;
let isDrawing = false;
const SNAP_EPS_METERS = 3000; // snapping distance between stroke endpoints

// Frontier (coastline) data and state
let coastlineLines = [];
let frontierStartRef = null; // { lineIdx, ptIdx, latlng }
let geoBorderLines = [];
let geoRegionsLayer = null;
let subzoneLayerGroup = null;

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

    if (feature.id) {
      layer.on("click", () => {
        emit("zone-click", feature.id);
      });
    }
  });
}

function renderAllFeatures() {
  if (!map) return;

  const currentFeatures = (props.features || []).filter(
    (f) => f?.properties?.mapElementType === "zone",
  );

  featureLayerManager.clearAllFeatures();
  renderZones(currentFeatures);

  emit("features-loaded", currentFeatures);
}

function renderSubzones(geoms) {
  if (!map || !subzoneLayerGroup) return;

  subzoneLayerGroup.clearLayers();

  const safe = Array.isArray(geoms) ? geoms : [];

  safe.forEach((g) => {
    if (!g || g.type !== "Polygon" || !Array.isArray(g.coordinates)) return;

    const layer = L.geoJSON(g, {
      style: {
        color: "#e11d48",
        weight: 1.5,
        fillOpacity: 0.15,
        fillColor: "#f97316",
      },
    });

    subzoneLayerGroup.addLayer(layer);
  });
}

function toArray(maybeArray) {
  if (Array.isArray(maybeArray)) return maybeArray;
  if (maybeArray == null) return [];
  return [maybeArray];
}
function allCreatePoints() {
  const pts = [];
  strokes.forEach((s) => {
    s.forEach((p) => pts.push(p));
  });
  currentStroke.forEach((p) => pts.push(p));
  return pts;
}

function latLngDistance(a, b) {
  if (!map) return Infinity;
  return map.distance(a, b);
}

function findNearestCoastVertex(latlng) {
  if (!map) return null;

  const lines = props.isGeoBorderMode ? geoBorderLines : coastlineLines;
  if (!lines || lines.length === 0) return null;

  let best = null;
  let bestDist = Infinity;

  lines.forEach((line, lineIdx) => {
    line.forEach((pt, ptIdx) => {
      const d = latLngDistance(latlng, pt);
      if (d < bestDist) {
        bestDist = d;
        best = { lineIdx, ptIdx, latlng: pt };
      }
    });
  });

  return best;
}

function chainEndpointsFromStrokes() {
  const pts = [];
  strokes.forEach((s) => {
    s.forEach((p) => pts.push(p));
  });
  if (pts.length === 0) return [];
  if (pts.length === 1) return [pts[0]];
  return [pts[0], pts[pts.length - 1]];
}

function snapToExistingEndpoints(latlng) {
  const candidates = chainEndpointsFromStrokes();
  if (candidates.length === 0) return latlng;

  let bestPoint = null;
  let bestDist = Infinity;

  candidates.forEach((pt) => {
    const d = latLngDistance(latlng, pt);
    if (d < bestDist) {
      bestDist = d;
      bestPoint = pt;
    }
  });

  if (bestPoint && bestDist <= SNAP_EPS_METERS) {
    return bestPoint;
  }
  return latlng;
}

function rebuildCreateLayers() {
  if (!map) return;

  if (createStrokeLayer) {
    map.removeLayer(createStrokeLayer);
    createStrokeLayer = null;
  }
  if (createPolygonLayer) {
    map.removeLayer(createPolygonLayer);
    createPolygonLayer = null;
  }

  const pts = allCreatePoints();
  if (pts.length < 2) {
    emit("create-updated", null);
    return;
  }

  createStrokeLayer = L.polyline(pts, {
    color: "#e11d48",
    weight: 2,
  });
  createStrokeLayer.addTo(map);

  const first = pts[0];
  const last = pts[pts.length - 1];
  const isClosed = latLngDistance(first, last) <= SNAP_EPS_METERS && pts.length >= 3;

  if (!isClosed) {
    emit("create-updated", null);
    return;
  }

  const ringLatLngs = [...pts];
  const ring = ringLatLngs.map((ll) => [ll.lng, ll.lat]);
  if (ring.length >= 3) {
    const firstCoord = ring[0];
    const lastCoord = ring[ring.length - 1];
    if (firstCoord[0] !== lastCoord[0] || firstCoord[1] !== lastCoord[1]) {
      ring.push([...firstCoord]);
    }
  }

  createPolygonLayer = L.polygon(ringLatLngs, {
    color: "#e11d48",
    weight: 2,
    fillOpacity: 0.25,
    fillColor: "#f97316",
  });
  createPolygonLayer.addTo(map);

  const geometry = {
    type: "Polygon",
    coordinates: [ring],
  };
  emit("create-updated", geometry);
}

function clearCreateDrawing() {
  strokes = [];
  currentStroke = [];
  isDrawing = false;
  if (createStrokeLayer && map) {
    map.removeLayer(createStrokeLayer);
    createStrokeLayer = null;
  }
  if (createPolygonLayer && map) {
    map.removeLayer(createPolygonLayer);
    createPolygonLayer = null;
  }
  if (map) {
    map.dragging.enable();
  }
  frontierStartRef = null;
}

function undoLastStroke() {
  // If a frontier start point was chosen but the segment not completed yet,
  // just cancel it without touching existing strokes.
  if (frontierStartRef) {
    frontierStartRef = null;
    return;
  }

  // If a stroke is currently being drawn, cancel it
  if (isDrawing) {
    isDrawing = false;
    currentStroke = [];
    if (map) {
      map.dragging.enable();
    }
    rebuildCreateLayers();
    return;
  }

  // Otherwise remove the last completed stroke, if any
  if (strokes.length > 0) {
    strokes.pop();
  }
  rebuildCreateLayers();
}

function handleMouseDown(e) {
  if (!props.isCreateMode || props.isFrontierMode || props.isGeoBorderMode) return;
  if (e.originalEvent && e.originalEvent.button !== 0) return;

  // Decide which end of the existing chain we want to continue from.
  // If the user clicks nearer to the "start" end, flip all strokes so that
  // this end becomes the logical end of the chain. This way, the bridge that
  // Leaflet draws (last point -> new stroke start) comes from the intended
  // endpoint (e.g. A) instead of always from the last-drawn endpoint (e.g. C).
  const endpoints = chainEndpointsFromStrokes();
  if (endpoints.length === 2) {
    const [startEnd, lastEnd] = endpoints;
    const distToStart = latLngDistance(e.latlng, startEnd);
    const distToLast = latLngDistance(e.latlng, lastEnd);

    if (distToStart < distToLast) {
      // User is closer to the start end: reverse all strokes so that this
      // end becomes the new "last" endpoint of the chain.
      strokes = strokes
        .slice()
        .reverse()
        .map((s) => s.slice().reverse());
    }
  }

  isDrawing = true;
  if (map) {
    map.dragging.disable();
  }

  const startPoint = snapToExistingEndpoints(e.latlng);
  currentStroke = [startPoint];
  rebuildCreateLayers();
}

function handleMouseMove(e) {
  if (!props.isCreateMode || props.isFrontierMode || props.isGeoBorderMode || !isDrawing) return;
  currentStroke.push(e.latlng);
  rebuildCreateLayers();
}

function handleMouseUp(e) {
  if (!isDrawing) return;
  isDrawing = false;
  if (map) {
    map.dragging.enable();
  }

  if (currentStroke.length > 1) {
    const endPoint = snapToExistingEndpoints(currentStroke[currentStroke.length - 1]);
    currentStroke[currentStroke.length - 1] = endPoint;
    strokes.push(currentStroke);
  }
  currentStroke = [];
  rebuildCreateLayers();
}

function handleMapClick(e) {
  if (!props.isCreateMode || (!props.isFrontierMode && !props.isGeoBorderMode)) return;
  if (!map) return;

  const nearest = findNearestCoastVertex(e.latlng);
  if (!nearest) return;

  if (!frontierStartRef) {
    frontierStartRef = nearest;
    return;
  }

  const start = frontierStartRef;
  frontierStartRef = null;

  if (start.lineIdx !== nearest.lineIdx) {
    // For now, require both points on the same coastline line
    console.warn("Frontier points are on different coastline segments; ignoring.");
    return;
  }

  const activeLines = props.isGeoBorderMode ? geoBorderLines : coastlineLines;
  if (!activeLines || activeLines.length === 0) return;

  const line = activeLines[start.lineIdx];
  const i1 = start.ptIdx;
  const i2 = nearest.ptIdx;

  if (i1 === i2) {
    return;
  }

  let segment;
  if (i1 < i2) {
    segment = line.slice(i1, i2 + 1);
  } else {
    segment = line.slice(i2, i1 + 1).reverse();
  }

  if (segment.length < 2) return;

  strokes.push(segment);
  rebuildCreateLayers();
}
async function loadGeoBorders() {
  if (!map) return;
  const filename = "/geojson/geoBoundaries-CAN-ADM1_simplified.geojson";

  try {
    const res = await fetch(filename);
    if (!res.ok) throw new Error(`File not found: ${filename}`);
    const data = await res.json();

    if (geoRegionsLayer) {
      map.removeLayer(geoRegionsLayer);
      geoRegionsLayer = null;
    }

    // Draw geopolitical regions as outlines
    geoRegionsLayer = L.geoJSON(data, {
      style: {
        color: "#666",
        weight: 2,
        fill: false,
      },
    }).addTo(map);

    // Build border lines from polygon rings
    geoBorderLines = [];
    const feats = Array.isArray(data.features) ? data.features : [];
    feats.forEach((f) => {
      const geom = f && f.geometry;
      if (!geom || !geom.type || !geom.coordinates) return;

      if (geom.type === "Polygon") {
        geom.coordinates.forEach((ring) => {
          let coords = ring;
          if (ring.length > 1) {
            const [firstLng, firstLat] = ring[0];
            const [lastLng, lastLat] = ring[ring.length - 1];
            if (firstLng === lastLng && firstLat === lastLat) {
              coords = ring.slice(0, -1);
            }
          }
          const line = coords.map(([lng, lat]) => L.latLng(lat, lng));
          geoBorderLines.push(line);
        });
      } else if (geom.type === "MultiPolygon") {
        geom.coordinates.forEach((poly) => {
          poly.forEach((ring) => {
            let coords = ring;
            if (ring.length > 1) {
              const [firstLng, firstLat] = ring[0];
              const [lastLng, lastLat] = ring[ring.length - 1];
              if (firstLng === lastLng && firstLat === lastLat) {
                coords = ring.slice(0, -1);
              }
            }
            const line = coords.map(([lng, lat]) => L.latLng(lat, lng));
            geoBorderLines.push(line);
          });
        });
      }
    });
  } catch (err) {
    console.warn("Error loading geopolitical borders:", err);
  }
}

onMounted(() => {
  map = L.map(mapEl.value).setView([52.9399, -73.5491], 5);

  baseTileLayer = L.tileLayer(
    "https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png",
    {
      attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
      subdomains: "abcd",
      maxZoom: 19,
    },
  ).addTo(map);

  subzoneLayerGroup = L.layerGroup().addTo(map);

  renderAllFeatures();

  map.on("mousedown", handleMouseDown);
  map.on("mousemove", handleMouseMove);
  map.on("mouseup", handleMouseUp);
  map.on("click", handleMapClick);

  // Load coastline data for frontier mode
  fetch("/geojson/ne_coastline.geojson")
    .then((res) => res.json())
    .then((data) => {
      if (isUnmounted || !map) return;
      try {
        const feats = Array.isArray(data.features) ? data.features : [];
        coastlineLines = [];
        feats.forEach((f) => {
          const geom = f && f.geometry;
          if (!geom || !geom.type || !geom.coordinates) return;

          if (geom.type === "LineString") {
            const line = geom.coordinates.map(([lng, lat]) => L.latLng(lat, lng));
            coastlineLines.push(line);
          } else if (geom.type === "MultiLineString") {
            geom.coordinates.forEach((coords) => {
              const line = coords.map(([lng, lat]) => L.latLng(lat, lng));
              coastlineLines.push(line);
            });
          }
        });
      } catch (err) {
        console.error("Error parsing coastline geojson", err);
      }
    })
    .catch((err) => {
      console.error("Failed to load coastline geojson", err);
    });
});

onBeforeUnmount(() => {
  isUnmounted = true;
  if (!map) return;

  try {
    map.off("mousedown", handleMouseDown);
    map.off("mousemove", handleMouseMove);
    map.off("mouseup", handleMouseUp);
    map.off("click", handleMapClick);
  } catch {
    // best-effort
  }

  try {
    map.remove();
  } catch {
    // best-effort
  }

  map = null;
  baseTileLayer = null;
  createStrokeLayer = null;
  createPolygonLayer = null;
  geoRegionsLayer = null;
  subzoneLayerGroup = null;
});

watch(
  () => props.isCreateMode,
  (newVal) => {
    if (!newVal) {
      clearCreateDrawing();
      emit("create-updated", null);
    }
  },
);

watch(
  () => props.resetCreateKey,
  () => {
    clearCreateDrawing();
    emit("create-updated", null);
  },
);

watch(
  () => props.undoCreateKey,
  () => {
    undoLastStroke();
  },
);

watch(
  () => props.isFrontierMode,
  (val) => {
    if (!val) {
      frontierStartRef = null;
    }
  },
);

watch(
  () => props.isGeoBorderMode,
  async (val) => {
    if (!val) {
      frontierStartRef = null;
      if (geoRegionsLayer && map) {
        map.removeLayer(geoRegionsLayer);
        geoRegionsLayer = null;
      }
      geoBorderLines = [];
      return;
    }
    await loadGeoBorders();
  },
);

watch(
  () => props.features,
  () => {
    renderAllFeatures();
  },
  { deep: true },
);

watch(
  () => props.subGeometries,
  (geoms) => {
    renderSubzones(geoms);
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
