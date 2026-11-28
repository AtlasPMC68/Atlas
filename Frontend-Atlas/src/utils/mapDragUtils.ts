import L from "leaflet";
import type { Feature } from "../typescript/feature";

export type PmDraggableLayer = L.Layer & {
  pm?: { enableLayerDrag?: () => void; disableLayerDrag?: () => void };
};

export function forEachLeafLayer(layer: L.Layer, fn: (l: L.Layer) => void) {
  if (!layer) return;
  if (layer instanceof L.LayerGroup) {
    (layer as L.LayerGroup).eachLayer((child) => forEachLeafLayer(child, fn));
  } else {
    fn(layer);
  }
}

export function enablePerFeatureDrag(layer: L.Layer) {
  forEachLeafLayer(layer, (leaf) => {
    if ((leaf as { options?: { interactive?: boolean } }).options?.interactive === false) return;
    try {
      (leaf as PmDraggableLayer).pm?.enableLayerDrag?.();
    } catch (e) {
      console.warn("Failed to enable drag on leaf layer:", e);
    }
  });
}

export function disablePerFeatureDrag(layer: L.Layer) {
  forEachLeafLayer(layer, (leaf) => {
    try {
      (leaf as PmDraggableLayer).pm?.disableLayerDrag?.();
    } catch (e) {
      // Ignore internal Geoman errors when disabling unsupported layers
    }
  });
}

/**
 * Override geoman's lat/lng-delta drag with a pixel-space translation so that
 * shapes keep their on-screen appearance regardless of latitude.
 *
 * Supports single feature drag or co-dragging multiple selected layers.
 *
 * Returns a cleanup function to remove all listeners.
 */
