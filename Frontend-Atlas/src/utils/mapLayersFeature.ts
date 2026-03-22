import L from "leaflet";

export function isAxisAlignedRectangle(latLngs: L.LatLngTuple[], tolerance = 1e-6) {
  if (!Array.isArray(latLngs) || latLngs.length < 4) return false;

  const normalized = latLngs.slice();
  const first = normalized[0];
  const last = normalized[normalized.length - 1];
  if (
    first &&
    last &&
    Math.abs(first[0] - last[0]) <= tolerance &&
    Math.abs(first[1] - last[1]) <= tolerance
  ) {
    normalized.pop();
  }

  if (normalized.length !== 4) return false;

  const roundToTolerance = (v: number) => Math.round(v / tolerance);
  const lats = new Set(normalized.map((p) => roundToTolerance(p[0])));
  const lngs = new Set(normalized.map((p) => roundToTolerance(p[1])));
  return lats.size === 2 && lngs.size === 2;
}

export function rectangleFromLatLngs(
  latLngs: L.LatLngTuple[],
  options: L.PathOptions,
) {
  const lats = latLngs.map((p) => p[0]);
  const lngs = latLngs.map((p) => p[1]);
  const bounds = L.latLngBounds(
    [Math.min(...lats), Math.min(...lngs)],
    [Math.max(...lats), Math.max(...lngs)],
  );
  return L.rectangle(bounds, options);
}