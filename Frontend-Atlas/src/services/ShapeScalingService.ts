import L from "leaflet";
import type { Ref } from "vue";
import type { Feature } from "../typescript/feature";
import type { PmIgnoreOptions } from "../typescript/mapDrawing";
import { extractFeatureFromLayer } from "../utils/mapDrawingFeature";

// ─── Types ────────────────────────────────────────────────────────────────────

type HandleId = "nw" | "n" | "ne" | "w" | "e" | "sw" | "s" | "se";

export interface PixelRect {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
}

interface HandleDef {
  id: HandleId;
  /** CSS class(es) applied to the marker icon div */
  cls: string;
  /** CSS cursor value shown while dragging this handle */
  cursor: string;
  /** Returns the container pixel position of this handle given the bounding rectangle */
  handlePx: (r: PixelRect) => L.Point;
  /** Returns the fixed anchor container pixel point (opposite corner/edge) */
  anchorPx: (r: PixelRect) => L.Point;
  /** Whether this handle produces horizontal scaling */
  scalesX: boolean;
  /** Whether this handle produces vertical scaling */
  scalesY: boolean;
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

// ─── Handle definitions ───────────────────────────────────────────────────────

const HANDLES: HandleDef[] = [
  // ── Corners ────────────────────────────────────────────────────────────────
  {
    id: "nw",
    cls: "shape-resize-handle shape-resize-handle--corner shape-resize-handle--nw",
    cursor: "nwse-resize",
    handlePx: (r) => L.point(r.minX, r.minY),
    anchorPx: (r) => L.point(r.maxX, r.maxY),
    scalesX: true,
    scalesY: true,
  },
  {
    id: "ne",
    cls: "shape-resize-handle shape-resize-handle--corner shape-resize-handle--ne",
    cursor: "nesw-resize",
    handlePx: (r) => L.point(r.maxX, r.minY),
    anchorPx: (r) => L.point(r.minX, r.maxY),
    scalesX: true,
    scalesY: true,
  },
  {
    id: "sw",
    cls: "shape-resize-handle shape-resize-handle--corner shape-resize-handle--sw",
    cursor: "nesw-resize",
    handlePx: (r) => L.point(r.minX, r.maxY),
    anchorPx: (r) => L.point(r.maxX, r.minY),
    scalesX: true,
    scalesY: true,
  },
  {
    id: "se",
    cls: "shape-resize-handle shape-resize-handle--corner shape-resize-handle--se",
    cursor: "nwse-resize",
    handlePx: (r) => L.point(r.maxX, r.maxY),
    anchorPx: (r) => L.point(r.minX, r.minY),
    scalesX: true,
    scalesY: true,
  },
  // ── Edge midpoints ─────────────────────────────────────────────────────────
  {
    id: "n",
    cls: "shape-resize-handle shape-resize-handle--edge shape-resize-handle--n",
    cursor: "ns-resize",
    handlePx: (r) => L.point((r.minX + r.maxX) / 2, r.minY),
    anchorPx: (r) => L.point((r.minX + r.maxX) / 2, r.maxY),
    scalesX: false,
    scalesY: true,
  },
  {
    id: "s",
    cls: "shape-resize-handle shape-resize-handle--edge shape-resize-handle--s",
    cursor: "ns-resize",
    handlePx: (r) => L.point((r.minX + r.maxX) / 2, r.maxY),
    anchorPx: (r) => L.point((r.minX + r.maxX) / 2, r.minY),
    scalesX: false,
    scalesY: true,
  },
  {
    id: "w",
    cls: "shape-resize-handle shape-resize-handle--edge shape-resize-handle--w",
    cursor: "ew-resize",
    handlePx: (r) => L.point(r.minX, (r.minY + r.maxY) / 2),
    anchorPx: (r) => L.point(r.maxX, (r.minY + r.maxY) / 2),
    scalesX: true,
    scalesY: false,
  },
  {
    id: "e",
    cls: "shape-resize-handle shape-resize-handle--edge shape-resize-handle--e",
    cursor: "ew-resize",
    handlePx: (r) => L.point(r.maxX, (r.minY + r.maxY) / 2),
    anchorPx: (r) => L.point(r.minX, (r.minY + r.maxY) / 2),
    scalesX: true,
    scalesY: false,
  },
];

// ─── Service ──────────────────────────────────────────────────────────────────

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
   * to prevent accidental deselection.
   */
  isTransforming(): boolean {
    return (
      this._isTransforming || Date.now() - this._lastTransformEndTime < 350
    );
  }

