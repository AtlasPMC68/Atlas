import "@geoman-io/leaflet-geoman-free";
import "@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css";
import { MapDrawingService } from "../services/MapDrawingService";
import type { MapDrawingEmitFn } from "../typescript/mapDrawing";

export function useMapDrawing(emit: MapDrawingEmitFn) {
  const service = new MapDrawingService(emit);
  return service.createDrawingTools();
}
