import type { Ref } from "vue";
import type L from "leaflet";
import type { Feature } from "../typescript/feature";
import { ImageOverlayService } from "../services/ImageOverlayService";

export function useImageOverlay({
  getMap,
  getLayerById,
  localFeaturesSnapshot,
  onBeforeEmit,
  onUpdate,
}: {
  getMap: () => L.Map | null;
  getLayerById: (id: string) => L.Layer | undefined;
  localFeaturesSnapshot: Ref<Feature[]>;
  onBeforeEmit: () => void;
  onUpdate: (features: Feature[]) => void;
}) {
  const service = new ImageOverlayService(
    getMap,
    getLayerById,
    localFeaturesSnapshot,
    onBeforeEmit,
    onUpdate,
  );
  return service.createTools();
}
