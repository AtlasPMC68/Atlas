import L from "leaflet";
import type { Ref } from "vue";
import type { Feature } from "../typescript/feature";
import type { PmIgnoreOptions } from "../typescript/mapDrawing";
import { extractFeatureFromLayer } from "../utils/mapDrawingFeature";

export const MIN_DRAG_THRESHOLD_PX = 4;
export const INTERACTION_COOLDOWN_MS = 350;
export const MIN_SHAPE_DIMENSION_PX = 10;

const CORNER_HANDLE_SIZE = 10;
const CORNER_HANDLE_ANCHOR = 5;
const EDGE_HANDLE_SIZE = 8;
const EDGE_HANDLE_ANCHOR = 4;

export interface PixelRect {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

type HandleId = "nw" | "n" | "ne" | "w" | "e" | "sw" | "s" | "se";

interface HandleDef {
  id: HandleId;
  cls: string;
  cursor: string;
  scalesX: boolean;
  scalesY: boolean;
  iconSize: [number, number];
  iconAnchor: [number, number];
  handlePx: (r: PixelRect) => L.Point;
  anchorPx: (r: PixelRect) => L.Point;
}

interface HandleState {
  marker: L.Marker;
  def: HandleDef;
}

interface ShapeInteractionState {
  layer: L.Layer;
  featureId: string;
  handles: HandleState[];
  boundingPolyline: L.Polyline;
  overlayRenderer: L.SVG;
  cleanup: () => void;
}

interface DragSession {
  def: HandleDef;
  startAnchorPx: L.Point;
  startHandlePx: L.Point;
  startInitialVec: L.Point;
  startRect: PixelRect;
  startWidth: number;
  startHeight: number;
  leafStates: Map<L.Layer, any>;
  isScalingActive: boolean;
  reEnableScrollWheel: boolean;
  reEnableTouchZoom: boolean;
}

const createCornerHandle = (
  id: "nw" | "ne" | "sw" | "se",
  cursor: string,
  handlePx: (r: PixelRect) => L.Point,
  anchorPx: (r: PixelRect) => L.Point,
): HandleDef => ({
  id,
  cls: `shape-resize-handle shape-resize-handle--corner shape-resize-handle--${id}`,
  cursor,
  scalesX: true,
  scalesY: true,
  iconSize: [CORNER_HANDLE_SIZE, CORNER_HANDLE_SIZE],
  iconAnchor: [CORNER_HANDLE_ANCHOR, CORNER_HANDLE_ANCHOR],
  handlePx,
  anchorPx,
});

const createEdgeHandle = (
  id: "n" | "s" | "w" | "e",
  cursor: string,
  scalesX: boolean,
  scalesY: boolean,
  handlePx: (r: PixelRect) => L.Point,
  anchorPx: (r: PixelRect) => L.Point,
): HandleDef => ({
  id,
  cls: `shape-resize-handle shape-resize-handle--edge shape-resize-handle--${id}`,
  cursor,
  scalesX,
  scalesY,
  iconSize: [EDGE_HANDLE_SIZE, EDGE_HANDLE_SIZE],
  iconAnchor: [EDGE_HANDLE_ANCHOR, EDGE_HANDLE_ANCHOR],
  handlePx,
  anchorPx,
});

const HANDLES: HandleDef[] = [
  createCornerHandle("nw", "nwse-resize", (r) => L.point(r.minX, r.minY), (r) => L.point(r.maxX, r.maxY)),
  createCornerHandle("ne", "nesw-resize", (r) => L.point(r.maxX, r.minY), (r) => L.point(r.minX, r.maxY)),
  createCornerHandle("sw", "nesw-resize", (r) => L.point(r.minX, r.maxY), (r) => L.point(r.maxX, r.minY)),
  createCornerHandle("se", "nwse-resize", (r) => L.point(r.maxX, r.maxY), (r) => L.point(r.minX, r.minY)),

  createEdgeHandle("n", "ns-resize", false, true, (r) => L.point((r.minX + r.maxX) / 2, r.minY), (r) => L.point((r.minX + r.maxX) / 2, r.maxY)),
  createEdgeHandle("s", "ns-resize", false, true, (r) => L.point((r.minX + r.maxX) / 2, r.maxY), (r) => L.point((r.minX + r.maxX) / 2, r.minY)),
  createEdgeHandle("w", "ew-resize", true, false, (r) => L.point(r.minX, (r.minY + r.maxY) / 2), (r) => L.point(r.maxX, (r.minY + r.maxY) / 2)),
  createEdgeHandle("e", "ew-resize", true, false, (r) => L.point(r.maxX, (r.minY + r.maxY) / 2), (r) => L.point(r.minX, (r.minY + r.maxY) / 2)),
];

/**
 * Projects the current drag vector onto the initial diagonal vector to produce
 * a uniform scale factor: (v_curr · v_init) / |v_init|², clamped to MIN_SHAPE_DIMENSION_PX.
 */
function projectAspectRatio(
  currentVec: L.Point,
  initialVec: L.Point,
  startWidth: number,
  startHeight: number,
): number {
  const lenSq = initialVec.x * initialVec.x + initialVec.y * initialVec.y;
  const dot = lenSq > 0 ? (currentVec.x * initialVec.x + currentVec.y * initialVec.y) / lenSq : 1;
  const minScale = Math.max(MIN_SHAPE_DIMENSION_PX / startWidth, MIN_SHAPE_DIMENSION_PX / startHeight);
  return Math.max(dot, minScale);
}

function forEachLeafLayer(layer: L.Layer, callback: (leaf: L.Layer) => void): void {
  if (layer instanceof L.LayerGroup) {
    layer.eachLayer((child) => forEachLeafLayer(child, callback));
  } else {
    callback(layer);
  }
}

function toContainerPoints(map: L.Map, coords: any): any {
  if (coords instanceof L.LatLng) return map.latLngToContainerPoint(coords);
  if (Array.isArray(coords)) return coords.map((c) => toContainerPoints(map, c));
  return coords;
}

function applyScaleToPoints(
  map: L.Map,
  pxCoords: any,
  anchorPx: L.Point,
  scaleX: number,
  scaleY: number,
  scalesX: boolean,
  scalesY: boolean,
): any {
  if (pxCoords instanceof L.Point) {
    const x = scalesX ? anchorPx.x + (pxCoords.x - anchorPx.x) * scaleX : pxCoords.x;
    const y = scalesY ? anchorPx.y + (pxCoords.y - anchorPx.y) * scaleY : pxCoords.y;
    return map.containerPointToLatLng(L.point(x, y));
  }
  if (Array.isArray(pxCoords)) {
    return pxCoords.map((c) => applyScaleToPoints(map, c, anchorPx, scaleX, scaleY, scalesX, scalesY));
  }
  return pxCoords;
}

export class ShapeScalingService {
  private interaction: ShapeInteractionState | null = null;
  private _isTransforming = false;
  private _lastTransformEndTime = 0;

