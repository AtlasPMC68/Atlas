import { ref } from "vue";
import L from "leaflet";
import { smoothFreeLinePoints, getRadiusForZoom } from "../utils/mapUtils";

type Geometry = any;
type Feature = { [key: string]: any };
type FeatureLayer = any;

type FeatureLayerManager = {
  layers: Map<string, any>;
  makeLayerClickable: (id: string, layer: any) => void;
};

type LayersComposable = {
  drawnItems: { value: L.FeatureGroup };
  allCircles: { value: Set<L.CircleMarker> };
  featureLayerManager: FeatureLayerManager;
};

type MapEditingProps = {
  mapId?: string | number;
  features: Feature[];
  editMode?: boolean;
  activeEditMode?: string | null;
};

type EmitFn = (event: string, ...args: unknown[]) => void;

type PointTree = any;
type LatLngTree = any;

function flattenPointTree(pts: PointTree, flat: L.Point[]): void {
  if (Array.isArray(pts)) {
    pts.forEach((x) => flattenPointTree(x as PointTree, flat));
    return;
  }
  flat.push(pts);
}

function scalePointsTree(
  ptsIn: PointTree,
  centerPt: L.Point,
  sx: number,
  sy: number,
): PointTree {
  if (Array.isArray(ptsIn)) {
    return (ptsIn as PointTree[]).map((x) =>
      scalePointsTree(x, centerPt, sx, sy),
    );
  }
  const x = centerPt.x + ((ptsIn as L.Point).x - centerPt.x) * sx;
  const y = centerPt.y + ((ptsIn as L.Point).y - centerPt.y) * sy;
  return L.point(x, y);
}

