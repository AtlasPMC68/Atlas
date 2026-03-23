import type { Ref } from "vue";
import type L from "leaflet";
import { Feature } from "./feature";

export type MapLayersProps = {
  featureVisibility: Ref<Map<string | number, boolean>>;
};

export type FeatureLayer = L.Layer & {
  options?: L.LayerOptions & {
    interactive?: boolean;
    bubblingMouseEvents?: boolean;
  };
  __atlasOnDown?: L.LeafletEventHandlerFn;
  __atlasOnPointerDown?: L.LeafletEventHandlerFn;
  __atlasOnClick?: L.LeafletEventHandlerFn;
  arrowheads?: (options: Record<string, unknown>) => void;
};

export type RadiusAdjustable = {
  setRadius: (radius: number) => void;
};

export type MapWithPm = L.Map & {
  pm?: {
    globalEditModeEnabled?: () => boolean;
    globalDragModeEnabled?: () => boolean;
    globalRemovalModeEnabled?: () => boolean;
  };
};

export type LeafletPointerEvent = L.LeafletEvent & {
  originalEvent?: Event;
};

export type LayerWithFeature<TFeature> = L.Layer & {
  feature?: TFeature;
  eachLayer?: (fn: (layer: L.Layer) => void) => void;
};

export type LayerWithFeatureRuntime = LayerWithFeature<Feature> & {
  _tmpFeatureId?: string;
};
