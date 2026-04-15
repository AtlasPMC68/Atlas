import L from "leaflet";
import { ref, nextTick } from "vue";
import type { Ref } from "vue";
import type { Feature } from "../typescript/feature";
import type { MapWithPm } from "../typescript/mapDrawing";
import type { PendingCity } from "../typescript/addCityMode";
import { upsertFeature } from "../utils/featureHelpers";

export class AddCityModeService {
  public addCityMode = ref(false);
  public pendingCity = ref<PendingCity | null>(null);
  public cityInputName = ref("");

  constructor(
    private getMap: () => L.Map | null,
    private selectedYear: Ref<number>,
    private localFeaturesSnapshot: Ref<Feature[]>,
    private cityInput: Ref<HTMLInputElement | null>,
    private onCreated: (features: Feature[]) => void,
    private onAfterCreate: () => void,
  ) {}

  private resetState() {
    this.pendingCity.value = null;
    this.cityInputName.value = "";
    this.addCityMode.value = false;
    const map = this.getMap();
    if (map) map.getContainer().style.cursor = "";
    (map as MapWithPm)?.pm?.Toolbar?.toggleButton?.("addCity", false);
  }

  cancel() {
    if (this.pendingCity.value) {
      this.pendingCity.value.marker.remove();
    }
    this.resetState();
  }

  confirm() {
    const map = this.getMap();
    if (!this.pendingCity.value || !map) return;
    const name = this.cityInputName.value.trim();
    const { latlng, marker } = this.pendingCity.value;
    marker.remove();
    this.resetState();
    const now = new Date().toISOString();
    const id = `tmp_${Math.random().toString(36).slice(2, 9)}`;
    const feature: Feature = {
      id,
      type: "Feature",
      mapId: "",
      geometry: {
        type: "Point",
        coordinates: [latlng.lng, latlng.lat] as [number, number],
      },
      properties: {
        name,
        labelText: "",
        colorName: "black",
        colorRgb: [0, 0, 0] as [number, number, number],
        strokeColor: [0, 0, 0] as [number, number, number],
        opacity: 1,
        strokeWidth: 1,
        strokeOpacity: 1,
        mapElementType: "point",
        startDate: `${this.selectedYear.value}-01-01`,
        endDate: `${this.selectedYear.value}-12-31`,
      },
      createdAt: now,
      updatedAt: now,
      name,
      opacity: 1,
      strokeWidth: 1,
    };
    const next = upsertFeature(this.localFeaturesSnapshot.value, feature);
    this.localFeaturesSnapshot.value = next;
    this.onAfterCreate();
    this.onCreated(next);
  }

  start() {
    this.addCityMode.value = true;
    const map = this.getMap();
    if (map) map.getContainer().style.cursor = "crosshair";
  }

  handleMapClick(latlng: L.LatLng) {
    const map = this.getMap();
    if (!map) return;
    if (this.pendingCity.value) {
      this.pendingCity.value.marker.remove();
    }
    const marker: L.CircleMarker = L.circleMarker(latlng, {
      radius: 6,
      fillColor: "#000000",
      color: "#000000",
      weight: 1,
      opacity: 1,
      fillOpacity: 1,
      interactive: false,
    }).addTo(map);
    const containerPos = map.latLngToContainerPoint(latlng);
    this.pendingCity.value = {
      latlng,
      screenPos: { x: containerPos.x + 12, y: containerPos.y - 40 },
      marker,
    };
    this.cityInputName.value = "";
    nextTick(() => this.cityInput.value?.focus());
  }

  createTools() {
    return {
      addCityMode: this.addCityMode,
      pendingCity: this.pendingCity,
      cityInputName: this.cityInputName,
      cancel: this.cancel.bind(this),
      confirm: this.confirm.bind(this),
      start: this.start.bind(this),
      handleMapClick: this.handleMapClick.bind(this),
    };
  }
}
