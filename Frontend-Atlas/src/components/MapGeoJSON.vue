<template>
  <div class="relative h-full w-full z-0 bg-[#d4dadc]">
    <!-- Hidden (not display:none, Leaflet still needs its size) until the first
         framing, so the map doesn't flash the default location before jumping.
         The class is toggled on a wrapper: Leaflet adds its own classes to #map
         (leaflet-container, ...), and Vue would wipe them when re-rendering a
         bound class there, which un-clips the canvas over the sidebar. -->
    <div class="h-full w-full" :class="{ invisible: !isViewReady }">
      <div id="map" class="h-full w-full bg-[#d4dadc]"></div>
    </div>
    <div
      v-if="!isViewReady"
      class="absolute inset-0 flex items-center justify-center"
    >
      <span class="loading loading-spinner loading-lg text-base-content/40"></span>
    </div>
    <div
      v-if="pendingCity"
      class="city-name-input-container"
      :style="{ left: pendingCity.screenPos.x + 'px', top: pendingCity.screenPos.y + 'px' }"
    >
      <input
        ref="cityInput"
        v-model="cityInputName"
        class="city-name-input"
        placeholder="Nom de la ville"
        @keydown.enter.prevent="confirmCity"
        @keydown.escape.prevent="cancelAddCity"
        @blur="confirmCity"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  onMounted,
  onBeforeUnmount,
  watch,
  ref,
  computed,
  nextTick,
} from "vue";
import L from "leaflet";
import "leaflet-geometryutil";
import "leaflet-arrowheads";
import { useMapDrawing } from "../composables/useMapDrawing";
import { useAddCityMode } from "../composables/useAddCityMode";
import { useImageOverlay } from "../composables/useImageOverlay";
import { useShapeScaling } from "../composables/useShapeScaling";
import { colorRgbToCss, getMapElementType, upsertFeature, getDefaultLayer } from "../utils/featureHelpers";
import {
  extractFeatureFromLayer,
  syncFeaturesFromLayerMap,
} from "../utils/mapDrawingFeature";
import {
  attachFeatureToLayer,
  bindRenderedFeatureEvents,
  applyStyleToLayer,
  getLayerStrokeColor,
  getLayerPathOptions,
} from "../utils/mapLayersFeature";
import {
  forEachLeafLayer,
  enablePerFeatureDrag,
  disablePerFeatureDrag,
  enablePixelSpaceDrag,
} from "../utils/mapDragUtils";
import { toArray, toImageSrc } from "../utils/utils";
import { createCartoTileLayer } from "../utils/basemap";
import {
  getLabelPresentation,
  MAP_POINT_MARKER_RADIUS_PX,
  STYLE_POINT_SWATCH_PX,
  mapPointSwatchSvg,
  type LabelPresentationModel,
} from "../utils/labelPresentation";
import { updateMapLabelVisibility } from "../services/MapLabelVisibilityService";
import {
  applySelectionModifier,
  deduplicateFeatures,
  doesLayerIntersectBounds,
} from "../utils/selectionUtils";
import { applySmartFeatureFraming } from "../utils/mapFraming";
import { createFeatureDoubleClickHandler } from "../utils/featureInteraction";
import type {
  Feature,
  FeatureId,
} from "../typescript/feature";
import type { AtlasRuntimeLayer } from "../typescript/mapLayers";
import type { MapWithPm, PmIgnoreOptions } from "../typescript/mapDrawing";

const props = defineProps<{
  features: Feature[];
  featureVisibility: Map<string, boolean>;
  projectId: string;
  selectedYear: number;
  canUndo: boolean;
  canRedo: boolean;
  selectedFeatureId?: string | null;
  multiSelectedFeatureIds?: string[];
}>();

const emit = defineEmits<{
  (e: "draw-create", features: Feature[]): void;
  (e: "draw-update", features: Feature[]): void;
  (e: "draw-delete", features: Feature[]): void; // Delete the Leaflet layer (unsaved feature)
  (e: "map-ready", map: L.Map): void;
  (e: "undo"): void;
  (e: "redo"): void;
  (e: "edit-feature-request", feature: Feature): void;
  (e: "select-feature", featureId: string | null): void;
  (e: "select-features", featureIds: string[]): void;
  (e: "move-selected", dx: number, dy: number): void;
  (e: "select-all"): void;
  (e: "duplicate-feature", feature: Feature): void;
  (e: "delete-feature", feature: Feature): void;
}>();

const previousFeatureIds = ref(new Set<FeatureId>());
const localFeaturesSnapshot = ref<Feature[]>([]);

let map: L.Map | null = null;
let vectorRenderer: L.Canvas | null = null;
// Set while the selection watcher turns edit/rotate mode off itself: it sets
// up the newly selected zone, so the mode-toggle handlers must not.
let leavingModesForSelectionChange = false;
// When the map itself is the source of a change (drag, edit, image move), we
// emit "draw-update" which propagates back down via props.features. This flag
// tells the props watcher to skip the re-render for that one echo update so we
// don't destroy and re-create the layer the user is actively interacting with.
let featurePropRenderHolds = 0;
let featurePropRenderHoldTimer: ReturnType<typeof setTimeout> | null = null;
const FEATURE_PROP_RENDER_HOLD_MS = 2500;

function scheduleFeaturePropRenderHoldTimeout() {
  if (featurePropRenderHoldTimer) clearTimeout(featurePropRenderHoldTimer);
  featurePropRenderHoldTimer = setTimeout(() => {
    featurePropRenderHoldTimer = null;
    if (featurePropRenderHolds <= 0) return;
    featurePropRenderHolds -= 1;
    if (featurePropRenderHolds > 0) scheduleFeaturePropRenderHoldTimeout();
  }, FEATURE_PROP_RENDER_HOLD_MS);
}

function holdFeaturePropRenders() {
  featurePropRenderHolds += 1;
  scheduleFeaturePropRenderHoldTimeout();
}
let blockNextMapClick = false;

// ---- Right-click drag panning ----
let didRightDrag = false;
let lastRightPos = { x: 0, y: 0 };
let rightDragCleanup: (() => void) | null = null;

// ---- Right-click rectangle multi-selection ----
let isRightSelectDragging = false;
let rightSelectStart: L.LatLng | null = null;
let rightSelectRect: L.Rectangle | null = null;
// IDs of features currently selected via box-selection (multi-select)
const multiSelectedIds = ref<Set<string>>(new Set<string>());
// A vertex that snaps onto another element is released away from the cursor,
// so the click that follows the drag lands on the map or on that other element
// instead of the dragged handle. Left alone it changes the selection, which
// ends edit mode in the middle of the edit. Clicks are ignored for a moment
// after every edit gesture.
const POST_EDIT_CLICK_GUARD_MS = 350;
let ignoreClicksUntil = 0;

function startPostEditClickGuard() {
  ignoreClicksUntil = Date.now() + POST_EDIT_CLICK_GUARD_MS;
}

function isPostEditClick(): boolean {
  return Date.now() < ignoreClicksUntil;
}
let labelVisibilityFrame: number | null = null;
const selectedLayersOriginalStyles = new Map<L.Layer, L.PathOptions>();
let selectedCityRing: L.Marker | null = null;
let selectedFeatureQuickActionsMarker: L.Marker | null = null;
let quickActionsCleanup: (() => void) | null = null;
let pixelSpaceDragCleanup: (() => void) | null = null;
let containerClickListener: ((e: MouseEvent) => void) | null = null;
let lastMapAnchorId: string | null = null;

function removeAllFloatingActionMarkers() {
  quickActionsCleanup?.();
  quickActionsCleanup = null;
  if (selectedFeatureQuickActionsMarker) {
    selectedFeatureQuickActionsMarker.remove();
    selectedFeatureQuickActionsMarker = null;
  }
  if (map) {
    map.eachLayer((l) => {
      if ((l as any).options?.icon?.options?.className === "feature-floating-actions-container") {
        map?.removeLayer(l);
      }
    });
  }
  document.querySelectorAll(".feature-floating-actions-container").forEach((el) => el.remove());
}

function removeAllCityRings() {
  if (selectedCityRing) {
    selectedCityRing.remove();
    selectedCityRing = null;
  }
  if (map) {
    map.eachLayer((l) => {
      if ((l as any).options?.icon?.options?.className === "city-selection-ring") {
        map?.removeLayer(l);
      }
    });
  }
  document.querySelectorAll(".city-selection-ring").forEach((el) => el.remove());
}

function clearAllLabelSelections() {
  document.querySelectorAll(".label-selected").forEach((el) => {
    el.classList.remove("label-selected");
    el.classList.remove("label-rotate-mode");
  });
  document.querySelectorAll(".multi-selected-label").forEach((el) => {
    el.classList.remove("multi-selected-label");
  });
  document.querySelectorAll(".image-overlay-selected").forEach((el) => {
    el.classList.remove("image-overlay-selected");
  });
}

function clearAllSelectionStyles() {
  selectedLayersOriginalStyles.forEach((origStyle, l) => {
    try {
      applyStyleToLayer(l, origStyle);
      disablePerFeatureDrag(l);
    } catch {
      // ignore
    }
  });
  selectedLayersOriginalStyles.clear();
}

