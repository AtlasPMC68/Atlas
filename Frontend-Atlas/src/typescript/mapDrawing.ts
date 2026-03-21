import type L from "leaflet";
import type { Feature } from "./feature";

export const drawingModes = {
  marker: "marker",
  polyline: "polyline",
  polygon: "polygon",
  rectangle: "rectangle",
  circle: "circle",
  freehand: "freehand",
} as const;

export type DrawingMode =
  | (typeof drawingModes)[keyof typeof drawingModes]
  | null;

export type DrawingEmitArgs =
  | [event: "feature-created", payload: Feature]
  | [event: "feature-updated", payload: Feature]
  | [event: "feature-deleted", payload: string];

export type EmitFn = (...args: DrawingEmitArgs) => void;

export type PmToolbar = {
  createCustomControl?: (options: {
    name: string;
    block: string;
    title: string;
    className: string;
    toggle: boolean;
    disableOtherButtons: boolean;
    disableByOtherButtons: boolean;
    actions: string[];
    onClick: () => void;
    afterClick: (
      event: unknown,
      context: { button: { toggled: () => boolean } },
    ) => void;
  }) => void;
  controlExists?: (name: string) => boolean;
  changeControlOrder?: () => void;
};

export type PmMapDrawingTool = {
  addControls: (options: Record<string, unknown>) => void;
  disableDraw: () => void;
  enableDraw: (shape: string, options?: Record<string, unknown>) => void;
  globalRemovalModeEnabled?: () => boolean;
  enableGlobalLassoMode?: (options: Record<string, unknown>) => void;
  disableGlobalLassoMode?: () => void;
  Toolbar?: PmToolbar;
};

export type MapWithPm = L.Map & {
  pm?: PmMapDrawingTool;
};

export type PmLayerEvent = {
  layer: L.Layer;
};

export type PmCutEvent = {
  originalLayer?: L.Layer;
  layer?: L.Layer;
};

export type PmRemovalToggleEvent = {
  enabled: boolean;
};

export type PmLassoSelectEvent = {
  selectedLayers?: L.Layer[];
};

export type PmDrawStartEvent = {
  shape: string;
};

export type MouseDrawListeners = {
  onMouseDown?: (event: L.LeafletMouseEvent) => void;
  onMouseMove?: (event: L.LeafletMouseEvent) => void;
  onMouseUp?: () => void;
};

export type FeatureBearingLayer = L.Layer & {
  feature?: Feature;
};