  // ─── Public API ─────────────────────────────────────────────────────────────

  detach() {
    if (!this.interaction) return;
    for (const h of this.interaction.handles) h.marker.remove();
    this.interaction.boundingPolyline.remove();
    this.interaction.overlayRenderer.remove();
    this.interaction.cleanup();
    this.interaction = null;
    this._isTransforming = false;
  }

  attach(featureId: string) {
    this.detach();

    const map = this.getMap();
    if (!map) return;

    const layer = this.getLayerById(featureId);
    if (!layer || layer instanceof L.ImageOverlay || layer instanceof L.Marker)
      return;

    const initialRect = this._computePixelRect(layer, map);
    if (!initialRect) return;

    // ── Dedicated SVG renderer for synchronous, zero-lag polyline updates ─────
    const overlayRenderer = L.svg({ padding: 0.5 });

    // ── Dashed bounding outline ──────────────────────────────────────────────
    const boundingPolyline = L.polyline([], {
      renderer: overlayRenderer,
      color: "#475569", // slate-600
      weight: 1.5,
      opacity: 0.9,
      dashArray: "6 4",
      interactive: false,
      className: "shape-bounding-box",
    }).addTo(map);
    (boundingPolyline.options as PmIgnoreOptions).pmIgnore = true;

    // ── Handle markers ───────────────────────────────────────────────────────
    const handles: HandleState[] = HANDLES.map((def) => {
      const pt = def.handlePx(initialRect);
      const marker = L.marker(map.containerPointToLatLng(pt), {
        icon: L.divIcon({
          className: def.cls,
          iconSize: [10, 10],
          iconAnchor: [5, 5],
        }),
        draggable: true,
        zIndexOffset: 1000,
      });
      (marker.options as PmIgnoreOptions).pmIgnore = true;
      marker.addTo(map);

      const setupElement = (el: HTMLElement) => {
        el.style.cursor = def.cursor;
        L.DomEvent.disableClickPropagation(el);
        // NOTE: We deliberately do NOT call stopPropagation on mouseup/pointerup here,
        // allowing the release event to bubble to document/window so Leaflet and global
        // listeners cleanly terminate the drag state.
      };

      marker.on("add", () => {
        const el = marker.getElement();
        if (el) setupElement(el);
      });
      const el = marker.getElement();
      if (el) setupElement(el);

      return { marker, def };
    });

    this.interaction = {
      layer,
      featureId,
      handles,
      boundingPolyline,
      overlayRenderer,
      cleanup: () => {},
    };

    // ── Shared helpers ───────────────────────────────────────────────────────

    const forEachLeafLayer = (l: L.Layer, fn: (l: L.Layer) => void): void => {
      if (l instanceof L.LayerGroup) {
        (l as L.LayerGroup).eachLayer((child) => forEachLeafLayer(child, fn));
      } else {
        fn(l);
      }
    };

    /** Recursively convert latlngs → container pixel points */
    const toPx = (coords: any): any => {
      if (coords instanceof L.LatLng) return map.latLngToContainerPoint(coords);
      if (Array.isArray(coords)) return coords.map(toPx);
      return coords;
    };

    /**
     * Scale a pixel point relative to anchor, returning LatLng.
     */
    const applyScale = (
      pxCoords: any,
      anchorPx: L.Point,
      scaleX: number,
      scaleY: number,
      scalesX: boolean,
      scalesY: boolean,
    ): any => {
      if (pxCoords instanceof L.Point) {
        const newX = scalesX
          ? anchorPx.x + (pxCoords.x - anchorPx.x) * scaleX
          : pxCoords.x;
        const newY = scalesY
          ? anchorPx.y + (pxCoords.y - anchorPx.y) * scaleY
          : pxCoords.y;
        return map.containerPointToLatLng(L.point(newX, newY));
      }
      if (Array.isArray(pxCoords)) {
        return pxCoords.map((c) =>
          applyScale(c, anchorPx, scaleX, scaleY, scalesX, scalesY),
        );
      }
      return pxCoords;
    };

    /** Synchronously update both the outline and all 8 handles from a pixel rect */
    const updateOverlayFromRect = (rect: PixelRect) => {
      const pNW = L.point(rect.minX, rect.minY);
      const pNE = L.point(rect.maxX, rect.minY);
      const pSE = L.point(rect.maxX, rect.maxY);
      const pSW = L.point(rect.minX, rect.maxY);

      const llNW = map.containerPointToLatLng(pNW);
      const llNE = map.containerPointToLatLng(pNE);
      const llSE = map.containerPointToLatLng(pSE);
      const llSW = map.containerPointToLatLng(pSW);

      boundingPolyline.setLatLngs([llNW, llNE, llSE, llSW, llNW]);

      for (const h of handles) {
        const handlePt = h.def.handlePx(rect);
        const handleLL = map.containerPointToLatLng(handlePt);
        h.marker.setLatLng(handleLL);

        // Keep Leaflet draggable internal position aligned with handle
        const draggable = (h.marker.dragging as any)?._draggable;
        if (draggable) {
          const layerPt = map.latLngToLayerPoint(handleLL).round();
          draggable._newPos = layerPt;
          const markerEl = h.marker.getElement();
          if (markerEl) L.DomUtil.setPosition(markerEl, layerPt);
        }
      }
    };

    /** Refresh overlay directly from the layer's current pixel coordinates */
    const refreshOverlay = () => {
      const rect = this._computePixelRect(layer, map);
      if (!rect) return;
      updateOverlayFromRect(rect);
    };

    // Initial overlay draw
    updateOverlayFromRect(initialRect);

    // Follow shape while it is being moved via geoman drag
    const onShapeDrag = () => refreshOverlay();
    forEachLeafLayer(layer, (leaf) => {
      leaf.on("pm:drag", onShapeDrag);
      leaf.on("pm:dragend", onShapeDrag);
    });

    // ── Drag state ───────────────────────────────────────────────────────────
    let activeHandleDef: HandleDef | null = null;
    let startAnchorPx: L.Point | null = null;
    let startHandlePx: L.Point | null = null;
    let startInitialVec: L.Point | null = null;
    let startRect: PixelRect | null = null;
    let startWidth = 0;
    let startHeight = 0;
    let leafStates: Map<L.Layer, any> | null = null;
    let isDraggingActive = false;

    // Shift-key tracking for aspect-ratio lock toggle
    let shiftHeld = false;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Shift") shiftHeld = true;
    };
    const onKeyUp = (e: KeyboardEvent) => {
      if (e.key === "Shift") shiftHeld = false;
    };
    document.addEventListener("keydown", onKeyDown);
    document.addEventListener("keyup", onKeyUp);