function getLayerTopRightLatLng(layer: L.Layer, currentMap: L.Map): L.LatLng | null {
  let maxX = -Infinity;
  let minY = Infinity;

  const traverse = (coords: any) => {
    if (coords instanceof L.LatLng) {
      const pt = currentMap.latLngToContainerPoint(coords);
      if (pt.x > maxX) maxX = pt.x;
      if (pt.y < minY) minY = pt.y;
    } else if (Array.isArray(coords)) {
      for (let i = 0; i < coords.length; i++) {
        traverse(coords[i]);
      }
    }
  };

  forEachLeafLayer(layer, (leaf) => {
    const s = leaf as any;
    if (typeof s.getLatLngs === "function") {
      traverse(s.getLatLngs());
    } else if (typeof s.getBounds === "function") {
      const b = s.getBounds();
      if (b && (!b.isValid || b.isValid())) {
        const corners = [b.getNorthWest(), b.getNorthEast(), b.getSouthEast(), b.getSouthWest()];
        corners.forEach((c) => {
          const pt = currentMap.latLngToContainerPoint(c);
          if (pt.x > maxX) maxX = pt.x;
          if (pt.y < minY) minY = pt.y;
        });
      }
    } else if (typeof s.getLatLng === "function") {
      traverse(s.getLatLng());
    }
  });

  if (!isFinite(maxX) || !isFinite(minY)) return null;
  return currentMap.containerPointToLatLng(L.point(maxX, minY));
}

function updateQuickActionsPosition(layer: L.Layer) {
  if (!selectedFeatureQuickActionsMarker || !map) return;
  const ne = getLayerTopRightLatLng(layer, map);
  if (ne) {
    selectedFeatureQuickActionsMarker.setLatLng(ne);
  }
}
let escapeKeyHandler: ((e: KeyboardEvent) => void) | null = null;

const selectedFeatureId = computed(() => props.selectedFeatureId ?? null);

const undoControlName = "atlasUndo";
const redoControlName = "atlasRedo";
const undoControlClass = "leaflet-pm-icon-atlas-undo";
const redoControlClass = "leaflet-pm-icon-atlas-redo";

function setToolbarButtonEnabled(className: string, enabled: boolean) {
  document.querySelectorAll<HTMLElement>(`.${className}`).forEach((el) => {
    el.classList.toggle("leaflet-pm-control-disabled", !enabled);
    el.setAttribute("aria-disabled", String(!enabled));
    el.tabIndex = enabled ? 0 : -1;
  });
}

function updateHistoryToolbarState() {
  setToolbarButtonEnabled(undoControlClass, props.canUndo);
  setToolbarButtonEnabled(redoControlClass, props.canRedo);
}

function addUndoRedoControls(mapInstance: L.Map) {
  const toolbar = (mapInstance as MapWithPm).pm?.Toolbar;

  if (!toolbar?.createCustomControl) {
    return;
  }

  if (!toolbar.controlExists?.(undoControlName)) {
    toolbar.createCustomControl({
      name: undoControlName,
      block: "custom",
      title: "Annuler",
      className: undoControlClass,
      toggle: false,
      onClick: () => {
        if (!props.canUndo) return;
        emit("undo");
      },
    });
  }

  if (!toolbar.controlExists?.(redoControlName)) {
    toolbar.createCustomControl({
      name: redoControlName,
      block: "custom",
      title: "Rétablir",
      className: redoControlClass,
      toggle: false,
      onClick: () => {
        if (!props.canRedo) return;
        emit("redo");
      },
    });
  }

  toolbar.setBlockPosition?.("custom", "topleft");
  toolbar.changeControlOrder?.([undoControlName, redoControlName]);

  updateHistoryToolbarState();
}

const { handleClick: handleLayerClick, handleDblClick: handleLayerDblClick } =
  createFeatureDoubleClickHandler<Feature>({
    onSelect: (feature: Feature) => {
      emit("select-feature", String(feature.id));
    },
    onEdit: (feature: Feature) => {
      emit("select-feature", String(feature.id));
      emit("edit-feature-request", feature);
    },
    getId: (feature: Feature) => feature.id ?? feature.properties?.id,
  });

const featureLayerManager = {
  layers: new Map<FeatureId, L.Layer>(),

  addFeatureLayer(featureId: string | number, layer: L.Layer) {
    const id = String(featureId);
    if (!map) return;

    if (this.layers.has(id)) {
      map.removeLayer(this.layers.get(id)!);
    }
    this.layers.set(id, layer);

    const clickHandler = (e: L.LeafletMouseEvent) => {
      if ((e as any)._featureClickHandled) return;
      (e as any)._featureClickHandled = true;

      const pm = (map as MapWithPm)?.pm;
      if (isPostEditClick()) return;
      // Don't steal clicks from active drawing tools
      if (drawing.activeDrawingMode.value !== null) return;
      if (pm?.globalRemovalModeEnabled?.()) return;
      // A snapped vertex mouseup lands on the neighbour zone. That must not
      // change the selection (it would leave edit mode and drop the handles).
      if (
        pm?.globalEditModeEnabled?.() &&
        selectedFeatureId.value &&
        id !== selectedFeatureId.value
      ) {
        return;
      }

      const orig = e.originalEvent as any;
      if (orig) {
        if (orig._atlasFeatureClickProcessed) return;
        orig._atlasFeatureClickProcessed = true;
        orig.__atlasFeatureClicked = true;
      }
      blockNextMapClick = true;
      setTimeout(() => {
        blockNextMapClick = false;
      }, 100);
      if (addCityMode.value) cityMode.cancel();

      const isCtrl = Boolean(orig?.ctrlKey || orig?.metaKey);
      const isShift = Boolean(orig?.shiftKey);

      if (isCtrl || isShift) {
        const result = applySelectionModifier(id, isCtrl, isShift, {
          selectedId: props.selectedFeatureId,
          multiSelectedIds: props.multiSelectedFeatureIds ?? Array.from(multiSelectedIds.value),
          lastAnchorId: lastMapAnchorId,
          orderedIds: props.features.map((f: Feature) => String(f.id)),
        });
        lastMapAnchorId = result.newAnchorId;
        emit("select-feature", result.selectedId);
        emit("select-features", result.multiSelectedIds);
        return;
      }

      lastMapAnchorId = id;
      emit("select-features", []);
      const feature = props.features.find(
        (f: Feature) => String(f.id) === id || String(f.properties?.id) === id,
      );
      if (feature) {
        handleLayerClick(feature);
      } else {
        emit("select-feature", id);
      }
    };

    const dblClickHandler = (e?: L.LeafletMouseEvent) => {
      if (e && (e as any)._featureDblClickHandled) return;
      if (e) (e as any)._featureDblClickHandled = true;

      const pm = (map as MapWithPm)?.pm;
      if (isPostEditClick()) return;
      // Don't steal clicks from active drawing tools
      if (drawing.activeDrawingMode.value !== null) return;
      if (pm?.globalRemovalModeEnabled?.()) return;

      const orig = e?.originalEvent as any;
      if (orig) {
        if (orig._atlasFeatureDblClickProcessed) return;
        orig._atlasFeatureDblClickProcessed = true;
        orig.__atlasFeatureClicked = true;
      }
      blockNextMapClick = true;
      setTimeout(() => {
        blockNextMapClick = false;
      }, 100);
      if (addCityMode.value) cityMode.cancel();

      const feature = props.features.find(
        (f: Feature) => String(f.id) === id || String(f.properties?.id) === id,
      );
      if (feature) {
        handleLayerDblClick(feature);
      }
    };

    layer.on("click", clickHandler);
    layer.on("dblclick", dblClickHandler);
    layer.on("pm:markerdragstart", startPostEditClickGuard);
    forEachLeafLayer(layer, (leaf) => {
      leaf.on("click", clickHandler);
      leaf.on("dblclick", dblClickHandler);
      leaf.on("pm:markerdragstart", startPostEditClickGuard);
    });

    const isVisible = props.featureVisibility.get(id) ?? true;
    if (isVisible) {
      map.addLayer(layer);
    }
  },

  toggleFeature(featureId: string | number, visible: boolean) {
    const id = String(featureId);
    const layer = this.layers.get(id);
    if (!layer || !map) return;

    if (visible) {
      if (map.hasLayer(layer)) return;
      const pm = (map as MapWithPm).pm;
      const anyModeActive =
        pm?.globalEditModeEnabled?.() ||
        pm?.globalRotateModeEnabled?.();

      // Geoman would otherwise grab the layer the moment it is added back
      // while global edit/rotate is on. pmIgnore keeps that from stealing
      // the vertices of the feature already being edited.
      const setIgnoreDeep = (l: L.Layer) => {
        (l.options as PmIgnoreOptions).pmIgnore = true;
        if (l instanceof L.LayerGroup) {
          (l as L.LayerGroup).eachLayer(setIgnoreDeep);
        }
      };

      const clearIgnoreDeep = (l: L.Layer) => {
        delete (l.options as PmIgnoreOptions).pmIgnore;
        if (l instanceof L.LayerGroup) {
          (l as L.LayerGroup).eachLayer(clearIgnoreDeep);
        }
      };

      if (anyModeActive) setIgnoreDeep(layer);
      map.addLayer(layer);
      if (anyModeActive) clearIgnoreDeep(layer);
    } else {
      map.removeLayer(layer);
    }
  },

  clearAllFeatures() {
    if (!map) return;
    this.layers.forEach((layer) => map!.removeLayer(layer));
    this.layers.clear();
  },
};


function applyLayerUpdate(layer: L.Layer) {
  const runtimeLayer = layer as AtlasRuntimeLayer;
  // Every sync event closes a mouse gesture (drag, vertex move, rotation).
  startPostEditClickGuard();

  if (runtimeLayer.__atlasApplyingSync) return;
  runtimeLayer.__atlasApplyingSync = true;

  try {
    const extracted = extractFeatureFromLayer(
      layer,
      props.selectedYear,
      props.projectId,
    );
    if (!extracted) return;

    attachFeatureToLayer(layer, extracted);

    const next = upsertFeature(localFeaturesSnapshot.value, extracted);
    localFeaturesSnapshot.value = next;
    holdFeaturePropRenders();
    emit("draw-update", next);
  } finally {
    runtimeLayer.__atlasApplyingSync = false;
  }
}