export function useMapEditing(props: MapEditingProps, emit: EmitFn) {
  const isDeleteMode = ref(false);

  function metersToLatLngOffsets(
    centerLat: number,
    halfWidthMeters: number,
    halfHeightMeters: number,
  ) {
    const dLat = halfHeightMeters / 111320;
    const dLng =
      halfWidthMeters / (111320 * Math.cos((centerLat * Math.PI) / 180));
    return { dLat, dLng };
  }

  function polygonFromCenterWidthHeight(
    center: L.LatLng,
    widthMeters: number | null,
    heightMeters: number | null,
    shapeType: string | null,
  ): Geometry | null {
    const w = Number(widthMeters);
    const h = Number(heightMeters);
    if (!Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0)
      return null;

    if (shapeType === "square") {
      const s = Math.min(w, h);
      return polygonFromCenterWidthHeight(center, s, s, "rectangle");
    }

    const halfW = w / 2;
    const halfH = h / 2;
    const { dLat, dLng } = metersToLatLngOffsets(center.lat, halfW, halfH);

    const north = center.lat + dLat;
    const south = center.lat - dLat;
    const east = center.lng + dLng;
    const west = center.lng - dLng;

    return {
      type: "Polygon",
      coordinates: [
        [
          [west, north],
          [east, north],
          [east, south],
          [west, south],
          [west, north],
        ],
      ],
    };
  }

  function circleFromCenterDiameter(
    center: L.LatLng,
    diameterMeters: number | null,
  ): Geometry | null {
    const d = Number(diameterMeters);
    if (!Number.isFinite(d) || d <= 0) return null;
    const r = d / 2;

    const steps = 32;
    const pts = [];
    for (let i = 0; i < steps; i++) {
      const a = (i / steps) * 2 * Math.PI;
      const lat = center.lat + (r / 111320) * Math.sin(a);
      const lng =
        center.lng +
        ((r / 111320) * Math.cos(a)) / Math.cos((center.lat * Math.PI) / 180);
      pts.push([lng, lat]);
    }
    pts.push(pts[0]);
    return { type: "Polygon", coordinates: [pts] };
  }

  function ovalFromCenterWidthHeight(
    center: L.LatLng,
    widthMeters: number | null,
    heightMeters: number | null,
  ): Geometry | null {
    const w = Number(widthMeters);
    const h = Number(heightMeters);
    if (!Number.isFinite(w) || !Number.isFinite(h) || w <= 0 || h <= 0)
      return null;

    const rx = w / 2;
    const ry = h / 2;

    const steps = 32;
    const pts = [];
    for (let i = 0; i < steps; i++) {
      const a = (i / steps) * 2 * Math.PI;
      const lat = center.lat + (ry / 111320) * Math.sin(a);
      const lng =
        center.lng +
        ((rx / 111320) * Math.cos(a)) / Math.cos((center.lat * Math.PI) / 180);
      pts.push([lng, lat]);
    }
    pts.push(pts[0]);
    return { type: "Polygon", coordinates: [pts] };
  }

  function inferShapeType(feature: Feature | null | undefined): string | null {
    const st = feature?.properties?.shapeType;
    if (st) return st;
    const t = feature?.type;
    if (t === "rectangle") return "rectangle";
    if (t === "square") return "square";
    if (t === "circle") return "circle";
    if (t === "triangle") return "triangle";
    if (t === "oval") return "oval";
    if (t === "polygon") return "polygon";
    return null;
  }

  function getCenterFromLayer(layer: FeatureLayer | null) {
    if (layer?.getBounds) return layer.getBounds().getCenter();
    if (layer?.getLatLng) return layer.getLatLng();
    return null;
  }

  function normalizeAngleDeg(a: number | string | null | undefined): number {
    const n = Number(a);
    if (!Number.isFinite(n)) return 0;
    let x = n % 360;
    if (x < 0) x += 360;
    return x;
  }

  function getAngleDegFromFeature(feature: Feature | null | undefined): number {
    const p = feature?.properties || {};
    return normalizeAngleDeg(
      p.rotation_deg ?? p.angleDeg ?? p.angle ?? p.rotation ?? 0,
    );
  }

  function rotatePoint(pt: L.Point, centerPt: L.Point, rad: number) {
    const dx = pt.x - centerPt.x;
    const dy = pt.y - centerPt.y;
    const c = Math.cos(rad);
    const s = Math.sin(rad);
    return L.point(centerPt.x + dx * c - dy * s, centerPt.y + dx * s + dy * c);
  }

  function rotatePointsTree(
    pts: PointTree,
    centerPt: L.Point,
    rad: number,
  ): PointTree {
    if (Array.isArray(pts))
      return (pts as PointTree[]).map((x) =>
        rotatePointsTree(x, centerPt, rad),
      );
    return rotatePoint(pts as L.Point, centerPt, rad);
  }

  function latlngsToPoints(map: L.Map, latlngs: LatLngTree): PointTree {
    if (Array.isArray(latlngs))
      return (latlngs as LatLngTree[]).map((x) => latlngsToPoints(map, x));
    return map.latLngToLayerPoint(latlngs as L.LatLng);
  }

  function pointsToLatlngs(map: L.Map, pts: PointTree): LatLngTree {
    if (Array.isArray(pts))
      return (pts as PointTree[]).map((x) => pointsToLatlngs(map, x));
    return map.layerPointToLatLng(pts as L.Point);
  }

  function geometryToLatLngs(geom: Geometry | null): LatLngTree | null {
    if (!geom) return null;

    const coords = geom.coordinates as any;

    if (geom.type === "Point") {
      const [lng, lat] = coords as number[];
      return L.latLng(lat, lng);
    }

    if (geom.type === "LineString") {
      return (coords as any[]).map((coord: any) =>
        L.latLng(coord[1], coord[0]),
      );
    }

    if (geom.type === "Polygon") {
      const ring = (coords?.[0] ?? []) as any[];
      const ringLatLngs = ring.map((coord: any) =>
        L.latLng(coord[1], coord[0]),
      );
      return [ringLatLngs];
    }

    return null;
  }

  function applyAngleToLayerFromCanonical(
    layer: FeatureLayer | null,
    map: L.Map | null,
    canonicalGeom: Geometry | null,
    angleDeg: number,
    pivotLatLng: L.LatLng | null,
  ) {
    if (!layer || !map) return;

    const a = normalizeAngleDeg(angleDeg);
    const rad = (a * Math.PI) / 180;

    if (
      typeof layer.getRadius === "function" &&
      typeof layer.setRadius === "function"
    ) {
      if (pivotLatLng && typeof layer.setLatLng === "function")
        layer.setLatLng(pivotLatLng);
      return;
    }

    if (typeof layer.setLatLngs !== "function") return;

    const latlngs0 = geometryToLatLngs(canonicalGeom);
    if (!latlngs0) return;

    if (Math.abs(rad) < 1e-9) {
      layer.setLatLngs(latlngs0);
      return;
    }

    const pivot = pivotLatLng || getCenterFromLayer(layer);
    if (!pivot) {
      layer.setLatLngs(latlngs0);
      return;
    }

    const centerPt = map.latLngToLayerPoint(pivot);

    const pts0 = latlngsToPoints(map, latlngs0);
    const ptsR = rotatePointsTree(pts0, centerPt, rad);
    const llR = pointsToLatlngs(map, ptsR);

    layer.setLatLngs(llR);
  }

  function geometryFromLayer(layer: FeatureLayer) {
    if (layer.getLatLng && !layer.getLatLngs) {
      const ll = layer.getLatLng();
      return { type: "Point", coordinates: [ll.lng, ll.lat] };
    }

    if (layer.getLatLngs) {
      const latlngs = layer.getLatLngs() as any[];

      const isPolygon =
        layer instanceof L.Polygon || layer instanceof L.Rectangle;

      if (!isPolygon) {
        const coords = (latlngs as any[]).map((ll: any) => [ll.lng, ll.lat]);
        return { type: "LineString", coordinates: coords };
      }

      const ring = (latlngs as any[])[0] ?? latlngs;
      const coords = (ring as any[]).map((ll: any) => [ll.lng, ll.lat]);

      if (
        coords.length &&
        (coords[0][0] !== coords[coords.length - 1][0] ||
          coords[0][1] !== coords[coords.length - 1][1])
      ) {
        coords.push(coords[0]);
      }
      return { type: "Polygon", coordinates: [coords] };
    }

    return null;
  }

  function applyLocalFeatureUpdate(fid: string, nextFeature: Feature) {
    const idx = props.features.findIndex((f) => String(f.id) === String(fid));
    if (idx !== -1) {
      const updatedFeatures = [...props.features];
      updatedFeatures[idx] = nextFeature;
      emit("features-loaded", updatedFeatures);
    }
  }

  async function applyResizeFromDims(
    featureId: string | number,
    widthMeters: number | null,
    heightMeters: number | null,
    map: L.Map,
    featureLayerManager: FeatureLayerManager,
  ) {
    const fid = String(featureId);

    const layer = featureLayerManager.layers.get(fid);
    if (!layer || !map) return;

    const feature =
      props.features.find((f) => String(f.id) === fid) || layer.feature || null;
    if (!feature) return;

    const center = feature?.properties?.center
      ? L.latLng(feature.properties.center.lat, feature.properties.center.lng)
      : getCenterFromLayer(layer);
    if (!center) return;

    const shapeType = inferShapeType(feature);
    const canScaleGeneric =
      !shapeType && layer.getLatLngs && typeof layer.setLatLngs === "function";
    if (!shapeType && !canScaleGeneric) return;

    if (canScaleGeneric) {
      const w = Number(widthMeters);
      const h = Number(heightMeters);

      const hasW = Number.isFinite(w) && w > 0;
      const hasH = Number.isFinite(h) && h > 0;
      if (!hasW && !hasH) return;

      const angleDeg = getAngleDegFromFeature(feature);
      const angleRad = (angleDeg * Math.PI) / 180;

      const latlngs = layer.getLatLngs ? layer.getLatLngs() : null;
      if (!latlngs) return;

      const centerPt = map.latLngToLayerPoint(center);
      const pts = latlngsToPoints(map, latlngs);
      const pts0 =
        Math.abs(angleRad) > 1e-9
          ? rotatePointsTree(pts, centerPt, -angleRad)
          : pts;

      const flat: L.Point[] = [];
      flattenPointTree(pts0 as PointTree, flat);

      let minX = Infinity,
        minY = Infinity,
        maxX = -Infinity,
        maxY = -Infinity;
      for (const p of flat) {
        if (p.x < minX) minX = p.x;
        if (p.y < minY) minY = p.y;
        if (p.x > maxX) maxX = p.x;
        if (p.y > maxY) maxY = p.y;
      }
      if (
        !Number.isFinite(minX) ||
        !Number.isFinite(maxX) ||
        !Number.isFinite(minY) ||
        !Number.isFinite(maxY)
      )
        return;

      const cx = (minX + maxX) / 2;
      const cy = (minY + maxY) / 2;

      const westLL = map.layerPointToLatLng(L.point(minX, cy));
      const eastLL = map.layerPointToLatLng(L.point(maxX, cy));
      const northLL = map.layerPointToLatLng(L.point(cx, minY));
      const southLL = map.layerPointToLatLng(L.point(cx, maxY));

      const curW = map.distance(westLL, eastLL);
      const curH = map.distance(northLL, southLL);
      if (
        !Number.isFinite(curW) ||
        !Number.isFinite(curH) ||
        curW <= 0 ||
        curH <= 0
      )
        return;

      const sx = hasW ? w / curW : 1;
      const sy = hasH ? h / curH : 1;

      const scaled0 = scalePointsTree(pts0 as PointTree, centerPt, sx, sy);
      const scaled =
        Math.abs(angleRad) > 1e-9
          ? rotatePointsTree(scaled0, centerPt, angleRad)
          : scaled0;
      const newLatLngs = pointsToLatlngs(map, scaled);

      layer.setLatLngs?.(newLatLngs);

      const newGeom0 = geometryFromLayer(layer);
      if (!newGeom0) return;

      const nextLayerFeature = {
        ...(layer.feature || feature),
        geometry: newGeom0,
        properties: {
          ...(feature.properties || {}),
          resizable: true,
          shapeType: feature?.properties?.shapeType || "polygon",
          center: { lat: center.lat, lng: center.lng },
          rotation_deg: angleDeg,
        },
      };
      layer.feature = nextLayerFeature;
      applyLocalFeatureUpdate(fid, nextLayerFeature);

      const isTemp = fid.startsWith("temp_") || feature._isTemporary === true;
      if (isTemp) return;

      return;
    }

    if (shapeType === "square") {
      const w = Number(widthMeters);
      const h = Number(heightMeters);
      const side =
        Number.isFinite(w) && w > 0
          ? w
          : Number.isFinite(h) && h > 0
            ? h
            : null;
      if (!side) return;
      widthMeters = side;
      heightMeters = side;
    }

    const w = Number(widthMeters);
    const h = Number(heightMeters);

    const hasW = Number.isFinite(w) && w > 0;
    const hasH = Number.isFinite(h) && h > 0;

    const d = hasW ? w : hasH ? h : null;
    if (shapeType === "circle" && (d == null || d <= 0)) return;
    if (shapeType !== "circle" && !hasW && !hasH) return;

    let newGeom0 = null;

    if (shapeType === "circle") {
      newGeom0 = circleFromCenterDiameter(center, d);
    } else if (shapeType === "oval") {
      newGeom0 = ovalFromCenterWidthHeight(
        center,
        hasW ? w : null,
        hasH ? h : null,
      );
    } else if (shapeType === "triangle") {
      const candidates = [];
      if (hasW) candidates.push(w / Math.sqrt(3));
      if (hasH) candidates.push(h / 1.5);
      if (!candidates.length) return;

      const R = candidates.reduce((a, b) => a + b, 0) / candidates.length;

      const points = [];
      for (let i = 0; i < 3; i++) {
        const angle = ((i * 120 + 90) * Math.PI) / 180;
        const lat = center.lat + (R / 111320) * Math.sin(angle);
        const lng =
          center.lng +
          ((R / 111320) * Math.cos(angle)) /
            Math.cos((center.lat * Math.PI) / 180);
        points.push([lng, lat]);
      }
      points.push(points[0]);
      newGeom0 = { type: "Polygon", coordinates: [points] };
    } else {
      newGeom0 = polygonFromCenterWidthHeight(
        center,
        hasW ? w : null,
        hasH ? h : null,
        shapeType,
      );
    }

    if (!newGeom0) return;

    const angleDeg = getAngleDegFromFeature(feature);

    if (shapeType === "circle" && typeof layer.setRadius === "function") {
      if (d == null) return;
      if (typeof layer.setLatLng === "function") layer.setLatLng(center);
      layer.setRadius(d / 2);
    } else {
      applyAngleToLayerFromCanonical(layer, map, newGeom0, angleDeg, center);
    }

    const nextLayerFeature = {
      ...(layer.feature || feature),
      geometry: newGeom0,
      properties: {
        ...(feature.properties || {}),
        resizable: true,
        shapeType,
        center: { lat: center.lat, lng: center.lng },
        rotation_deg: angleDeg,
      },
    };
    layer.feature = nextLayerFeature;
    applyLocalFeatureUpdate(fid, nextLayerFeature);
  }

  // ==========================
  // NEW: ROTATION (angle absolu)
  // ==========================
  async function applyRotateFromAngle(
    featureId: string | number,
    angleDeg: number,
    map: L.Map,
    featureLayerManager: FeatureLayerManager,
  ) {
    const fid = String(featureId);

    const layer = featureLayerManager.layers.get(fid);
    if (!layer || !map) return;

    const isCircle =
      typeof layer.getRadius === "function" &&
      typeof layer.setRadius === "function";

    const feature =
      props.features.find((f) => String(f.id) === fid) || layer.feature || null;
    if (!feature) return;

    const nextAngle = normalizeAngleDeg(angleDeg);
    const curAngle = getAngleDegFromFeature(feature);

    const diff = Math.abs(nextAngle - curAngle);
    const wrapped = Math.min(diff, 360 - diff);

    if (!feature.properties) feature.properties = {};
    feature.properties.rotation_deg = nextAngle;

    if (!layer.feature) layer.feature = feature;
    else {
      layer.feature.properties = layer.feature.properties || {};
      layer.feature.properties.rotation_deg = nextAngle;
    }

    if (wrapped < 1e-9 || isCircle) return;

    if (!layer.getLatLngs || typeof layer.setLatLngs !== "function") return;

    const bounds = layer.getBounds ? layer.getBounds() : null;
    const centerLL = bounds?.isValid?.()
      ? bounds.getCenter()
      : getCenterFromLayer(layer);
    if (!centerLL) return;

    const latlngs = layer.getLatLngs ? layer.getLatLngs() : null;
    if (!latlngs) return;

    const centerPt = map.latLngToLayerPoint(centerLL);
    const pts = latlngsToPoints(map, latlngs);

    const curRad = (curAngle * Math.PI) / 180;
    const pts0 =
      Math.abs(curRad) > 1e-9 ? rotatePointsTree(pts, centerPt, -curRad) : pts;
    const ll0 = pointsToLatlngs(map, pts0);

    const isPolygon =
      layer instanceof L.Polygon || layer instanceof L.Rectangle;

    let geom0 = null;
    if (!isPolygon) {
      geom0 = {
        type: "LineString",
        coordinates: (ll0 as any[]).map((ll: any) => [ll.lng, ll.lat]),
      };
    } else {
      const ring = (ll0 as any[])[0] ?? ll0;
      const coords = (ring as any[]).map((ll: any) => [ll.lng, ll.lat]);
      if (
        coords.length &&
        (coords[0][0] !== coords[coords.length - 1][0] ||
          coords[0][1] !== coords[coords.length - 1][1])
      ) {
        coords.push(coords[0]);
      }
      geom0 = { type: "Polygon", coordinates: [coords] };
    }

    const updatedFeature = {
      ...(layer.feature || feature),
      geometry: geom0,
      properties: {
        ...((layer.feature || feature).properties || {}),
        rotation_deg: nextAngle,
      },
    };

    layer.feature = updatedFeature;
    applyLocalFeatureUpdate(fid, updatedFeature);

    applyAngleToLayerFromCanonical(layer, map, geom0, nextAngle, centerLL);
  }

  // ===== SHAPE CREATION FUNCTIONS =====
  function createSquare(
    center: L.LatLng,
    sizePoint: L.LatLng,
    map: L.Map,
    layersComposable: LayersComposable,
  ) {
    const centerPixel = map.latLngToContainerPoint(center);
    const sizePixel = map.latLngToContainerPoint(sizePoint);

    const pixelDistance = centerPixel.distanceTo(sizePixel);
    const halfSidePixels = pixelDistance / Math.sqrt(2);

    const topLeftPixel = L.point(
      centerPixel.x - halfSidePixels,
      centerPixel.y - halfSidePixels,
    );
    const bottomRightPixel = L.point(
      centerPixel.x + halfSidePixels,
      centerPixel.y + halfSidePixels,
    );

    const topLeft = map.containerPointToLatLng(topLeftPixel);
    const bottomRight = map.containerPointToLatLng(bottomRightPixel);

    const square = L.rectangle(
      [
        [topLeft.lat, topLeft.lng],
        [bottomRight.lat, bottomRight.lng],
      ],
      { color: "#000000", weight: 2, fillColor: "#cccccc", fillOpacity: 0.5 },
    );

    layersComposable.drawnItems.value.addLayer(square);

    const feature = squareToFeatureFromCenter(center, sizePoint, map);

    const tempFeature = {
      ...feature,
      id: `temp_${Date.now()}_${Math.random()}`,
      _isTemporary: true,
    };

    (square as FeatureLayer).feature = tempFeature;

    layersComposable.featureLayerManager.layers.set(tempFeature.id, square);
    layersComposable.featureLayerManager.makeLayerClickable(
      tempFeature.id,
      square,
    );
  }

  function createRectangle(
    startCorner: L.LatLng,
    endCorner: L.LatLng,
    map: L.Map,
    layersComposable: LayersComposable,
  ) {
    void map;
    const minLat = Math.min(startCorner.lat, endCorner.lat);
    const maxLat = Math.max(startCorner.lat, endCorner.lat);
    const minLng = Math.min(startCorner.lng, endCorner.lng);
    const maxLng = Math.max(startCorner.lng, endCorner.lng);

    const rectangle = L.rectangle(
      [
        [minLat, minLng],
        [maxLat, maxLng],
      ],
      { color: "#000000", weight: 2, fillColor: "#cccccc", fillOpacity: 0.5 },
    );

    layersComposable.drawnItems.value.addLayer(rectangle);

    const feature = rectangleToFeatureFromCorners(startCorner, endCorner);

    const tempFeature = {
      ...feature,
      id: `temp_${Date.now()}_${Math.random()}`,
      _isTemporary: true,
      properties: {
        ...(feature.properties || {}),
        rotation_deg: 0,
      },
    };

    (rectangle as FeatureLayer).feature = tempFeature;

    layersComposable.featureLayerManager.layers.set(tempFeature.id, rectangle);
    layersComposable.featureLayerManager.makeLayerClickable(
      tempFeature.id,
      rectangle,
    );
  }

  function createCircle(
    center: L.LatLng,
    edgePoint: L.LatLng,
    map: L.Map,
    layersComposable: LayersComposable,
  ) {
    const radius = map.distance(center, edgePoint);

    const circle = L.circle(center, {
      radius,
      color: "#000000",
      weight: 2,
      fillColor: "#cccccc",
      fillOpacity: 0.5,
    });

    layersComposable.drawnItems.value.addLayer(circle);

    const feature = circleToFeatureFromCenter(center, edgePoint, map);

    const tempFeature = {
      ...feature,
      id: `temp_${Date.now()}_${Math.random()}`,
      _isTemporary: true,
    };

    (circle as FeatureLayer).feature = tempFeature;

    layersComposable.featureLayerManager.layers.set(tempFeature.id, circle);
    layersComposable.featureLayerManager.makeLayerClickable(
      tempFeature.id,
      circle,
    );
  }

  function createTriangle(
    center: L.LatLng,
    sizePoint: L.LatLng,
    map: L.Map,
    layersComposable: LayersComposable,
  ) {
    const distance = map.distance(center, sizePoint);

    const points = [];
    for (let i = 0; i < 3; i++) {
      const angle = ((i * 120 + 90) * Math.PI) / 180;
      const lat = center.lat + (distance / 111320) * Math.sin(angle);
      const lng =
        center.lng +
        ((distance / 111320) * Math.cos(angle)) /
          Math.cos((center.lat * Math.PI) / 180);
      points.push([lat, lng]);
    }

    const triangle = L.polygon(points as L.LatLngExpression[], {
      color: "#000000",
      weight: 2,
      fillColor: "#cccccc",
      fillOpacity: 0.5,
    });

    layersComposable.drawnItems.value.addLayer(triangle);

    const feature = triangleToFeatureFromCenter(center, sizePoint, map);

    const tempFeature = {
      ...feature,
      id: `temp_${Date.now()}_${Math.random()}`,
      _isTemporary: true,
    };

    (triangle as FeatureLayer).feature = tempFeature;

    layersComposable.featureLayerManager.layers.set(tempFeature.id, triangle);
    layersComposable.featureLayerManager.makeLayerClickable(
      tempFeature.id,
      triangle,
    );
  }

  function createOval(
    center: L.LatLng,
    heightPoint: L.LatLng,
    widthPoint: L.LatLng,
    map: L.Map,
    layersComposable: LayersComposable,
  ) {
    void map;
    const heightRadius = Math.abs(center.lat - heightPoint.lat) * 111320;
    const widthRadius =
      Math.abs(center.lng - widthPoint.lng) *
      111320 *
      Math.cos((center.lat * Math.PI) / 180);

    const points = [];
    const steps = 32;
    for (let i = 0; i < steps; i++) {
      const angle = (i / steps) * 2 * Math.PI;
      const lat = center.lat + (heightRadius / 111320) * Math.sin(angle);
      const lng =
        center.lng +
        ((widthRadius / 111320) * Math.cos(angle)) /
          Math.cos((center.lat * Math.PI) / 180);
      points.push([lat, lng]);
    }

    const oval = L.polygon(points as L.LatLngExpression[], {
      color: "#000000",
      weight: 2,
      fillColor: "#cccccc",
      fillOpacity: 0.5,
    });

    layersComposable.drawnItems.value.addLayer(oval);

    const feature = ovalToFeatureFromCenter(center, heightPoint, widthPoint);

    const tempFeature = {
      ...feature,
      id: `temp_${Date.now()}_${Math.random()}`,
      _isTemporary: true,
      properties: {
        ...(feature.properties || {}),
        rotation_deg: 0,
      },
    };

    (oval as FeatureLayer).feature = tempFeature;

    layersComposable.featureLayerManager.layers.set(tempFeature.id, oval);
    layersComposable.featureLayerManager.makeLayerClickable(
      tempFeature.id,
      oval,
    );
  }

  function createPointAt(
    latlng: L.LatLng,
    map: L.Map,
    layersComposable: LayersComposable,
  ) {
    const currentZoom = map.getZoom();
    const radius = getRadiusForZoom(currentZoom);

    const circle = L.circleMarker(latlng, {
      radius,
      fillColor: "#000000",
      color: "#333333",
      weight: 1,
      opacity: 0.8,
      fillOpacity: 0.8,
      draggable: true,
    } as any);

    layersComposable.allCircles.value.add(circle);
    layersComposable.drawnItems.value.addLayer(circle);

    const feature = {
      map_id: props.mapId,
      type: "point",
      geometry: { type: "Point", coordinates: [latlng.lng, latlng.lat] },
      color: "#000000",
      opacity: 0.8,
      z_index: 1,
      properties: { rotation_deg: 0, mapElementType: "point" },
    };

    const tempFeature = {
      ...feature,
      id: `temp_${Date.now()}_${Math.random()}`,
      _isTemporary: true,
    };

    (circle as FeatureLayer).feature = tempFeature;

    layersComposable.featureLayerManager.layers.set(tempFeature.id, circle);
    layersComposable.featureLayerManager.makeLayerClickable(
      tempFeature.id,
      circle,
    );
  }

  function createLine(
    startLatLng: L.LatLng,
    endLatLng: L.LatLng,
    map: L.Map,
    layersComposable: LayersComposable,
  ) {
    void map;
    const line = L.polyline([startLatLng, endLatLng], {
      color: "#000000",
      weight: 2,
      opacity: 1.0,
    });

    layersComposable.drawnItems.value.addLayer(line);

    const feature = {
      map_id: props.mapId,
      type: "polyline",
      geometry: {
        type: "LineString",
        coordinates: [
          [startLatLng.lng, startLatLng.lat],
          [endLatLng.lng, endLatLng.lat],
        ],
      },
      color: "#000000",
      stroke_width: 2,
      opacity: 1.0,
      z_index: 1,
      properties: { rotation_deg: 0, mapElementType: "polyline" },
    };

    const tempFeature = {
      ...feature,
      id: `temp_${Date.now()}_${Math.random()}`,
      _isTemporary: true,
    };

    (line as FeatureLayer).feature = tempFeature;

    layersComposable.featureLayerManager.layers.set(tempFeature.id, line);
    layersComposable.featureLayerManager.makeLayerClickable(
      tempFeature.id,
      line,
    );
  }

  function createPolygon(
    points: L.LatLng[],
    map: L.Map,
    layersComposable: LayersComposable,
  ) {
    void map;
    const polygon = L.polygon(points, {
      color: "#000000",
      weight: 2,
      fillColor: "#cccccc",
      fillOpacity: 0.5,
    });

    layersComposable.drawnItems.value.addLayer(polygon);

    const feature = {
      map_id: props.mapId,
      type: "polygon",
      geometry: {
        type: "Polygon",
        coordinates: [points.map((p) => [p.lng, p.lat])],
      },
      color: "#cccccc",
      opacity: 0.5,
      z_index: 1,
      properties: {
        rotation_deg: 0,
        mapElementType: "zone",
        shapeType: "polygon",
      },
    };

    const tempFeature = {
      ...feature,
      id: `temp_${Date.now()}_${Math.random()}`,
      _isTemporary: true,
    };

    (polygon as FeatureLayer).feature = tempFeature;

    layersComposable.featureLayerManager.layers.set(tempFeature.id, polygon);
    layersComposable.featureLayerManager.makeLayerClickable(
      tempFeature.id,
      polygon,
    );
  }

  function finishFreeLine(
    freeLinePoints: L.LatLng[],
    tempFreeLine: L.Polyline | null,
    map: L.Map,
    layersComposable: LayersComposable,
  ) {
    void map;
    if (freeLinePoints.length < 2) return;

    const smoothedPoints = smoothFreeLinePoints(freeLinePoints);

    if (tempFreeLine)
      layersComposable.drawnItems.value.removeLayer(tempFreeLine);

    const freeLine = L.polyline(smoothedPoints, {
      color: "#000000",
      weight: 2,
      opacity: 1.0,
    });

    layersComposable.drawnItems.value.addLayer(freeLine);

    const feature = {
      map_id: props.mapId,
      type: "polyline",
      geometry: {
        type: "LineString",
        coordinates: smoothedPoints.map((point: L.LatLng) => [
          point.lng,
          point.lat,
        ]),
      },
      color: "#000000",
      stroke_width: 2,
      opacity: 1.0,
      z_index: 1,
      properties: { rotation_deg: 0, mapElementType: "polyline" },
    };

    const tempId = `temp_freeline_${Date.now()}_${Math.random()}`;
    const tempFeature = { ...feature, id: tempId, _isTemporary: true };

    (freeLine as FeatureLayer).feature = tempFeature;

    layersComposable.featureLayerManager.layers.set(tempId, freeLine);
    if (props.editMode) {
      layersComposable.featureLayerManager.makeLayerClickable(tempId, freeLine);
    }
  }

  // ===== TEMPORARY SHAPE UPDATE FUNCTIONS =====
  function updateTempSquareFromCenter(
    center: L.LatLng,
    sizePoint: L.LatLng,
    map: L.Map,
    layersComposable: LayersComposable,
    tempShape: L.Layer | null,
  ) {
    if (tempShape) layersComposable.drawnItems.value.removeLayer(tempShape);

    const centerPixel = map.latLngToContainerPoint(center);
    const sizePixel = map.latLngToContainerPoint(sizePoint);
    const pixelDistance = centerPixel.distanceTo(sizePixel);
    const halfSidePixels = pixelDistance / Math.sqrt(2);

    const topLeftPixel = L.point(
      centerPixel.x - halfSidePixels,
      centerPixel.y - halfSidePixels,
    );
    const bottomRightPixel = L.point(
      centerPixel.x + halfSidePixels,
      centerPixel.y + halfSidePixels,
    );

    const topLeft = map.containerPointToLatLng(topLeftPixel);
    const bottomRight = map.containerPointToLatLng(bottomRightPixel);

    const newTempShape = L.rectangle(
      [
        [topLeft.lat, topLeft.lng],
        [bottomRight.lat, bottomRight.lng],
      ],
      { color: "#000000", weight: 2, fillColor: "#cccccc", fillOpacity: 0.5 },
    );

    layersComposable.drawnItems.value.addLayer(newTempShape);
    return newTempShape;
  }

  function updateTempRectangleFromCorners(
    startCorner: L.LatLng,
    endCorner: L.LatLng,
    map: L.Map,
    layersComposable: LayersComposable,
    tempShape: L.Layer | null,
  ) {
    void map;
    if (tempShape) layersComposable.drawnItems.value.removeLayer(tempShape);

    const minLat = Math.min(startCorner.lat, endCorner.lat);
    const maxLat = Math.max(startCorner.lat, endCorner.lat);
    const minLng = Math.min(startCorner.lng, endCorner.lng);
    const maxLng = Math.max(startCorner.lng, endCorner.lng);

    const newTempShape = L.rectangle(
      [
        [minLat, minLng],
        [maxLat, maxLng],
      ],
      { color: "#000000", weight: 2, fillColor: "#cccccc", fillOpacity: 0.5 },
    );

    layersComposable.drawnItems.value.addLayer(newTempShape);
    return newTempShape;
  }

  function updateTempCircleFromCenter(
    center: L.LatLng,
    edgePoint: L.LatLng,
    map: L.Map,
    layersComposable: LayersComposable,
    tempShape: L.Layer | null,
  ) {
    if (tempShape) layersComposable.drawnItems.value.removeLayer(tempShape);

    const radius = map.distance(center, edgePoint);

    const newTempShape = L.circle(center, {
      radius,
      color: "#000000",
      weight: 2,
      fillColor: "#cccccc",
      fillOpacity: 0.5,
    });

    layersComposable.drawnItems.value.addLayer(newTempShape);
    return newTempShape;
  }

  function updateTempTriangleFromCenter(
    center: L.LatLng,
    sizePoint: L.LatLng,
    map: L.Map,
    layersComposable: LayersComposable,
    tempShape: L.Layer | null,
  ) {
    if (tempShape) layersComposable.drawnItems.value.removeLayer(tempShape);

    const distance = map.distance(center, sizePoint);

    const points = [];
    for (let i = 0; i < 3; i++) {
      const angle = ((i * 120 + 90) * Math.PI) / 180;
      const lat = center.lat + (distance / 111320) * Math.sin(angle);
      const lng =
        center.lng +
        ((distance / 111320) * Math.cos(angle)) /
          Math.cos((center.lat * Math.PI) / 180);
      points.push([lat, lng]);
    }

    const newTempShape = L.polygon(points as L.LatLngExpression[], {
      color: "#000000",
      weight: 2,
      fillColor: "#cccccc",
      fillOpacity: 0.5,
    });

    layersComposable.drawnItems.value.addLayer(newTempShape);
    return newTempShape;
  }

  function updateTempOvalHeight(
    center: L.LatLng,
    heightPoint: L.LatLng,
    map: L.Map,
    layersComposable: LayersComposable,
    tempShape: L.Layer | null,
  ) {
    void map;
    if (tempShape) layersComposable.drawnItems.value.removeLayer(tempShape);

    const radius = Math.abs(center.lat - heightPoint.lat) * 111320;

    const newTempShape = L.circle(center, {
      radius,
      color: "#000000",
      weight: 2,
      fillColor: "#cccccc",
      fillOpacity: 0.5,
    });

    layersComposable.drawnItems.value.addLayer(newTempShape);
    return newTempShape;
  }

  function updateTempOvalWidth(
    center: L.LatLng,
    heightPoint: L.LatLng,
    widthPoint: L.LatLng,
    map: L.Map,
    layersComposable: LayersComposable,
    tempShape: L.Layer | null,
  ) {
    void map;
    if (tempShape) layersComposable.drawnItems.value.removeLayer(tempShape);

    const heightRadius = Math.abs(center.lat - heightPoint.lat) * 111320;
    const widthRadius =
      Math.abs(center.lng - widthPoint.lng) *
      111320 *
      Math.cos((center.lat * Math.PI) / 180);

    const points = [];
    const steps = 32;
    for (let i = 0; i < steps; i++) {
      const angle = (i / steps) * 2 * Math.PI;
      const lat = center.lat + (heightRadius / 111320) * Math.sin(angle);
      const lng =
        center.lng +
        ((widthRadius / 111320) * Math.cos(angle)) /
          Math.cos((center.lat * Math.PI) / 180);
      points.push([lat, lng]);
    }

    const newTempShape = L.polygon(points as L.LatLngExpression[], {
      color: "#000000",
      weight: 2,
      fillColor: "#cccccc",
      fillOpacity: 0.5,
    });

    layersComposable.drawnItems.value.addLayer(newTempShape);
    return newTempShape;
  }

  // ===== FEATURE CONVERSION FUNCTIONS =====
  function squareToFeatureFromCenter(
    center: L.LatLng,
    sizePoint: L.LatLng,
    map: L.Map,
  ): Feature {
    const distance = map.distance(center, sizePoint);
    const halfSide = distance / Math.sqrt(2);

    const latOffset = halfSide / 111320;
    const lngOffset =
      halfSide / (111320 * Math.cos((center.lat * Math.PI) / 180));

    const geometry = {
      type: "Polygon",
      coordinates: [
        [
          [center.lng - lngOffset, center.lat + latOffset],
          [center.lng + lngOffset, center.lat + latOffset],
          [center.lng + lngOffset, center.lat - latOffset],
          [center.lng - lngOffset, center.lat - latOffset],
          [center.lng - lngOffset, center.lat + latOffset],
        ],
      ],
    };

    return {
      map_id: props.mapId,
      type: "square",
      geometry,
      color: "#cccccc",
      opacity: 0.5,
      z_index: 1,
      properties: {
        shapeType: "square",
        center: { lat: center.lat, lng: center.lng },
        size: distance,
        resizable: true,
        rotation_deg: 0,
        mapElementType: "shape",
        shapeKind: "square",
      },
    };
  }

  function rectangleToFeatureFromCorners(
    startCorner: L.LatLng,
    endCorner: L.LatLng,
  ): Feature {
    const minLat = Math.min(startCorner.lat, endCorner.lat);
    const maxLat = Math.max(startCorner.lat, endCorner.lat);
    const minLng = Math.min(startCorner.lng, endCorner.lng);
    const maxLng = Math.max(startCorner.lng, endCorner.lng);

    const geometry = {
      type: "Polygon",
      coordinates: [
        [
          [minLng, maxLat],
          [maxLng, maxLat],
          [maxLng, minLat],
          [minLng, minLat],
          [minLng, maxLat],
        ],
      ],
    };

    return {
      map_id: props.mapId,
      type: "rectangle",
      geometry,
      color: "#cccccc",
      opacity: 0.5,
      z_index: 1,
      properties: {
        rotation_deg: 0,
        mapElementType: "shape",
        shapeKind: "rectangle",
        shapeType: "rectangle",
      },
    };
  }

  function circleToFeatureFromCenter(
    center: L.LatLng,
    edgePoint: L.LatLng,
    map: L.Map,
  ): Feature {
    const radius = map.distance(center, edgePoint);

    const points = [];
    const steps = 32;
    for (let i = 0; i < steps; i++) {
      const angle = (i / steps) * 2 * Math.PI;
      const lat = center.lat + (radius / 111320) * Math.sin(angle);
      const lng =
        center.lng +
        ((radius / 111320) * Math.cos(angle)) /
          Math.cos((center.lat * Math.PI) / 180);
      points.push([lng, lat]);
    }
    points.push(points[0]);

    const geometry = { type: "Polygon", coordinates: [points] };

    return {
      map_id: props.mapId,
      type: "circle",
      geometry,
      color: "#cccccc",
      opacity: 0.5,
      z_index: 1,
      properties: {
        shapeType: "circle",
        center: { lat: center.lat, lng: center.lng },
        size: radius,
        resizable: true,
        rotation_deg: 0,
        mapElementType: "shape",
        shapeKind: "circle",
      },
    };
  }

  function triangleToFeatureFromCenter(
    center: L.LatLng,
    sizePoint: L.LatLng,
    map: L.Map,
  ): Feature {
    const distance = map.distance(center, sizePoint);

    const points = [];
    for (let i = 0; i < 3; i++) {
      const angle = ((i * 120 + 90) * Math.PI) / 180;
      const lat = center.lat + (distance / 111320) * Math.sin(angle);
      const lng =
        center.lng +
        ((distance / 111320) * Math.cos(angle)) /
          Math.cos((center.lat * Math.PI) / 180);
      points.push([lng, lat]);
    }
    points.push(points[0]);

    const geometry = { type: "Polygon", coordinates: [points] };

    return {
      map_id: props.mapId,
      type: "triangle",
      geometry,
      color: "#cccccc",
      opacity: 0.5,
      z_index: 1,
      properties: {
        shapeType: "triangle",
        center: { lat: center.lat, lng: center.lng },
        size: distance,
        resizable: true,
        rotation_deg: 0,
        mapElementType: "shape",
        shapeKind: "triangle",
      },
    };
  }

  function ovalToFeatureFromCenter(
    center: L.LatLng,
    heightPoint: L.LatLng,
    widthPoint: L.LatLng,
  ): Feature {
    const heightRadius = Math.abs(center.lat - heightPoint.lat) * 111320;
    const widthRadius =
      Math.abs(center.lng - widthPoint.lng) *
      111320 *
      Math.cos((center.lat * Math.PI) / 180);

    const points = [];
    const steps = 32;
    for (let i = 0; i < steps; i++) {
      const angle = (i / steps) * 2 * Math.PI;
      const lat = center.lat + (heightRadius / 111320) * Math.sin(angle);
      const lng =
        center.lng +
        ((widthRadius / 111320) * Math.cos(angle)) /
          Math.cos((center.lat * Math.PI) / 180);
      points.push([lng, lat]);
    }
    points.push(points[0]);

    const geometry = { type: "Polygon", coordinates: [points] };

    return {
      map_id: props.mapId,
      type: "oval",
      geometry,
      color: "#cccccc",
      opacity: 0.5,
      z_index: 1,
      properties: {
        rotation_deg: 0,
        mapElementType: "shape",
        shapeKind: "oval",
        shapeType: "oval",
      },
    };
  }

  // ===== SELECTION AND VISUAL MANAGEMENT =====
  function updateFeatureSelectionVisual(
    map: L.Map | null,
    layerManager: FeatureLayerManager | null,
    selectedFeatures: Set<string>,
  ) {
    if (!map || !layerManager) return;

    const defaultStyles = {
      borderColor: "#000000",
      fillColor: "#cccccc",
      opacity: 0.5,
      strokeWidth: 2,
    };

    const selectedStyle = { color: "#ff6b6b", weight: 3, fillOpacity: 0.8 };

    const styleStrategies = {
      CircleMarker: (
        layer: any,
        isSelected: boolean,
        feature: Feature | undefined,
      ) => {
        const baseColor = feature?.color || defaultStyles.borderColor;
        layer.setStyle({
          color: isSelected ? selectedStyle.color : baseColor,
          fillColor: isSelected ? selectedStyle.color : baseColor,
          weight: isSelected ? selectedStyle.weight : 1,
          fillOpacity: isSelected
            ? selectedStyle.fillOpacity
            : (feature?.opacity ?? 0.8),
        });
      },

      Polygon: (
        layer: any,
        isSelected: boolean,
        feature: Feature | undefined,
      ) => {
        const borderColor = feature?.color || defaultStyles.borderColor;
        const fillColor = feature?.color || defaultStyles.fillColor;
        layer.setStyle({
          color: isSelected ? selectedStyle.color : borderColor,
          weight: isSelected ? selectedStyle.weight : 2,
          fillColor: isSelected ? selectedStyle.color : fillColor,
          fillOpacity: isSelected
            ? selectedStyle.fillOpacity
            : (feature?.opacity ?? defaultStyles.opacity),
        });
      },

      Polyline: (
        layer: any,
        isSelected: boolean,
        feature: Feature | undefined,
      ) => {
        const color = feature?.color || defaultStyles.borderColor;
        const weight = feature?.stroke_width ?? defaultStyles.strokeWidth;
        layer.setStyle({
          color: isSelected ? selectedStyle.color : color,
          weight: isSelected ? 4 : weight,
          opacity: feature?.opacity ?? 1,
        });
      },
    };

    layerManager.layers.forEach((layer, featureId) => {
      if (!layer.setStyle) return;

      const fid = String(featureId);
      const isSelected = selectedFeatures.has(fid);
      const feature = props.features.find((f) => String(f.id) === fid);

      if (!isSelected && layer.__atlas_originalStyle) {
        layer.setStyle(layer.__atlas_originalStyle);
        return;
      }

      if (layer instanceof L.CircleMarker) {
        styleStrategies.CircleMarker(layer, isSelected, feature);
      } else if (layer instanceof L.Polygon || layer instanceof L.Rectangle) {
        styleStrategies.Polygon(layer, isSelected, feature);
      } else if (layer instanceof L.Polyline) {
        styleStrategies.Polyline(layer, isSelected, feature);
      }
    });
  }

  // ===== CRUD OPERATIONS =====
  async function updateFeaturePosition(
    feature: Feature,
    deltaLat: number,
    deltaLng: number,
  ) {
    try {
      const updatedGeometry = updateGeometryCoordinates(
        feature.geometry,
        deltaLat,
        deltaLng,
      );
      const updateData = { geometry: updatedGeometry };

      const idx = props.features.findIndex(
        (f) => String(f.id) === String(feature.id),
      );
      if (idx !== -1) {
        const next = [...props.features];
        next[idx] = { ...feature, geometry: updatedGeometry };
        emit("features-loaded", next);
      }

      const response = await fetch(
        `${import.meta.env.VITE_API_URL}/maps/features/${feature.id}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(updateData),
        },
      );

      if (!response.ok)
        throw new Error(`HTTP error! status: ${response.status}`);

      const updatedFeature = await response.json();

      const featureIndex = props.features.findIndex((f) => f.id === feature.id);
      if (featureIndex !== -1) {
        const updatedFeatures = [...props.features];
        updatedFeatures[featureIndex] = updatedFeature;
        emit("features-loaded", updatedFeatures);
      }
    } catch (error) {
      console.error("Error updating feature position:", error);
    }
  }

  async function deleteFeatures(
    featuresToDelete: string[] | Set<string>,
    featureLayerManager: FeatureLayerManager,
    map: L.Map,
    emit: EmitFn,
    options?: { clearSelection?: boolean; updateVisualsAfter?: boolean },
  ) {
    const featureIds = Array.isArray(featuresToDelete)
      ? featuresToDelete
      : Array.from(featuresToDelete);

    if (featureIds.length === 0) return;

    featureIds.forEach((featureId) => {
      const fid = String(featureId);
      const layer = featureLayerManager.layers.get(fid);
      if (layer) {
        map.removeLayer(layer);
        featureLayerManager.layers.delete(fid);
      }
    });

    const deletePromises = featureIds
      .filter((fid) => !fid.startsWith("temp_"))
      .map((featureId) =>
        fetch(`${import.meta.env.VITE_API_URL}/maps/features/${featureId}`, {
          method: "DELETE",
        })
          .then((response) => {
            if (!response.ok) {
              console.error(`Failed to delete feature ${featureId}`);
            }
          })
          .catch((error) => {
            console.error(`Error deleting feature ${featureId}:`, error);
          }),
      );

    await Promise.all(deletePromises);

    const remainingFeatures = props.features.filter(
      (f) => !featureIds.includes(String(f.id)),
    );
    emit("features-loaded", remainingFeatures);

    if (options?.clearSelection && featuresToDelete instanceof Set) {
      featuresToDelete.clear();
    }

    if (options?.updateVisualsAfter) {
      updateFeatureSelectionVisual(map, featureLayerManager, new Set());
    }
  }

  async function deleteSelectedFeatures(
    selectedFeatures: Set<string>,
    featureLayerManager: FeatureLayerManager,
    map: L.Map,
    emit: EmitFn,
  ) {
    await deleteFeatures(selectedFeatures, featureLayerManager, map, emit, {
      clearSelection: true,
      updateVisualsAfter: true,
    });
  }

  async function deleteFeature(
    featureId: string | number,
    featureLayerManager: FeatureLayerManager,
    map: L.Map,
    emit: EmitFn,
  ) {
    await deleteFeatures([String(featureId)], featureLayerManager, map, emit);
  }

  function updateGeometryCoordinates(
    geometry: Geometry | null,
    deltaLat: number,
    deltaLng: number,
  ) {
    if (!geometry || !geometry.coordinates) return geometry;

    const updatedGeometry = { ...geometry };

    switch (geometry.type) {
      case "Point":
        updatedGeometry.coordinates = [
          geometry.coordinates[0] + deltaLng,
          geometry.coordinates[1] + deltaLat,
        ];
        break;
      case "LineString":
        updatedGeometry.coordinates = geometry.coordinates.map((coord: any) => [
          coord[0] + deltaLng,
          coord[1] + deltaLat,
        ]);
        break;
      case "Polygon":
        updatedGeometry.coordinates = geometry.coordinates.map((ring: any[]) =>
          ring.map((coord: any) => [coord[0] + deltaLng, coord[1] + deltaLat]),
        );
        break;
      default:
        return geometry;
    }

    return updatedGeometry;
  }

  function toggleDeleteMode() {
    if (props.activeEditMode === "DELETE_FEATURE") emit("mode-change", null);
    else emit("mode-change", "DELETE_FEATURE");
  }

  return {
    isDeleteMode,

    createSquare,
    createRectangle,
    createCircle,
    createTriangle,
    createOval,
    createPointAt,
    createLine,
    createPolygon,
    finishFreeLine,

    updateTempSquareFromCenter,
    updateTempRectangleFromCorners,
    updateTempCircleFromCenter,
    updateTempTriangleFromCenter,
    updateTempOvalHeight,
    updateTempOvalWidth,

    squareToFeatureFromCenter,
    rectangleToFeatureFromCorners,
    circleToFeatureFromCenter,
    triangleToFeatureFromCenter,
    ovalToFeatureFromCenter,

    updateFeatureSelectionVisual,

    updateFeaturePosition,
    deleteSelectedFeatures,
    deleteFeature,
    updateGeometryCoordinates,

    toggleDeleteMode,

    smoothFreeLinePoints,

    applyResizeFromDims,

    applyRotateFromAngle,
    applyAngleToLayerFromCanonical,
  };
}
