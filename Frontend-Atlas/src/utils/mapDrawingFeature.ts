import L from "leaflet";
import { getFeatureRgbColor } from "./featureHelpers";
import type {
  Coordinate,
  Feature,
  MapElementType,
  PolygonGeometry,
  PointFeature,
} from "../typescript/feature";
import type { LayerWithFeature as LayerWithFeatureType } from "../typescript/mapLayers";
import type { TextMarkerLayer } from "../typescript/mapDrawing";

function isLatLng(value: unknown): value is L.LatLng {
  const point = value as { lat?: unknown; lng?: unknown } | null;
  return (
    !!point && typeof point.lat === "number" && typeof point.lng === "number"
  );
}

export function isPointFeature(feature: Feature): feature is PointFeature {
  return feature.geometry.type === "Point";
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

export function layerToFeature(
  layer: L.Layer,
  selectedYear: number,
): Feature | null {
  let geometry: Feature["geometry"] | null = null;
  let type: MapElementType = "shape";
  let labelText = "";

  if (isTextMarkerLayer(layer)) {
    labelText = (layer.pm?.getText?.() ?? layer.options.text ?? "").trim();

    if (!labelText) {
      return null;
    }
    const latlng = layer.getLatLng();
    geometry = {
      type: "Point",
      coordinates: [latlng.lng, latlng.lat],
    };
    type = "label";
  } else if (layer instanceof L.CircleMarker && !(layer instanceof L.Circle)) {
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

    if (isLatLngArray(latlngs)) {
      geometry = {
        type: "Polygon",
        coordinates: [closeRing(latlngs.map(toCoord))],
      };
      type = "zone";
    } else if (isLatLngArrayArray(latlngs)) {
      geometry = {
        type: "Polygon",
        coordinates: latlngs.map((ring) => closeRing(ring.map(toCoord))),
      };
      type = "zone";
    } else if (isLatLngArrayArrayArray(latlngs)) {
      geometry = {
        type: "MultiPolygon",
        coordinates: latlngs.map((polygon) =>
          polygon.map((ring) => closeRing(ring.map(toCoord))),
        ),
      };
      type = "zone";
    }
  }

  if (!geometry) return null;

  const now = new Date();
  const isoDate = now.toISOString();

  return {
    id: `tmp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    type: "Feature",
    mapId: "",
    geometry,
    properties: {
      name: "",
      labelText: labelText,
      colorName: "black",
      colorRgb: [0, 0, 0],
      mapElementType: type,
      startDate: `${selectedYear}-01-01`,
      endDate: `${selectedYear}-01-01`,
    },
    createdAt: isoDate,
    updatedAt: isoDate,
    name: "",
    opacity: 0.5,
    strokeWidth: 2,
  };
}

export function featureToLayer(feature: Feature): L.Layer | null {
  const geom = feature.geometry;

  if (!geom) return null;

  const colorFromRgb = getFeatureRgbColor(feature);
  const strokeColor = colorFromRgb || "#000000";
  const fillColor = colorFromRgb || "#cccccc";

  const style = {
    color: strokeColor,
    weight: feature.strokeWidth || 2,
    fillColor,
    fillOpacity: feature.opacity || 0.5,
  };

  switch (geom.type) {
    case "Point": {
      const [lng, lat] = geom.coordinates;

      if (feature.properties.mapElementType === "label") {
        const labelText =
          feature.properties.labelText ||
          feature.properties.name ||
          feature.name ||
          "";

        const marker = L.marker([lat, lng], {
          icon: L.divIcon({
            className: "city-label-text geoman-text-label",
            html: labelText,
            iconSize: [120, 20],
            iconAnchor: [0, 10],
          }),
          textMarker: true,
          text: labelText,
        } as L.MarkerOptions & { text?: string; textMarker?: boolean });

        return marker;
      }

      return L.circleMarker([lat, lng], { ...style, radius: 6 });
    }

    case "LineString": {
      const latlngs: L.LatLngTuple[] = geom.coordinates.map(
        ([lng, lat]: [number, number]) => [lat, lng] as L.LatLngTuple,
      );
      return L.polyline(latlngs, style);
    }

    case "Polygon": {
      const latlngs: L.LatLngTuple[][] = geom.coordinates.map((ring) =>
        ring.map(([lng, lat]: [number, number]) => [lat, lng] as L.LatLngTuple),
      );
      return L.polygon(latlngs, style);
    }

    case "MultiPolygon": {
      const latlngs: L.LatLngTuple[][][] = geom.coordinates.map((polygon) =>
        polygon.map((ring) =>
          ring.map(([lng, lat]: [number, number]) => [lat, lng] as L.LatLngTuple),
        ),
      );
      return L.polygon(latlngs, style);
    }

    default:
      return null;
  }
}

function featureIdAsString(featureOrId: Feature | string | number): string {
  if (typeof featureOrId === "object" && featureOrId !== null) {
    return String(featureOrId.id);
  }
  return String(featureOrId);
}

export function extractFeatureFromLayer(
  layer: L.Layer,
  selectedYear: number,
): Feature | null {
  const layerWithFeature: LayerWithFeatureType<Feature> = layer;
  const baseFeature = layerWithFeature.feature;
  const extracted = layerToFeature(layer, selectedYear);

  if (extracted && baseFeature?.id) {
    extracted.id = baseFeature.id;
    extracted.mapId = baseFeature.mapId;
    extracted.createdAt = baseFeature.createdAt;
    extracted.updatedAt = new Date().toISOString();
    extracted.name = baseFeature.name;
    extracted.opacity = baseFeature.opacity;
    extracted.strokeWidth = baseFeature.strokeWidth;
    extracted.properties = {
      ...(extracted.properties || {}),
      ...(baseFeature.properties || {}),
    };
    return extracted;
  }

  if (typeof layerWithFeature.eachLayer === "function") {
    let childFeature: Feature | null = null;
    layerWithFeature.eachLayer((childLayer) => {
      if (childFeature) return;
      childFeature = extractFeatureFromLayer(childLayer, selectedYear);
    });
    if (childFeature) {
      return childFeature;
    }
  }

  return baseFeature ? { ...baseFeature } : null;
}

export function syncFeaturesFromLayerMap(
  layers: Map<string, L.Layer>,
  snapshot: Feature[],
  selectedYear: number,
): Feature[] {
  const nextById = new Map<string, Feature>();
  snapshot.forEach((feature) => {
    nextById.set(featureIdAsString(feature), { ...feature });
  });

  layers.forEach((layer, featureId) => {
    const layerId = String(featureId);
    const extracted = extractFeatureFromLayer(layer, selectedYear);
    if (extracted) {
      extracted.id = layerId;
      nextById.set(layerId, extracted);
      return;
    }

    const fallback = snapshot.find(
      (feature) => featureIdAsString(feature) === layerId,
    );
    if (fallback) {
      nextById.set(layerId, fallback);
    }
  });

  return Array.from(nextById.values());
}

function isTextMarkerLayer(layer: L.Layer): layer is TextMarkerLayer {
  const marker = layer as TextMarkerLayer;

  return Boolean(
    marker instanceof L.Marker &&
      (marker.options?.textMarker === true ||
        typeof marker.pm?.getText === "function"),
  );
}

function toCoord(latlng: L.LatLng): Coordinate {
  return [latlng.lng, latlng.lat];
}

function closeRing(coords: Coordinate[]): Coordinate[] {
  if (coords.length === 0) return coords;

  const [fx, fy] = coords[0];
  const [lx, ly] = coords[coords.length - 1];

  if (fx === lx && fy === ly) {
    return coords;
  }

  return [...coords, coords[0]];
}

function isLatLngArray(value: unknown): value is L.LatLng[] {
  return (
    Array.isArray(value) &&
    value.length > 0 &&
    value.every((item) => isLatLng(item))
  );
}

function isLatLngArrayArray(value: unknown): value is L.LatLng[][] {
  return (
    Array.isArray(value) &&
    value.length > 0 &&
    value.every((item) => isLatLngArray(item))
  );
}

function isLatLngArrayArrayArray(value: unknown): value is L.LatLng[][][] {
  return (
    Array.isArray(value) &&
    value.length > 0 &&
    value.every((item) => isLatLngArrayArray(item))
  );
}
