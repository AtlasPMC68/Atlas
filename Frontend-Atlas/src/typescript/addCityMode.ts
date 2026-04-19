import type L from "leaflet";

export interface PendingCity {
  latlng: L.LatLng;
  screenPos: { x: number; y: number };
  marker: L.CircleMarker;
}