function syncFeaturesFromMapLayers(): Feature[] {
  const mergedById = new Map<string, Feature>();

  const renderedFeatures = syncFeaturesFromLayerMap(
    featureLayerManager.layers,
    localFeaturesSnapshot.value,
    props.selectedYear,
    props.projectId,
  );

  renderedFeatures.forEach((feature) => {
    mergedById.set(String(feature.id), feature);
  });

  drawing.drawnItems.value?.eachLayer((layer: L.Layer) => {
    const extracted = extractFeatureFromLayer(
      layer,
      props.selectedYear,
      props.projectId,
    );
    if (!extracted?.id) {
      return;
    }
    mergedById.set(String(extracted.id), extracted);
  });

  return Array.from(mergedById.values());
}

const isViewReady = ref(false);
// Shows the map even if the parent never frames it (e.g. a failed load)
const VIEW_READY_FALLBACK_MS = 5000;
let viewReadyFallback: ReturnType<typeof setTimeout> | null = null;
let containerResizeObserver: ResizeObserver | null = null;

function revealMap() {
  isViewReady.value = true;
  if (viewReadyFallback) clearTimeout(viewReadyFallback);
  viewReadyFallback = null;
}

// Frames the features currently drawn on the map (visibility and timeline
// filters applied), or targets `featureIds` with smart framing when given.
function fitToVisibleFeatures(
  featureIds?: ReadonlySet<string> | string[] | Set<string>,
  animate = false,
) {
  if (!map) return;
  revealMap();

  const idArray = featureIds
    ? Array.from(featureIds instanceof Set ? featureIds : featureIds)
    : [];

  // When specific feature IDs are requested, apply smart framing/zoom
  if (idArray.length > 0) {
    const bounds = L.latLngBounds([]);

    idArray.forEach((id) => {
      const layer = featureLayerManager.layers.get(id);
      if (layer) {
        extendBoundsWithLayer(bounds, layer);
      }
      const feat = (props.features ?? []).find(
        (f: Feature) => String(f.id) === String(id),
      );
      if (feat?.geometry) {
        extendBoundsWithGeometry(bounds, feat.geometry);
      }
    });

    if (!bounds.isValid()) return;

    const currentZoom = map.getZoom();

    // Global map zoom level
    const overviewBounds = getMapOverviewBounds();
    let mapLevelZoom = currentZoom;
    if (overviewBounds.isValid()) {
      try {
        const calculatedZoom = map.getBoundsZoom(overviewBounds, false, L.point(50, 50));
        if (Number.isFinite(calculatedZoom)) {
          mapLevelZoom = Math.min(calculatedZoom, 6);
        }
      } catch {
        // ignore
      }
    } else {
      mapLevelZoom = Math.min(currentZoom, 5);
    }

    applySmartFeatureFraming(map, bounds, {
      mapLevelZoom,
      animate,
      multi: idArray.length > 1,
    });
    return;
  }

  // When no IDs are specified, frame all features currently drawn on the map
  const bounds = L.latLngBounds([]);
  featureLayerManager.layers.forEach((layer) => {
    if (!map!.hasLayer(layer)) return;
    extendBoundsWithLayer(bounds, layer);
  });
  if (!bounds.isValid()) return;
  map.fitBounds(bounds, { padding: [50, 50], maxZoom: 10, animate });
}

function extendBoundsWithLayer(bounds: L.LatLngBounds, layer: L.Layer) {
  const located = layer as Partial<{
    getBounds: () => L.LatLngBounds;
    getLatLng: () => L.LatLng;
    eachLayer: (fn: (child: L.Layer) => void) => void;
  }>;
  if (typeof located.getBounds === "function") {
    const layerBounds = located.getBounds();
    if (layerBounds.isValid()) bounds.extend(layerBounds);
  } else if (typeof located.getLatLng === "function") {
    bounds.extend(located.getLatLng());
  } else if (typeof located.eachLayer === "function") {
    // A city is a plain LayerGroup (point + label), which has no bounds of its own
    located.eachLayer((child) => extendBoundsWithLayer(bounds, child));
  }
}

function extendBoundsWithGeometry(bounds: L.LatLngBounds, geom: any) {
  if (!geom || !geom.coordinates) return;
  const { type, coordinates } = geom;
  if (type === "Point") {
    const [lng, lat] = coordinates as [number, number];
    if (Number.isFinite(lat) && Number.isFinite(lng)) bounds.extend([lat, lng]);
  } else if (type === "MultiPoint" || type === "LineString") {
    (coordinates as number[][]).forEach(([lng, lat]) => {
      if (Number.isFinite(lat) && Number.isFinite(lng)) bounds.extend([lat, lng]);
    });
  } else if (type === "Polygon" || type === "MultiLineString") {
    (coordinates as number[][][]).forEach((ring) => {
      ring?.forEach(([lng, lat]) => {
        if (Number.isFinite(lat) && Number.isFinite(lng)) bounds.extend([lat, lng]);
      });
    });
  } else if (type === "MultiPolygon") {
    (coordinates as number[][][][]).forEach((poly) => {
      poly?.forEach((ring) => {
        ring?.forEach(([lng, lat]) => {
          if (Number.isFinite(lat) && Number.isFinite(lng)) bounds.extend([lat, lng]);
        });
      });
    });
  }
}

function getMapOverviewBounds(): L.LatLngBounds {
  const bounds = L.latLngBounds([]);
  featureLayerManager.layers.forEach((layer) => {
    if (map && map.hasLayer(layer)) {
      extendBoundsWithLayer(bounds, layer);
    }
  });
  if (!bounds.isValid()) {
    (props.features ?? []).forEach((f: Feature) => {
      if (f.geometry) extendBoundsWithGeometry(bounds, f.geometry);
    });
  }
  return bounds;
}

function clearDraftLayers() {
  drawing.clearDrawnItems();
}

function resetSelection() {
  lastMapAnchorId = null;
  multiSelectedIds.value = new Set();

  removeAllFloatingActionMarkers();
  removeAllCityRings();
  clearAllLabelSelections();
  clearAllSelectionStyles();
  clearMultiSelectStylesAndDrag();

  shapeScaling.detach();
  imageOverlay.detach();
  pixelSpaceDragCleanup?.();
  pixelSpaceDragCleanup = null;

  const pm = (map as MapWithPm)?.pm;
  if (pm?.globalEditModeEnabled?.()) pm.disableGlobalEditMode?.();
  if (pm?.globalRotateModeEnabled?.()) pm.disableGlobalRotateMode?.();
  drawing.setToolbarMode("global");

  emit("select-feature", null);
  emit("select-features", []);
  updateLabelVisibility();
}

defineExpose({
  syncFeaturesFromMapLayers,
  clearDraftLayers,
  resetSelection,
  fitToVisibleFeatures,
  multiSelectedIds,
});

// During a Geoman cut, layers can be removed from the map then re-added.
// Track which features were visible / updated so we don't treat a temporary
// detach as "this shape left the map".
let cuttingUpdatedIds: Set<string> | null = null;
let cuttingVisibleIds: Set<string> | null = null;

function isLayerOffMap(layer: L.Layer): boolean {
  if (!map!.hasLayer(layer)) return true;
  const asGroup = layer as unknown as Partial<L.LayerGroup>;
  if (typeof asGroup.getLayers === "function") {
    const children = asGroup.getLayers() as L.Layer[];
    if (children.length === 0) return true;
    return children.every((child: L.Layer) => isLayerOffMap(child));
  }
  return false;
}

const drawing = useMapDrawing(
  (event, ...args) => {
    const current = localFeaturesSnapshot.value;
    if (event === "cut-started") {
      cuttingUpdatedIds = new Set<string>();
      cuttingVisibleIds = new Set<string>();
      if (map) {
        featureLayerManager.layers.forEach((layer, id) => {
          if (!isLayerOffMap(layer)) cuttingVisibleIds!.add(id);
        });
      }
      return;
    }
    if (event === "feature-created") {
      const payload = args[0] as Feature;
      const next = upsertFeature(current, payload);
      localFeaturesSnapshot.value = next;
      emit("draw-create", next);
      return;
    }

    if (event === "feature-updated") {
      const payload = args[0] as Feature;
      cuttingUpdatedIds?.add(String(payload.id));
      const next = upsertFeature(current, payload);
      localFeaturesSnapshot.value = next;
      holdFeaturePropRenders();
      emit("draw-update", next);
      return;
    }

    if (event === "feature-deleted") {
      const deletedId = String(args[0]);
      const next = current.filter(
        (feature: Feature) => String(feature.id) !== deletedId,
      );
      localFeaturesSnapshot.value = next;
      emit("draw-delete", next);
      return;
    }
    if (event === "cut-complete") {
      if (map && cuttingUpdatedIds !== null && cuttingVisibleIds !== null) {
        const removedIds: string[] = [];
        featureLayerManager.layers.forEach((layer, id) => {
          if (
            cuttingVisibleIds!.has(id) &&
            isLayerOffMap(layer) &&
            !cuttingUpdatedIds!.has(id)
          ) {
            removedIds.push(id);
          }
        });
        if (removedIds.length > 0) {
          let next = localFeaturesSnapshot.value;
          for (const deletedId of removedIds) {
            next = next.filter((f: Feature) => String(f.id) !== deletedId);
            featureLayerManager.layers.delete(deletedId);
          }
          localFeaturesSnapshot.value = next;
          emit("draw-delete", next);
        }
      }
      cuttingUpdatedIds = null;
      cuttingVisibleIds = null;
      renderAllFeatures();
      return;
    }
  },
  () => props.projectId,
);

const cityInput = ref<HTMLInputElement | null>(null);
const cityMode = useAddCityMode({
  getMap: () => map,
  localFeaturesSnapshot,
  cityInput,
  onCreated: (next: any) => emit('draw-create', next),
  onAfterCreate: () => renderAllFeatures(),
  getProjectId: () => props.projectId,
});
const { addCityMode, pendingCity, cityInputName } = cityMode;
const cancelAddCity = cityMode.cancel;
const confirmCity = cityMode.confirm;

