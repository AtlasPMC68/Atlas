import L from "leaflet";
import { colorRgbToCss } from "./featureHelpers";
import type {
  Coordinate,
  Feature,
  MapElementType,
  PolygonGeometry,
  PointFeature,
} from "../typescript/feature";
import type { LayerWithFeatureRuntime } from "../typescript/mapLayers";
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

function getStableLayerFeatureId(layer: L.Layer): string {
  const runtimeLayer = layer as LayerWithFeatureRuntime;

  if (runtimeLayer.feature?.id) {
    return String(runtimeLayer.feature.id);
  }

  if (runtimeLayer._tmpFeatureId) {
    return runtimeLayer._tmpFeatureId;
  }

  const newId = `tmp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  runtimeLayer._tmpFeatureId = newId;
  return newId;
}

export function layerToFeature(
  layer: L.Layer,
  _selectedYear: number,
  currentProjectId: string,
): Feature | null {
  const layerWithFeature = layer as LayerWithFeatureRuntime;
  const baseFeature = layerWithFeature.feature;
  const existingType = baseFeature?.properties?.mapElementType;
  const resolvedProjectId = baseFeature?.projectId ?? currentProjectId;

  let geometry: Feature["geometry"] | null = null;
  let inferredType: MapElementType = "zone";
  let labelText = undefined;
  let sizePx = undefined;

  if (isTextMarkerLayer(layer)) {
    labelText = (layer.pm?.getText?.() ?? layer.options.text ?? "").trim();
    sizePx = baseFeature?.properties?.sizePx ?? 12;

    if (!labelText) {
      return null;
    }

    const latlng = layer.getLatLng();
    geometry = {
      type: "Point",
      coordinates: [latlng.lng, latlng.lat],
    };
    inferredType = "label";
  } else if (layer instanceof L.CircleMarker && !(layer instanceof L.Circle)) {
    const latlng = layer.getLatLng();
    geometry = {
      type: "Point",
      coordinates: [latlng.lng, latlng.lat],
    };
    inferredType = "point";
  } else if (layer instanceof L.Circle) {
    const center = layer.getLatLng();
    const radius = layer.getRadius();
    geometry = circleToPolygon(center, radius);

    inferredType = "shape";
  } else if (layer instanceof L.Polyline && !(layer instanceof L.Polygon)) {
    const latlngs = layer.getLatLngs();
    geometry = {
      type: "LineString",
      coordinates: (latlngs as L.LatLng[]).map(
        (ll) => [ll.lng, ll.lat] as [number, number],
      ),
    };
    inferredType = "polyline";
  } else if (layer instanceof L.Polygon || layer instanceof L.Rectangle) {
    const latlngs = layer.getLatLngs() as unknown;

    if (isLatLngArray(latlngs)) {
      geometry = {
        type: "Polygon",
        coordinates: [closeRing(latlngs.map(toCoord))],
      };
    } else if (isLatLngArrayArray(latlngs)) {
      geometry = {
        type: "Polygon",
        coordinates: latlngs.map((ring) => closeRing(ring.map(toCoord))),
      };
    } else if (isLatLngArrayArrayArray(latlngs)) {
      geometry = {
        type: "MultiPolygon",
        coordinates: latlngs.map((polygon) =>
          polygon.map((ring) => closeRing(ring.map(toCoord))),
        ),
      };
    }
    if (layer instanceof L.Rectangle) {
      inferredType = "shape";
    } else if (layer instanceof L.Polygon) {
      inferredType = "zone";
    }
  }

  if (!geometry) return null;
  if (!resolvedProjectId) return null;

  const type: MapElementType = existingType ?? inferredType;

  const now = new Date().toISOString();

  return {
    id: getStableLayerFeatureId(layer),
    type: "Feature",
    projectId: resolvedProjectId,
    mapId: baseFeature?.mapId ?? null,
    geometry,
    properties: {
      name: baseFeature?.properties?.name ?? "",
      labelText,
      sizePx: sizePx,
      colorName: baseFeature?.properties?.colorName ?? "black",
      colorRgb: baseFeature?.properties?.colorRgb ?? [0, 0, 0],
      fillOpacity: baseFeature?.properties?.fillOpacity ?? 0.5,
      strokeColor:
        baseFeature?.properties?.strokeColor ??
        baseFeature?.properties?.colorRgb,
      strokeWidth: baseFeature?.properties?.strokeWidth ?? 2,
      strokeOpacity: baseFeature?.properties?.strokeOpacity ?? 0.5,
      mapElementType: type,
    },
    createdAt: baseFeature?.createdAt ?? now,
    updatedAt: now,
    name: baseFeature?.name ?? "",
  };
}

export function featureToLayer(feature: Feature): L.Layer | null {
  const geom = feature.geometry;

  if (!geom) return null;

  const fillColor = colorRgbToCss(feature.properties.colorRgb) || "#000000";
  const strokeColor =
    colorRgbToCss(feature.properties.strokeColor) || fillColor;

  const style = {
    weight: feature.properties.strokeWidth || 2,
    fillColor: fillColor,
    fillOpacity: feature.properties.fillOpacity || 0.5,
    strokeColor: strokeColor,
    strokeWidth: feature.properties.strokeWidth || 2,
    strokeOpacity: feature.properties.strokeOpacity ?? 0.5,
  };

  let layer: L.Layer | null = null;

  switch (geom.type) {
    case "Point": {
      const [lng, lat] = geom.coordinates;

      if (feature.properties.mapElementType === "label") {
        const labelText = feature.properties.labelText || "";

        layer = L.marker([lat, lng], {
          icon: L.divIcon({
            className: "city-label-text geoman-text-label",
            html: labelText,
            iconSize: [120, 20],
            iconAnchor: [0, 10],
          }),
          textMarker: true,
          text: labelText,
        } as L.MarkerOptions & { text?: string; textMarker?: boolean });
        break;
      }

      layer = L.circleMarker([lat, lng], { ...style, radius: 6 });
      break;
    }

    case "LineString": {
      const latlngs: L.LatLngTuple[] = geom.coordinates.map(
        ([lng, lat]: [number, number]) => [lat, lng] as L.LatLngTuple,
      );
      layer = L.polyline(latlngs, style);
      break;
    }

    case "Polygon": {
      const latlngs: L.LatLngTuple[][] = geom.coordinates.map((ring) =>
        ring.map(([lng, lat]: [number, number]) => [lat, lng] as L.LatLngTuple),
      );
      layer = L.polygon(latlngs, style);
      break;
    }

    case "MultiPolygon": {
      const latlngs: L.LatLngTuple[][][] = geom.coordinates.map((polygon) =>
        polygon.map((ring) =>
          ring.map(
            ([lng, lat]: [number, number]) => [lat, lng] as L.LatLngTuple,
          ),
        ),
      );
      layer = L.polygon(latlngs, style);
      break;
    }

    default:
      return null;
  }

  const runtimeLayer = layer as LayerWithFeatureRuntime;
  runtimeLayer.feature = feature;
  runtimeLayer._tmpFeatureId = String(feature.id);

  return layer;
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
  currentProjectId: string,
): Feature | null {
  const layerWithFeature = layer as LayerWithFeatureRuntime;
  const baseFeature = layerWithFeature.feature;
  const extracted = layerToFeature(layer, selectedYear, currentProjectId);

  if (extracted) {
    if (baseFeature?.id) {
      extracted.id = baseFeature.id;
      extracted.mapId = baseFeature.mapId;
      extracted.createdAt = baseFeature.createdAt;
      extracted.name = baseFeature.name;
      extracted.properties.fillOpacity = baseFeature.properties.fillOpacity;
      extracted.properties = {
        ...(baseFeature.properties || {}),
        ...(extracted.properties || {}),
      };
    }

    extracted.updatedAt = new Date().toISOString();
    layerWithFeature.feature = extracted;
    layerWithFeature._tmpFeatureId = String(extracted.id);

    return extracted;
  }

  if (typeof layerWithFeature.eachLayer === "function") {
    let childFeature: Feature | null = null;
    layerWithFeature.eachLayer((childLayer: L.Layer) => {
      if (childFeature) return;
      childFeature = extractFeatureFromLayer(
        childLayer,
        selectedYear,
        currentProjectId,
      );
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
  currentProjectId: string,
): Feature[] {
  const nextById = new Map<string, Feature>();
  snapshot.forEach((feature) => {
    nextById.set(featureIdAsString(feature), { ...feature });
  });

  layers.forEach((layer, featureId) => {
    const layerId = String(featureId);
    const extracted = extractFeatureFromLayer(
      layer,
      selectedYear,
      currentProjectId,
    );
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
