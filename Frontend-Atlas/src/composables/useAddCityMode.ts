import type { Ref } from "vue";
import type L from "leaflet";
import type { Feature } from "../typescript/feature";
import { AddCityModeService } from "../services/AddCityModeService";
export type { PendingCity } from "../typescript/addCityMode";

export function useAddCityMode({
  getMap,
  selectedYear,
  localFeaturesSnapshot,
  cityInput,
  onCreated,
  onAfterCreate,
}: {
  getMap: () => L.Map | null;
  selectedYear: Ref<number>;
  localFeaturesSnapshot: Ref<Feature[]>;
  cityInput: Ref<HTMLInputElement | null>;
  onCreated: (features: Feature[]) => void;
  onAfterCreate: () => void;
}) {
  const service = new AddCityModeService(
    getMap,
    selectedYear,
    localFeaturesSnapshot,
    cityInput,
    onCreated,
    onAfterCreate,
  );
  return service.createTools();
}
