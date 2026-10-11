import L from "leaflet";
import type { Ref } from "vue";
import type { Feature } from "../typescript/feature";
import type { ImageInteractionState } from "../typescript/imageOverlay";
import type { MapWithPm, PmIgnoreOptions } from "../typescript/mapDrawing";

export class ImageOverlayService {
  private imageInteraction: ImageInteractionState | null = null;

  constructor(
    private getMap: () => L.Map | null,
    private getLayerById: (id: string) => L.Layer | undefined,
    private localFeaturesSnapshot: Ref<Feature[]>,
    private onBeforeEmit: () => void,
    private onUpdate: (features: Feature[]) => void,
  ) {}

  private getCurrentRotation(): number {
    if (!this.imageInteraction) return 0;
    const layer = this.imageInteraction.overlay as L.Layer & { feature?: Feature };
    if (layer.feature?.properties?.rotation !== undefined) {
      return layer.feature.properties.rotation;
    }
    const idx = this.localFeaturesSnapshot.value.findIndex(
      (f) => String(f.id) === this.imageInteraction!.featureId,
    );
    if (idx !== -1) {
      return this.localFeaturesSnapshot.value[idx].properties?.rotation ?? 0;
    }
    return 0;
  }

  private getRotatedLatLng(
    map: L.Map,
    centerPoint: L.Point,
    unrotatedLatLng: L.LatLng,
    rotationDeg: number,
    pixelOffset: L.Point = L.point(0, 0),
  ): L.LatLng {
    const p = map.latLngToContainerPoint(unrotatedLatLng);
    const dx = p.x + pixelOffset.x - centerPoint.x;
    const dy = p.y + pixelOffset.y - centerPoint.y;

    const rad = (rotationDeg * Math.PI) / 180;
    const cos = Math.cos(rad);
    const sin = Math.sin(rad);

    const rotX = centerPoint.x + (dx * cos - dy * sin);
    const rotY = centerPoint.y + (dx * sin + dy * cos);

    return map.containerPointToLatLng(L.point(rotX, rotY));
  }

  private updateHandlesPosition(overrideRotation?: number) {
    if (!this.imageInteraction) return;
    const map = this.getMap();
    if (!map) return;

    const { overlay, resizeMarker, rotateMarker } = this.imageInteraction;
    const bounds = overlay.getBounds();
    const centerPoint = map.latLngToContainerPoint(bounds.getCenter());
    const rotation = overrideRotation !== undefined ? overrideRotation : this.getCurrentRotation();

    // 1. Resize handle positioned at rotated SouthEast corner
    const rotatedSe = this.getRotatedLatLng(
      map,
      centerPoint,
      bounds.getSouthEast(),
      rotation,
    );
    resizeMarker.setLatLng(rotatedSe);

    // 2. Rotate handle positioned 20px above the rotated North-Center edge
    const northCenter = L.latLng(bounds.getNorth(), bounds.getCenter().lng);
    const rotatedTop = this.getRotatedLatLng(
      map,
      centerPoint,
      northCenter,
      rotation,
      L.point(0, -20),
    );
    rotateMarker.setLatLng(rotatedTop);
  }

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

