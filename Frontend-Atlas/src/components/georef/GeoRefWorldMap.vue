<template>
  <div class="relative w-full h-full">
    <div ref="mapContainer" class="w-full h-full bg-[#cfe8ff]"></div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref, watch } from "vue";
import L from "leaflet";
import type {
  WorldBounds,
  WorldMapPoint,
  MatchedWorldPointSummary,
} from "../../typescript/georef";

// The reference side of a control-point modal: the real coastline, the points
// to match (SIFT keypoints or gazetteer cities), and which are matched already.
const props = withDefaults(
  defineProps<{
    worldBounds: WorldBounds | null;
    points: WorldMapPoint[];
    activeIndex: number;
    // The points already matched, by index into `points`.
    matchedPoints: MatchedWorldPointSummary[];
    // Points from another step, shown greyed for context and not clickable
    contextPoints?: WorldMapPoint[];
    usedLakes?: boolean;
    // Each circle carries its number (index + 1), the number the image side
    // shows for its match: SIFT keypoints. Cities are told apart by their name.
    numbered?: boolean;
  }>(),
  {
    worldBounds: null,
    points: () => [],
    activeIndex: 0,
    matchedPoints: () => [],
    contextPoints: () => [],
    usedLakes: false,
    numbered: false,
  },
);

const emit = defineEmits<{
  (e: "select-point", index: number): void;
}>();

const mapContainer = ref<HTMLDivElement | null>(null);
let map: L.Map | null = null;
let landLayer: L.GeoJSON | null = null;
let markers: L.Layer[] = [];

function clearMarkers(): void {
  if (!map || !markers.length) return;
  const currentMap = map;
  markers.forEach((m) => currentMap.removeLayer(m));
  markers = [];
}

// Every point is a circle: red while it is the one being placed, pale blue
// until it is matched, blue once matched, green for a check point. The image
// map draws the matches the same way. Numbered (SIFT) points carry their number,
// the one the image side shows for their match; cities carry their name instead.
function pointIcon(
  isActive: boolean,
  match: MatchedWorldPointSummary | undefined,
  number: number | null,
): L.DivIcon {
  const size = number === null ? (isActive ? 16 : 12) : isActive ? 24 : 20;
  let tone = "bg-blue-200 text-blue-800 ring-1 ring-blue-600";
  if (isActive) tone = "bg-red-600 text-white ring-2 ring-white";
  else if (match?.check) tone = "bg-green-600 text-white ring-2 ring-white";
  else if (match) tone = "bg-blue-600 text-white ring-2 ring-white";
  const text = isActive ? "text-[10px]" : "text-[9px]";
  return L.divIcon({
    className: "",
    html: `<span class="flex items-center justify-center rounded-full font-bold shadow ${tone} ${text}" style="width:${size}px;height:${size}px">${number ?? ""}</span>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

function renderPoints(): void {
  if (!map) return;
  const currentMap = map;
  clearMarkers();

  props.contextPoints.forEach((pt) => {
    const marker = L.circleMarker([pt.lat, pt.lng], {
      radius: 3,
      fillColor: "#9ca3af",
      color: "#6b7280",
      weight: 1,
      opacity: 0.8,
      fillOpacity: 0.6,
      interactive: false,
    });
    marker.addTo(currentMap);
    markers.push(marker);
  });

  props.points.forEach((pt, index) => {
    const { lat, lng } = pt;
    if (typeof lat !== "number" || typeof lng !== "number") return;

    const isActive = index === props.activeIndex;

    const match = props.matchedPoints.find((m) => m.index === index);
    const marker = L.marker([lat, lng], {
      icon: pointIcon(isActive, match, props.numbered ? index + 1 : null),
      zIndexOffset: isActive ? 1000 : 0,
    });

    if (pt.label) {
      marker.bindTooltip(pt.label, {
        permanent: true,
        direction: "right",
        offset: [6, 0],
        className: "text-xs",
      });
    }

    // Allow user to choose the current point by clicking a marker
    marker.on("click", () => {
      emit("select-point", index);
    });

    marker.addTo(currentMap);
    markers.push(marker);
  });
}

function updateActiveMarker(): void {
  // Re-render everything so every circle reflects the current active index.
  renderPoints();
}

async function initMap(): Promise<void> {
  if (!mapContainer.value || map) return;

  map = L.map(mapContainer.value, {
    maxBoundsViscosity: 1.0,
  }).setView([20, 0], 2);

  try {
    // Load coastline, plus lakes when they were used for SIFT detection
    const geojsonFiles = props.usedLakes
      ? ["/geojson/ne_coastline.geojson", "/geojson/ne_50m_lakes.geojson"]
      : ["/geojson/ne_coastline.geojson"];

    const responses = await Promise.all(
      geojsonFiles.map(file => fetch(file))
    );

    for (const res of responses) {
      if (!res.ok) throw new Error(`Failed to load geojson : ${res.status}`);
    }

    const geojsonData = await Promise.all(
      responses.map(res => res.json())
    );

    // Combine all features
    const combinedGeoJSON: GeoJSON.FeatureCollection = {
      type: "FeatureCollection",
      features: geojsonData.flatMap((data: any) => data.features || []),
    };

    landLayer = L.geoJSON(combinedGeoJSON, {
      style: {
        fillColor: "#e5e7eb",
        fillOpacity: 0.9,
        color: "#9ca3af",
        weight: 1,
        opacity: 1,
      },
    }).addTo(map);

    const bounds = landLayer.getBounds();
    if (bounds.isValid()) {
      const padded = bounds.pad(0.05);
      map.setMaxBounds(padded);
    }
  } catch (e) {
    console.error("Failed to load Natural Earth land basemap", e);
  }

  if (props.worldBounds) {
    const { west, south, east, north } = props.worldBounds;
    const b = L.latLngBounds([south, west], [north, east]);
    if (b.isValid()) {
      const padded = b.pad(0.05);
      map.fitBounds(padded, { padding: [10, 10] });
      map.setMaxBounds(padded);
    }
  }

  renderPoints();
}

onMounted(async () => {
  await initMap();
});

onBeforeUnmount(() => {
  if (map) {
    clearMarkers();
    if (landLayer) {
      map.removeLayer(landLayer);
      landLayer = null;
    }
    map.remove();
    map = null;
  }
});

watch(
  () => [props.points, props.contextPoints],
  () => {
    renderPoints();
  },
  { deep: true },
);

watch(
  () => props.activeIndex,
  () => {
    updateActiveMarker();
  },
);

watch(
  () => props.matchedPoints,
  () => {
    renderPoints();
  },
  { deep: true },
);

watch(
  () => props.worldBounds,
  (bounds: WorldBounds | null) => {
    if (!map || !bounds) return;
    const { west, south, east, north } = bounds;
    const b = L.latLngBounds([south, west], [north, east]);
    if (b.isValid()) {
      const padded = b.pad(0.05);
      map.fitBounds(padded, { padding: [10, 10] });
      map.setMaxBounds(padded);
    }
  },
  { deep: true },
);
</script>