const imageOverlay = useImageOverlay({
  getMap: () => map,
  getLayerById: (id: string) => featureLayerManager.layers.get(id),
  localFeaturesSnapshot,
  onBeforeEmit: () => { holdFeaturePropRenders(); },
  onUpdate: (next: any) => emit('draw-update', next),
});

const shapeScaling = useShapeScaling({
  getMap: () => map,
  getLayerById: (id: string) => featureLayerManager.layers.get(id),
  localFeaturesSnapshot,
  getProjectId: () => props.projectId,
  getSelectedYear: () => props.selectedYear,
  onBeforeEmit: () => { holdFeaturePropRenders(); },
  onUpdate: (next: any) => emit('draw-update', next),
});

const isScalableFeature = (feature?: Feature | null): boolean => {
  if (!feature) return false;
  const type = getMapElementType(feature);
  return type === "shape" || type === "zone" || type === "polyline";
};

const attachScalingIfEligible = (featureId: string) => {
  const feature = localFeaturesSnapshot.value.find((f: Feature) => String(f.id) === featureId);
  if (isScalableFeature(feature)) {
    shapeScaling.attach(featureId);
  }
};

function applyLabelPresentationStyle(
  marker: L.Marker,
  presentation: LabelPresentationModel,
  featureId: string | number,
) {
  const el = marker.getElement() as HTMLElement | null;
  if (!el) return;

  el.style.setProperty("--label-color", presentation.colorCss);
  el.style.setProperty("--label-size", `${presentation.sizePx}px`);
  el.style.setProperty("--label-style", presentation.fontStyle);
  el.style.setProperty("--label-weight", presentation.fontWeight);
  el.style.setProperty("--label-transform", presentation.textTransform);
  el.dataset.sizePx = String(presentation.sizePx);
  el.dataset.wordType = presentation.wordType;
  el.dataset.featureId = String(featureId);
  if (selectedFeatureId.value === String(featureId)) {
    el.classList.add("label-selected");
  }
}

function getActionButtonsHtml(): string {
  return `
    <button class="label-action-btn action-duplicate" title="Dupliquer" type="button">
      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor" width="13" height="13">
        <path stroke-linecap="round" stroke-linejoin="round" d="M15.75 17.25v3.375c0 .621-.504 1.125-1.125 1.125h-9.75a1.125 1.125 0 0 1-1.125-1.125V7.875c0-.621.504-1.125 1.125-1.125H6.75a9.06 9.06 0 0 1 1.5.124m7.5 10.376h3.375c.621 0 1.125-.504 1.125-1.125V11.25c0-4.46-3.243-8.161-7.5-8.876a9.06 9.06 0 0 0-1.5-.124H9.375c-.621 0-1.125.504-1.125 1.125v3.5m7.5 10.375H9.375a1.125 1.125 0 0 1-1.125-1.125v-9.25m12 6.625v-1.875a3.375 3.375 0 0 0-3.375-3.375h-1.5a1.125 1.125 0 0 1-1.125-1.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H9.75" />
      </svg>
    </button>
    <button class="label-action-btn action-delete" title="Supprimer" type="button">
      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.8" stroke="currentColor" width="13" height="13">
        <path stroke-linecap="round" stroke-linejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
      </svg>
    </button>
  `;
}

function bindActionButtons(
  containerEl: HTMLElement,
  onDuplicate: () => void,
  onDelete: () => void,
): void {
  const dupBtn = containerEl.querySelector<HTMLElement>(".action-duplicate");
  if (dupBtn && !(dupBtn as any).__bound) {
    (dupBtn as any).__bound = true;
    dupBtn.addEventListener("click", (e) => {
      L.DomEvent.stopPropagation(e as unknown as Event);
      e.preventDefault();
      onDuplicate();
    });
    dupBtn.addEventListener("mousedown", (e) => {
      L.DomEvent.stopPropagation(e as unknown as Event);
    });
  }

  const delBtn = containerEl.querySelector<HTMLElement>(".action-delete");
  if (delBtn && !(delBtn as any).__bound) {
    (delBtn as any).__bound = true;
    delBtn.addEventListener("click", (e) => {
      L.DomEvent.stopPropagation(e as unknown as Event);
      e.preventDefault();
      onDelete();
    });
    delBtn.addEventListener("mousedown", (e) => {
      L.DomEvent.stopPropagation(e as unknown as Event);
    });
  }
}

function buildLabelMarker(
  feature: Feature,
  presentation: LabelPresentationModel,
  iconAnchor?: [number, number],
): L.Marker {
  const [lng, lat] = feature.geometry.coordinates as [number, number];
  const coord: L.LatLngTuple = [lat, lng];
  const isSelected = selectedFeatureId.value === String(feature.id);

  const marker = L.marker(coord, {
    icon: L.divIcon({
      className: isSelected ? "city-label-text label-selected" : "city-label-text",
      html: `
        <div class="label-wrapper" data-feature-id="${feature.id}">
          <div class="label-content"${presentation.styleAttribute}>${presentation.html}</div>
          <div class="label-anchor rotate-handle"></div>
          <div class="label-quick-actions">
            ${getActionButtonsHtml()}
          </div>
        </div>
      `,
      iconSize: null as any,
      iconAnchor: iconAnchor ? (iconAnchor as any) : undefined,
    }),
  } as any);

  const bindQuickActionButtons = () => {
    const el = marker.getElement();
    if (!el) return;
    bindActionButtons(
      el,
      () => emit("duplicate-feature", feature),
      () => emit("delete-feature", feature),
    );
  };

  const preventSelection = () => {
    const el = marker.getElement();
    if (el) {
      el.addEventListener("selectstart", (e) => e.preventDefault());
      el.addEventListener("mousedown", () => {
        window.getSelection()?.removeAllRanges();
      });
    }
  };

  marker.on("add", () => {
    applyLabelPresentationStyle(marker, presentation, feature.id);
    preventSelection();
    bindQuickActionButtons();
    if (selectedFeatureId.value === String(feature.id)) {
      marker.getElement()?.classList.add("label-selected");
    }
  });
  if (marker.getElement()) {
    applyLabelPresentationStyle(marker, presentation, feature.id);
    preventSelection();
    bindQuickActionButtons();
    if (selectedFeatureId.value === String(feature.id)) {
      marker.getElement()?.classList.add("label-selected");
    }
  }

  return marker;
}

function bindRotationHandle(label: L.Marker, feature: Feature, layerToUpdate: L.Layer, anchorX: number, anchorY: number) {
  const applyRotation = () => {
    const el = label.getElement();
    if (!el) return;
    const wrapper = el.querySelector(".label-wrapper") as HTMLElement | null;
    if (wrapper) {
      const rotation = feature.properties.rotation ?? 0;
      wrapper.style.transformOrigin = `${anchorX}px ${anchorY}px`;
      wrapper.style.transform = rotation ? `rotate(${rotation}deg)` : "";
    }
  };

  label.on("add", () => {
    applyRotation();
    const el = label.getElement();
    if (!el) return;

    const anchor = el.querySelector<HTMLElement>('.label-anchor.rotate-handle');
    if (anchor) {
      anchor.addEventListener('mousedown', (e: MouseEvent) => {
        L.DomEvent.stopPropagation(e);
        if (!map) return;
        map.dragging.disable();
        window.getSelection()?.removeAllRanges();
        document.body.style.userSelect = 'none';

        const containerRect = map.getContainer().getBoundingClientRect();
        const point = map.latLngToContainerPoint(label.getLatLng());
        const centerX = containerRect.left + point.x;
        const centerY = containerRect.top + point.y;

        let startAngle = Math.atan2(e.clientY - centerY, e.clientX - centerX);
        let initialRotation = feature.properties.rotation ?? 0;

        const wrapper = el.querySelector('.label-wrapper') as HTMLElement | null;

        const onMouseMove = (moveEvent: MouseEvent) => {
          const angle = Math.atan2(moveEvent.clientY - centerY, moveEvent.clientX - centerX);
          let delta = (angle - startAngle) * (180 / Math.PI);
          let newRotation = initialRotation + delta;

          (el as any).__currentRotation = newRotation;
          if (wrapper) {
            wrapper.style.transformOrigin = `${anchorX}px ${anchorY}px`;
            wrapper.style.transform = `rotate(${newRotation}deg)`;
          }
        };

        const onMouseUp = () => {
          document.removeEventListener('mousemove', onMouseMove);
          document.removeEventListener('mouseup', onMouseUp);
          document.body.style.userSelect = '';
          window.getSelection()?.removeAllRanges();
          map!.dragging.enable();

          if ((el as any).__currentRotation !== undefined) {
            feature.properties.rotation = (el as any).__currentRotation;
            applyLayerUpdate(layerToUpdate);
          }
        };

        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
      });
    }
  });

  if (label.getElement()) {
    applyRotation();
  }
}

