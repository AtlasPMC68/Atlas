import { MapLayersService } from "../services/MapLayersService";
import type { MapLayersProps } from "../typescript/mapLayers";

export function useMapLayers(props: MapLayersProps) {
  const service = new MapLayersService(props);
  return service.getApi();
}