  constructor(
    private getMap: () => L.Map | null,
    private getLayerById: (id: string) => L.Layer | undefined,
    private localFeaturesSnapshot: Ref<Feature[]>,
    private getProjectId: () => string,
    private getSelectedYear: () => number,
    private onBeforeEmit: () => void,
    private onUpdate: (features: Feature[]) => void,
  ) {}

  /**
   * Returns true while any handle is actively scaling or within a post-scaling cooldown
   * to prevent accidental map deselection.
   */
  isTransforming(): boolean {
    return (
      this._isTransforming ||
      Date.now() - this._lastTransformEndTime < INTERACTION_COOLDOWN_MS
    );
  }

  detach(): void {
    if (!this.interaction) return;
    for (const h of this.interaction.handles) h.marker.remove();
    this.interaction.boundingPolyline.remove();
    this.interaction.overlayRenderer.remove();
    this.interaction.cleanup();
    this.interaction = null;
    this._isTransforming = false;
  }

  attach(featureId: string): void {
    this.detach();

    const map = this.getMap();
    if (!map) return;

    const layer = this.getLayerById(featureId);
    if (!layer || layer instanceof L.ImageOverlay || layer instanceof L.Marker) {
      return;
    }

    const initialRect = this._computePixelRect(layer, map);
    if (!initialRect) return;

    const overlayRenderer = L.svg({ padding: 0.5 });
    const boundingPolyline = L.polyline([], {
      renderer: overlayRenderer,
      color: "#475569",
      weight: 1.5,
      opacity: 0.9,
      dashArray: "6 4",
      interactive: false,
      className: "shape-bounding-box",
    }).addTo(map);
    (boundingPolyline.options as PmIgnoreOptions).pmIgnore = true;

    const handles: HandleState[] = HANDLES.map((def) => {
      const pt = def.handlePx(initialRect);
      const marker = L.marker(map.containerPointToLatLng(pt), {
        icon: L.divIcon({
          className: def.cls,
          iconSize: def.iconSize,
          iconAnchor: def.iconAnchor,
        }),
        draggable: true,
        zIndexOffset: 1000,
      });
      (marker.options as PmIgnoreOptions).pmIgnore = true;
      marker.addTo(map);

      const bindElement = () => {
        const el = marker.getElement();
        if (el) {
          el.style.cursor = def.cursor;
          L.DomEvent.disableClickPropagation(el);
        }
      };
      marker.on("add", bindElement);
      bindElement();

      return { marker, def };
    });

    const updateOverlayFromRect = (rect: PixelRect) => {
      const llNW = map.containerPointToLatLng(L.point(rect.minX, rect.minY));
      const llNE = map.containerPointToLatLng(L.point(rect.maxX, rect.minY));
      const llSE = map.containerPointToLatLng(L.point(rect.maxX, rect.maxY));
      const llSW = map.containerPointToLatLng(L.point(rect.minX, rect.maxY));

      boundingPolyline.setLatLngs([llNW, llNE, llSE, llSW, llNW]);

      for (const h of handles) {
        const handlePt = h.def.handlePx(rect);
        const handleLL = map.containerPointToLatLng(handlePt);
        h.marker.setLatLng(handleLL);

        const draggable = (h.marker.dragging as any)?._draggable;
        if (draggable) {
          const layerPt = map.latLngToLayerPoint(handleLL).round();
          draggable._newPos = layerPt;
          const markerEl = h.marker.getElement();
          if (markerEl) L.DomUtil.setPosition(markerEl, layerPt);
        }
      }
    };

    const refreshOverlay = () => {
      const rect = this._computePixelRect(layer, map);
      if (rect) updateOverlayFromRect(rect);
    };

    updateOverlayFromRect(initialRect);

    const onShapeDrag = () => refreshOverlay();
    forEachLeafLayer(layer, (leaf) => {
      leaf.on("pm:drag", onShapeDrag);
      leaf.on("pm:dragend", onShapeDrag);
    });

    let dragSession: DragSession | null = null;
    let shiftHeld = false;

    const onMapZoomOrReset = () => {
      if (!dragSession?.isScalingActive) {
        refreshOverlay();
      }
    };
    map.on("zoomend", onMapZoomOrReset);
    map.on("viewreset", onMapZoomOrReset);

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Shift") shiftHeld = true;
    };
    const onKeyUp = (e: KeyboardEvent) => {
      if (e.key === "Shift") shiftHeld = false;
    };
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("keyup", onKeyUp);

