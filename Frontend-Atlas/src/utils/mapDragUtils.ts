import L from "leaflet";

export type PmDraggableLayer = L.Layer & {
  pm?: { enableLayerDrag?: () => void; disableLayerDrag?: () => void };
};

export function forEachLeafLayer(layer: L.Layer, fn: (l: L.Layer) => void) {
  if (layer instanceof L.LayerGroup) {
    (layer as L.LayerGroup).eachLayer((child) => forEachLeafLayer(child, fn));
  } else {
    fn(layer);
  }
}

export function enablePerFeatureDrag(layer: L.Layer) {
  forEachLeafLayer(layer, (leaf) => {
    if ((leaf as { options?: { interactive?: boolean } }).options?.interactive === false) return;
    (leaf as PmDraggableLayer).pm?.enableLayerDrag?.();
  });
}

export function disablePerFeatureDrag(layer: L.Layer) {
  forEachLeafLayer(layer, (leaf) => {
    (leaf as PmDraggableLayer).pm?.disableLayerDrag?.();
  });
}

/**
 * Override geoman's lat/lng-delta drag with a pixel-space translation so that
 * shapes keep their on-screen appearance regardless of latitude.
 *
 * How it works:
 *  1. mousedown  → capture precise start mouse pixel position.
 *  2. pm:dragstart → snapshot every vertex in pixel coords.
 *  3. pm:drag    → geoman has already moved vertices using a lat/lng delta;
 *                  we immediately override with our own pixel-space result.
 *  4. pm:dragend → clean up.
 *
 * Returns a cleanup function to remove all listeners.
 */
export function enablePixelSpaceDrag(map: L.Map, featureLayer: L.Layer): () => void {
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

  forEachLeafLayer(featureLayer, (leaf) => {
    if ((leaf as { options?: { interactive?: boolean } }).options?.interactive === false) return;

    // Capture the precise mouse pixel position at mousedown (before pm:dragstart fires).
    const onMouseDown = (e: L.LeafletMouseEvent) => {
      currentMousePx = map.latLngToContainerPoint(e.latlng);
    };

    const onDragStart = () => {
      const leafStates = new Map<L.Layer, unknown>();
      forEachLeafLayer(featureLayer, (sibling) => {
        if ((sibling as { options?: { interactive?: boolean } }).options?.interactive === false) return;
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const s = sibling as any;
        if (typeof s.getLatLngs === 'function') {
          leafStates.set(sibling, toPx(s.getLatLngs()));
        } else if (typeof s.getLatLng === 'function') {
          leafStates.set(sibling, toPx(s.getLatLng()));
        }
      });
      dragState = { startMousePx: currentMousePx.clone(), leafStates };
      map.on('mousemove', onMapMouseMove);
    };

    const onDrag = () => applyCorrection();

    const onDragEnd = () => {
      map.off('mousemove', onMapMouseMove);
      dragState = null;
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
    handlers.forEach(({ layer, type, fn }) => layer.off(type, fn as (e: L.LeafletEvent) => void));
    dragState = null;
  };
}
