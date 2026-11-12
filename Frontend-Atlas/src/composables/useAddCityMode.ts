import type { Ref } from "vue";
import type L from "leaflet";
import type { Feature } from "../typescript/feature";
import { AddCityModeService } from "../services/AddCityModeService";
export type { PendingCity } from "../typescript/addCityMode";

export function useAddCityMode({
  getMap,
  localFeaturesSnapshot,
  cityInput,
  onCreated,
  onAfterCreate,
  getProjectId,
}: {
  getMap: () => L.Map | null;
  localFeaturesSnapshot: Ref<Feature[]>;
  cityInput: Ref<HTMLInputElement | null>;
  onCreated: (features: Feature[]) => void;
  onAfterCreate: () => void;
  getProjectId: () => string;
}) {
  const service = new AddCityModeService(
    getMap,
    localFeaturesSnapshot,
    cityInput,
    onCreated,
    onAfterCreate,
    getProjectId,
  );
  return service.createTools();
}
