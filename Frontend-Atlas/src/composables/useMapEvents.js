import { ref } from "vue";
import L from "leaflet";
import { getPixelDistance } from "../utils/mapUtils.js";
import { MAP_CONFIG } from "./useMapConfig.js";

export function useMapEvents(props, emit, layersComposable, editingComposable) {
  const isDrawingLine = ref(false);
  const lineStartPoint = ref(null);
  let tempLine = null;

  const isDrawingFree = ref(false);
  const freeLinePoints = ref([]);
  let tempFreeLine = null;

  let shapeState = null;
  let shapeStartPoint = null;
  let shapeEndPoint = null;
  let tempShape = null;
  let lastMousePos = null;
  let isDrawingShape = false;

  const currentPolygonPoints = ref([]);
  let tempPolygon = null;

  const selectedFeatures = ref(new Set());
  const isDraggingFeatures = ref(false);
  const originalPositions = ref(new Map());
  const justFinishedDrag = ref(false);

  const suppressNextFeatureClick = ref(false);

  let moveDownClient = null;
  let moveDownLatLng = null;
  let downFeatureId = null;
  let cancelDeselect = false;

  let anchorDrag = null;

  // =======================
  // DOM → featureId resolver
  // =======================
  function getFeatureIdFromDomTarget(domTarget) {
    let el = domTarget;
    for (let i = 0; i < 6 && el; i += 1, el = el.parentElement) {
      if (el._atlasFeatureId) return String(el._atlasFeatureId);
    }
    return null;
  }

  // =======================
  // Layer resolving (critical)
  // =======================
  function resolveEditLayer(raw) {
    if (!raw) return null;

    if (typeof raw.getLatLngs === "function" && typeof raw.setLatLngs === "function") return raw;

    if (typeof raw.getLatLng === "function" && typeof raw.setLatLng === "function" && !raw.getLatLngs) return raw;

    if (typeof raw.getLayers === "function") {
      const kids = raw.getLayers();
      if (Array.isArray(kids) && kids.length) {
        const polys = kids.find((k) => k instanceof L.Polygon || k instanceof L.Rectangle);
        if (polys && typeof polys.getLatLngs === "function" && typeof polys.setLatLngs === "function") return polys;

        const lines = kids.find(
          (k) => k instanceof L.Polyline && typeof k.getLatLngs === "function" && typeof k.setLatLngs === "function"
        );
        if (lines) return lines;

        const pt = kids.find((k) => typeof k.getLatLng === "function" && typeof k.setLatLng === "function" && !k.getLatLngs);
        if (pt) return pt;

        for (const k of kids) {
          const r = resolveEditLayer(k);
          if (r) return r;
        }
      }
    }

    return raw;
  }

  function getLayerForOps(featureLayerManager, fid) {
    const raw = featureLayerManager.layers.get(String(fid));
    return resolveEditLayer(raw);
  }

  // =======================
  // Rotation / geometry helpers
  // =======================
  function normalizeAngleDeg(a) {
    const n = Number(a);
    if (!Number.isFinite(n)) return 0;
    let x = n % 360;
    if (x < 0) x += 360;
    return x;
  }

  function shortestDeltaDeg(fromDeg, toDeg) {
    let d = normalizeAngleDeg(toDeg) - normalizeAngleDeg(fromDeg);
    if (d > 180) d -= 360;
    if (d < -180) d += 360;
    return d;
  }

  function getFeatureById(fid) {
    const id = String(fid);
    return props.features.find((f) => String(f.id) === id) || null;
  }

  function getAngleDegFor(fid, layer) {
    const feature = getFeatureById(fid) || layer?.feature || null;
    const p = feature?.properties || {};
    const raw = p.rotationDeg ?? p.angleDeg ?? p.angle ?? p.rotation ?? 0;
    return normalizeAngleDeg(raw);
  }

  function setAngleDegFor(fid, layer, angleDeg) {
    const a = normalizeAngleDeg(angleDeg);
    const feature = getFeatureById(fid) || layer?.feature || null;
    if (!feature) return;
    if (!feature.properties) feature.properties = {};
    feature.properties.rotationDeg = a;

    if (layer?.feature?.properties) {
      layer.feature.properties.rotationDeg = a;
    }
  }

  function setCenterFor(fid, layer, centerLatLng) {
    const feature = getFeatureById(fid) || layer?.feature || null;
    if (!feature) return;
    if (!feature.properties) feature.properties = {};

    const c = feature.properties.center;

    if (Array.isArray(c) && c.length >= 2) {
      feature.properties.center = [centerLatLng.lng, centerLatLng.lat];
    } else if (c && typeof c === "object" && "lat" in c && "lng" in c) {
      feature.properties.center = { lat: centerLatLng.lat, lng: centerLatLng.lng };
    } else {
      feature.properties.center = { lat: centerLatLng.lat, lng: centerLatLng.lng };
    }

    if (layer?.feature?.properties) {
      layer.feature.properties.center = feature.properties.center;
    }
  }

  function rotatePoint(pt, centerPt, rad) {
    const dx = pt.x - centerPt.x;
    const dy = pt.y - centerPt.y;
    const c = Math.cos(rad);
    const s = Math.sin(rad);
    return L.point(centerPt.x + dx * c - dy * s, centerPt.y + dx * s + dy * c);
  }

  function rotatePointsTree(pts, centerPt, rad) {
    if (Array.isArray(pts)) return pts.map((x) => rotatePointsTree(x, centerPt, rad));
    return rotatePoint(pts, centerPt, rad);
  }

  function flattenPoints(pts, out = []) {
    if (Array.isArray(pts)) pts.forEach((x) => flattenPoints(x, out));
    else out.push(pts);
    return out;
  }

  function boundsFromPoints(pointsFlat) {
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const p of pointsFlat) {
      if (p.x < minX) minX = p.x;
      if (p.y < minY) minY = p.y;
      if (p.x > maxX) maxX = p.x;
      if (p.y > maxY) maxY = p.y;
    }
    return { minX, minY, maxX, maxY };
  }

  function handleToAnchorPoint(b, handle) {
    const cx = (b.minX + b.maxX) / 2;
    const cy = (b.minY + b.maxY) / 2;
    switch (handle) {
      case "nw": return L.point(b.minX, b.minY);
      case "ne": return L.point(b.maxX, b.minY);
      case "se": return L.point(b.maxX, b.maxY);
      case "sw": return L.point(b.minX, b.maxY);
      case "n":  return L.point(cx, b.minY);
      case "e":  return L.point(b.maxX, cy);
      case "s":  return L.point(cx, b.maxY);
      case "w":  return L.point(b.minX, cy);
      default:   return L.point(cx, cy);
    }
  }

  function oppositeHandle(handle) {
    switch (handle) {
      case "nw": return "se";
      case "ne": return "sw";
      case "se": return "nw";
      case "sw": return "ne";
      case "n":  return "s";
      case "s":  return "n";
      case "e":  return "w";
      case "w":  return "e";
      default:   return null;
    }
  }

  function ensureSelectionBBoxGroup(map) {
    if (!map) return null;
    if (!map._selectionBBoxGroup) {
      map._selectionBBoxGroup = L.layerGroup().addTo(map);
      map._selectionBBoxes = new Map();
    }
    return map._selectionBBoxGroup;
  }

  function ensureSelectionAnchorsPane(map) {
    if (!map) return "overlayPane";
    if (!map.getPane("selectionAnchorsPane")) {
      const pane = map.createPane("selectionAnchorsPane");
      pane.style.zIndex = "800";
      pane.style.pointerEvents = "auto";
    }
    return "selectionAnchorsPane";
  }

  function ensureSelectionAnchorGroup(map) {
    if (!map) return null;
    if (!map._selectionAnchorGroup) {
      map._selectionAnchorGroup = L.layerGroup().addTo(map);
      map._selectionAnchors = new Map();
    }
    return map._selectionAnchorGroup;
  }

  function createAnchorMarker(latlng, kind, map) {
    const base = {
      weight: 2,
      pane: ensureSelectionAnchorsPane(map),
      interactive: true,
      bubblingMouseEvents: false,
    };

    if (kind === "rotate") {
      return L.circleMarker(latlng, {
        ...base,
        radius: 6,
        color: "#1a3a8a",
        fillColor: "#dbe7ff",
        fillOpacity: 1.0,
      });
    }

    return L.circleMarker(latlng, {
      ...base,
      radius: kind === "corner" ? 6 : 5,
      color: "#111",
      fillColor: "#fff",
      fillOpacity: 1.0,
    });
  }

  function mapLatLngsToPoints(map, latlngs) {
    if (Array.isArray(latlngs)) return latlngs.map((x) => mapLatLngsToPoints(map, x));
    return map.latLngToLayerPoint(latlngs);
  }

  function mapPointsToLatLngs(map, pts) {
    if (Array.isArray(pts)) return pts.map((x) => mapPointsToLatLngs(map, x));
    return map.layerPointToLatLng(pts);
  }

  function getLayerAllLatLngs(layer) {
    if (layer.getLatLngs) return layer.getLatLngs();
    if (layer.getLatLng) return layer.getLatLng();
    return null;
  }

  function getRotatedFrameData(layer, map, angleDeg) {
    const angleRad = (normalizeAngleDeg(angleDeg) * Math.PI) / 180;
    const bounds = layer.getBounds?.();
    if (!bounds?.isValid?.()) return null;

    const centerLL = bounds.getCenter();
    const centerPt = map.latLngToLayerPoint(centerLL);

    const latlngs = layer.getLatLngs?.();
    if (!latlngs) return null;

    const pts = mapLatLngsToPoints(map, latlngs);
    const pts0 = Math.abs(angleRad) > 1e-9 ? rotatePointsTree(pts, centerPt, -angleRad) : pts;

    const flat0 = flattenPoints(pts0, []);
    const b0 = boundsFromPoints(flat0);

    return { angleRad, centerPt, b0, pts0 };
  }

  function rotatedBBoxLatLngs(layer, map, angleDeg) {
    const fd = getRotatedFrameData(layer, map, angleDeg);
    if (!fd) return null;

    const { angleRad, centerPt, b0 } = fd;

    const nw0 = handleToAnchorPoint(b0, "nw");
    const ne0 = handleToAnchorPoint(b0, "ne");
    const se0 = handleToAnchorPoint(b0, "se");
    const sw0 = handleToAnchorPoint(b0, "sw");

    const back = (p0) => (Math.abs(angleRad) > 1e-9 ? rotatePoint(p0, centerPt, angleRad) : p0);

    const nw = map.layerPointToLatLng(back(nw0));
    const ne = map.layerPointToLatLng(back(ne0));
    const se = map.layerPointToLatLng(back(se0));
    const sw = map.layerPointToLatLng(back(sw0));

    return [nw, ne, se, sw, nw];
  }

  function rotatedAnchorsLatLngs(layer, map, angleDeg) {
    const fd = getRotatedFrameData(layer, map, angleDeg);
    if (!fd) return null;

    const { angleRad, centerPt, b0 } = fd;
    const keys = ["nw", "ne", "se", "sw", "n", "e", "s", "w"];

    const back = (p0) => (Math.abs(angleRad) > 1e-9 ? rotatePoint(p0, centerPt, angleRad) : p0);

    const pts = {};
    for (const k of keys) {
      const p0 = handleToAnchorPoint(b0, k);
      const p = back(p0);
      pts[k] = map.layerPointToLatLng(p);
    }

    return {
      corners: { nw: pts.nw, ne: pts.ne, se: pts.se, sw: pts.sw },
      mids: { n: pts.n, e: pts.e, s: pts.s, w: pts.w },
    };
  }

  function computeRotationHandleLatLng(layer, map, angleDeg) {
    if (!layer || !map || !layer.getLatLngs) return null;

    const fd = getRotatedFrameData(layer, map, angleDeg);
    if (!fd) return null;

    const { angleRad, centerPt, b0 } = fd;

    const n0 = handleToAnchorPoint(b0, "n");
    const n = Math.abs(angleRad) > 1e-9 ? rotatePoint(n0, centerPt, angleRad) : n0;

    const offsetPx = 30;
    const rotPt = L.point(n.x, n.y - offsetPx);

    return map.layerPointToLatLng(rotPt);
  }

  // =======================
  // Selection overlays
  // =======================
  function upsertSelectionBBox(featureId, map, featureLayerManager) {
    if (!map) return;
    ensureSelectionBBoxGroup(map);

    const id = String(featureId);
    const layer = getLayerForOps(featureLayerManager, id);
    if (!layer || typeof layer.getBounds !== "function") return;

    const isLine = layer instanceof L.Polyline && !(layer instanceof L.Polygon);
    if (isLine) return;

    const bounds = layer.getBounds();
    if (!bounds || !bounds.isValid?.()) return;

    const angleDeg = getAngleDegFor(id, layer);
    const useRot = Math.abs(angleDeg) > 1e-6 && typeof layer.getLatLngs === "function";

    const existing = map._selectionBBoxes.get(id);

    if (!useRot) {
      if (existing && typeof existing.setBounds === "function") {
        existing.setBounds(bounds);
        existing.bringToFront?.();
        return;
      }

      if (existing) {
        existing.remove();
        map._selectionBBoxes.delete(id);
      }

      const rect = L.rectangle(bounds, {
        color: "#111",
        weight: 2,
        dashArray: "6 6",
        fill: false,
        interactive: false,
        pane: "overlayPane",
      });

      rect.addTo(map._selectionBBoxGroup);
      rect.bringToFront?.();
      map._selectionBBoxes.set(id, rect);
      return;
    }

    const ring = rotatedBBoxLatLngs(layer, map, angleDeg);
    if (!ring) return;

    if (existing && typeof existing.setLatLngs === "function") {
      existing.setLatLngs(ring);
      existing.bringToFront?.();
      return;
    }

    if (existing) {
      existing.remove();
      map._selectionBBoxes.delete(id);
    }

    const poly = L.polygon(ring, {
      color: "#111",
      weight: 2,
      dashArray: "6 6",
      fill: false,
      interactive: false,
      pane: "overlayPane",
    });

    poly.addTo(map._selectionBBoxGroup);
    poly.bringToFront?.();
    map._selectionBBoxes.set(id, poly);
  }

  function removeSelectionBBox(featureId, map) {
    if (!map || !map._selectionBBoxes) return;
    const id = String(featureId);
    const rect = map._selectionBBoxes.get(id);
    if (rect) {
      rect.remove();
      map._selectionBBoxes.delete(id);
    }
  }

  function clearSelectionBBoxes(map) {
    if (!map || !map._selectionBBoxes) return;
    for (const rect of map._selectionBBoxes.values()) rect.remove();
    map._selectionBBoxes.clear();
  }

  function upsertSelectionAnchors(featureId, map, featureLayerManager) {
    if (!map) return;
    ensureSelectionAnchorGroup(map);

    const id = String(featureId);
    const layer = getLayerForOps(featureLayerManager, id);
    if (!layer || typeof layer.getBounds !== "function") return;

    const isLine = layer instanceof L.Polyline && !(layer instanceof L.Polygon);
    if (isLine && typeof layer.getLatLngs === "function") {
      const latlngs = layer.getLatLngs();
      if (!Array.isArray(latlngs) || latlngs.length < 2) return;

      const a = latlngs[0];
      const b = latlngs[latlngs.length - 1];

      const existing = map._selectionAnchors.get(id);
      if (existing && existing.markers?.length === 2) {
        existing.markers[0].setLatLng(a);
        existing.markers[1].setLatLng(b);
        existing.group.bringToFront?.();
        return;
      }

      if (existing) {
        existing.group.remove();
        map._selectionAnchors.delete(id);
      }

      const group = L.layerGroup();

      const mA = createAnchorMarker(a, "corner", map);
      const mB = createAnchorMarker(b, "corner", map);

      mA._isSelectionAnchor = true;
      mB._isSelectionAnchor = true;

      mA._atlasFeatureId = id;
      mB._atlasFeatureId = id;

      mA._anchorHandle = "lineStart";
      mB._anchorHandle = "lineEnd";

      mA.on("mousedown", (ev) => {
        ev.originalEvent?.preventDefault();
        ev.originalEvent?.stopPropagation();
        startLineEndpointDrag(id, 0, ev, map);
      });

      mB.on("mousedown", (ev) => {
        ev.originalEvent?.preventDefault();
        ev.originalEvent?.stopPropagation();
        startLineEndpointDrag(id, latlngs.length - 1, ev, map);
      });

      group.addLayer(mA);
      group.addLayer(mB);

      group.addTo(map._selectionAnchorGroup);
      group.bringToFront?.();
      map._selectionAnchors.set(id, { group, markers: [mA, mB] });
      return;
    }

    const bounds = layer.getBounds();
    if (!bounds || !bounds.isValid?.()) return;

    const angleDeg = getAngleDegFor(id, layer);
    const useRot = Math.abs(angleDeg) > 1e-6 && typeof layer.getLatLngs === "function";

    const cornersMids = useRot
      ? rotatedAnchorsLatLngs(layer, map, angleDeg)
      : (() => {
          const nw = bounds.getNorthWest();
          const ne = bounds.getNorthEast();
          const sw = bounds.getSouthWest();
          const se = bounds.getSouthEast();

          const n = L.latLng(nw.lat, (nw.lng + ne.lng) / 2);
          const s = L.latLng(sw.lat, (sw.lng + se.lng) / 2);
          const w = L.latLng((nw.lat + sw.lat) / 2, nw.lng);
          const e = L.latLng((ne.lat + se.lat) / 2, ne.lng);

          return {
            corners: { nw, ne, se, sw },
            mids: { n, e, s, w },
          };
        })();

    const rotLatLng = computeRotationHandleLatLng(layer, map, angleDeg);

    const existing = map._selectionAnchors.get(id);
    if (existing) {
      const arr = existing.markers;
      if (arr.length >= 8) {
        arr[0].setLatLng(cornersMids.corners.nw);
        arr[1].setLatLng(cornersMids.corners.ne);
        arr[2].setLatLng(cornersMids.corners.se);
        arr[3].setLatLng(cornersMids.corners.sw);

        arr[4].setLatLng(cornersMids.mids.n);
        arr[5].setLatLng(cornersMids.mids.e);
        arr[6].setLatLng(cornersMids.mids.s);
        arr[7].setLatLng(cornersMids.mids.w);

        if (arr[8] && rotLatLng) arr[8].setLatLng(rotLatLng);
      }
      existing.group.bringToFront?.();
      return;
    }

    const group = L.layerGroup();

    const markerSpecs = [
      { ll: cornersMids.corners.nw, kind: "corner", key: "nw" },
      { ll: cornersMids.corners.ne, kind: "corner", key: "ne" },
      { ll: cornersMids.corners.se, kind: "corner", key: "se" },
      { ll: cornersMids.corners.sw, kind: "corner", key: "sw" },
      { ll: cornersMids.mids.n, kind: "mid", key: "n" },
      { ll: cornersMids.mids.e, kind: "mid", key: "e" },
      { ll: cornersMids.mids.s, kind: "mid", key: "s" },
      { ll: cornersMids.mids.w, kind: "mid", key: "w" },
    ];

    const markers = markerSpecs.map((spec) => {
      const m = createAnchorMarker(spec.ll, spec.kind, map);

      m._isSelectionAnchor = true;
      m._atlasFeatureId = id;
      m._anchorHandle = spec.key;

      m.on("mousedown", (ev) => {
        ev.originalEvent?.preventDefault();
        ev.originalEvent?.stopPropagation();
        startAnchorDrag(id, spec.key, ev, map);
      });

      group.addLayer(m);
      return m;
    });

    if (rotLatLng) {
      const mRot = createAnchorMarker(rotLatLng, "rotate", map);
      mRot._isSelectionAnchor = true;
      mRot._atlasFeatureId = id;
      mRot._anchorHandle = "rot";

      mRot.on("mousedown", (ev) => {
        ev.originalEvent?.preventDefault();
        ev.originalEvent?.stopPropagation();
        startRotateDrag(id, ev, map);
      });

      group.addLayer(mRot);
      markers.push(mRot);
    }

    group.addTo(map._selectionAnchorGroup);
    group.bringToFront?.();
    map._selectionAnchors.set(id, { group, markers });
  }

  function removeSelectionAnchors(featureId, map) {
    if (!map || !map._selectionAnchors) return;
    const id = String(featureId);
    const entry = map._selectionAnchors.get(id);
    if (!entry) return;
    entry.group.remove();
    map._selectionAnchors.delete(id);
  }

  function clearSelectionAnchors(map) {
    if (!map || !map._selectionAnchors) return;
    for (const entry of map._selectionAnchors.values()) entry.group.remove();
    map._selectionAnchors.clear();
  }

  function syncSelectionOverlays(map) {
    clearSelectionBBoxes(map);
    clearSelectionAnchors(map);

    selectedFeatures.value.forEach((fid) => {
      upsertSelectionBBox(fid, map, layersComposable.featureLayerManager);
      upsertSelectionAnchors(fid, map, layersComposable.featureLayerManager);
    });
  }

  // =======================
  // Anchor drag: resize/line/rotate
  // =======================
  function startAnchorDrag(fid, handle, ev, map) {
    const layer = getLayerForOps(layersComposable.featureLayerManager, fid);
    if (!layer) return;

    const isCircle = typeof layer.getRadius === "function" && typeof layer.setRadius === "function";
    const centerLatLng = isCircle ? layer.getLatLng() : (layer.getBounds ? layer.getBounds().getCenter() : null);

    if (isCircle && !centerLatLng) return;

    const latlngs = !isCircle ? getLayerAllLatLngs(layer) : null;
    if (!isCircle && !latlngs) return;

    map.dragging.disable();

    if (isCircle) {
      anchorDrag = {
        kind: "resize",
        fid: String(fid),
        handle,
        isCircle: true,
        centerLatLng,
      };
      return;
    }

    const angleDeg = getAngleDegFor(fid, layer);
    const angleRad = (angleDeg * Math.PI) / 180;

    const startMousePt = map.latLngToLayerPoint(ev.latlng);
    const ptsScreen = mapLatLngsToPoints(map, latlngs);

    const bounds = layer.getBounds();
    const centerLL = bounds.getCenter();
    const centerPt = map.latLngToLayerPoint(centerLL);

    const pts0 = Math.abs(angleRad) > 1e-9 ? rotatePointsTree(ptsScreen, centerPt, -angleRad) : ptsScreen;
    const flat0 = flattenPoints(pts0, []);
    const b0 = boundsFromPoints(flat0);

    const movingPtStart0 = handleToAnchorPoint(b0, handle);
    const fixedH = oppositeHandle(handle);
    const fixedPt0 = fixedH ? handleToAnchorPoint(b0, fixedH) : L.point((b0.minX + b0.maxX) / 2, (b0.minY + b0.maxY) / 2);

    anchorDrag = {
      kind: "resize",
      fid: String(fid),
      handle,
      isCircle: false,
      angleRad,
      centerPt,
      startMousePt0: Math.abs(angleRad) > 1e-9 ? rotatePoint(startMousePt, centerPt, -angleRad) : startMousePt,
      fixedPt0,
      movingPtStart0,
      startPts0: pts0,
    };
  }

  function startLineEndpointDrag(fid, index, ev, map) {
    const layer = getLayerForOps(layersComposable.featureLayerManager, fid);
    if (!layer || !map) return;

    const isLine = layer instanceof L.Polyline && !(layer instanceof L.Polygon);
    if (!isLine || typeof layer.getLatLngs !== "function" || typeof layer.setLatLngs !== "function") return;

    const latlngs = layer.getLatLngs();
    if (!Array.isArray(latlngs) || latlngs.length < 2) return;

    const idx = index === 0 ? 0 : latlngs.length - 1;

    map.dragging.disable();

    anchorDrag = {
      kind: "lineEndpoint",
      fid: String(fid),
      index: idx,
    };
  }

  function startRotateDrag(fid, ev, map) {
    const layer = getLayerForOps(layersComposable.featureLayerManager, fid);
    if (!layer || !map) return;

    if (!layer.getLatLngs || typeof layer.setLatLngs !== "function") return;

    const angleStartDeg = getAngleDegFor(fid, layer);

    const fd = getRotatedFrameData(layer, map, angleStartDeg);
    if (!fd) return;

    const { centerPt } = fd;

    const startMousePt = map.latLngToLayerPoint(ev.latlng);
    const startMouseAngle = Math.atan2(startMousePt.y - centerPt.y, startMousePt.x - centerPt.x);

    const latlngs = layer.getLatLngs();
    const ptsScreen = mapLatLngsToPoints(map, latlngs);

    map.dragging.disable();

    anchorDrag = {
      kind: "rotate",
      fid: String(fid),
      centerPt,
      startMouseAngle,
      startAngleDeg: angleStartDeg,
      startPtsScreen: ptsScreen,
    };
  }

  function updateAnchorDrag(ev, map) {
    if (!anchorDrag) return;

    const fid = anchorDrag.fid;
    const layer = getLayerForOps(layersComposable.featureLayerManager, fid);
    if (!layer) return;

    if (anchorDrag.kind === "rotate") {
      const { centerPt, startMouseAngle, startAngleDeg, startPtsScreen } = anchorDrag;

      const curMousePt = map.latLngToLayerPoint(ev.latlng);
      const curMouseAngle = Math.atan2(curMousePt.y - centerPt.y, curMousePt.x - centerPt.x);

      const deltaRad = curMouseAngle - startMouseAngle;
      const deltaDeg = (deltaRad * 180) / Math.PI;

      const newAngleDeg = normalizeAngleDeg(startAngleDeg + deltaDeg);
      setAngleDegFor(fid, layer, newAngleDeg);

      const newRad = (newAngleDeg * Math.PI) / 180;
      const startRad = (startAngleDeg * Math.PI) / 180;
      const applyDelta = newRad - startRad;

      const rotatedPts = rotatePointsTree(startPtsScreen, centerPt, applyDelta);
      const newLatLngs = mapPointsToLatLngs(map, rotatedPts);

      layer.setLatLngs(newLatLngs);

      upsertSelectionBBox(fid, map, layersComposable.featureLayerManager);
      upsertSelectionAnchors(fid, map, layersComposable.featureLayerManager);

      if (props.activeEditMode === "RESIZE_SHAPE") {
        const dims = getDimsMetersFromLayerId(fid, map);
        emit("resize-selection", { featureId: String(fid), ...dims, angleDeg: newAngleDeg });
      }
      return;
    }

    if (anchorDrag.kind === "lineEndpoint") {
      if (!layer.getLatLngs || !layer.setLatLngs) return;

      const latlngs = layer.getLatLngs();
      if (!Array.isArray(latlngs) || latlngs.length < 2) return;

      const idx = anchorDrag.index === 0 ? 0 : latlngs.length - 1;
      const next = latlngs.slice();
      next[idx] = ev.latlng;

      layer.setLatLngs(next);

      upsertSelectionBBox(fid, map, layersComposable.featureLayerManager);
      upsertSelectionAnchors(fid, map, layersComposable.featureLayerManager);
      return;
    }

    if (anchorDrag.kind === "resize" && anchorDrag.isCircle) {
      const layerCircle = layer;

      const c = anchorDrag.centerLatLng;
      const p = ev.latlng;

      const dx = map.distance([c.lat, c.lng], [c.lat, p.lng]);
      const dy = map.distance([c.lat, c.lng], [p.lat, c.lng]);

      let r;
      if (anchorDrag.handle === "e" || anchorDrag.handle === "w") r = dx;
      else if (anchorDrag.handle === "n" || anchorDrag.handle === "s") r = dy;
      else r = Math.max(dx, dy);

      r = Math.max(1, r);

      layerCircle.setLatLng(c);
      layerCircle.setRadius(r);

      setCenterFor(fid, layerCircle, c);

      if (props.activeEditMode === "RESIZE_SHAPE") {
        const dims = getDimsMetersFromLayerId(fid, map);
        const angleDeg = getAngleDegFor(fid, layerCircle);
        emit("resize-selection", { featureId: String(fid), ...dims, angleDeg });
      }

      upsertSelectionBBox(fid, map, layersComposable.featureLayerManager);
      upsertSelectionAnchors(fid, map, layersComposable.featureLayerManager);
      return;
    }

    if (anchorDrag.kind === "resize" && !anchorDrag.isCircle) {
      const curMousePt = map.latLngToLayerPoint(ev.latlng);

      const angleRad = anchorDrag.angleRad || 0;
      const centerPt = anchorDrag.centerPt;

      const cur0 = Math.abs(angleRad) > 1e-9 ? rotatePoint(curMousePt, centerPt, -angleRad) : curMousePt;

      const fixed0 = anchorDrag.fixedPt0;
      const startMove0 = anchorDrag.movingPtStart0;

      const denomX = startMove0.x - fixed0.x;
      const denomY = startMove0.y - fixed0.y;

      let sx = denomX !== 0 ? (cur0.x - fixed0.x) / denomX : 1;
      let sy = denomY !== 0 ? (cur0.y - fixed0.y) / denomY : 1;

      if (anchorDrag.handle === "n" || anchorDrag.handle === "s") sx = 1;
      if (anchorDrag.handle === "e" || anchorDrag.handle === "w") sy = 1;

      const feature = getFeatureById(fid) || layer.feature || null;
      const shapeType = feature?.properties?.shapeType || feature?.properties?.shape || null;

      if (shapeType === "square") {
        if (["nw", "ne", "se", "sw"].includes(anchorDrag.handle)) {
          const s = Math.max(sx, sy);
          sx = s;
          sy = s;
        } else {
          const s = (anchorDrag.handle === "n" || anchorDrag.handle === "s") ? sy : sx;
          sx = s;
          sy = s;
        }
      }

      const MIN_SCALE = 0.05;
      sx = Math.max(MIN_SCALE, sx);
      sy = Math.max(MIN_SCALE, sy);

      function scalePoints0(pts0) {
        if (Array.isArray(pts0)) return pts0.map(scalePoints0);
        const x = fixed0.x + (pts0.x - fixed0.x) * sx;
        const y = fixed0.y + (pts0.y - fixed0.y) * sy;
        return L.point(x, y);
      }

      const newPts0 = scalePoints0(anchorDrag.startPts0);
      const newPts = Math.abs(angleRad) > 1e-9 ? rotatePointsTree(newPts0, centerPt, angleRad) : newPts0;
      const newLatLngs = mapPointsToLatLngs(map, newPts);

      layer.setLatLngs(newLatLngs);

      const newCenter = layer.getBounds?.()?.getCenter?.();
      if (newCenter) setCenterFor(fid, layer, newCenter);

      if (props.activeEditMode === "RESIZE_SHAPE") {
        const dims = getDimsMetersFromLayerId(fid, map);
        const angleDeg = getAngleDegFor(fid, layer);
        emit("resize-selection", { featureId: String(fid), ...dims, angleDeg });
      }

      upsertSelectionBBox(fid, map, layersComposable.featureLayerManager);
      upsertSelectionAnchors(fid, map, layersComposable.featureLayerManager);
    }
  }

  function geometryFromLayer(layer) {
    layer = resolveEditLayer(layer);

    if (layer.getLatLng && !layer.getLatLngs) {
      const ll = layer.getLatLng();
      return { type: "Point", coordinates: [ll.lng, ll.lat] };
    }

    if (layer.getLatLngs) {
      const latlngs = layer.getLatLngs();
      const isPolygon = layer instanceof L.Polygon || layer instanceof L.Rectangle;

      if (!isPolygon) {
        const coords = latlngs.map((ll) => [ll.lng, ll.lat]);
        return { type: "LineString", coordinates: coords };
      }

      const ring = latlngs[0] ?? latlngs;
      const coords = ring.map((ll) => [ll.lng, ll.lat]);

      if (coords.length && (coords[0][0] !== coords[coords.length - 1][0] || coords[0][1] !== coords[coords.length - 1][1])) {
        coords.push(coords[0]);
      }
      return { type: "Polygon", coordinates: [coords] };
    }

    return null;
  }

  async function finishAnchorDrag(map) {
    if (!anchorDrag) return;

    const fid = anchorDrag.fid;
    const raw = layersComposable.featureLayerManager.layers.get(String(fid));
    const layer = resolveEditLayer(raw);

    map.dragging.enable();

    if (!layer) {
      anchorDrag = null;
      return;
    }

    const feature = getFeatureById(fid) || layer.feature || null;

    const geom = geometryFromLayer(layer);
    if (geom) {
      try {
        const response = await fetch(`${import.meta.env.VITE_API_URL}/maps/features/${fid}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ geometry: geom, properties: feature?.properties }),
        });
        if (response.ok) {
          const updated = await response.json();
          const idx = props.features.findIndex((f) => String(f.id) === fid);
          if (idx !== -1) {
            const next = [...props.features];
            next[idx] = updated;
            emit("features-loaded", next);
          }
        }
      } catch (e) {
        console.error("Error updating geometry:", e);
      }
    }

    upsertSelectionBBox(fid, map, layersComposable.featureLayerManager);
    upsertSelectionAnchors(fid, map, layersComposable.featureLayerManager);

    anchorDrag = null;
  }

  // =======================
  // Dims/angle exposure to UI
  // =======================
  function getDimsMetersFromLayerId(fid, map) {
    const layer = getLayerForOps(layersComposable.featureLayerManager, fid);
    if (!layer || !map) return { widthMeters: null, heightMeters: null };

    if (typeof layer.getRadius === "function") {
      const d = 2 * layer.getRadius();
      return { widthMeters: d, heightMeters: d };
    }

    if (typeof layer.getLatLngs === "function" && typeof layer.getBounds === "function") {
      const angleDeg = getAngleDegFor(fid, layer);
      const angleRad = (angleDeg * Math.PI) / 180;

      const bounds = layer.getBounds();
      if (!bounds?.isValid?.()) return { widthMeters: null, heightMeters: null };

      const centerLL = bounds.getCenter();
      const centerPt = map.latLngToLayerPoint(centerLL);

      const latlngs = layer.getLatLngs();
      const pts = mapLatLngsToPoints(map, latlngs);
      const pts0 = Math.abs(angleRad) > 1e-9 ? rotatePointsTree(pts, centerPt, -angleRad) : pts;

      const flat0 = flattenPoints(pts0, []);
      const b0 = boundsFromPoints(flat0);

      const cx = (b0.minX + b0.maxX) / 2;
      const cy = (b0.minY + b0.maxY) / 2;

      const west0 = L.point(b0.minX, cy);
      const east0 = L.point(b0.maxX, cy);
      const north0 = L.point(cx, b0.minY);
      const south0 = L.point(cx, b0.maxY);

      const back = (p0) => (Math.abs(angleRad) > 1e-9 ? rotatePoint(p0, centerPt, angleRad) : p0);

      const westLL = map.layerPointToLatLng(back(west0));
      const eastLL = map.layerPointToLatLng(back(east0));
      const northLL = map.layerPointToLatLng(back(north0));
      const southLL = map.layerPointToLatLng(back(south0));

      const widthMeters = map.distance(westLL, eastLL);
      const heightMeters = map.distance(northLL, southLL);

      return {
        widthMeters: Number.isFinite(widthMeters) && widthMeters > 0 ? widthMeters : null,
        heightMeters: Number.isFinite(heightMeters) && heightMeters > 0 ? heightMeters : null,
      };
    }

    if (typeof layer.getBounds === "function") {
      const b = layer.getBounds();
      if (!b || typeof b.getWest !== "function") return { widthMeters: null, heightMeters: null };

      const c = b.getCenter();

      const widthMeters = map.distance([c.lat, b.getWest()], [c.lat, b.getEast()]);
      const heightMeters = map.distance([b.getSouth(), c.lng], [b.getNorth(), c.lng]);

      return {
        widthMeters: Number.isFinite(widthMeters) && widthMeters > 0 ? widthMeters : null,
        heightMeters: Number.isFinite(heightMeters) && heightMeters > 0 ? heightMeters : null,
      };
    }

    return { widthMeters: null, heightMeters: null };
  }

  function getAngleDegFromLayerId(fid) {
    const layer = getLayerForOps(layersComposable.featureLayerManager, fid);
    if (!layer) return 0;
    return getAngleDegFor(fid, layer);
  }

  function setRotationDegForSelection(angleDeg, map) {
    if (!map) return;
    const a = normalizeAngleDeg(angleDeg);

    selectedFeatures.value.forEach((fid) => {
      const layer = getLayerForOps(layersComposable.featureLayerManager, fid);
      if (!layer || !layer.getLatLngs || typeof layer.setLatLngs !== "function") return;

      const oldAngle = getAngleDegFor(fid, layer);
      const deltaDeg = shortestDeltaDeg(oldAngle, a);
      if (Math.abs(deltaDeg) < 1e-9) {
        upsertSelectionBBox(fid, map, layersComposable.featureLayerManager);
        upsertSelectionAnchors(fid, map, layersComposable.featureLayerManager);
        return;
      }

      const bounds = layer.getBounds?.();
      if (!bounds?.isValid?.()) return;
      const centerPt = map.latLngToLayerPoint(bounds.getCenter());

      const latlngs = layer.getLatLngs();
      const pts = mapLatLngsToPoints(map, latlngs);

      const deltaRad = (deltaDeg * Math.PI) / 180;
      const rotatedPts = rotatePointsTree(pts, centerPt, deltaRad);
      const newLatLngs = mapPointsToLatLngs(map, rotatedPts);

      layer.setLatLngs(newLatLngs);

      setAngleDegFor(fid, layer, a);

      upsertSelectionBBox(fid, map, layersComposable.featureLayerManager);
      upsertSelectionAnchors(fid, map, layersComposable.featureLayerManager);

      if (props.activeEditMode === "RESIZE_SHAPE") {
        const dims = getDimsMetersFromLayerId(fid, map);
        emit("resize-selection", { featureId: String(fid), ...dims, angleDeg: a });
      }
    });
  }

  function applySelectionClick(fid, isCtrl, map) {
    const id = String(fid);

    if (isCtrl) {
      if (selectedFeatures.value.has(id)) selectedFeatures.value.delete(id);
      else selectedFeatures.value.add(id);
    } else {
      if (selectedFeatures.value.size === 1 && selectedFeatures.value.has(id)) {
        selectedFeatures.value.clear();
      } else {
        selectedFeatures.value.clear();
        selectedFeatures.value.add(id);
      }
    }

    syncSelectionOverlays(map);

    if (props.activeEditMode === "RESIZE_SHAPE") {
      if (selectedFeatures.value.has(id)) {
        const dims = getDimsMetersFromLayerId(id, map);
        const angleDeg = getAngleDegFromLayerId(id);
        emit("resize-selection", { featureId: id, ...dims, angleDeg });
      } else {
        emit("resize-selection", { featureId: null, widthMeters: null, heightMeters: null, angleDeg: null });
      }
    }
  }

  function cloneLatLngs(latlngs) {
    if (Array.isArray(latlngs)) return latlngs.map(cloneLatLngs);
    return L.latLng(latlngs.lat, latlngs.lng);
  }

  function translateLatLngs(latlngs, dLat, dLng) {
    if (Array.isArray(latlngs)) return latlngs.map((x) => translateLatLngs(x, dLat, dLng));
    return L.latLng(latlngs.lat + dLat, latlngs.lng + dLng);
  }

  function snapshotSelectedOriginalPositions() {
    originalPositions.value.clear();

    selectedFeatures.value.forEach((featureId) => {
      const layer = getLayerForOps(layersComposable.featureLayerManager, featureId);
      if (!layer) return;

      if (layer.getLatLng && typeof layer.setLatLng === "function" && !layer.getLatLngs) {
        const ll = layer.getLatLng();
        originalPositions.value.set(String(featureId), L.latLng(ll.lat, ll.lng));
        return;
      }

      if (layer.getLatLngs && typeof layer.setLatLngs === "function") {
        originalPositions.value.set(String(featureId), cloneLatLngs(layer.getLatLngs()));
      }
    });
  }

  // =======================
  // Mouse handlers (lines)
  // =======================
  function handleMouseDown(e, map) {
    if (!props.editMode) return;

    if (props.activeEditMode === "CREATE_LINE") {
      e.originalEvent?.preventDefault();
      e.originalEvent?.stopPropagation();

      isDrawingLine.value = true;
      lineStartPoint.value = e.latlng;

      map.dragging.disable();

      tempLine = L.polyline([lineStartPoint.value, lineStartPoint.value], {
        color: "#000000",
        weight: 2,
        opacity: 0.7,
      });
      layersComposable.drawnItems.value.addLayer(tempLine);
      return;
    }

    if (props.activeEditMode === "CREATE_FREE_LINE") {
      e.originalEvent?.preventDefault();
      e.originalEvent?.stopPropagation();

      isDrawingFree.value = true;
      freeLinePoints.value = [e.latlng];

      map.dragging.disable();

      tempFreeLine = L.polyline([e.latlng], {
        color: "#000000",
        weight: 2,
        opacity: 0.7,
        interactive: false,
        pane: "overlayPane",
      });

      layersComposable.drawnItems.value.addLayer(tempFreeLine);
      tempFreeLine.bringToFront();
    }
  }

  function handleMouseMove(e, map) {
    if (isDrawingLine.value && lineStartPoint.value && tempLine) {
      tempLine.setLatLngs([lineStartPoint.value, e.latlng]);
      return;
    }

    if (isDrawingFree.value && tempFreeLine) {
      freeLinePoints.value.push(e.latlng);
      const smoothedPoints = editingComposable.smoothFreeLinePoints(freeLinePoints.value);
      tempFreeLine.setLatLngs(smoothedPoints);
    }

    if (anchorDrag) {
      updateAnchorDrag(e, map);
    }
  }

  function handleMouseUp(e, map) {
    if (isDrawingLine.value && lineStartPoint.value) {
      isDrawingLine.value = false;
      map.dragging.enable();

      const distance = getPixelDistance(map, lineStartPoint.value, e.latlng);
      if (distance < MAP_CONFIG.DRAWING_TOLERANCE) {
        cleanupTempLine();
        lineStartPoint.value = null;
        return;
      }

      if (tempLine) {
        layersComposable.drawnItems.value.removeLayer(tempLine);
        tempLine = null;
      }

      editingComposable.createLine(lineStartPoint.value, e.latlng, map, layersComposable);
      lineStartPoint.value = null;
      return;
    }

    if (isDrawingFree.value) {
      isDrawingFree.value = false;
      map.dragging.enable();

      editingComposable.finishFreeLine(freeLinePoints.value, tempFreeLine, map, layersComposable);

      freeLinePoints.value = [];
      tempFreeLine = null;
    }
  }

  // =======================
  // Shape drawing handlers
  // =======================
  function handleShapeMouseDown(e, map) {
    if (e.target && e.target._isFeatureClick) return;
    if (props.activeEditMode !== "CREATE_SHAPES" || !props.selectedShape) return;

    isDrawingShape = true;
    map.dragging.disable();

    e.originalEvent?.preventDefault();
    e.originalEvent?.stopPropagation();
    e.originalEvent?.stopImmediatePropagation?.();

    const shapeType = props.selectedShape;

    switch (shapeType) {
      case "square":
        shapeState = "drawing";
        shapeStartPoint = e.latlng;
        break;

      case "rectangle":
        shapeState = "drawing";
        shapeStartPoint = e.latlng;
        tempShape = L.rectangle(
          [
            [shapeStartPoint.lat, shapeStartPoint.lng],
            [shapeStartPoint.lat, shapeStartPoint.lng],
          ],
          { color: "#000000", weight: 2, fillColor: "#cccccc", fillOpacity: 0.5 }
        );
        layersComposable.drawnItems.value.addLayer(tempShape);
        break;

      case "circle":
      case "triangle":
        shapeState = "drawing";
        shapeStartPoint = e.latlng;
        break;

      case "oval":
        if (shapeState === null) {
          shapeState = "adjusting_height";
          shapeStartPoint = e.latlng;
        }
        break;

      default:
        isDrawingShape = false;
        map.dragging.enable();
        break;
    }
  }

  function handleShapeMouseMove(e, map) {
    lastMousePos = e.latlng;

    if (props.activeEditMode !== "CREATE_SHAPES" || !props.selectedShape) return;

    const shapeType = props.selectedShape;

    switch (shapeType) {
      case "square":
        if (shapeState === "drawing" && shapeStartPoint) {
          tempShape = editingComposable.updateTempSquareFromCenter(shapeStartPoint, e.latlng, map, layersComposable, tempShape);
        }
        break;

      case "rectangle":
        if (shapeState === "drawing" && shapeStartPoint) {
          tempShape = editingComposable.updateTempRectangleFromCorners(shapeStartPoint, e.latlng, map, layersComposable, tempShape);
        }
        break;

      case "circle":
        if (shapeState === "drawing" && shapeStartPoint) {
          tempShape = editingComposable.updateTempCircleFromCenter(shapeStartPoint, e.latlng, map, layersComposable, tempShape);
        }
        break;

      case "triangle":
        if (shapeState === "drawing" && shapeStartPoint) {
          tempShape = editingComposable.updateTempTriangleFromCenter(shapeStartPoint, e.latlng, map, layersComposable, tempShape);
        }
        break;

      case "oval":
        if (shapeState === "adjusting_height" && shapeStartPoint) {
          tempShape = editingComposable.updateTempOvalHeight(shapeStartPoint, e.latlng, map, layersComposable, tempShape);
        } else if (shapeState === "adjusting_width" && shapeStartPoint && shapeEndPoint) {
          tempShape = editingComposable.updateTempOvalWidth(shapeStartPoint, shapeEndPoint, e.latlng, map, layersComposable, tempShape);
        }
        break;
    }
  }

  function handleShapeMouseUp(e, map) {
    if (!shapeStartPoint || !props.selectedShape) return;

    const shapeType = props.selectedShape;

    switch (shapeType) {
      case "square":
        if (shapeState === "drawing") {
          isDrawingShape = false;
          map.dragging.enable();

          const distance = getPixelDistance(map, shapeStartPoint, e.latlng);
          if (distance < MAP_CONFIG.DRAWING_TOLERANCE) {
            cleanupTempShape();
            return;
          }

          if (tempShape) {
            layersComposable.drawnItems.value.removeLayer(tempShape);
            tempShape = null;
          }
          editingComposable.createSquare(shapeStartPoint, e.latlng, map, layersComposable);

          shapeState = null;
          shapeStartPoint = null;
          lastMousePos = null;
        }
        break;

      case "rectangle":
        if (shapeState === "drawing") {
          isDrawingShape = false;
          map.dragging.enable();

          const distance = getPixelDistance(map, shapeStartPoint, e.latlng);
          if (distance < MAP_CONFIG.DRAWING_TOLERANCE) {
            cleanupTempShape();
            return;
          }

          if (tempShape) {
            layersComposable.drawnItems.value.removeLayer(tempShape);
            tempShape = null;
          }
          editingComposable.createRectangle(shapeStartPoint, e.latlng, map, layersComposable);

          shapeState = null;
          shapeStartPoint = null;
          lastMousePos = null;
        }
        break;

      case "circle":
        if (shapeState === "drawing") {
          isDrawingShape = false;
          map.dragging.enable();

          const distance = getPixelDistance(map, shapeStartPoint, e.latlng);
          if (distance < MAP_CONFIG.DRAWING_TOLERANCE) {
            cleanupTempShape();
            return;
          }

          if (tempShape) {
            layersComposable.drawnItems.value.removeLayer(tempShape);
            tempShape = null;
          }
          editingComposable.createCircle(shapeStartPoint, e.latlng, map, layersComposable);

          shapeState = null;
          shapeStartPoint = null;
          lastMousePos = null;
        }
        break;

      case "triangle":
        if (shapeState === "drawing") {
          isDrawingShape = false;
          map.dragging.enable();

          const distance = getPixelDistance(map, shapeStartPoint, e.latlng);
          if (distance < MAP_CONFIG.DRAWING_TOLERANCE) {
            cleanupTempShape();
            return;
          }

          if (tempShape) {
            layersComposable.drawnItems.value.removeLayer(tempShape);
            tempShape = null;
          }
          editingComposable.createTriangle(shapeStartPoint, e.latlng, map, layersComposable);

          shapeState = null;
          shapeStartPoint = null;
          lastMousePos = null;
        }
        break;

      case "oval":
        if (shapeState === "adjusting_height") {
          shapeState = "adjusting_width";
          shapeEndPoint = e.latlng;
        } else if (shapeState === "adjusting_width") {
          isDrawingShape = false;
          map.dragging.enable();

          if (tempShape) {
            layersComposable.drawnItems.value.removeLayer(tempShape);
            tempShape = null;
          }
          editingComposable.createOval(shapeStartPoint, shapeEndPoint, e.latlng, map, layersComposable);

          shapeState = null;
          shapeStartPoint = null;
          shapeEndPoint = null;
          lastMousePos = null;
        }
        break;
    }
  }

  // =======================
  // Map click handler
  // =======================
  function handleMapClick(e, map) {
    if (!props.editMode || !props.activeEditMode) return;

    switch (props.activeEditMode) {
      case "CREATE_POINT":
        editingComposable.createPointAt(e.latlng, map, layersComposable);
        break;
      case "CREATE_POLYGON":
        handlePolygonClick(e.latlng, map);
        break;
      default:
        break;
    }
  }

  // =======================
  // Polygon handlers
  // =======================
  function handlePolygonClick(latlng, map) {
    currentPolygonPoints.value.push(latlng);
    updatePolygonLines(map);
  }

  function updatePolygonLines(map) {
    if (tempPolygon) {
      layersComposable.drawnItems.value.removeLayer(tempPolygon);
    }

    if (currentPolygonPoints.value.length < 2) return;

    const lines = [];
    for (let i = 0; i < currentPolygonPoints.value.length - 1; i += 1) {
      lines.push(currentPolygonPoints.value[i], currentPolygonPoints.value[i + 1]);
    }

    if (currentPolygonPoints.value.length >= 3) {
      lines.push(currentPolygonPoints.value[currentPolygonPoints.value.length - 1], currentPolygonPoints.value[0]);
    }

    tempPolygon = L.polyline(lines, {
      color: "#000000",
      weight: 2,
      opacity: 1.0,
    });
    layersComposable.drawnItems.value.addLayer(tempPolygon);
  }

  function finishPolygon(map) {
    if (currentPolygonPoints.value.length < 3) return;

    const points = [...currentPolygonPoints.value, currentPolygonPoints.value[0]];

    if (tempPolygon) {
      layersComposable.drawnItems.value.removeLayer(tempPolygon);
      tempPolygon = null;
    }

    editingComposable.createPolygon(points, map, layersComposable);
    currentPolygonPoints.value = [];
  }

  function handleRightClick(e, map) {
    if (!props.editMode || props.activeEditMode !== "CREATE_POLYGON") return;
    e.originalEvent?.preventDefault();
    if (currentPolygonPoints.value.length >= 3) finishPolygon(map);
  }

  function handleMapDoubleClick(e, map) {
    if (!props.editMode || props.activeEditMode !== "CREATE_POLYGON") return;
    if (currentPolygonPoints.value.length >= 3) finishPolygon(map);
  }

  // =======================
  // Movement handlers (select + drag objects)
  // =======================
  function handleMoveMouseDown(e, map) {
    if (!props.editMode) return;
    if (props.activeEditMode && props.activeEditMode !== "RESIZE_SHAPE") return;

    justFinishedDrag.value = false;

    const oe = e.originalEvent;
    moveDownClient = oe ? L.point(oe.clientX, oe.clientY) : null;
    moveDownLatLng = e.latlng;
    cancelDeselect = false;

    downFeatureId = getFeatureIdFromDomTarget(oe?.target);

    if (downFeatureId) {
      map.dragging.disable();

      isDraggingFeatures.value = false;

      if (selectedFeatures.value.has(String(downFeatureId))) snapshotSelectedOriginalPositions();
      else originalPositions.value.clear();

      return;
    }

    isDraggingFeatures.value = false;
    originalPositions.value.clear();
  }

  function handleMoveMouseMove(e, map) {
    if (anchorDrag) {
      updateAnchorDrag(e, map);
      return;
    }
    if (!props.editMode) return;
    if (props.activeEditMode && props.activeEditMode !== "RESIZE_SHAPE") return;
    if (!moveDownClient || !moveDownLatLng) return;

    const oe = e.originalEvent;
    const cur = oe ? L.point(oe.clientX, oe.clientY) : null;
    const distPx = cur ? moveDownClient.distanceTo(cur) : 0;

    if (downFeatureId) {
      if (!isDraggingFeatures.value && distPx > MAP_CONFIG.DRAG_THRESHOLD) {
        isDraggingFeatures.value = true;

        const isCtrl = !!(oe?.ctrlKey || oe?.metaKey);

        if (!selectedFeatures.value.has(String(downFeatureId))) {
          if (!isCtrl) selectedFeatures.value.clear();
          selectedFeatures.value.add(String(downFeatureId));
          syncSelectionOverlays(map);
        }

        snapshotSelectedOriginalPositions();
      }

      if (isDraggingFeatures.value) {
        const dLat = e.latlng.lat - moveDownLatLng.lat;
        const dLng = e.latlng.lng - moveDownLatLng.lng;

        selectedFeatures.value.forEach((featureId) => {
          const layer = getLayerForOps(layersComposable.featureLayerManager, featureId);
          const orig = originalPositions.value.get(String(featureId));
          if (!layer || !orig) return;

          if (layer.getLatLng && typeof layer.setLatLng === "function" && !layer.getLatLngs) {
            layer.setLatLng(L.latLng(orig.lat + dLat, orig.lng + dLng));
            return;
          }

          if (layer.getLatLngs && typeof layer.setLatLngs === "function") {
            layer.setLatLngs(translateLatLngs(orig, dLat, dLng));
          }
        });

        selectedFeatures.value.forEach((fid) => {
          upsertSelectionBBox(fid, map, layersComposable.featureLayerManager);
          upsertSelectionAnchors(fid, map, layersComposable.featureLayerManager);
        });
      }

      return;
    }

    if (distPx > MAP_CONFIG.DRAG_THRESHOLD) cancelDeselect = true;
  }

  function handleMoveMouseUp(e, map) {
    if (anchorDrag) {
      finishAnchorDrag(map);
      return;
    }
    if (!props.editMode) return;
    if (props.activeEditMode && props.activeEditMode !== "RESIZE_SHAPE") return;
    if (!moveDownClient || !moveDownLatLng) return;

    const oe = e.originalEvent;
    const isCtrl = !!(oe?.ctrlKey || oe?.metaKey);

    if (downFeatureId) {
      map.dragging.enable();

      if (isDraggingFeatures.value) {
        const dLat = e.latlng.lat - moveDownLatLng.lat;
        const dLng = e.latlng.lng - moveDownLatLng.lng;

        selectedFeatures.value.forEach((featureId) => {
          const feature = props.features.find((f) => String(f.id) === String(featureId));
          if (feature) editingComposable.updateFeaturePosition(feature, dLat, dLng);
        });

        justFinishedDrag.value = true;
        setTimeout(() => { justFinishedDrag.value = false; }, 100);
      } else {
        if (props.activeEditMode === "RESIZE_SHAPE") {
          suppressNextFeatureClick.value = true;
          setTimeout(() => { suppressNextFeatureClick.value = false; }, 0);
          applySelectionClick(downFeatureId, isCtrl, map);
        }
      }

      isDraggingFeatures.value = false;
      originalPositions.value.clear();
    } else {
      if (!cancelDeselect && selectedFeatures.value.size > 0) {
        selectedFeatures.value.clear();
        syncSelectionOverlays(map);

        if (props.activeEditMode === "RESIZE_SHAPE") {
          emit("resize-selection", {
            featureId: null,
            widthMeters: null,
            heightMeters: null,
            angleDeg: null,
          });
        }
      }
    }

    moveDownClient = null;
    moveDownLatLng = null;
    downFeatureId = null;
    cancelDeselect = false;
  }

  // =======================
  // Keyboard handler
  // =======================
  function handleKeyDown(e, map) {
    const key = e.originalEvent?.key;

    if (key === "Delete" && selectedFeatures.value.size > 0) {
      selectedFeatures.value.forEach((fid) => {
        removeSelectionBBox(fid, map);
        removeSelectionAnchors(fid, map);
      });

      editingComposable.deleteSelectedFeatures(selectedFeatures.value, layersComposable.featureLayerManager, map, emit);

      selectedFeatures.value.clear();
      if (props.activeEditMode === "RESIZE_SHAPE") {
        emit("resize-selection", {
          featureId: null,
          widthMeters: null,
          heightMeters: null,
          angleDeg: null,
        });
      }
      return;
    }

    if (key === "Escape") {
      selectedFeatures.value.clear();
      syncSelectionOverlays(map);

      if (props.activeEditMode === "RESIZE_SHAPE") {
        emit("resize-selection", {
          featureId: null,
          widthMeters: null,
          heightMeters: null,
          angleDeg: null,
        });
      }
    }
  }

  // =======================
  // Cleanup
  // =======================
  function cleanupTempLine() {
    if (tempLine) {
      layersComposable.drawnItems.value.removeLayer(tempLine);
      tempLine = null;
    }
    isDrawingLine.value = false;
    lineStartPoint.value = null;
  }

  function cleanupTempShape() {
    shapeState = null;
    shapeStartPoint = null;
    lastMousePos = null;
    isDrawingShape = false;

    if (tempShape) {
      layersComposable.drawnItems.value.removeLayer(tempShape);
      tempShape = null;
    }
  }

  function cleanupCurrentDrawing() {
    if (tempLine) {
      layersComposable.drawnItems.value.removeLayer(tempLine);
      tempLine = null;
    }
    isDrawingLine.value = false;
    lineStartPoint.value = null;

    freeLinePoints.value = [];
    isDrawingFree.value = false;
    if (tempFreeLine) {
      layersComposable.drawnItems.value.removeLayer(tempFreeLine);
      tempFreeLine = null;
    }

    cleanupTempShape();
  }

  function preventDragDuringShapeDrawing(e) {
    if (!isDrawingShape) return;
    if (e.originalEvent) {
      e.originalEvent.preventDefault();
      e.originalEvent.stopPropagation();
    }
    return false;
  }

  return {
    selectedFeatures,
    isDraggingFeatures,
    currentPolygonPoints,
    isDrawingLine,
    isDrawingFree,
    justFinishedDrag,
    suppressNextFeatureClick,

    handleMouseDown,
    handleMouseMove,
    handleMouseUp,
    handleShapeMouseDown,
    handleShapeMouseMove,
    handleShapeMouseUp,
    handleMapClick,
    handlePolygonClick,
    handleRightClick,
    handleMapDoubleClick,
    handleMoveMouseDown,
    handleMoveMouseMove,
    handleMoveMouseUp,
    handleKeyDown,

    finishPolygon,
    cleanupTempLine,
    cleanupTempShape,
    cleanupCurrentDrawing,
    preventDragDuringShapeDrawing,
    applySelectionClick,
    syncSelectionOverlays,
    clearSelectionBBoxes,
    clearSelectionAnchors,
    upsertSelectionBBox,
    upsertSelectionAnchors,

    setRotationDegForSelection,
  };
}