function materializeTextLayer(feature: Feature): L.Layer | null {
  if (!map || feature.geometry.type !== "Point") return null;

  const [lng, lat] = feature.geometry.coordinates as [number, number];
  if (lng === 0 && lat === 0) return null;

  const presentation = getLabelPresentation(feature);
  const coord: L.LatLngTuple = [lat, lng];

  if (presentation.mapElementType === "point") {
    const fillColor = presentation.pointColor || "#000000";
    const strokeColor = presentation.pointStrokeColor || "#000000";
    const strokeW = presentation.pointStrokeWidth ?? 1;
    const swatch = STYLE_POINT_SWATCH_PX;
    const anchorX = -Math.round(swatch / 2 + 2);
    const anchorY = Math.round(presentation.sizePx * 0.6 + 6);

    const point = L.marker(coord, {
      icon: L.divIcon({
        className: "map-point-marker",
        html: mapPointSwatchSvg({
          fill: fillColor,
          stroke: strokeColor,
          fillOpacity: presentation.pointFillOpacity ?? 1,
          strokeOpacity: presentation.pointStrokeOpacity ?? 1,
          strokeWidth: strokeW,
        }),
        iconSize: [swatch, swatch],
        iconAnchor: [swatch / 2, swatch / 2],
      }),
      zIndexOffset: 400,
      keyboard: false,
    });

    const label = buildLabelMarker(feature, presentation, [anchorX, anchorY]);

    attachFeatureToLayer(point, feature);
    bindRenderedFeatureEvents(point, applyLayerUpdate);

    const layerGroup = L.layerGroup([point, label]);

    const syncCityRing = (latLng: L.LatLng) => {
      if (selectedCityRing && selectedFeatureId.value === String(feature.id)) {
        selectedCityRing.setLatLng(latLng);
      }
    };

    point.on("pm:drag", () => {
      const latLng = point.getLatLng();
      label.setLatLng(latLng);
      syncCityRing(latLng);
    });
    point.on("pm:dragend", () => {
      const latLng = point.getLatLng();
      label.setLatLng(latLng);
      syncCityRing(latLng);
    });

    label.on("pm:drag", () => {
      const latLng = label.getLatLng();
      point.setLatLng(latLng);
      syncCityRing(latLng);
    });
    label.on("pm:dragend", () => {
      const latLng = label.getLatLng();
      point.setLatLng(latLng);
      syncCityRing(latLng);
      applyLayerUpdate(point);
    });

    attachFeatureToLayer(label, feature);
    bindRotationHandle(label, feature, point, anchorX, anchorY);
    attachFeatureToLayer(layerGroup, feature);

    return layerGroup;
  } else {
    const label = buildLabelMarker(feature, presentation);
    bindRotationHandle(label, feature, label, 0, 10);
    attachFeatureToLayer(label, feature);
    bindRenderedFeatureEvents(label, applyLayerUpdate);
    return label;
  }
}

function renderTextFeature(feature: Feature, seenKeys?: Set<string>) {
  if (!map || feature.geometry.type !== "Point") return;
  const [lng, lat] = feature.geometry.coordinates as [number, number];
  if (lng === 0 && lat === 0) return;

  if (seenKeys) {
    const key = feature.id ? String(feature.id) : `${lng.toFixed(5)}_${lat.toFixed(5)}`;
    if (seenKeys.has(key)) return;
    seenKeys.add(key);
  }

  const layer = materializeTextLayer(feature);
  if (layer) {
    featureLayerManager.addFeatureLayer(feature.id, layer);
  }
}

function renderCities(features: Feature[]) {
  const safeFeatures = toArray(features);
  const seenCityKeys = new Set<string>();
  safeFeatures.forEach((feature) => renderTextFeature(feature, seenCityKeys));
}

function renderLabels(features: Feature[]) {
  const safeFeatures = toArray(features);
  safeFeatures.forEach((feature) => renderTextFeature(feature));
}

function renderPolygonFeatures(features: Feature[]) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach((feature) => {
    if (!map) return;
    if (
      feature.geometry.type !== "Polygon" &&
      feature.geometry.type !== "MultiPolygon"
    ) {
      return;
    }

    const fp = feature.properties;
    const fillColor = colorRgbToCss(fp.colorRgb) || "#000000";
    const strokeColor = colorRgbToCss(fp.strokeColor) || fillColor;

    const layer = L.geoJSON(feature.geometry, {
      style: {
        renderer: vectorRenderer ?? undefined,
        fillColor,
        fillOpacity: fp.fillOpacity ?? 0.5,
        color: strokeColor,
        weight: fp.strokeWidth || 1,
        opacity: fp.strokeOpacity ?? 1,
      },
    });

    attachFeatureToLayer(layer, feature);
    bindRenderedFeatureEvents(layer, applyLayerUpdate);

    featureLayerManager.addFeatureLayer(feature.id, layer);
  });
}

function renderLineFeatures(features: Feature[], isArrow = false) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach((feature) => {
    if (!map || feature.geometry.type !== "LineString") return;

    const latLngs = feature.geometry.coordinates.map(
      ([lng, lat]) => [lat, lng] as L.LatLngTuple,
    );

    const fillColor = colorRgbToCss(feature.properties.colorRgb) || "#000000";
    const strokeColor =
      colorRgbToCss(feature.properties.strokeColor) || fillColor;

    const line = L.polyline(latLngs, {
      renderer: vectorRenderer ?? undefined,
      color: strokeColor,
      weight: feature.properties.strokeWidth ?? 2,
      opacity: feature.properties.strokeOpacity ?? 1,
    });

    attachFeatureToLayer(line, feature);
    bindRenderedFeatureEvents(line, applyLayerUpdate);

    if (isArrow) {
      line.arrowheads({
        size: "10px",
        frequency: "endonly",
        fill: true,
      });
    }

    featureLayerManager.addFeatureLayer(feature.id, line);
  });
}

function renderZones(features: Feature[]) {
  renderPolygonFeatures(
    features.filter((feature) => getMapElementType(feature) === "zone"),
  );
}

function renderShapes(features: Feature[]) {
  renderPolygonFeatures(
    features.filter((feature) => getMapElementType(feature) === "shape"),
  );
}

function renderPolylines(features: Feature[]) {
  renderLineFeatures(
    features.filter((feature) => getMapElementType(feature) === "polyline"),
  );
}

function renderArrows(features: Feature[]) {
  renderLineFeatures(
    features.filter((feature) => getMapElementType(feature) === "arrow"),
    true,
  );
}

function renderImages(features: Feature[]) {
  const safeFeatures = toArray(features);

  safeFeatures.forEach((feature) => {
    if (!map || !feature.image) return;

    const bounds = feature.properties?.bounds as [[number, number], [number, number]] | undefined;

    if (!bounds) return;

    const src = toImageSrc(feature.image);
    const overlay = L.imageOverlay(src, bounds, {
      opacity: 1,
      interactive: true,
      pane: 'imagePane',
    });
    const strokeCss = colorRgbToCss(feature.properties.strokeColor);

    const applyRotation = (layer: any) => {
      const currentFeature = layer.feature || feature;
      const rotation = currentFeature.properties?.rotation ?? 0;
      if (layer._image) {
        layer._image.style.transformOrigin = "center center";
        const transform = layer._image.style.transform || "";
        if (rotation) {
          if (!transform.includes('rotate')) {
            layer._image.style.transform = `${transform} rotate(${rotation}deg)`.trim();
          } else {
            layer._image.style.transform = transform.replace(/rotate\([^)]+\)/, `rotate(${rotation}deg)`);
          }
        } else if (transform.includes('rotate')) {
          layer._image.style.transform = transform.replace(/rotate\([^)]+\)/, '').trim();
        }
      }
    };

    const originalAnimateZoom = (overlay as any)._animateZoom;
    (overlay as any)._animateZoom = function(e: any) {
      if (originalAnimateZoom) {
        originalAnimateZoom.call(this, e);
      }
      applyRotation(this);
    };

    const originalReset = (overlay as any)._reset;
    (overlay as any)._reset = function() {
      originalReset.call(this);
      applyRotation(this);
    };

    overlay.on('add', () => {
      const el = overlay.getElement();
      if (el) {
        el.setAttribute('draggable', 'false');
        if (strokeCss) {
          el.style.outline = `2px solid ${strokeCss}`;
        }
      }
      applyRotation(overlay);
    });

    attachFeatureToLayer(overlay, feature);
    (overlay as any).feature = feature;

    featureLayerManager.addFeatureLayer(feature.id, overlay);
  });
}

function renderAllFeaturesSafely() {
  if (!map) return;

  const pm = (map as MapWithPm).pm;
  const wasGlobalRotateEnabled = pm?.globalRotateModeEnabled?.() ?? false;

  if (wasGlobalRotateEnabled) {
    pm?.disableGlobalRotateMode?.();
  }

  try {
    renderAllFeatures();
  } finally {
    if (wasGlobalRotateEnabled) {
      pm?.enableGlobalRotateMode?.();
    }
  }
}

function renderAllFeatures() {
  if (!map) return;

  const currentFeatures = deduplicateFeatures(props.features);
  const currentIds = new Set(currentFeatures.map((f: Feature) => String(f.id)));
  const previousIds = previousFeatureIds.value;

  previousIds.forEach((oldId: string) => {
    if (!currentIds.has(oldId)) {
      const layer = featureLayerManager.layers.get(oldId);
      if (layer) {
        map!.removeLayer(layer);
        featureLayerManager.layers.delete(oldId);
      }
    }
  });

  const sortedFeatures = [...currentFeatures].sort((a, b) => {
    const layerA = a.properties.layer ?? getDefaultLayer(getMapElementType(a));
    const layerB = b.properties.layer ?? getDefaultLayer(getMapElementType(b));
    return layerA - layerB;
  });

  sortedFeatures.forEach((feature) => {
    const type = getMapElementType(feature);
    switch (type) {
      case "zone":
        renderZones([feature]);
        break;
      case "shape":
        renderShapes([feature]);
        break;
      case "polyline":
        renderPolylines([feature]);
        break;
      case "arrow":
        renderArrows([feature]);
        break;
      case "point":
        renderCities([feature]);
        break;
      case "label":
        renderLabels([feature]);
        break;
      case "image":
        renderImages([feature]);
        break;
    }
  });

  // Re-apply selection effects if the selected feature was re-rendered
  if (selectedFeatureId.value) {
    applySelectionEffects(selectedFeatureId.value);
  }

  previousFeatureIds.value = currentIds;

  scheduleLabelVisibilityUpdate();
}

function updateLabelVisibility() {
  if (!map) return;
  updateMapLabelVisibility(map, selectedFeatureId.value, featureLayerManager.layers);
}

function scheduleLabelVisibilityUpdate() {
  if (labelVisibilityFrame !== null) return;
  labelVisibilityFrame = requestAnimationFrame(() => {
    labelVisibilityFrame = null;
    updateLabelVisibility();
  });
}

