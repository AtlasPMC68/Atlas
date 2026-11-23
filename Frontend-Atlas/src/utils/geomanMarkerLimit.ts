import L from "leaflet";

type LimitFilterArgs = { latlng?: L.LatLngExpression };
type EditLinePrototype = {
  applyLimitFilters: (args: LimitFilterArgs) => void;
  _map?: L.Map;
};
type MapWithCursor = L.Map & { _atlasCursorLatLng?: L.LatLng };

let patched = false;

export function anchorMarkerLimitToCursor(map: L.Map): void {
  const tracked = map as MapWithCursor;
  map.on("mousemove", (e: L.LeafletMouseEvent) => {
    tracked._atlasCursorLatLng = e.latlng;
  });
  // A vertex is removed by right-clicking it: the cursor is on it.
  map.on("contextmenu", (e: L.LeafletMouseEvent) => {
    tracked._atlasCursorLatLng = e.latlng;
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
    if (args.latlng) return original.call(this, args);
    const m = this._map as MapWithCursor | undefined;
    const latlng = m?._atlasCursorLatLng ?? m?.getCenter();
    return original.call(this, latlng ? { latlng } : args);
  };
}
