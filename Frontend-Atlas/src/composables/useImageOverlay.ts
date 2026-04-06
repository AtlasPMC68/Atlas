import L from "leaflet";
import type { Ref } from "vue";
import type { Feature } from "../typescript/feature";
import type { PmIgnoreOptions } from "../typescript/mapDrawing";

interface ImageInteractionState {
  overlay: L.ImageOverlay;
  featureId: string;
  resizeMarker: L.Marker;
  aspectRatio: number; // pixel width / pixel height at attach time
  cleanupDrag?: () => void;
}

export function useImageOverlay({
  getMap,
  getLayerById,
  localFeaturesSnapshot,
  onBeforeEmit,
  onUpdate,
}: {
  getMap: () => L.Map | null;
  getLayerById: (id: string) => L.Layer | undefined;
  localFeaturesSnapshot: Ref<Feature[]>;
  onBeforeEmit: () => void;
  onUpdate: (features: Feature[]) => void;
}) {
  let imageInteraction: ImageInteractionState | null = null;

  function updateImageFeatureBounds(featureId: string, bounds: L.LatLngBounds) {
    const sw = bounds.getSouthWest();
    const ne = bounds.getNorthEast();
    const boundsArray: [[number, number], [number, number]] = [
      [sw.lat, sw.lng],
      [ne.lat, ne.lng],
    ];
    const idx = localFeaturesSnapshot.value.findIndex(
      (f) => String(f.id) === featureId,
    );
    if (idx === -1) return;
    const next = [...localFeaturesSnapshot.value];
    next[idx] = {
      ...next[idx],
      properties: { ...next[idx].properties, bounds: boundsArray },
    };
    localFeaturesSnapshot.value = next;

    // Also update the feature stored on the layer itself so that
    // extractFeatureFromLayer returns the updated bounds during save.
    const layer = getLayerById(featureId);
    if (layer) {
      const layerWithFeature = layer as L.Layer & { feature?: (typeof next)[0] };
      if (layerWithFeature.feature) {
        layerWithFeature.feature = next[idx];
      }
    }

    onBeforeEmit();
    onUpdate(next);
  }

  function detach() {
    if (!imageInteraction) return;
    imageInteraction.resizeMarker.remove();
    imageInteraction.cleanupDrag?.();
    imageInteraction = null;
  }

  function attach(featureId: string) {
    detach();
    const map = getMap();
    if (!map) return;
    const layer = getLayerById(featureId);
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
      if (!imageInteraction) return;
      const nw = imageInteraction.overlay.getBounds().getNorthWest();
      const nwPx = map.latLngToContainerPoint(nw);
      const rawSePx = map.latLngToContainerPoint(resizeMarker.getLatLng());
      // Constrain to aspect ratio: fix width, derive height
      const w = Math.max(rawSePx.x - nwPx.x, 10);
      const h = w / imageInteraction.aspectRatio;
      const constrainedSe = map.containerPointToLatLng(
        L.point(nwPx.x + w, nwPx.y + h),
      );
      imageInteraction.overlay.setBounds(L.latLngBounds(nw, constrainedSe));
      resizeMarker.setLatLng(constrainedSe);
    });

    resizeMarker.on("dragend", () => {
      if (!imageInteraction) return;
      updateImageFeatureBounds(
        imageInteraction.featureId,
        imageInteraction.overlay.getBounds(),
      );
    });

    imageInteraction = { overlay: layer, featureId, resizeMarker, aspectRatio };

    // The image is in its own pane above the canvas so it receives native pointer
    // events — we can use overlay.on("mousedown") directly here.
    let isDragging = false;
    let startLatLng: L.LatLng | null = null;
    let startBounds: L.LatLngBounds | null = null;

    const onOverlayMouseDown = (e: L.LeafletMouseEvent) => {
      if (!imageInteraction) return;
      L.DomEvent.stopPropagation(e);
      isDragging = true;
      startLatLng = e.latlng;
      startBounds = imageInteraction.overlay.getBounds();
      map.dragging.disable();
    };

    const onMapMouseMove = (e: L.LeafletMouseEvent) => {
      if (!isDragging || !startLatLng || !startBounds || !imageInteraction) return;
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
      imageInteraction.overlay.setBounds(newBounds);
      imageInteraction.resizeMarker.setLatLng(newBounds.getSouthEast());
    };

    const onMapMouseUp = () => {
      if (!isDragging) return;
      isDragging = false;
      map.dragging.enable();
      if (imageInteraction) {
        updateImageFeatureBounds(imageInteraction.featureId, imageInteraction.overlay.getBounds());
      }
      startLatLng = null;
      startBounds = null;
    };

    layer.on("mousedown", onOverlayMouseDown);
    map.on("mousemove", onMapMouseMove);
    map.on("mouseup", onMapMouseUp);

    imageInteraction.cleanupDrag = () => {
      layer.off("mousedown", onOverlayMouseDown);
      map.off("mousemove", onMapMouseMove);
      map.off("mouseup", onMapMouseUp);
      map.dragging.enable();
    };
  }

  return { attach, detach };
}