  private updateImageFeatureRotation(featureId: string, rotation: number) {
    const idx = this.localFeaturesSnapshot.value.findIndex(
      (f) => String(f.id) === featureId,
    );
    if (idx === -1) return;
    const next = [...this.localFeaturesSnapshot.value];
    next[idx] = {
      ...next[idx],
      properties: { ...next[idx].properties, rotation },
    };
    this.localFeaturesSnapshot.value = next;

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
    this.imageInteraction.rotateMarker.remove();
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
    const pixelW = Math.abs(sePx.x - nwPx.x);
    const pixelH = Math.abs(sePx.y - nwPx.y);
    const aspectRatio = pixelH > 0 ? pixelW / pixelH : 1;

    // SE corner drag handle (custom drag implementation to prevent Leaflet MarkerDrag glitches)
    const resizeMarker = L.marker(bounds.getSouthEast(), {
      icon: L.divIcon({
        className: "image-resize-handle",
        iconSize: [12, 12],
        iconAnchor: [6, 6],
      }),
      draggable: false,
      zIndexOffset: 1000,
    });
    (resizeMarker.options as PmIgnoreOptions).pmIgnore = true;
    resizeMarker.addTo(map);

    // Top-center rotate handle
    const rotateMarker = L.marker(L.latLng(bounds.getNorth(), bounds.getCenter().lng), {
      icon: L.divIcon({
        className: "image-rotate-handle label-selected",
        iconSize: [14, 14],
        iconAnchor: [7, 7],
      }),
      draggable: false,
      zIndexOffset: 1000,
    });
    (rotateMarker.options as PmIgnoreOptions).pmIgnore = true;
    rotateMarker.addTo(map);

    const pm = (map as MapWithPm).pm;
    if (pm?.globalRotateModeEnabled?.()) {
      rotateMarker.getElement()?.classList.add("label-rotate-mode");
    }

    this.imageInteraction = { overlay: layer, featureId, resizeMarker, rotateMarker, aspectRatio };

    // Align handles to current rotation
    this.updateHandlesPosition();

    // Handle rotation interaction
    const onRotateMouseDown = (e: MouseEvent) => {
      L.DomEvent.stopPropagation(e as any);
      if (!this.imageInteraction) return;
      map.dragging.disable();

      const containerRect = map.getContainer().getBoundingClientRect();
      const centerLatLng = this.imageInteraction.overlay.getBounds().getCenter();
      const point = map.latLngToContainerPoint(centerLatLng);
      const centerX = containerRect.left + point.x;
      const centerY = containerRect.top + point.y;

      const startAngle = Math.atan2(e.clientY - centerY, e.clientX - centerX);
      const initialRotation = this.getCurrentRotation();
      let liveRotation = initialRotation;

      const onMouseMove = (moveEvent: MouseEvent) => {
        if (!this.imageInteraction) return;
        const currentAngle = Math.atan2(moveEvent.clientY - centerY, moveEvent.clientX - centerX);
        const delta = (currentAngle - startAngle) * (180 / Math.PI);
        liveRotation = Math.round(((initialRotation + delta) % 360 + 360) % 360);

        const imgEl = this.imageInteraction.overlay.getElement();
        if (imgEl) {
          imgEl.style.transformOrigin = "center center";
          const transform = imgEl.style.transform || "";
          if (!transform.includes("rotate")) {
            imgEl.style.transform = `${transform} rotate(${liveRotation}deg)`.trim();
          } else {
            imgEl.style.transform = transform.replace(/rotate\([^)]+\)/, `rotate(${liveRotation}deg)`);
          }
        }

        this.updateHandlesPosition(liveRotation);
      };

      const onMouseUp = () => {
        document.removeEventListener("mousemove", onMouseMove);
        document.removeEventListener("mouseup", onMouseUp);
        map.dragging.enable();

        if (this.imageInteraction) {
          this.updateImageFeatureRotation(featureId, liveRotation);
          this.updateHandlesPosition(liveRotation);
        }
      };

      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    };

    rotateMarker.on("mousedown", (e: L.LeafletMouseEvent) => {
      onRotateMouseDown(e.originalEvent);
    });
    rotateMarker.getElement()?.addEventListener("mousedown", onRotateMouseDown);

