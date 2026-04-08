import "@geoman-io/leaflet-geoman-free";
import "@geoman-io/leaflet-geoman-free/dist/leaflet-geoman.css";
import { MapDrawingService } from "../services/MapDrawingService";
import type { EmitFn } from "../typescript/mapDrawing";

export function useMapDrawing(
  emit: EmitFn,
  getProjectId: () => string,
) {
  const service = new MapDrawingService(emit, getProjectId);
  return service.createDrawingTools();
}
