import { ref } from 'vue';
import L from 'leaflet';
import { getClosestAvailableYear, debounce } from '../utils/mapUtils.js';
import { normalizeFeatures, getMapElementType } from '../utils/featureTypes.js';

export function useMapTimeline() {
  const selectedYear = ref(1740);
  let lastCurrentYear = null;
  let currentRegionsLayer = null;

  async function loadRegionsForYear(year, map, isFirstTime = false) {
    const closestYear = getClosestAvailableYear(year);

    if (isFirstTime) {
      lastCurrentYear = closestYear;
    } else {
      if (lastCurrentYear === closestYear) {
        return;
      }
    }

    lastCurrentYear = closestYear;
    const filename = `/geojson/world_${closestYear}.geojson`;

    try {
      const res = await fetch(filename);
      if (!res.ok) throw new Error("File not found: " + filename);

      const data = await res.json();

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
    } catch (err) {
      console.warn(err.message);
    }
  }

  async function fetchFeaturesAndRender(year, map, emit) {
    const mapId = "11111111-1111-1111-1111-111111111111";

    try {
      const res = await fetch(`${import.meta.env.VITE_API_URL}/maps/features/${mapId}`);
      if (!res.ok) throw new Error("Failed to fetch features");

      const allFeatures = await res.json();

      const normalized = normalizeFeatures(allFeatures);
      emit("features-loaded", normalized);

      const features = normalized.filter((f) => new Date(f.start_date).getFullYear() <= year);
      const cities = features.filter((f) => getMapElementType(f) === "point");
      const zones = features.filter((f) => getMapElementType(f) === "zone");
      const arrows = features.filter((f) => getMapElementType(f) === "arrow");

      return { cities, zones, arrows };
    } catch (err) {
      console.warn("Error fetching features:", err);
      return { cities: [], zones: [], arrows: [] };
    }
  }

  let isLoading = false;
  const debouncedUpdate = debounce(async (year, map, emit, renderFunctions) => {
    if (isLoading) return;
    isLoading = true;

    try {
      await loadRegionsForYear(year, map);
      const { cities, zones, arrows } = await fetchFeaturesAndRender(year, map, emit);

      renderFunctions.renderCities(cities, map);
      renderFunctions.renderZones(zones, map);
      renderFunctions.renderArrows(arrows, map);
    } catch (e) {
      console.warn("Error loading layers:", e);
    } finally {
      isLoading = false;
    }
  }, 100);

  return {
    // State
    selectedYear,

    // Functions
    loadRegionsForYear,
    fetchFeaturesAndRender,
    debouncedUpdate,
  };
}