    // Handle smooth resize interaction with Top-Left pinned
    const onResizeMouseDown = (e: MouseEvent) => {
      L.DomEvent.stopPropagation(e as any);
      if (!this.imageInteraction) return;
      map.dragging.disable();

      const overlay = this.imageInteraction.overlay;
      const initialBounds = overlay.getBounds();
      const initialCenterPt = map.latLngToContainerPoint(initialBounds.getCenter());
      const initialNW = map.latLngToContainerPoint(initialBounds.getNorthWest());
      const initialSE = map.latLngToContainerPoint(initialBounds.getSouthEast());

      const initialWidth = Math.abs(initialSE.x - initialNW.x);
      const initialHeight = Math.abs(initialSE.y - initialNW.y);
      const currentAspectRatio = this.imageInteraction.aspectRatio;
      const rotation = this.getCurrentRotation();

      const rad = (rotation * Math.PI) / 180;
      const cos = Math.cos(rad);
      const sin = Math.sin(rad);

      // Pinned visual Top-Left (NW) corner in container pixels:
      // Local NW is (-initialWidth / 2, -initialHeight / 2) relative to center
      const pinnedNWWorld = L.point(
        initialCenterPt.x + (-initialWidth / 2 * cos - -initialHeight / 2 * sin),
        initialCenterPt.y + (-initialWidth / 2 * sin + -initialHeight / 2 * cos),
      );

      const onMouseMove = (moveEvent: MouseEvent) => {
        if (!this.imageInteraction) return;
        const containerRect = map.getContainer().getBoundingClientRect();
        const mouseX = moveEvent.clientX - containerRect.left;
        const mouseY = moveEvent.clientY - containerRect.top;

        // Vector from pinned Top-Left corner to mouse in world coordinates
        const vx = mouseX - pinnedNWWorld.x;
        const vy = mouseY - pinnedNWWorld.y;

        // Unrotate by -rotation into local image coordinate space:
        const lx = vx * cos + vy * sin;
        const ly = -vx * sin + vy * cos;

        // Project along diagonal using aspect ratio for natural resizing
        const projectedW = (lx + ly * currentAspectRatio) / 2;
        const newW = Math.max(projectedW, 20);
        const newH = newW / currentAspectRatio;

        // Compute new center in world container coordinates:
        const newCenterX = pinnedNWWorld.x + (newW / 2 * cos - newH / 2 * sin);
        const newCenterY = pinnedNWWorld.y + (newW / 2 * sin + newH / 2 * cos);

        // Convert unrotated bounds back to LatLng
        const unrotatedNW = map.containerPointToLatLng(
          L.point(newCenterX - newW / 2, newCenterY - newH / 2),
        );
        const unrotatedSE = map.containerPointToLatLng(
          L.point(newCenterX + newW / 2, newCenterY + newH / 2),
        );

        overlay.setBounds(L.latLngBounds(unrotatedNW, unrotatedSE));
        this.updateHandlesPosition(rotation);
      };

      const onMouseUp = () => {
        document.removeEventListener("mousemove", onMouseMove);
        document.removeEventListener("mouseup", onMouseUp);
        map.dragging.enable();

        if (this.imageInteraction) {
          this.updateImageFeatureBounds(
            this.imageInteraction.featureId,
            this.imageInteraction.overlay.getBounds(),
          );
          this.updateHandlesPosition();
        }
      };

      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    };

    resizeMarker.on("mousedown", (e: L.LeafletMouseEvent) => {
      onResizeMouseDown(e.originalEvent);
    });
    resizeMarker.getElement()?.addEventListener("mousedown", onResizeMouseDown);

    // Handle moving the entire image
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
      this.updateHandlesPosition();
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
        this.updateHandlesPosition();
      }
      startLatLng = null;
      startBounds = null;
    };

    const onMapMoveOrZoom = () => {
      this.updateHandlesPosition();
    };

    layer.on("mousedown", onOverlayMouseDown);
    map.on("mousemove", onMapMouseMove);
    map.on("mouseup", onMapMouseUp);
    map.on("zoom", onMapMoveOrZoom);
    map.on("zoomend", onMapMoveOrZoom);
    map.on("move", onMapMoveOrZoom);

    this.imageInteraction.cleanupDrag = () => {
      layer.off("mousedown", onOverlayMouseDown);
      map.off("mousemove", onMapMouseMove);
      map.off("mouseup", onMapMouseUp);
      map.off("zoom", onMapMoveOrZoom);
      map.off("zoomend", onMapMoveOrZoom);
      map.off("move", onMapMoveOrZoom);
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