    const finishDrag = () => {
      if (!activeHandleDef) return;

      map.dragging.enable();
      window.removeEventListener("pointerup", onGlobalUp, true);
      window.removeEventListener("mouseup", onGlobalUp, true);

      const didTransform = isDraggingActive;
      isDraggingActive = false;
      activeHandleDef = null;

      this._lastTransformEndTime = Date.now();
      setTimeout(() => {
        this._isTransforming = false;
      }, 350);

      startAnchorPx = null;
      startHandlePx = null;
      startInitialVec = null;
      startRect = null;
      leafStates = null;

      if (didTransform) {
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

    // Global release safety net: guarantees drag termination on release anywhere
    const onGlobalUp = (_e: MouseEvent | PointerEvent) => {
      if (activeHandleDef) {
        finishDrag();
      }
    };

    for (const h of handles) {
      const { marker, def } = h;

      marker.on("dragstart", () => {
        activeHandleDef = def;
        isDraggingActive = false;

        const currentRect = this._computePixelRect(layer, map);
        if (!currentRect) return;

        startRect = currentRect;
        startAnchorPx = def.anchorPx(currentRect);
        startHandlePx = def.handlePx(currentRect);
        startWidth = Math.max(currentRect.maxX - currentRect.minX, 1);
        startHeight = Math.max(currentRect.maxY - currentRect.minY, 1);
        startInitialVec = L.point(
          startHandlePx.x - startAnchorPx.x,
          startHandlePx.y - startAnchorPx.y,
        );

        leafStates = new Map();
        forEachLeafLayer(layer, (sibling) => {
          const s = sibling as any;
          if (typeof s.getLatLngs === "function") {
            leafStates!.set(sibling, toPx(s.getLatLngs()));
          }
        });

        // Register global release safety net
        window.addEventListener("pointerup", onGlobalUp, true);
        window.addEventListener("mouseup", onGlobalUp, true);

        // Prevent map panning while dragging handle
        map.dragging.disable();
      });

      marker.on("drag", (e: L.LeafletEvent) => {
        if (
          !activeHandleDef ||
          !startAnchorPx ||
          !startHandlePx ||
          !startInitialVec ||
          !startRect ||
          !leafStates
        ) {
          return;
        }

        // Active button check: abort immediately if mouse button was released
        const orig = (e as any)?.originalEvent as MouseEvent | undefined;
        if (orig && orig.buttons !== undefined && orig.buttons !== 1) {
          finishDrag();
          return;
        }

        const currentMousePx = map.latLngToContainerPoint(marker.getLatLng());

        // Drag threshold check (minimal 4px movement before scaling pipeline begins)
        if (!isDraggingActive) {
          const dist = startHandlePx.distanceTo(currentMousePx);
          if (dist < 4) {
            return;
          }
          isDraggingActive = true;
          this._isTransforming = true;
        }

        const currentVec = L.point(
          currentMousePx.x - startAnchorPx.x,
          currentMousePx.y - startAnchorPx.y,
        );

        let scaleX: number;
        let scaleY: number;

        if (def.scalesX && def.scalesY) {
          // Corner handle: preserve aspect ratio by default (!shiftHeld)
          if (!shiftHeld) {
            const lenSq =
              startInitialVec.x * startInitialVec.x +
              startInitialVec.y * startInitialVec.y;
            const dot =
              lenSq > 0
                ? (currentVec.x * startInitialVec.x +
                    currentVec.y * startInitialVec.y) /
                  lenSq
                : 1;
            const minScale = Math.max(10 / startWidth, 10 / startHeight);
            const uniformScale = Math.max(dot, minScale);
            scaleX = uniformScale;
            scaleY = uniformScale;
          } else {
            // Free scaling when Shift is held
            scaleX = Math.max(Math.abs(currentVec.x), 10) / startWidth;
            scaleY = Math.max(Math.abs(currentVec.y), 10) / startHeight;
          }
        } else if (def.scalesX) {
          // E / W edge handle: single-axis X stretch
          scaleX = Math.max(Math.abs(currentVec.x), 10) / startWidth;
          scaleY = 1;
        } else {
          // N / S edge handle: single-axis Y stretch
          scaleX = 1;
          scaleY = Math.max(Math.abs(currentVec.y), 10) / startHeight;
        }

        // 1. Transform shape geometry
        leafStates.forEach((pxCoords, leaf) => {
          const scaled = applyScale(
            pxCoords,
            startAnchorPx!,
            scaleX,
            scaleY,
            def.scalesX,
            def.scalesY,
          );
          (leaf as any).setLatLngs(scaled);
        });

        // 2. Compute canonical 2D pixel bounding rect directly from the scale transform
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

        const currentRect: PixelRect = {
          minX: Math.min(newMinX, newMaxX),
          maxX: Math.max(newMinX, newMaxX),
          minY: Math.min(newMinY, newMaxY),
          maxY: Math.max(newMinY, newMaxY),
        };

        // 3. Update both the dashed outline and all 8 handles strictly from this pixel rect
        updateOverlayFromRect(currentRect);
      });

      marker.on("dragend", () => {
        finishDrag();
      });
    }

    // Register cleanup
    this.interaction!.cleanup = () => {
      finishDrag();
      forEachLeafLayer(layer, (leaf) => {
        leaf.off("pm:drag", onShapeDrag);
        leaf.off("pm:dragend", onShapeDrag);
      });
      document.removeEventListener("keydown", onKeyDown);
      document.removeEventListener("keyup", onKeyUp);
      window.removeEventListener("pointerup", onGlobalUp, true);
      window.removeEventListener("mouseup", onGlobalUp, true);
      map.dragging.enable();
    };
  }

  // ─── Private helpers ─────────────────────────────────────────────────────

  /**
   * Computes the 2D bounding rectangle of all vertices of the layer in screen container pixels.
   */
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

    const forEachLeaf = (l: L.Layer) => {
      if (l instanceof L.LayerGroup) {
        l.eachLayer(forEachLeaf);
      } else {
        const s = l as any;
        if (typeof s.getLatLngs === "function") {
          traverse(s.getLatLngs());
        } else if (typeof s.getLatLng === "function") {
          traverse(s.getLatLng());
        }
      }
    };

    forEachLeaf(layer);

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
