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

export type EmitFn = (event: string, ...args: unknown[]) => void;

export type TextMarkerLayer = L.Marker & {
  options: L.MarkerOptions & {
    text?: string;
    textMarker?: boolean;
  };
  pm?: {
    getText?: () => string;
  };
};

export type PmCustomControlOptions = {
  name: string;
  block: "draw" | "edit" | "custom" | "options";
  title: string;
  className: string;
  toggle?: boolean;
  disableOtherButtons?: boolean;
  disableByOtherButtons?: boolean;
  actions?: string[];
  onClick?: () => void;
  afterClick?: (
    event: unknown,
    context: { button: { toggled: () => boolean } },
  ) => void;
};

export type PmToolbar = {
  createCustomControl?: (options: PmCustomControlOptions) => void;
  controlExists?: (name: string) => boolean;
  changeControlOrder?: (order?: string[]) => void;
  setBlockPosition?: (
    block: "draw" | "edit" | "custom" | "options",
    position: "topleft" | "topright" | "bottomleft" | "bottomright",
  ) => void;
};

export type PmMapDrawingTool = {
  addControls: (options: Record<string, unknown>) => void;
  disableDraw: () => void;
  enableDraw: (shape: string, options?: Record<string, unknown>) => void;
  globalRemovalModeEnabled?: () => boolean;
  enableGlobalLassoMode?: (options: Record<string, unknown>) => void;
  disableGlobalLassoMode?: () => void;
  globalRotateModeEnabled?: () => boolean;
  enableGlobalRotateMode?: () => void;
  disableGlobalRotateMode?: () => void;
  Toolbar?: PmToolbar;
};

export type MapWithPm = L.Map & {
  pm?: PmMapDrawingTool;
};

export type PmLayerEvent = {
  shape?: string;
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

export type TextCapableMarker = L.Marker & {
  options: L.MarkerOptions & {
    text?: string;
    textMarker?: boolean;
    className?: string;
  };
  pm?: {
    getText?: () => string;
  };
  getText?: () => string;
  _text?: string;
};

export type MarkerIconLike = {
  options?: {
    className?: string;
    html?: string | HTMLElement;
  };
};