    const finishDrag = () => {
      if (!dragSession) return;
      const { isScalingActive, reEnableScrollWheel, reEnableTouchZoom } = dragSession;
      dragSession = null;

      map.dragging.enable();
      if (reEnableScrollWheel) map.scrollWheelZoom?.enable();
      if (reEnableTouchZoom) map.touchZoom?.enable();

      window.removeEventListener("pointerup", onGlobalUp, true);
      window.removeEventListener("mouseup", onGlobalUp, true);

      this._lastTransformEndTime = Date.now();
      setTimeout(() => {
        this._isTransforming = false;
      }, INTERACTION_COOLDOWN_MS);

      if (isScalingActive) {
        const extracted = extractFeatureFromLayer(
          layer,
          this.getSelectedYear(),
          this.getProjectId(),
        );
        if (extracted) {
          const idx = this.localFeaturesSnapshot.value.findIndex(
            (f) => String(f.id) === featureId,
          );
          if (idx !== -1) {
            const next = [...this.localFeaturesSnapshot.value];
            next[idx] = {
              ...extracted,
              id: next[idx].id,
              createdAt: next[idx].createdAt,
              updatedAt: next[idx].updatedAt,
            };
            this.localFeaturesSnapshot.value = next;
            this.onBeforeEmit();
            this.onUpdate(next);
          }
        }
      }

      refreshOverlay();
    };

    const onGlobalUp = () => {
      if (dragSession) finishDrag();
    };

