import { ref } from "vue";
import L from "leaflet";
import { getClosestAvailableYear } from "../utils/mapUtils";

const regionsLayerOptions = {
  style: {
    color: "#444",
    weight: 2,
    fill: false,
  },
  onEachFeature: (feature: any, layer: any) => {
    if (layer?.pm?.setOptions) {
      layer.pm.setOptions({ pmIgnore: true });
    }
    layer.bindPopup(feature?.properties?.name || "Unnamed");
  },
} as const;

function createRegionsLayer(map: L.Map, data: any): L.GeoJSON {
  return L.geoJSON(data, regionsLayerOptions).addTo(map);
}

class MapTimeline {
  public selectedYear = ref(1740);
  private lastCurrentYear: number | null = null;
  private currentRegionsLayer: L.GeoJSON | null = null;

  async loadRegionsForYear(
    year: number,
    map: L.Map,
    isFirstTime = false,
  ): Promise<void> {
    const closestYear = getClosestAvailableYear(year);

    if (!isFirstTime && this.lastCurrentYear === closestYear) {
      return;
    }

    this.lastCurrentYear = closestYear;
    const filename = `/geojson/world_${closestYear}.geojson`;

    try {
      const res = await fetch(filename);
      if (!res.ok) throw new Error("File not found: " + filename);

      const data = await res.json();

      if (this.currentRegionsLayer) {
        map.removeLayer(this.currentRegionsLayer);
        this.currentRegionsLayer = null;
      }

      this.currentRegionsLayer = createRegionsLayer(map, data);
    } catch (err) {
      if (err instanceof Error) {
        console.warn(err.message);
      } else {
        console.warn("Failed to load regions");
      }
    }
  }
}

export function useMapTimeline() {
  return new MapTimeline();
}
