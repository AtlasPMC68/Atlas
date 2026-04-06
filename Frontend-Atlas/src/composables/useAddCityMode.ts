import L from "leaflet";
import { ref, nextTick } from "vue";
import type { Ref } from "vue";
import type { Feature } from "../typescript/feature";
import type { MapWithPm } from "../typescript/mapDrawing";

export interface PendingCity {
  latlng: L.LatLng;
  screenPos: { x: number; y: number };
  marker: L.CircleMarker;
}

function upsertFeature(features: Feature[], feature: Feature): Feature[] {
  const next = [...features];
  const index = next.findIndex((f) => f.id === feature.id);
  if (index >= 0) { next[index] = feature; return next; }
  next.push(feature);
  return next;
}

export function useAddCityMode({
  getMap,
  selectedYear,
  localFeaturesSnapshot,
  cityInput,
  onCreated,
  onAfterCreate,
}: {
  getMap: () => L.Map | null;
  selectedYear: Ref<number>;
  localFeaturesSnapshot: Ref<Feature[]>;
  cityInput: Ref<HTMLInputElement | null>;
  onCreated: (features: Feature[]) => void;
  onAfterCreate: () => void;
}) {
  const addCityMode = ref(false);
  const pendingCity = ref<PendingCity | null>(null);
  const cityInputName = ref('');

  function resetState() {
    pendingCity.value = null;
    cityInputName.value = '';
    addCityMode.value = false;
    const map = getMap();
    if (map) map.getContainer().style.cursor = '';
    (map as MapWithPm)?.pm?.Toolbar?.toggleButton?.('addCity', false);
  }

  function cancel() {
    if (pendingCity.value) {
      pendingCity.value.marker.remove();
    }
    resetState();
  }

  function confirm() {
    const map = getMap();
    if (!pendingCity.value || !map) return;
    const name = cityInputName.value.trim();
    const { latlng, marker } = pendingCity.value;
    marker.remove();
    resetState();
    const now = new Date().toISOString();
    const id = `tmp_${Math.random().toString(36).slice(2, 9)}`;
    const feature: Feature = {
      id,
      type: 'Feature',
      mapId: '',
      geometry: { type: 'Point', coordinates: [latlng.lng, latlng.lat] as [number, number] },
      properties: {
        name,
        labelText: '',
        colorName: 'black',
        colorRgb: [0, 0, 0] as [number, number, number],
        strokeColor: [0, 0, 0] as [number, number, number],
        opacity: 1,
        strokeWidth: 1,
        strokeOpacity: 1,
        mapElementType: 'point',
        startDate: `${selectedYear.value}-01-01`,
        endDate: `${selectedYear.value}-12-31`,
      },
      createdAt: now,
      updatedAt: now,
      name,
      opacity: 1,
      strokeWidth: 1,
    };
    const next = upsertFeature(localFeaturesSnapshot.value, feature);
    localFeaturesSnapshot.value = next;
    onAfterCreate();
    onCreated(next);
  }

  function start() {
    addCityMode.value = true;
    const map = getMap();
    if (map) map.getContainer().style.cursor = 'crosshair';
  }

  function handleMapClick(latlng: L.LatLng) {
    const map = getMap();
    if (!map) return;
    if (pendingCity.value) {
      pendingCity.value.marker.remove();
    }
    const marker: L.CircleMarker = L.circleMarker(latlng, {
      radius: 6,
      fillColor: '#000000',
      color: '#000000',
      weight: 1,
      opacity: 1,
      fillOpacity: 1,
      interactive: false,
    }).addTo(map);
    const containerPos = map.latLngToContainerPoint(latlng);
    pendingCity.value = {
      latlng,
      screenPos: { x: containerPos.x + 12, y: containerPos.y - 40 },
      marker,
    };
    cityInputName.value = '';
    nextTick(() => cityInput.value?.focus());
  }

  return {
    addCityMode,
    pendingCity,
    cityInputName,
    cancel,
    confirm,
    start,
    handleMapClick,
  };
}