onMounted(() => {
  map = L.map("map", {
    zoomControl: false,
    preferCanvas: true,
    doubleClickZoom: false,
    zoomSnap: 0.25,
    zoomDelta: 0.5,
    wheelPxPerZoomLevel: 200,
    maxBounds: [[-90, -180], [90, 180]],
    maxBoundsViscosity: 1.0,
  }).setView(
    [52.9399, -73.5491],
    5,
  );
  viewReadyFallback = setTimeout(revealMap, VIEW_READY_FALLBACK_MS);
  // One canvas for all vector paths so pan/zoom does not create a DOM node per shape.
  vectorRenderer = L.canvas({ padding: 0.5 });
  (map.options as Record<string, unknown>).renderer = vectorRenderer;

  createCartoTileLayer({ noWrap: true }).addTo(map);

  // Images sit above the basemap but below Geoman vertex handles.
  const imagePane = map.createPane('imagePane');
  imagePane.style.zIndex = '410';

  const updateMinZoom = () => {
    const wz = map!.getBoundsZoom(L.latLngBounds([[-90, -180], [90, 180]]), false);
    map!.setMinZoom(wz);
  };
  map.whenReady(updateMinZoom);
  map.on('resize', updateMinZoom);
  map.on("dragstart", () => window.getSelection()?.removeAllRanges());
  map.on("moveend", scheduleLabelVisibilityUpdate);
  map.on("zoomend", scheduleLabelVisibilityUpdate);

  const mapContainer = map.getContainer();
  if (typeof ResizeObserver !== "undefined" && mapContainer) {
    containerResizeObserver = new ResizeObserver(() => {
      map?.invalidateSize();
    });
    containerResizeObserver.observe(mapContainer);
  }

  drawing.initializeDrawing(map);
  L.control.zoom({ position: "topleft" }).addTo(map);
  addUndoRedoControls(map);
  drawing.setToolbarMode("global");

  // ---- Box selection (rectangle) ----
  // Shift + Left-click drag OR Right-click drag
  const container = map.getContainer();
  let activeBoxButton: number | null = null;

  const onContainerMousedown = (e: MouseEvent) => {
    const isShiftLeft = e.button === 0 && e.shiftKey;
    const isRight = e.button === 2;
    if (!isShiftLeft && !isRight) return;

    activeBoxButton = e.button;
    isRightSelectDragging = false;
    rightSelectStart = null;
    didRightDrag = false;
    lastRightPos = { x: e.clientX, y: e.clientY };
    if (isShiftLeft) {
      map?.dragging.disable();
    }
  };

  const onWindowMousemoveRight = (e: MouseEvent) => {
    if (!map || activeBoxButton === null) return;
    const buttonMask = activeBoxButton === 2 ? 2 : 1;
    if (!(e.buttons & buttonMask)) return;

    const dx = e.clientX - lastRightPos.x;
    const dy = e.clientY - lastRightPos.y;
    const totalMoved = Math.abs(dx) + Math.abs(dy);

    if (!isRightSelectDragging && totalMoved > 4) {
      isRightSelectDragging = true;
      didRightDrag = true;
      map.dragging.disable();
      const containerRect = container.getBoundingClientRect();
      const point = L.point(lastRightPos.x - containerRect.left, lastRightPos.y - containerRect.top);
      rightSelectStart = map.containerPointToLatLng(point);
      if (!rightSelectRect) {
        rightSelectRect = L.rectangle(L.latLngBounds(rightSelectStart, rightSelectStart), {
          color: '#2563eb',
          weight: 2,
          fillColor: '#2563eb',
          fillOpacity: 0.12,
          dashArray: '5 4',
        }).addTo(map);
      }
    }

    if (isRightSelectDragging && rightSelectStart) {
      const containerRect = container.getBoundingClientRect();
      const point = L.point(e.clientX - containerRect.left, e.clientY - containerRect.top);
      const currentLatLng = map.containerPointToLatLng(point);
      const bounds = L.latLngBounds(rightSelectStart, currentLatLng);
      rightSelectRect?.setBounds(bounds);
    }
  };

  const onWindowMouseupRight = (e: MouseEvent) => {
    if (activeBoxButton !== null && e.button !== activeBoxButton) return;
    map?.dragging.enable();

    if (isRightSelectDragging && rightSelectRect && map) {
      const selBounds = rightSelectRect.getBounds();
      const selectedIds: string[] = [];
      featureLayerManager.layers.forEach((layer, id) => {
        if (!map!.hasLayer(layer)) return;
        try {
          if (doesLayerIntersectBounds(layer, selBounds)) {
            selectedIds.push(id);
          }
        } catch {}
      });
      multiSelectedIds.value = new Set(selectedIds);
      emit("select-feature", null);
      emit("select-features", selectedIds);
    }
    if (rightSelectRect && map) {
      map.removeLayer(rightSelectRect);
      rightSelectRect = null;
    }
    isRightSelectDragging = false;
    rightSelectStart = null;
    activeBoxButton = null;
  };

  const onContainerContextmenu = (e: MouseEvent) => {
    if (didRightDrag) {
      e.preventDefault();
      didRightDrag = false;
    }
  };

  container.addEventListener('mousedown', onContainerMousedown);
  window.addEventListener('mousemove', onWindowMousemoveRight);
  window.addEventListener('mouseup', onWindowMouseupRight);
  container.addEventListener('contextmenu', onContainerContextmenu);

  rightDragCleanup = () => {
    container.removeEventListener('mousedown', onContainerMousedown);
    window.removeEventListener('mousemove', onWindowMousemoveRight);
    window.removeEventListener('mouseup', onWindowMouseupRight);
    container.removeEventListener('contextmenu', onContainerContextmenu);
    if (rightSelectRect && map) { map.removeLayer(rightSelectRect); rightSelectRect = null; }
  };

  const savedPmIgnore = new Map<L.Layer, boolean | undefined>();

  const restorePmIgnore = () => {
    savedPmIgnore.forEach((original, layer) => {
      const opts = layer.options as PmIgnoreOptions;
      if (original === undefined) {
        delete opts.pmIgnore;
      } else {
        opts.pmIgnore = original;
      }
    });
    savedPmIgnore.clear();
  };

  map.on("pm:buttonclick", (e: { btnName: string }) => {
    const { btnName } = e;
    const pm = (map as MapWithPm).pm;

    if (btnName === "addCity") {
      if (addCityMode.value) {
        cityMode.cancel();
      } else {
        cityMode.start();
        resetSelection();
      }
      return;
    }

    if (btnName === "editMode" || btnName === "rotateMode") {
      shapeScaling.detach();
    }
    if (btnName === "editMode" && pm?.globalEditModeEnabled?.()) return;
    if (btnName === "rotateMode" && pm?.globalRotateModeEnabled?.()) return;
    if (btnName !== "editMode" && btnName !== "rotateMode") return;
    if (!selectedFeatureId.value) return;

    const selectedLayer = featureLayerManager.layers.get(selectedFeatureId.value);
    const selectedLayers = new Set<L.Layer>();
    const addLayersDeep = (l: L.Layer) => {
      selectedLayers.add(l);
      if (l instanceof L.LayerGroup) {
        (l as L.LayerGroup).eachLayer(addLayersDeep);
      }
    };
    if (selectedLayer) addLayersDeep(selectedLayer);

    savedPmIgnore.clear();
    map!.eachLayer((l: L.Layer) => {
      if (selectedLayers.has(l)) return;
      const opts = l.options as PmIgnoreOptions;
      savedPmIgnore.set(l, opts.pmIgnore);
      opts.pmIgnore = true;
    });
  });

  map.on("pm:globaleditmodetoggled", restorePmIgnore);
  map.on("pm:globaleditmodetoggled", (e: { enabled?: boolean }) => {
    const isEnabled = e.enabled;
    // Vertex edit and the scale bounding-box must not overlap: the box
    // handles sit above Geoman vertices and steal the drag.
    if (isEnabled) {
      shapeScaling.detach();
    }
    if (!selectedFeatureId.value || leavingModesForSelectionChange) return;
    const selectedLayer = featureLayerManager.layers.get(selectedFeatureId.value);
    if (!selectedLayer || selectedLayer instanceof L.ImageOverlay) return;
    if (isEnabled) {
      disablePerFeatureDrag(selectedLayer);
      pixelSpaceDragCleanup?.();
      pixelSpaceDragCleanup = null;
    } else {
      enablePerFeatureDrag(selectedLayer);
      if (map) pixelSpaceDragCleanup = enablePixelSpaceDrag(map, selectedLayer);
      attachScalingIfEligible(selectedFeatureId.value);
    }
  });
  map.on("pm:globalrotatemodetoggled", restorePmIgnore);
  map.on("pm:globalrotatemodetoggled", () => {
    const pm = (map as MapWithPm).pm;
    const isEnabled = pm?.globalRotateModeEnabled?.();
    if (isEnabled) {
      document.querySelectorAll('.label-selected').forEach(el => el.classList.add('label-rotate-mode'));
      if (selectedFeatureId.value) shapeScaling.detach();
    } else {
      document.querySelectorAll('.label-rotate-mode').forEach(el => el.classList.remove('label-rotate-mode'));
      if (selectedFeatureId.value && !leavingModesForSelectionChange) attachScalingIfEligible(selectedFeatureId.value);
    }
  });

  map.on("click", (e: L.LeafletMouseEvent) => {
    if ((e.originalEvent as any)?.__atlasFeatureClicked) return;
    if (blockNextMapClick) {
      blockNextMapClick = false;
      return;
    }
    if (isPostEditClick()) return;
    if (shapeScaling.isTransforming?.()) {
      return;
    }
    if (addCityMode.value) {
      cityMode.handleMapClick((e as L.LeafletMouseEvent).latlng);
      return;
    }
    resetSelection();
  });

  containerClickListener = (e: MouseEvent) => {
    if ((e as any).__atlasFeatureClicked) return;
    const target = e.target as HTMLElement | null;
    if (!target) return;
    if (
      target.classList.contains("leaflet-container") ||
      target.classList.contains("leaflet-pane") ||
      target.classList.contains("leaflet-tile-pane") ||
      target.classList.contains("leaflet-tile") ||
      target.tagName === "CANVAS" ||
      target.tagName === "svg"
    ) {
      resetSelection();
    }
  };
  map.getContainer().addEventListener("click", containerClickListener);

  L.control
    .scale({ position: "bottomright", metric: true, imperial: false })
    .addTo(map);

  drawing.setSelectedYear(props.selectedYear);
  emit("map-ready", map);
  renderAllFeaturesSafely();
  escapeKeyHandler = (e: KeyboardEvent) => {
    if (!map) return;
    const pm = (map as MapWithPm).pm;

    if (e.key === "Escape" && multiSelectedIds.value.size > 0) {
      multiSelectedIds.value = new Set();
      emit("select-features", []);
      return;
    }

    if (e.key !== "Escape") return;
    if (addCityMode.value) {
      cityMode.cancel();
      return;
    }
    if (drawing.activeDrawingMode.value === "freehand") {
      drawing.stopFreehandDrawing(map);
      drawing.activeDrawingMode.value = null;
      pm?.Toolbar?.toggleButton?.("drawFreehand", false);
      return;
    }
    if (drawing.activeDrawingMode.value !== null) {
      pm?.disableDraw();
      return;
    }
    if (pm?.globalRemovalModeEnabled?.()) { pm.disableGlobalRemovalMode?.(); return; }
    if (pm?.globalEditModeEnabled?.()) { pm.disableGlobalEditMode?.(); return; }
    if (pm?.globalRotateModeEnabled?.()) { pm.disableGlobalRotateMode?.(); return; }
    if (selectedFeatureId.value !== null) {
      resetSelection();
      return;
    }
  };
  document.addEventListener("keydown", escapeKeyHandler);
});

