import L from "leaflet";
import type { Ref } from "vue";
import type { Feature } from "../typescript/feature";
import type { PmIgnoreOptions } from "../typescript/mapDrawing";
import { extractFeatureFromLayer } from "../utils/mapDrawingFeature";

interface ShapeInteractionState {
  layer: L.Layer;
  featureId: string;
  resizeMarker: L.Marker;
  cleanupDrag?: () => void;
}

export class ShapeScalingService {
  private interaction: ShapeInteractionState | null = null;

  constructor(
    private getMap: () => L.Map | null,
    private getLayerById: (id: string) => L.Layer | undefined,
    private localFeaturesSnapshot: Ref<Feature[]>,
    private getProjectId: () => string,
    private getSelectedYear: () => number,
    private onBeforeEmit: () => void,
    private onUpdate: (features: Feature[]) => void,
  ) {}

  detach() {
    if (!this.interaction) return;
    this.interaction.resizeMarker.remove();
    this.interaction.cleanupDrag?.();
    this.interaction = null;
  }

  attach(featureId: string) {
    this.detach();
    const map = this.getMap();
    if (!map) return;
    const layer = this.getLayerById(featureId);
    if (!layer || (layer instanceof L.ImageOverlay) || layer instanceof L.Marker) return;

    if (typeof (layer as any).getBounds !== 'function' && !(layer instanceof L.LayerGroup)) return;

    let bounds: L.LatLngBounds;
    if (typeof (layer as any).getBounds === 'function') {
        bounds = (layer as any).getBounds();
    } else if (layer instanceof L.LayerGroup) {
        const b = new L.LatLngBounds([]);
        layer.eachLayer(l => {
            if (typeof (l as any).getBounds === 'function') b.extend((l as any).getBounds());
            else if (typeof (l as any).getLatLng === 'function') b.extend((l as any).getLatLng());
        });
        bounds = b;
    } else {
        return;
    }

    if (!bounds.isValid()) return;

    // SE corner drag handle, using same styling as image resize handle
    const resizeMarker = L.marker(bounds.getSouthEast(), {
      icon: L.divIcon({
        className: "image-resize-handle", 
        iconSize: [10, 10],
        iconAnchor: [5, 5],
      }),
      draggable: true,
      zIndexOffset: 1000,
    });
    (resizeMarker.options as PmIgnoreOptions).pmIgnore = true;
    resizeMarker.addTo(map);

    this.interaction = { layer, featureId, resizeMarker };

    const forEachLeafLayer = (l: L.Layer, fn: (l: L.Layer) => void) => {
      if (l instanceof L.LayerGroup) {
        (l as L.LayerGroup).eachLayer((child) => forEachLeafLayer(child, fn));
      } else {
        fn(l);
      }
    };

    const updateMarkerPos = () => {
      let newBounds: L.LatLngBounds;
      if (typeof (layer as any).getBounds === 'function') {
          newBounds = (layer as any).getBounds();
      } else {
          const b = new L.LatLngBounds([]);
          forEachLeafLayer(layer, l => {
              if (typeof (l as any).getBounds === 'function') b.extend((l as any).getBounds());
              else if (typeof (l as any).getLatLng === 'function') b.extend((l as any).getLatLng());
          });
          newBounds = b;
      }
      resizeMarker.setLatLng(newBounds.getSouthEast());
    };

    const onShapeDrag = () => {
      updateMarkerPos();
    };

    forEachLeafLayer(layer, (leaf) => {
      leaf.on("pm:drag", onShapeDrag);
      leaf.on("pm:dragend", onShapeDrag);
    });

    this.interaction.cleanupDrag = () => {
      forEachLeafLayer(layer, (leaf) => {
        leaf.off("pm:drag", onShapeDrag);
        leaf.off("pm:dragend", onShapeDrag);
      });
    };

    let startNwPx: L.Point | null = null;
    let startWidth: number = 0;
    let startHeight: number = 0;
    let leafStates: Map<L.Layer, any> | null = null;

    const toPx = (coords: any): any => {
      if (coords instanceof L.LatLng) return map.latLngToContainerPoint(coords);
      if (Array.isArray(coords)) return coords.map(toPx);
      return coords;
    };

    const applyScale = (pxCoords: any, scaleX: number, scaleY: number): any => {
      if (!startNwPx) return pxCoords;
      if (pxCoords instanceof L.Point) {
        const newX = startNwPx.x + (pxCoords.x - startNwPx.x) * scaleX;
        const newY = startNwPx.y + (pxCoords.y - startNwPx.y) * scaleY;
        return map.containerPointToLatLng(L.point(newX, newY));
      }
      if (Array.isArray(pxCoords)) return pxCoords.map((c) => applyScale(c, scaleX, scaleY));
      return pxCoords;
    };

    resizeMarker.on("dragstart", () => {
      let currentBounds: L.LatLngBounds;
      if (typeof (layer as any).getBounds === 'function') {
          currentBounds = (layer as any).getBounds();
      } else {
          const b = new L.LatLngBounds([]);
          forEachLeafLayer(layer, l => {
              if (typeof (l as any).getBounds === 'function') b.extend((l as any).getBounds());
              else if (typeof (l as any).getLatLng === 'function') b.extend((l as any).getLatLng());
          });
          currentBounds = b;
      }

      const nw = currentBounds.getNorthWest();
      const se = currentBounds.getSouthEast();
      startNwPx = map.latLngToContainerPoint(nw);
      const startSePx = map.latLngToContainerPoint(se);
      
      startWidth = Math.max(startSePx.x - startNwPx.x, 1);
      startHeight = Math.max(startSePx.y - startNwPx.y, 1);

      leafStates = new Map();
      forEachLeafLayer(layer, (sibling) => {
        const s = sibling as any;
        if (typeof s.getLatLngs === 'function') {
          leafStates!.set(sibling, toPx(s.getLatLngs()));
        }
      });
    });

    resizeMarker.on("drag", () => {
      if (!startNwPx || !leafStates) return;
      
      const rawSePx = map.latLngToContainerPoint(resizeMarker.getLatLng());
      const w = Math.max(rawSePx.x - startNwPx.x, 10);
      const h = Math.max(rawSePx.y - startNwPx.y, 10);
      
      const scaleX = w / startWidth;
      const scaleY = h / startHeight;

      leafStates.forEach((pxCoords, leaf) => {
        const newCoords = applyScale(pxCoords, scaleX, scaleY);
        const asAny = leaf as any;
        if (typeof asAny.setLatLngs === 'function') {
          asAny.setLatLngs(newCoords);
        }
      });
    });

    resizeMarker.on("dragend", () => {
      startNwPx = null;
      leafStates = null;

      const extracted = extractFeatureFromLayer(layer, this.getSelectedYear(), this.getProjectId());
      if (!extracted) return;
      
      const idx = this.localFeaturesSnapshot.value.findIndex(
        (f) => String(f.id) === featureId,
      );
      if (idx === -1) return;
      
      const next = [...this.localFeaturesSnapshot.value];
      // Keep old properties that extractFeatureFromLayer doesn't know about or keep id
      next[idx] = { ...extracted, id: next[idx].id, createdAt: next[idx].createdAt, updatedAt: next[idx].updatedAt };
      this.localFeaturesSnapshot.value = next;
      
      this.onBeforeEmit();
      this.onUpdate(next);
      
      updateMarkerPos();
    });
  }

  createTools() {
    return {
      attach: this.attach.bind(this),
      detach: this.detach.bind(this),
    };
  }
}