    for (const h of handles) {
      const { marker, def } = h;

      marker.on("dragstart", () => {
        const currentRect = this._computePixelRect(layer, map);
        if (!currentRect) return;

        const startAnchorPx = def.anchorPx(currentRect);
        const startHandlePx = def.handlePx(currentRect);
        const leafStates = new Map<L.Layer, any>();

        forEachLeafLayer(layer, (sibling) => {
          const s = sibling as any;
          if (typeof s.getLatLngs === "function") {
            leafStates.set(sibling, toContainerPoints(map, s.getLatLngs()));
          }
        });

        const reEnableScrollWheel = Boolean(map.scrollWheelZoom?.enabled());
        const reEnableTouchZoom = Boolean(map.touchZoom?.enabled());
        if (reEnableScrollWheel) map.scrollWheelZoom.disable();
        if (reEnableTouchZoom) map.touchZoom.disable();
        map.dragging.disable();

        window.addEventListener("pointerup", onGlobalUp, true);
        window.addEventListener("mouseup", onGlobalUp, true);

        dragSession = {
          def,
          startAnchorPx,
          startHandlePx,
          startInitialVec: L.point(
            startHandlePx.x - startAnchorPx.x,
            startHandlePx.y - startAnchorPx.y,
          ),
          startRect: currentRect,
          startWidth: Math.max(currentRect.maxX - currentRect.minX, 1),
          startHeight: Math.max(currentRect.maxY - currentRect.minY, 1),
          leafStates,
          isScalingActive: false,
          reEnableScrollWheel,
          reEnableTouchZoom,
        };
      });

      marker.on("drag", (e: L.LeafletEvent) => {
        if (!dragSession) return;

        const orig = (e as any)?.originalEvent as MouseEvent | undefined;
        if (orig?.buttons !== undefined && orig.buttons !== 1) {
          finishDrag();
          return;
        }

        const currentMousePx = map.latLngToContainerPoint(marker.getLatLng());

        if (!dragSession.isScalingActive) {
          if (dragSession.startHandlePx.distanceTo(currentMousePx) < MIN_DRAG_THRESHOLD_PX) {
            return;
          }
          dragSession.isScalingActive = true;
          this._isTransforming = true;
        }

        const {
          startAnchorPx,
          startInitialVec,
          startWidth,
          startHeight,
          startRect,
          leafStates,
        } = dragSession;

        const currentVec = L.point(
          currentMousePx.x - startAnchorPx.x,
          currentMousePx.y - startAnchorPx.y,
        );

        let scaleX: number;
        let scaleY: number;

        if (def.scalesX && def.scalesY) {
          if (!shiftHeld) {
            const uniformScale = projectAspectRatio(currentVec, startInitialVec, startWidth, startHeight);
            scaleX = uniformScale;
            scaleY = uniformScale;
          } else {
            scaleX = Math.max(Math.abs(currentVec.x), MIN_SHAPE_DIMENSION_PX) / startWidth;
            scaleY = Math.max(Math.abs(currentVec.y), MIN_SHAPE_DIMENSION_PX) / startHeight;
          }
        } else if (def.scalesX) {
          scaleX = Math.max(Math.abs(currentVec.x), MIN_SHAPE_DIMENSION_PX) / startWidth;
          scaleY = 1;
        } else {
          scaleX = 1;
          scaleY = Math.max(Math.abs(currentVec.y), MIN_SHAPE_DIMENSION_PX) / startHeight;
        }

        leafStates.forEach((pxCoords, leaf) => {
          const scaled = applyScaleToPoints(
            map,
            pxCoords,
            startAnchorPx,
            scaleX,
            scaleY,
            def.scalesX,
            def.scalesY,
          );
          (leaf as any).setLatLngs(scaled);
        });

        const newMinX = def.scalesX
          ? startAnchorPx.x + (startRect.minX - startAnchorPx.x) * scaleX
          : startRect.minX;
        const newMaxX = def.scalesX
          ? startAnchorPx.x + (startRect.maxX - startAnchorPx.x) * scaleX
          : startRect.maxX;
        const newMinY = def.scalesY
          ? startAnchorPx.y + (startRect.minY - startAnchorPx.y) * scaleY
          : startRect.minY;
        const newMaxY = def.scalesY
          ? startAnchorPx.y + (startRect.maxY - startAnchorPx.y) * scaleY
          : startRect.maxY;

        updateOverlayFromRect({
          minX: Math.min(newMinX, newMaxX),
          maxX: Math.max(newMinX, newMaxX),
          minY: Math.min(newMinY, newMaxY),
          maxY: Math.max(newMinY, newMaxY),
        });
      });

      marker.on("dragend", () => finishDrag());
    }

    this.interaction = {
      layer,
      featureId,
      handles,
      boundingPolyline,
      overlayRenderer,
      cleanup: () => {
        finishDrag();
        forEachLeafLayer(layer, (leaf) => {
          leaf.off("pm:drag", onShapeDrag);
          leaf.off("pm:dragend", onShapeDrag);
        });
        map.off("zoomend", onMapZoomOrReset);
        map.off("viewreset", onMapZoomOrReset);
        document.removeEventListener("keydown", onKeyDown);
        document.removeEventListener("keyup", onKeyUp);
        window.removeEventListener("pointerup", onGlobalUp, true);
        window.removeEventListener("mouseup", onGlobalUp, true);
        map.dragging.enable();
      },
    };
  }

  private _computePixelRect(layer: L.Layer, map: L.Map): PixelRect | null {
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;

    const traverse = (coords: any) => {
      if (coords instanceof L.LatLng) {
        const pt = map.latLngToContainerPoint(coords);
        if (pt.x < minX) minX = pt.x;
        if (pt.x > maxX) maxX = pt.x;
        if (pt.y < minY) minY = pt.y;
        if (pt.y > maxY) maxY = pt.y;
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
      } else if (typeof s.getLatLng === "function") {
        traverse(s.getLatLng());
      }
    });

    if (!isFinite(minX) || !isFinite(maxX)) return null;
    return { minX, minY, maxX, maxY };
  }

  createTools() {
    return {
      attach: this.attach.bind(this),
      detach: this.detach.bind(this),
      isTransforming: this.isTransforming.bind(this),
    };
  }
}