onBeforeUnmount(() => {
  if (featurePropRenderHoldTimer) {
    clearTimeout(featurePropRenderHoldTimer);
    featurePropRenderHoldTimer = null;
  }
  featurePropRenderHolds = 0;
  containerResizeObserver?.disconnect();
  containerResizeObserver = null;
  if (viewReadyFallback) clearTimeout(viewReadyFallback);
  if (labelVisibilityFrame !== null) {
    cancelAnimationFrame(labelVisibilityFrame);
    labelVisibilityFrame = null;
  }
  if (escapeKeyHandler) {
    document.removeEventListener("keydown", escapeKeyHandler);
    escapeKeyHandler = null;
  }
  rightDragCleanup?.();
  rightDragCleanup = null;
  clearMultiSelectStylesAndDrag();
  quickActionsCleanup?.();
  quickActionsCleanup = null;
  selectedCityRing?.remove();
  selectedFeatureQuickActionsMarker?.remove();
  selectedFeatureQuickActionsMarker = null;
  pixelSpaceDragCleanup?.();
  imageOverlay.detach();
  shapeScaling.detach();
  if (containerClickListener && map) {
    try {
      map.getContainer()?.removeEventListener("click", containerClickListener);
    } catch {
      // ignore
    }
    containerClickListener = null;
  }
  if (map) {
    featureLayerManager.clearAllFeatures();
    map.remove();
    map = null;
  }
});

watch(
  () => props.selectedYear,
  (val: string | number | undefined) => {
    const numericYear = Number(val ?? 0);
    drawing.setSelectedYear(Number.isFinite(numericYear) ? numericYear : 0);
  },
);

watch(drawing.activeDrawingMode, (mode: string | null) => {
  if (!map) return;
  // Drawing tools sit above the vector canvas; disable canvas hits so a click
  // starts a new shape instead of selecting one underneath.
  map.getContainer().querySelectorAll<HTMLCanvasElement>('canvas').forEach((canvas: HTMLCanvasElement) => {
    canvas.style.pointerEvents = mode !== null ? 'none' : '';
  });
});

watch(
  () => props.features,
  (newFeatures: Feature[]) => {
    localFeaturesSnapshot.value = [...newFeatures];
    if (featurePropRenderHolds > 0) {
      featurePropRenderHolds = Math.max(0, featurePropRenderHolds - 1);
      if (featurePropRenderHolds === 0 && featurePropRenderHoldTimer) {
        clearTimeout(featurePropRenderHoldTimer);
        featurePropRenderHoldTimer = null;
      }
      return;
    }
    if (!map) return;
    renderAllFeaturesSafely();
  },
  { deep: true },
);

localFeaturesSnapshot.value = [...props.features];

function clearSelection(oldId?: string | null) {
  removeAllFloatingActionMarkers();
  removeAllCityRings();
  clearAllLabelSelections();
  clearAllSelectionStyles();
  clearMultiSelectStylesAndDrag();

  if (oldId != null && selectedFeatureId.value !== oldId) {
    const pm = (map as MapWithPm)?.pm;
    leavingModesForSelectionChange = true;
    try {
      if (pm?.globalEditModeEnabled?.()) pm.disableGlobalEditMode?.();
      if (pm?.globalRotateModeEnabled?.()) pm.disableGlobalRotateMode?.();
    } finally {
      leavingModesForSelectionChange = false;
    }
  }

  if (oldId != null) {
    const oldLayer = featureLayerManager.layers.get(String(oldId));
    if (oldLayer instanceof L.ImageOverlay) {
      oldLayer.getElement()?.classList.remove("image-overlay-selected");
    } else if (oldLayer !== undefined) {
      disablePerFeatureDrag(oldLayer);
      pixelSpaceDragCleanup?.();
      pixelSpaceDragCleanup = null;
    }
  }
}

function applySelectionEffects(id: string) {
  removeAllFloatingActionMarkers();
  removeAllCityRings();
  clearAllLabelSelections();
  clearAllSelectionStyles();

  const layer = featureLayerManager.layers.get(String(id));
  const selectedFeature = props.features.find((f: Feature) => String(f.id) === String(id)) ||
    localFeaturesSnapshot.value.find((f: Feature) => String(f.id) === String(id));
  const elementType = selectedFeature ? getMapElementType(selectedFeature) : null;
  const isImage =
    elementType === "image" || layer instanceof L.ImageOverlay;
  const isTextOrPoint =
    !isImage &&
    (elementType === "point" ||
      elementType === "label" ||
      selectedFeature?.geometry?.type === "Point");

  if (layer instanceof L.ImageOverlay) {
    drawing.setToolbarMode("label");
    layer.getElement()?.classList.add("image-overlay-selected");
  } else if (layer && isTextOrPoint) {
    if (map && !map.hasLayer(layer)) {
      map.addLayer(layer);
    }
    drawing.setToolbarMode("label");
    enablePerFeatureDrag(layer);
    pixelSpaceDragCleanup = enablePixelSpaceDrag(
      map!,
      layer,
      () => (selectedCityRing ? [selectedCityRing] : []),
    );

    let cityLatLng: L.LatLng | null = null;
    let cityLabel: L.Marker | null = null;
    forEachLeafLayer(layer, (leaf) => {
      if (!(leaf instanceof L.Marker)) return;
      const el = leaf.getElement();
      if (el?.classList.contains("map-point-marker")) {
        if (!cityLatLng) {
          cityLatLng = leaf.getLatLng();
        }
        return;
      }
      if (!cityLabel) {
        cityLabel = leaf as L.Marker;
      }
    });

    if (!cityLabel && layer instanceof L.Marker) {
      cityLabel = layer;
    }

    const applyLabelClasses = () => {
      if (cityLabel) {
        const el = (cityLabel as any).getElement?.();
        el?.classList.add("label-selected");
        const pm = (map as MapWithPm)?.pm;
        if (pm?.globalRotateModeEnabled?.()) {
          el?.classList.add("label-rotate-mode");
        }
      }
      document.querySelectorAll(
        `.city-label-text[data-feature-id="${id}"], [data-feature-id="${id}"].city-label-text, .label-wrapper[data-feature-id="${id}"]`
      ).forEach((node) => {
        const markerRoot = node.closest(".city-label-text") || node;
        markerRoot.classList.add("label-selected");
        const pm = (map as MapWithPm)?.pm;
        if (pm?.globalRotateModeEnabled?.()) {
          markerRoot.classList.add("label-rotate-mode");
        }
      });
    };

    applyLabelClasses();
    nextTick(applyLabelClasses);

    if (cityLatLng && map) {
      const ringSize = Math.round(MAP_POINT_MARKER_RADIUS_PX * 2 + 10);
      selectedCityRing = L.marker(cityLatLng, {
        icon: L.divIcon({
          className: "city-selection-ring",
          iconSize: [ringSize, ringSize],
          iconAnchor: [ringSize / 2, ringSize / 2],
        }),
        interactive: false,
        zIndexOffset: 1000,
      }).addTo(map);
    }
  } else if (layer) {
    drawing.setToolbarMode("feature");
    enablePerFeatureDrag(layer);
    pixelSpaceDragCleanup = enablePixelSpaceDrag(map!, layer);
    const originalOpts = getLayerPathOptions(layer) ?? {};
    if (!selectedLayersOriginalStyles.has(layer)) {
      selectedLayersOriginalStyles.set(layer, originalOpts);
    }
    applyStyleToLayer(layer, {
      color: "#2563eb",
      weight: Math.max(Number(originalOpts?.weight) || 2, 3),
      opacity: 1,
    });
  } else {
    drawing.setToolbarMode("global");
  }

  imageOverlay.detach();
  shapeScaling.detach();
  if (selectedFeature && getMapElementType(selectedFeature) === "image") {
    imageOverlay.attach(id);
  } else if (isScalableFeature(selectedFeature)) {
    shapeScaling.attach(id);
  }

  if (layer && !isTextOrPoint && selectedFeature && map) {
    const topRight = getLayerTopRightLatLng(layer, map);
    if (topRight) {
      selectedFeatureQuickActionsMarker = L.marker(topRight, {
        icon: L.divIcon({
          className: "feature-floating-actions-container",
          html: `
            <div class="label-quick-actions is-floating">
              ${getActionButtonsHtml()}
            </div>
          `,
          iconSize: [47, 22],
          iconAnchor: [-8, 0],
        }),
        interactive: true,
        zIndexOffset: 1200,
      }).addTo(map);

      const onPosChange = () => updateQuickActionsPosition(layer);
      map.on("zoom", onPosChange);
      map.on("viewreset", onPosChange);
      map.on("move", onPosChange);
      (layer as any).on?.("pm:drag", onPosChange);
      (layer as any).on?.("pm:dragend", onPosChange);

      quickActionsCleanup = () => {
        map?.off("zoom", onPosChange);
        map?.off("viewreset", onPosChange);
        map?.off("move", onPosChange);
        (layer as any).off?.("pm:drag", onPosChange);
        (layer as any).off?.("pm:dragend", onPosChange);
      };

      const el = selectedFeatureQuickActionsMarker.getElement();
      if (el) {
        bindActionButtons(
          el,
          () => emit("duplicate-feature", selectedFeature),
          () => emit("delete-feature", selectedFeature),
        );
      }
    }
  }

  updateLabelVisibility();
}