export function enablePixelSpaceDrag(
  map: L.Map,
  featureLayer: L.Layer,
  getCoDraggableLayers?: () => L.Layer[],
  onCoDragEnd?: () => void,
): () => void {
  // Track current mouse pixel position while the map mousemove listener is active.
  let currentMousePx: L.Point = L.point(0, 0);
  let dragState: {
    startMousePx: L.Point;
    leafStates: Map<L.Layer, unknown>;
  } | null = null;

  const onMapMouseMove = (e: L.LeafletMouseEvent) => {
    currentMousePx = map.latLngToContainerPoint(e.latlng);
  };

  // Recursively convert a LatLng / LatLng[] / LatLng[][] hierarchy to pixels.
  const toPx = (coords: unknown): unknown => {
    if (coords instanceof L.LatLng) return map.latLngToContainerPoint(coords);
    if (Array.isArray(coords)) return coords.map(toPx);
    return coords;
  };

  // Recursively translate pixel coords by (dx, dy) and convert back to LatLng.
  const applyDelta = (pxCoords: unknown, dx: number, dy: number): unknown => {
    if (pxCoords instanceof L.Point) {
      return map.containerPointToLatLng(L.point(pxCoords.x + dx, pxCoords.y + dy));
    }
    if (Array.isArray(pxCoords)) return pxCoords.map((c) => applyDelta(c, dx, dy));
    return pxCoords;
  };

  const applyCorrection = () => {
    if (!dragState) return;
    const dx = currentMousePx.x - dragState.startMousePx.x;
    const dy = currentMousePx.y - dragState.startMousePx.y;
    dragState.leafStates.forEach((pxCoords, leaf) => {
      const newCoords = applyDelta(pxCoords, dx, dy);
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const asAny = leaf as any;
      if (typeof asAny.setLatLngs === 'function') {
        asAny.setLatLngs(newCoords);
      } else if (typeof asAny.setLatLng === 'function') {
        asAny.setLatLng(newCoords);
      }
    });
  };

  const handlers: Array<{ layer: L.Layer; type: string; fn: (e: unknown) => void }> = [];
  let prevBodyUserSelect = "";
  let prevBodyWebkitUserSelect = "";
  let isSelectSuppressed = false;

  const preventSelection = (e: Event) => {
    e.preventDefault();
  };

  const suppressTextSelection = () => {
    if (isSelectSuppressed) return;
    isSelectSuppressed = true;
    window.getSelection()?.removeAllRanges();
    if (typeof document !== "undefined" && document.body) {
      prevBodyUserSelect = document.body.style.userSelect;
      prevBodyWebkitUserSelect = (document.body.style as any).webkitUserSelect ?? "";
      document.body.style.userSelect = "none";
      (document.body.style as any).webkitUserSelect = "none";
    }
    if (typeof window !== "undefined") {
      window.addEventListener("selectstart", preventSelection);
      window.addEventListener("pointerup", restoreTextSelection);
      window.addEventListener("mouseup", restoreTextSelection);
    }
  };

  const restoreTextSelection = () => {
    if (!isSelectSuppressed) return;
    isSelectSuppressed = false;
    if (typeof window !== "undefined") {
      window.removeEventListener("selectstart", preventSelection);
      window.removeEventListener("pointerup", restoreTextSelection);
      window.removeEventListener("mouseup", restoreTextSelection);
      window.getSelection()?.removeAllRanges();
    }
    if (typeof document !== "undefined" && document.body) {
      document.body.style.userSelect = prevBodyUserSelect;
      (document.body.style as any).webkitUserSelect = prevBodyWebkitUserSelect;
    }
  };

  forEachLeafLayer(featureLayer, (leaf) => {
    if ((leaf as { options?: { interactive?: boolean } }).options?.interactive === false) return;

    // Capture the precise mouse pixel position at mousedown (before pm:dragstart fires).
    const onMouseDown = (e: L.LeafletMouseEvent) => {
      currentMousePx = map.latLngToContainerPoint(e.latlng);
      suppressTextSelection();
    };

    const onDragStart = () => {
      suppressTextSelection();
      const leafStates = new Map<L.Layer, unknown>();
      const layersToCapture: L.Layer[] = [featureLayer];
      if (getCoDraggableLayers) {
        layersToCapture.push(...getCoDraggableLayers());
      }

      layersToCapture.forEach((parent) => {
        forEachLeafLayer(parent, (sibling) => {
          if ((sibling as { options?: { interactive?: boolean } }).options?.interactive === false) return;
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          const s = sibling as any;
          if (typeof s.getLatLngs === 'function') {
            leafStates.set(sibling, toPx(s.getLatLngs()));
          } else if (typeof s.getLatLng === 'function') {
            leafStates.set(sibling, toPx(s.getLatLng()));
          }
        });
      });

      dragState = { startMousePx: currentMousePx.clone(), leafStates };
      map.on('mousemove', onMapMouseMove);
    };

    const onDrag = () => applyCorrection();

    const onDragEnd = () => {
      map.off('mousemove', onMapMouseMove);
      restoreTextSelection();
      dragState = null;
      if (onCoDragEnd) {
        onCoDragEnd();
      }
    };

    leaf.on('mousedown', onMouseDown as (e: L.LeafletEvent) => void);
    leaf.on('pm:dragstart', onDragStart);
    leaf.on('pm:drag', onDrag);
    leaf.on('pm:dragend', onDragEnd);
    handlers.push(
      { layer: leaf, type: 'mousedown', fn: onMouseDown as (e: unknown) => void },
      { layer: leaf, type: 'pm:dragstart', fn: onDragStart },
      { layer: leaf, type: 'pm:drag', fn: onDrag },
      { layer: leaf, type: 'pm:dragend', fn: onDragEnd },
    );
  });

  return () => {
    map.off('mousemove', onMapMouseMove);
    restoreTextSelection();
    handlers.forEach(({ layer, type, fn }) => layer.off(type, fn as (e: L.LeafletEvent) => void));
    dragState = null;
  };
}

/**
 * Translates a Feature's coordinates in pixel space by (dx, dy) on the given Leaflet map.
 */
export function nudgeFeatureByPixels(
  feature: Feature,
  leafletMap: L.Map,
  dx: number,
  dy: number,
): Feature {
  if (!feature.geometry) return feature;

  const shiftLatLng = (lat: number, lng: number): [number, number] => {
    const pt = leafletMap.latLngToContainerPoint([lat, lng]);
    const newPt = L.point(pt.x + dx, pt.y + dy);
    const ll = leafletMap.containerPointToLatLng(newPt);
    return [ll.lat, ll.lng];
  };

  const shiftCoords = (coords: unknown): unknown => {
    if (!Array.isArray(coords)) return coords;
    if (typeof coords[0] === "number") {
      const [sLat, sLng] = shiftLatLng(
        coords[1] as number,
        coords[0] as number,
      );
      return [sLng, sLat];
    }
    return coords.map(shiftCoords);
  };

  return {
    ...feature,
    geometry: {
      ...feature.geometry,
      coordinates: shiftCoords(
        feature.geometry.coordinates,
      ) as typeof feature.geometry.coordinates,
    } as any,
  };
}

