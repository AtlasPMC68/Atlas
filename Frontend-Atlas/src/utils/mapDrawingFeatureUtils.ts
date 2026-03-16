import L from "leaflet";
import type {
  Coordinate,
  Feature,
  MapElementType,
  PolygonGeometry,
} from "../typescript/feature";

function isLatLng(value: unknown): value is L.LatLng {
  const point = value as { lat?: unknown; lng?: unknown } | null;
  return (
    !!point && typeof point.lat === "number" && typeof point.lng === "number"
  );
}

export function circleToPolygon(
  center: L.LatLng,
  radiusMeters: number,
  steps: number = 32,
): PolygonGeometry {
  const coords: Coordinate[] = [];
  const radiusLat = radiusMeters / 111320;
  const radiusLng =
    radiusMeters / (111320 * Math.cos((center.lat * Math.PI) / 180));

  for (let i = 0; i < steps; i++) {
    const angle = (i / steps) * 2 * Math.PI;
    const lat = center.lat + radiusLat * Math.sin(angle);
    const lng = center.lng + radiusLng * Math.cos(angle);
    coords.push([lng, lat]);
  }

  coords.push(coords[0]);

  return {
    type: "Polygon",
    coordinates: [coords],
  };
}

export function layerToFeature(layer: L.Layer): Feature | null {
  let geometry: Feature["geometry"] | null = null;
  let type: MapElementType = "shape";

  if (layer instanceof L.CircleMarker && !(layer instanceof L.Circle)) {
    const latlng = layer.getLatLng();
    geometry = {
      type: "Point",
      coordinates: [latlng.lng, latlng.lat],
    };
    type = "point";
  } else if (layer instanceof L.Circle) {
    const center = layer.getLatLng();
    const radius = layer.getRadius();
    geometry = circleToPolygon(center, radius);
    type = "zone";
  } else if (layer instanceof L.Polyline && !(layer instanceof L.Polygon)) {
    const latlngs = layer.getLatLngs();
    geometry = {
      type: "LineString",
      coordinates: (latlngs as L.LatLng[]).map(
        (ll) => [ll.lng, ll.lat] as [number, number],
      ),
    };
    type = "polyline";
  } else if (layer instanceof L.Polygon || layer instanceof L.Rectangle) {
    const latlngs = layer.getLatLngs() as unknown;

    let ring: L.LatLng[] | null = null;

    if (Array.isArray(latlngs) && latlngs.length > 0) {
      if (isLatLng(latlngs[0])) {
        ring = latlngs as L.LatLng[];
      }

      if (!ring && Array.isArray(latlngs[0]) && latlngs[0].length > 0) {
        const firstRing = latlngs[0] as unknown[];
        if (isLatLng(firstRing[0])) {
          ring = firstRing as L.LatLng[];
        }
      }

      if (
        !ring &&
        Array.isArray(latlngs[0]) &&
        (latlngs[0] as unknown[]).length > 0 &&
        Array.isArray((latlngs[0] as unknown[])[0])
      ) {
        const firstPolygonOuterRing = (latlngs[0] as unknown[])[0] as
          | unknown[]
          | undefined;
        if (
          firstPolygonOuterRing &&
          firstPolygonOuterRing.length > 0 &&
          isLatLng(firstPolygonOuterRing[0])
        ) {
          ring = firstPolygonOuterRing as L.LatLng[];
        }
      }
    }

    if (ring && ring.length > 0) {
      const coords = ring.map((ll) => [ll.lng, ll.lat] as [number, number]);

      if (coords.length > 0) {
        const first = coords[0];
        const last = coords[coords.length - 1];
        if (first[0] !== last[0] || first[1] !== last[1]) {
          coords.push(first);
        }
      }

      geometry = {
        type: "Polygon",
        coordinates: [coords],
      };
      type = "zone";
    }
  }

  if (!geometry) return null;

  const now = new Date();
  const isoDate = now.toISOString();
  const day = isoDate.slice(0, 10);

  return {
    id: `tmp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    type: "Feature",
    mapId: "",
    geometry,
    properties: {
      name: "",
      colorName: "black",
      colorRgb: [0, 0, 0],
      mapElementType: type,
      startDate: day,
      endDate: day,
    },
    createdAt: isoDate,
    updatedAt: isoDate,
    name: "",
    color: "#000000",
    opacity: 0.5,
    strokeWidth: 2,
  };
}

export function featureToLayer(feature: Feature): L.Layer | null {
  const geom = feature.geometry;

  if (!geom) return null;

  const style = {
    color: feature.color || "#000000",
    weight: feature.strokeWidth || 2,
    fillColor: feature.color || "#cccccc",
    fillOpacity: feature.opacity || 0.5,
  };

  switch (geom.type) {
    case "Point": {
      const [lng, lat] = geom.coordinates;
      return L.circleMarker([lat, lng], { ...style, radius: 6 });
    }

    case "LineString": {
      const latlngs: L.LatLngTuple[] = geom.coordinates.map(
        ([lng, lat]: [number, number]) => [lat, lng] as L.LatLngTuple,
      );
      return L.polyline(latlngs, style);
    }

    case "Polygon": {
      const coords = geom.coordinates[0];
      const latlngs: L.LatLngTuple[] = coords.map(
        ([lng, lat]: [number, number]) => [lat, lng] as L.LatLngTuple,
      );
      return L.polygon(latlngs, style);
    }

    default:
      return null;
  }
}
