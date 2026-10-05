import type { Ref } from "vue";
import type L from "leaflet";
import type { Feature } from "../typescript/feature";
import { ShapeScalingService } from "../services/ShapeScalingService";

export function useShapeScaling({
  getMap,
  getLayerById,
  localFeaturesSnapshot,
  getProjectId,
  getSelectedYear,
  onBeforeEmit,
  onUpdate,
}: {
  getMap: () => L.Map | null;
  getLayerById: (id: string) => L.Layer | undefined;
  localFeaturesSnapshot: Ref<Feature[]>;
  getProjectId: () => string;
  getSelectedYear: () => number;
  onBeforeEmit: () => void;
  onUpdate: (features: Feature[]) => void;
}) {
  const service = new ShapeScalingService(
    getMap,
    getLayerById,
    localFeaturesSnapshot,
    getProjectId,
    getSelectedYear,
    onBeforeEmit,
    onUpdate,
  );
  return service.createTools();
}
