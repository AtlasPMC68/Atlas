import { ref } from "vue";
import { getClosestAvailableYear } from "../utils/mapUtils.js";

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

  return {
    // State
    selectedYear,

    // Functions
    loadRegionsForYear,
  };
}
