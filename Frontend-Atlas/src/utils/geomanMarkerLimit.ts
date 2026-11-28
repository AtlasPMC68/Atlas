import L from "leaflet";

type LimitFilterArgs = { latlng?: L.LatLngExpression };
type EditLinePrototype = {
  applyLimitFilters: (args: LimitFilterArgs) => void;
  _map?: L.Map;
};
type MapWithCursor = L.Map & {
  _atlasCursorLatLng?: L.LatLng;
  _atlasVertexDragging?: boolean;
};

let patched = false;

function setCursorFromEvent(map: L.Map, e: { latlng?: L.LatLng } | MouseEvent | PointerEvent) {
  const tracked = map as MapWithCursor;
  if ("latlng" in e && e.latlng) {
    tracked._atlasCursorLatLng = e.latlng;
    return;
  }
  if ("clientX" in e) {
    tracked._atlasCursorLatLng = map.mouseEventToLatLng(e);
  }
}

export function anchorMarkerLimitToCursor(map: L.Map): void {
  const tracked = map as MapWithCursor;
  map.on("mousemove", (e: L.LeafletMouseEvent) => {
    tracked._atlasCursorLatLng = e.latlng;
  });
  // A vertex is removed by right-clicking it: the cursor is on it.
  map.on("contextmenu", (e: L.LeafletMouseEvent) => {
    tracked._atlasCursorLatLng = e.latlng;
  });
  // Leaflet mousemove does not fire while a vertex marker is dragged, and
  // pointer capture on that marker can skip the map container. Track the
  // pointer on document (capture) and freeze the limit filter during drag.
  const onPointerMove = (e: PointerEvent) => setCursorFromEvent(map, e);
  document.addEventListener("pointermove", onPointerMove, true);
  map.on("pm:markerdragstart", () => {
    tracked._atlasVertexDragging = true;
  });
  map.on("pm:markerdragend", () => {
    tracked._atlasVertexDragging = false;
    const latlng = tracked._atlasCursorLatLng;
    if (!latlng) return;
    map.eachLayer((layer) => {
      const pm = (layer as { pm?: { applyLimitFilters?: (args: LimitFilterArgs) => void } }).pm;
      pm?.applyLimitFilters?.({ latlng });
    });
  });

  map.once("unload", () => {
    document.removeEventListener("pointermove", onPointerMove, true);
    tracked._atlasVertexDragging = false;
  });

  if (patched) return;
  const editLine = (
    L as unknown as {
      PM?: { Edit?: { Line?: { prototype: EditLinePrototype } } };
    }
  ).PM?.Edit?.Line?.prototype;
  if (!editLine?.applyLimitFilters) return;
  patched = true;

  const original = editLine.applyLimitFilters;
  editLine.applyLimitFilters = function (
    this: EditLinePrototype,
    args: LimitFilterArgs = {},
  ) {
    const m = this._map as MapWithCursor | undefined;
    if (m?._atlasVertexDragging) return;
    if (args.latlng) return original.call(this, args);
    const latlng = m?._atlasCursorLatLng ?? m?.getCenter();
    return original.call(this, latlng ? { latlng } : args);
  };
}
