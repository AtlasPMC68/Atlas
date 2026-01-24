import { ref } from 'vue';
import L from 'leaflet';
import { getClosestAvailableYear, debounce } from '../utils/mapUtils.js';

// Composable for managing map timeline and year-based layers
export function useMapTimeline() {
  const selectedYear = ref(1740); // initial displayed year
  let lastCurrentYear = null;
  let currentRegionsLayer = null;

  // Load GeoJSON file for specific year
  async function loadRegionsForYear(year, map, isFirstTime = false) {
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

    try {
      const res = await fetch(filename);
      if (!res.ok) throw new Error("File not found: " + filename);

      const data = await res.json();

      // Remove existing regions layer
      if (currentRegionsLayer) {
        map.removeLayer(currentRegionsLayer);
        currentRegionsLayer = null;
      }

      // Add new regions layer
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

  // Fetch features and render for specific year
  async function fetchFeaturesAndRender(year, map, emit) {
    const mapId = "11111111-1111-1111-1111-111111111111";

    try {
      const res = await fetch(`http://localhost:8000/maps/features/${mapId}`);
      if (!res.ok) throw new Error("Failed to fetch features");

      const allFeatures = await res.json();

      // Update features in parent
      emit("features-loaded", allFeatures);

      // Filter by year
      const features = allFeatures.filter(
        (f) => new Date(f.start_date).getFullYear() <= year
      );

      // Dispatch according to type
      const cities = features.filter((f) => f.type === "point");
      const zones = features.filter((f) => f.type === "zone");
      const arrows = features.filter((f) => f.type === "arrow");

      // These will be handled by the layers composable
      return { cities, zones, arrows };
    } catch (err) {
      console.warn("Error fetching features:", err);
      return { cities: [], zones: [], arrows: [] };
    }
  }

  // Load all layers for a specific year
  let isLoading = false;
  const debouncedUpdate = debounce(async (year, map, emit, renderFunctions) => {
    if (isLoading) return;
    isLoading = true;

    try {
      await loadRegionsForYear(year, map);
      const { cities, zones, arrows } = await fetchFeaturesAndRender(year, map, emit);

      // Render features using provided functions
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