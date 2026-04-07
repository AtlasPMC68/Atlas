import L from "leaflet";
import type { Ref } from "vue";
import type { Feature } from "../typescript/feature";
import type { ImageInteractionState } from "../typescript/imageOverlay";
import type { PmIgnoreOptions } from "../typescript/mapDrawing";

export class ImageOverlayService {
  private imageInteraction: ImageInteractionState | null = null;

  constructor(
    private getMap: () => L.Map | null,
    private getLayerById: (id: string) => L.Layer | undefined,
    private localFeaturesSnapshot: Ref<Feature[]>,
    private onBeforeEmit: () => void,
    private onUpdate: (features: Feature[]) => void,
  ) {}

  private updateImageFeatureBounds(featureId: string, bounds: L.LatLngBounds) {
    const sw = bounds.getSouthWest();
    const ne = bounds.getNorthEast();
    const boundsArray: [[number, number], [number, number]] = [
      [sw.lat, sw.lng],
      [ne.lat, ne.lng],
    ];
    const idx = this.localFeaturesSnapshot.value.findIndex(
      (f) => String(f.id) === featureId,
    );
    if (idx === -1) return;
    const next = [...this.localFeaturesSnapshot.value];
    next[idx] = {
      ...next[idx],
      properties: { ...next[idx].properties, bounds: boundsArray },
    };
    this.localFeaturesSnapshot.value = next;

    // Also update the feature stored on the layer itself so that
    // extractFeatureFromLayer returns the updated bounds during save.
    const layer = this.getLayerById(featureId);
    if (layer) {
      const layerWithFeature = layer as L.Layer & { feature?: (typeof next)[0] };
      if (layerWithFeature.feature) {
        layerWithFeature.feature = next[idx];
      }
    }

    this.onBeforeEmit();
    this.onUpdate(next);
  }

  detach() {
    if (!this.imageInteraction) return;
    this.imageInteraction.resizeMarker.remove();
    this.imageInteraction.cleanupDrag?.();
    this.imageInteraction = null;
  }

  attach(featureId: string) {
    this.detach();
    const map = this.getMap();
    if (!map) return;
    const layer = this.getLayerById(featureId);
    if (!(layer instanceof L.ImageOverlay)) return;

    const bounds = layer.getBounds();

    // Pixel aspect ratio (width/height) at current zoom — preserved during resize
    const nwPx = map.latLngToContainerPoint(bounds.getNorthWest());
    const sePx = map.latLngToContainerPoint(bounds.getSouthEast());
    const aspectRatio = Math.abs(sePx.x - nwPx.x) / Math.abs(sePx.y - nwPx.y);

    // SE corner drag handle
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

    resizeMarker.on("drag", () => {
      if (!this.imageInteraction) return;
      const nw = this.imageInteraction.overlay.getBounds().getNorthWest();
      const nwPx = map.latLngToContainerPoint(nw);
      const rawSePx = map.latLngToContainerPoint(resizeMarker.getLatLng());
      // Constrain to aspect ratio: fix width, derive height
      const w = Math.max(rawSePx.x - nwPx.x, 10);
      const h = w / this.imageInteraction.aspectRatio;
      const constrainedSe = map.containerPointToLatLng(
        L.point(nwPx.x + w, nwPx.y + h),
      );
      this.imageInteraction.overlay.setBounds(L.latLngBounds(nw, constrainedSe));
      resizeMarker.setLatLng(constrainedSe);
    });

    resizeMarker.on("dragend", () => {
      if (!this.imageInteraction) return;
      this.updateImageFeatureBounds(
        this.imageInteraction.featureId,
        this.imageInteraction.overlay.getBounds(),
      );
    });

    this.imageInteraction = { overlay: layer, featureId, resizeMarker, aspectRatio };

    // The image is in its own pane above the canvas so it receives native pointer
    // events — we can use overlay.on("mousedown") directly here.
    let isDragging = false;
    let startLatLng: L.LatLng | null = null;
    let startBounds: L.LatLngBounds | null = null;

    const onOverlayMouseDown = (e: L.LeafletMouseEvent) => {
      if (!this.imageInteraction) return;
      L.DomEvent.stopPropagation(e);
      isDragging = true;
      startLatLng = e.latlng;
      startBounds = this.imageInteraction.overlay.getBounds();
      map.dragging.disable();
    };

    const onMapMouseMove = (e: L.LeafletMouseEvent) => {
      if (!isDragging || !startLatLng || !startBounds || !this.imageInteraction) return;
      const startPx = map.latLngToContainerPoint(startLatLng);
      const nowPx = map.latLngToContainerPoint(e.latlng);
      const dx = nowPx.x - startPx.x;
      const dy = nowPx.y - startPx.y;
      const swPx = map.latLngToContainerPoint(startBounds.getSouthWest());
      const nePx = map.latLngToContainerPoint(startBounds.getNorthEast());
      const newBounds = L.latLngBounds(
        map.containerPointToLatLng(L.point(swPx.x + dx, swPx.y + dy)),
        map.containerPointToLatLng(L.point(nePx.x + dx, nePx.y + dy)),
      );
      this.imageInteraction.overlay.setBounds(newBounds);
      this.imageInteraction.resizeMarker.setLatLng(newBounds.getSouthEast());
    };

    const onMapMouseUp = () => {
      if (!isDragging) return;
      isDragging = false;
      map.dragging.enable();
      if (this.imageInteraction) {
        this.updateImageFeatureBounds(
          this.imageInteraction.featureId,
          this.imageInteraction.overlay.getBounds(),
        );
      }
      startLatLng = null;
      startBounds = null;
    };

    layer.on("mousedown", onOverlayMouseDown);
    map.on("mousemove", onMapMouseMove);
    map.on("mouseup", onMapMouseUp);

    this.imageInteraction.cleanupDrag = () => {
      layer.off("mousedown", onOverlayMouseDown);
      map.off("mousemove", onMapMouseMove);
      map.off("mouseup", onMapMouseUp);
      map.dragging.enable();
    };
  }

  createTools() {
    return {
      attach: this.attach.bind(this),
      detach: this.detach.bind(this),
    };
  }
}
