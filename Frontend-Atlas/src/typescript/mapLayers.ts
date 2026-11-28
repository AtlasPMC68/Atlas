import type L from "leaflet";
import type { Feature } from "./feature";

export type LayerWithFeature<TFeature> = L.Layer & {
  feature?: TFeature;
  eachLayer?: (fn: (layer: L.Layer) => void) => void;
};

export type LayerWithFeatureRuntime = LayerWithFeature<Feature> & {
  _tmpFeatureId?: string;
};

export type AtlasRuntimeLayer = LayerWithFeatureRuntime & {
  __atlasFeatureEventsBound?: boolean;
  __atlasApplyingSync?: boolean;
};