watch(selectedFeatureId, async (id: string | null, oldId: string | null) => {
  clearSelection(oldId);

  if (id != null) {
    await nextTick();
    applySelectionEffects(id);
  } else {
    const pm = (map as MapWithPm)?.pm;
    if (pm?.globalEditModeEnabled?.()) pm.disableGlobalEditMode?.();
    if (pm?.globalRotateModeEnabled?.()) pm.disableGlobalRotateMode?.();
    drawing.setToolbarMode("global");
    imageOverlay.detach();
    shapeScaling.detach();
    removeAllFloatingActionMarkers();
    removeAllCityRings();
    clearAllLabelSelections();
    clearAllSelectionStyles();
  }
  updateLabelVisibility();
});

const multiSelectOriginalStyles = new Map<L.Layer, L.PathOptions>();
const multiDragCleanups: Array<() => void> = [];

function clearMultiSelectStylesAndDrag() {
  multiDragCleanups.forEach((cleanup) => cleanup());
  multiDragCleanups.length = 0;

  multiSelectOriginalStyles.forEach((origStyle, layer) => {
    applyStyleToLayer(layer, origStyle);
    disablePerFeatureDrag(layer);
  });
  multiSelectOriginalStyles.clear();

  document.querySelectorAll('.multi-selected-label').forEach((el) => {
    el.classList.remove('multi-selected-label');
  });
}

function updateMultiSelection(ids: string[]) {
  clearMultiSelectStylesAndDrag();
  if (!map || ids.length === 0) return;

  const validLayers = ids
    .map((id) => featureLayerManager.layers.get(id))
    .filter((l): l is L.Layer => Boolean(l && map?.hasLayer(l)));

  if (validLayers.length === 0) return;

  validLayers.forEach((layer) => {
    const origColor = getLayerStrokeColor(layer);
    if (origColor !== undefined) {
      multiSelectOriginalStyles.set(layer, { color: origColor, dashArray: "" });
      applyStyleToLayer(layer, { color: "#2563eb", dashArray: "4 4" });
    }
    forEachLeafLayer(layer, (leaf) => {
      if (leaf instanceof L.Marker && !(leaf instanceof L.CircleMarker)) {
        const el = (leaf as any).getElement?.();
        el?.classList.add("multi-selected-label");
      }
    });

    enablePerFeatureDrag(layer);
    const coLayers = validLayers.filter((l) => l !== layer);
    const cleanup = enablePixelSpaceDrag(map!, layer, () => coLayers, handleMultiDragEnd);
    multiDragCleanups.push(cleanup);
  });
}

function handleMultiDragEnd() {
  const next = syncFeaturesFromMapLayers();
  localFeaturesSnapshot.value = next;
  holdFeaturePropRenders();
  emit("draw-update", next);
}

watch(
  () => props.multiSelectedFeatureIds,
  (newIds) => {
    multiSelectedIds.value = new Set(newIds ?? []);
    updateMultiSelection(newIds ?? []);
  },
  { immediate: true },
);

watch(
  () => props.featureVisibility,
  (newVisibility: Map<string, boolean>) => {
    if (!newVisibility) return;
    newVisibility.forEach((visible: boolean, featureId: string) => {
      featureLayerManager.toggleFeature(featureId, visible);
    });
    featureLayerManager.layers.forEach((_layer, featureId) => {
      if (!newVisibility.has(featureId)) {
        featureLayerManager.toggleFeature(featureId, false);
      }
    });
    if (selectedFeatureId.value && newVisibility.get(selectedFeatureId.value) !== false) {
      const pm = (map as MapWithPm | null)?.pm;
      const isEditingOrRotating =
        pm?.globalEditModeEnabled?.() || pm?.globalRotateModeEnabled?.();
      if (!isEditingOrRotating) {
        nextTick(() => {
          if (!selectedFeatureId.value) return;
          const currentPm = (map as MapWithPm | null)?.pm;
          if (
            currentPm?.globalEditModeEnabled?.() ||
            currentPm?.globalRotateModeEnabled?.()
          ) {
            return;
          }
          applySelectionEffects(selectedFeatureId.value);
        });
      }
    }
  },
  { deep: true, immediate: true },
);

watch(
  () => [props.canUndo, props.canRedo],
  async () => {
    await nextTick();
    updateHistoryToolbarState();
  },
  { immediate: true },
);
</script>

<style>
.map-point-marker {
  background: none !important;
  border: none !important;
}

.map-point-marker svg {
  display: block;
  width: 12px;
  height: 12px;
}

.city-label-text {
  font-size: var(--label-size, 14px);
  font-weight: var(--label-weight, bold);
  font-style: var(--label-style, normal);
  text-transform: var(--label-transform, none);
  color: var(--label-color, #000);
  background: transparent;
  padding: 0;
  border-radius: 3px;
  border: transparent;
  user-select: none;
}

.label-wrapper {
  position: relative;
  display: inline-block;
  white-space: nowrap;
  padding: 4px;
}

.label-content {
  line-height: 1.2;
  text-align: center;
}

.label-anchor {
  position: absolute;
  width: 10px;
  height: 10px;
  background-color: white;
  border: 1px solid #3b82f6;
  border-radius: 50%;
  display: none;
  cursor: grab;
  z-index: 1000;
}

.label-anchor:active {
  cursor: grabbing;
}

.label-rotate-mode .label-wrapper {
  outline: 1px dashed #3b82f6;
}

.label-selected .label-wrapper,
.city-label-text.label-selected .label-wrapper {
  outline: 2px solid #2563eb;
  background-color: rgba(37, 99, 235, 0.08);
  border-radius: 4px;
}

.multi-selected-label .label-wrapper,
.city-label-text.multi-selected-label .label-wrapper {
  outline: 2px dashed #2563eb;
  background-color: rgba(37, 99, 235, 0.08);
  border-radius: 4px;
}

.label-quick-actions {
  display: none;
  position: absolute;
  top: 50%;
  left: 100%;
  transform: translateY(-50%);
  margin-left: 6px;
  flex-direction: row;
  align-items: center;
  gap: 3px;
  z-index: 1005;
}

.label-selected .label-quick-actions {
  display: flex !important;
}

.label-quick-actions.is-floating {
  display: flex !important;
  position: static !important;
  left: auto !important;
  top: auto !important;
  transform: none !important;
  margin: 0 !important;
}

.feature-floating-actions-container {
  overflow: visible !important;
  background: transparent !important;
  border: none !important;
}

.label-action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 4px;
  background-color: #ffffff;
  border: 1px solid #cbd5e1;
  color: #475569;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
  cursor: pointer;
  padding: 0;
  transition: transform 0.1s ease, background-color 0.1s ease;
}

.label-action-btn:hover {
  transform: scale(1.12);
}

.label-action-btn.action-duplicate {
  border-color: #bfdbfe;
  color: #2563eb;
}

.label-action-btn.action-duplicate:hover {
  background-color: #eff6ff;
  border-color: #2563eb;
  color: #1d4ed8;
}

.label-action-btn.action-delete {
  border-color: #fecaca;
  color: #ef4444;
}

.label-action-btn.action-delete:hover {
  background-color: #fef2f2;
  border-color: #dc2626;
  color: #b91c1c;
}

.label-rotate-mode .label-anchor,
.label-anchor.label-rotate-mode {
  display: block;
}

.label-anchor.rotate-handle {
  top: -20px;
  left: 50%;
  margin-left: -5px;
}

.image-rotate-handle {
  width: 14px !important;
  height: 14px !important;
  background-color: white !important;
  border: 2px solid #3b82f6 !important;
  border-radius: 50% !important;
  cursor: grab !important;
  display: none !important;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.3) !important;
  z-index: 1000 !important;
}

.image-rotate-handle.label-rotate-mode {
  display: block !important;
}

.image-rotate-handle:active {
  cursor: grabbing !important;
}

.label-anchor.rotate-handle::after {
  content: '';
  position: absolute;
  top: 10px;
  left: 4px;
  width: 1px;
  height: 10px;
  background-color: #3b82f6;
  pointer-events: none;
}

.city-selection-ring {
  border-radius: 50%;
  border: 2.5px solid #3b82f6;
  background: transparent;
  box-sizing: border-box;
  pointer-events: none;
}

.arrow-head {
  font-size: 20px;
  color: black;
  transform: rotate(0deg);
}
</style>