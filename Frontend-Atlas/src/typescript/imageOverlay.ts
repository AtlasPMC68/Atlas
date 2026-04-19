import type L from "leaflet";

export interface ImageInteractionState {
  overlay: L.ImageOverlay;
  featureId: string;
  resizeMarker: L.Marker;
  aspectRatio: number; // pixel width / pixel height at attach time
  cleanupDrag?: () => void;
}
