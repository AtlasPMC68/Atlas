import { ref } from "vue";
import L from "leaflet";
import { getPixelDistance } from "../utils/mapUtils.js";
import { MAP_CONFIG } from "./useMapConfig.js";

export function useMapEvents(props, emit, layersComposable, editingComposable) {
  // =======================
  // Drawing state variables
  // =======================
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

  // ==============================
  // Selection and movement state
  // ==============================
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
  // Resize state (existing)
  // =======================
  let resizeHandles = new Map();
  let isResizing = false;
  let resizeStartPoint = null;
  let resizeHandle = null;
  let originalGeometry = null;
  let originalBounds = null;
  let tempResizeShape = null;

  // =======================
  // Helpers
  // =======================
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
      map._selectionAnchors = new Map(); // featureId -> { group: LayerGroup, markers: L.CircleMarker[] }
    }
    return map._selectionAnchorGroup;
  }

  function getBoundsAnchorLatLngs(bounds) {
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
  }

  function createAnchorMarker(latlng, kind, map) {
    return L.circleMarker(latlng, {
      radius: kind === "corner" ? 6 : 5,
      weight: 2,
      color: "#111",
      fillColor: "#fff",
      fillOpacity: 1.0,

      pane: ensureSelectionAnchorsPane(map),
      interactive: true,
      bubblingMouseEvents: false,
    });
  }

  function upsertSelectionAnchors(featureId, map, featureLayerManager) {
    if (!map) return;
    ensureSelectionAnchorGroup(map);

    const id = String(featureId);
    const layer = featureLayerManager.layers.get(id);

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

      // sinon on recrée
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

    const pts = getBoundsAnchorLatLngs(bounds);

    const existing = map._selectionAnchors.get(id);
    if (existing) {
      const arr = existing.markers;
      if (arr.length >= 8) {
        arr[0].setLatLng(pts.corners.nw);
        arr[1].setLatLng(pts.corners.ne);
        arr[2].setLatLng(pts.corners.se);
        arr[3].setLatLng(pts.corners.sw);

        arr[4].setLatLng(pts.mids.n);
        arr[5].setLatLng(pts.mids.e);
        arr[6].setLatLng(pts.mids.s);
        arr[7].setLatLng(pts.mids.w);
      }
      existing.group.bringToFront?.();
      return;
    }

    const group = L.layerGroup();

    const markerSpecs = [
      { ll: pts.corners.nw, kind: "corner", key: "nw" },
      { ll: pts.corners.ne, kind: "corner", key: "ne" },
      { ll: pts.corners.se, kind: "corner", key: "se" },
      { ll: pts.corners.sw, kind: "corner", key: "sw" },
      { ll: pts.mids.n, kind: "mid", key: "n" },
      { ll: pts.mids.e, kind: "mid", key: "e" },
      { ll: pts.mids.s, kind: "mid", key: "s" },
      { ll: pts.mids.w, kind: "mid", key: "w" },
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

  function getLayerAllLatLngs(layer) {
    if (layer.getLatLngs) return layer.getLatLngs();

    if (layer.getLatLng) return layer.getLatLng();

    return null;
  }

  function mapLatLngsToPoints(map, latlngs) {
    if (Array.isArray(latlngs)) return latlngs.map((x) => mapLatLngsToPoints(map, x));
    return map.latLngToLayerPoint(latlngs);
  }

  function mapPointsToLatLngs(map, pts) {
    if (Array.isArray(pts)) return pts.map((x) => mapPointsToLatLngs(map, x));
    return map.layerPointToLatLng(pts);
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

  function startAnchorDrag(fid, handle, ev, map) {
    const layer = layersComposable.featureLayerManager.layers.get(String(fid));
    if (!layer) return;

    const isCircle = typeof layer.getRadius === "function" && typeof layer.setRadius === "function";
    const centerLatLng = isCircle
      ? layer.getLatLng()
      : (layer.getBounds ? layer.getBounds().getCenter() : null);

    if (isCircle && !centerLatLng) return;

    const latlngs = !isCircle ? getLayerAllLatLngs(layer) : null;
    if (!isCircle && !latlngs) return;

    map.dragging.disable();

    const startMousePt = map.latLngToLayerPoint(ev.latlng);

    if (isCircle) {
      anchorDrag = {
        fid: String(fid),
        handle,
        isCircle: true,
        centerLatLng,
        startMousePt,
      };
      return;
    }

    const pts = mapLatLngsToPoints(map, latlngs);
    const flat = flattenPoints(pts, []);
    const b = boundsFromPoints(flat);

    const movingPtStart = handleToAnchorPoint(b, handle);
    const fixedH = oppositeHandle(handle);
    const fixedPt = fixedH ? handleToAnchorPoint(b, fixedH) : L.point((b.minX+b.maxX)/2, (b.minY+b.maxY)/2);

    anchorDrag = {
      fid: String(fid),
      handle,
      isCircle: false,
      startMousePt,
      fixedPt,
      startBounds: b,
      startLatLngs: latlngs,
      startPts: pts,
      movingPtStart,
    };
  }

  function startLineEndpointDrag(fid, index, ev, map) {
    const id = String(fid);
    const layer = layersComposable.featureLayerManager.layers.get(id);
    if (!layer || !map) return;

    const isLine = layer instanceof L.Polyline && !(layer instanceof L.Polygon);
    if (!isLine || typeof layer.getLatLngs !== "function" || typeof layer.setLatLngs !== "function") return;

    const latlngs = layer.getLatLngs();
    if (!Array.isArray(latlngs) || latlngs.length < 2) return;

    const idx = index === 0 ? 0 : latlngs.length - 1;

    map.dragging.disable();

    anchorDrag = {
      kind: "lineEndpoint",
      fid: id,
      index: idx,
    };
  }

  function updateAnchorDrag(ev, map) {
    if (!anchorDrag) return;

    const fid = anchorDrag.fid;
    const layer = layersComposable.featureLayerManager.layers.get(String(fid));
    if (!layer) return;

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

    if (anchorDrag.isCircle) {
      const c = anchorDrag.centerLatLng;
      const p = ev.latlng;

      const dx = map.distance([c.lat, c.lng], [c.lat, p.lng]);
      const dy = map.distance([c.lat, c.lng], [p.lat, c.lng]);

      let r;
      if (anchorDrag.handle === "e" || anchorDrag.handle === "w") r = dx;
      else if (anchorDrag.handle === "n" || anchorDrag.handle === "s") r = dy;
      else r = Math.max(dx, dy);

      r = Math.max(1, r);

      layer.setLatLng(c);
      layer.setRadius(r);

      upsertSelectionBBox(fid, map, layersComposable.featureLayerManager);
      upsertSelectionAnchors(fid, map, layersComposable.featureLayerManager);
      return;
    }

    const curMousePt = map.latLngToLayerPoint(ev.latlng);

    const fixed = anchorDrag.fixedPt;
    const startMove = anchorDrag.movingPtStart;

    const denomX = (startMove.x - fixed.x);
    const denomY = (startMove.y - fixed.y);

    let sx = denomX !== 0 ? (curMousePt.x - fixed.x) / denomX : 1;
    let sy = denomY !== 0 ? (curMousePt.y - fixed.y) / denomY : 1;

    if (anchorDrag.handle === "n" || anchorDrag.handle === "s") sx = 1;
    if (anchorDrag.handle === "e" || anchorDrag.handle === "w") sy = 1;

    const MIN_SCALE = 0.05;
    sx = Math.max(MIN_SCALE, sx);
    sy = Math.max(MIN_SCALE, sy);

    function scalePoints(pts) {
      if (Array.isArray(pts)) return pts.map(scalePoints);
      const x = fixed.x + (pts.x - fixed.x) * sx;
      const y = fixed.y + (pts.y - fixed.y) * sy;
      return L.point(x, y);
    }

    const newPts = scalePoints(anchorDrag.startPts);
    const newLatLngs = mapPointsToLatLngs(map, newPts);

    if (layer.setLatLngs) layer.setLatLngs(newLatLngs);

    upsertSelectionBBox(fid, map, layersComposable.featureLayerManager);
    upsertSelectionAnchors(fid, map, layersComposable.featureLayerManager);
  }

  function geometryFromLayer(layer) {
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

      if (coords.length && (coords[0][0] !== coords[coords.length-1][0] || coords[0][1] !== coords[coords.length-1][1])) {
        coords.push(coords[0]);
      }
      return { type: "Polygon", coordinates: [coords] };
    }

    return null;
  }

  async function finishAnchorDrag(map) {
    if (!anchorDrag) return;

    const fid = anchorDrag.fid;
    const layer = layersComposable.featureLayerManager.layers.get(String(fid));

    map.dragging.enable();

    if (!layer) {
      anchorDrag = null;
      map.dragging.enable();
      return;
    }

    const feature = getFeatureById(fid) || layer.feature || null;
    if (feature && isResizableFeature(feature) && props.activeEditMode === "RESIZE_SHAPE") {
      let w = null, h = null;

      if (typeof layer.getRadius === "function") {
        const d = 2 * layer.getRadius();
        w = d; h = d;
      } else if (layer.getBounds && map) {
        const b = layer.getBounds();
        const c = b.getCenter();
        w = map.distance([c.lat, b.getWest()], [c.lat, b.getEast()]);
        h = map.distance([b.getSouth(), c.lng], [b.getNorth(), c.lng]);
      }

      await editingComposable.applyResizeFromDims(fid, w, h, map, layersComposable.featureLayerManager, emit);

      upsertSelectionBBox(fid, map, layersComposable.featureLayerManager);
      upsertSelectionAnchors(fid, map, layersComposable.featureLayerManager);

      anchorDrag = null;
      return;
    }

    const geom = geometryFromLayer(layer);
    if (geom) {
      try {
        const response = await fetch(`http://localhost:8000/maps/features/${fid}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ geometry: geom }),
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

  function upsertSelectionBBox(featureId, map, featureLayerManager) {
    if (!map) return;
    ensureSelectionBBoxGroup(map);

    const id = String(featureId);
    const layer = featureLayerManager.layers.get(id);
    if (!layer || typeof layer.getBounds !== "function") return;

    const bounds = layer.getBounds();
    if (!bounds || !bounds.isValid?.()) return;

    const existing = map._selectionBBoxes.get(id);

    if (existing) {
      existing.setBounds(bounds);
      existing.bringToFront?.();
      return;
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

  function syncSelectionOverlays(map) {
    clearSelectionBBoxes(map);
    clearSelectionAnchors(map);

    selectedFeatures.value.forEach((fid) => {
      upsertSelectionBBox(fid, map, layersComposable.featureLayerManager);
      upsertSelectionAnchors(fid, map, layersComposable.featureLayerManager);
    });
  }

  function getFeatureIdFromDomTarget(domTarget) {
    let el = domTarget;
    for (let i = 0; i < 6 && el; i += 1, el = el.parentElement) {
      if (el._atlasFeatureId) return String(el._atlasFeatureId);
    }
    return null;
  }

  function getFeatureById(fid) {
    const id = String(fid);
    return props.features.find((f) => String(f.id) === id) || null;
  }

  function isResizableFeature(feature) {
    return (
      !!feature?.properties?.resizable &&
      !!feature?.properties?.shapeType &&
      !!feature?.properties?.center
    );
  }

  function cloneLatLngs(latlngs) {
    if (Array.isArray(latlngs)) return latlngs.map(cloneLatLngs);
    return L.latLng(latlngs.lat, latlngs.lng);
  }

  function translateLatLngs(latlngs, dLat, dLng) {
    if (Array.isArray(latlngs))
      return latlngs.map((x) => translateLatLngs(x, dLat, dLng));
    return L.latLng(latlngs.lat + dLat, latlngs.lng + dLng);
  }

  function snapshotSelectedOriginalPositions() {
    originalPositions.value.clear();

    selectedFeatures.value.forEach((featureId) => {
      const layer = layersComposable.featureLayerManager.layers.get(
        String(featureId),
      );
      if (!layer) return;

      // Circle / Marker-like (getLatLng but not getLatLngs)
      if (
        layer.getLatLng &&
        typeof layer.setLatLng === "function" &&
        !layer.getLatLngs
      ) {
        const ll = layer.getLatLng();
        originalPositions.value.set(featureId, L.latLng(ll.lat, ll.lng));
        return;
      }

      // Polyline / Polygon / Rectangle
      if (layer.getLatLngs && typeof layer.setLatLngs === "function") {
        originalPositions.value.set(
          featureId,
          cloneLatLngs(layer.getLatLngs()),
        );
      }
    });
  }

  function getDimsMetersFromLayerId(fid, map) {
    const id = String(fid);
    const layer = layersComposable.featureLayerManager.layers.get(id);
    if (!layer || !map) return { widthMeters: null, heightMeters: null };

    if (typeof layer.getBounds === "function") {
      const b = layer.getBounds();
      if (!b || typeof b.getWest !== "function")
        return { widthMeters: null, heightMeters: null };

      const c = b.getCenter();

      const widthMeters = map.distance(
        [c.lat, b.getWest()],
        [c.lat, b.getEast()],
      );
      const heightMeters = map.distance(
        [b.getSouth(), c.lng],
        [b.getNorth(), c.lng],
      );

      return {
        widthMeters:
          Number.isFinite(widthMeters) && widthMeters > 0 ? widthMeters : null,
        heightMeters:
          Number.isFinite(heightMeters) && heightMeters > 0
            ? heightMeters
            : null,
      };
    }

    return { widthMeters: null, heightMeters: null };
  }

  function applySelectionClick(fid, isCtrl, map) {
    const id = String(fid);

    // Multi-selection: toggle
    if (isCtrl) {
      if (selectedFeatures.value.has(id)) selectedFeatures.value.delete(id);
      else selectedFeatures.value.add(id);
    } else {
      // Simple click: select single (or deselect if already single-selected)
      if (selectedFeatures.value.size === 1 && selectedFeatures.value.has(id)) {
        selectedFeatures.value.clear();
      } else {
        selectedFeatures.value.clear();
        selectedFeatures.value.add(id);
      }
    }

    syncSelectionOverlays(map);

    // In RESIZE_SHAPE, also update the right panel with dims for the last clicked object
    if (props.activeEditMode === "RESIZE_SHAPE") {
      if (selectedFeatures.value.has(id)) {
        const dims = getDimsMetersFromLayerId(id, map);
        emit("resize-selection", { featureId: id, ...dims });
      } else {
        emit("resize-selection", {
          featureId: null,
          widthMeters: null,
          heightMeters: null,
        });
      }
    }
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

      const smoothedPoints = editingComposable.smoothFreeLinePoints(
        freeLinePoints.value,
      );
      tempFreeLine.setLatLngs(smoothedPoints);
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

      editingComposable.createLine(
        lineStartPoint.value,
        e.latlng,
        map,
        layersComposable,
      );
      lineStartPoint.value = null;
      return;
    }

    if (isDrawingFree.value) {
      isDrawingFree.value = false;
      map.dragging.enable();

      editingComposable.finishFreeLine(
        freeLinePoints.value,
        tempFreeLine,
        map,
        layersComposable,
      );

      freeLinePoints.value = [];
      tempFreeLine = null;
    }
  }

  // =======================
  // Shape drawing handlers
  // =======================
  function handleShapeMouseDown(e, map) {
    if (e.target && e.target._isFeatureClick) return;

    if (props.activeEditMode !== "CREATE_SHAPES" || !props.selectedShape)
      return;

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
          {
            color: "#000000",
            weight: 2,
            fillColor: "#cccccc",
            fillOpacity: 0.5,
          },
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

    if (props.activeEditMode !== "CREATE_SHAPES" || !props.selectedShape)
      return;

    const shapeType = props.selectedShape;

    switch (shapeType) {
      case "square":
        if (shapeState === "drawing" && shapeStartPoint) {
          tempShape = editingComposable.updateTempSquareFromCenter(
            shapeStartPoint,
            e.latlng,
            map,
            layersComposable,
            tempShape,
          );
        }
        break;

      case "rectangle":
        if (shapeState === "drawing" && shapeStartPoint) {
          tempShape = editingComposable.updateTempRectangleFromCorners(
            shapeStartPoint,
            e.latlng,
            map,
            layersComposable,
            tempShape,
          );
        }
        break;

      case "circle":
        if (shapeState === "drawing" && shapeStartPoint) {
          tempShape = editingComposable.updateTempCircleFromCenter(
            shapeStartPoint,
            e.latlng,
            map,
            layersComposable,
            tempShape,
          );
        }
        break;

      case "triangle":
        if (shapeState === "drawing" && shapeStartPoint) {
          tempShape = editingComposable.updateTempTriangleFromCenter(
            shapeStartPoint,
            e.latlng,
            map,
            layersComposable,
            tempShape,
          );
        }
        break;

      case "oval":
        if (shapeState === "adjusting_height" && shapeStartPoint) {
          tempShape = editingComposable.updateTempOvalHeight(
            shapeStartPoint,
            e.latlng,
            map,
            layersComposable,
            tempShape,
          );
        } else if (
          shapeState === "adjusting_width" &&
          shapeStartPoint &&
          shapeEndPoint
        ) {
          tempShape = editingComposable.updateTempOvalWidth(
            shapeStartPoint,
            shapeEndPoint,
            e.latlng,
            map,
            layersComposable,
            tempShape,
          );
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
          editingComposable.createSquare(
            shapeStartPoint,
            e.latlng,
            map,
            layersComposable,
          );

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
          editingComposable.createRectangle(
            shapeStartPoint,
            e.latlng,
            map,
            layersComposable,
          );

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
          editingComposable.createCircle(
            shapeStartPoint,
            e.latlng,
            map,
            layersComposable,
          );

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
          editingComposable.createTriangle(
            shapeStartPoint,
            e.latlng,
            map,
            layersComposable,
          );

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
          editingComposable.createOval(
            shapeStartPoint,
            shapeEndPoint,
            e.latlng,
            map,
            layersComposable,
          );

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
      case "CREATE_SHAPES":
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
      lines.push(
        currentPolygonPoints.value[i],
        currentPolygonPoints.value[i + 1],
      );
    }

    if (currentPolygonPoints.value.length >= 3) {
      lines.push(
        currentPolygonPoints.value[currentPolygonPoints.value.length - 1],
        currentPolygonPoints.value[0],
      );
    }

    if (lines.length > 0) {
      tempPolygon = L.polyline(lines, {
        color: "#000000",
        weight: 2,
        opacity: 1.0,
      });
      layersComposable.drawnItems.value.addLayer(tempPolygon);
    }
  }

  function finishPolygon(map) {
    if (currentPolygonPoints.value.length < 3) return;

    const points = [
      ...currentPolygonPoints.value,
      currentPolygonPoints.value[0],
    ];

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

    if (currentPolygonPoints.value.length >= 3) {
      finishPolygon(map);
    }
  }

  function handleMapDoubleClick(e, map) {
    if (!props.editMode || props.activeEditMode !== "CREATE_POLYGON") return;

    if (currentPolygonPoints.value.length >= 3) {
      finishPolygon(map);
    }
  }

  // =======================
  // Movement handlers (fixed)
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

      if (selectedFeatures.value.has(downFeatureId)) {
        snapshotSelectedOriginalPositions();
      } else {
        originalPositions.value.clear();
      }
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

        if (!selectedFeatures.value.has(downFeatureId)) {
          if (!isCtrl) selectedFeatures.value.clear();
          selectedFeatures.value.add(downFeatureId);

          syncSelectionOverlays(map);
        }

        snapshotSelectedOriginalPositions();
      }

      if (isDraggingFeatures.value) {
        const dLat = e.latlng.lat - moveDownLatLng.lat;
        const dLng = e.latlng.lng - moveDownLatLng.lng;

        selectedFeatures.value.forEach((featureId) => {
          const layer = layersComposable.featureLayerManager.layers.get(
            String(featureId),
          );
          const orig = originalPositions.value.get(featureId);
          if (!layer || !orig) return;

          if (
            layer.getLatLng &&
            typeof layer.setLatLng === "function" &&
            !layer.getLatLngs
          ) {
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

    if (distPx > MAP_CONFIG.DRAG_THRESHOLD) {
      cancelDeselect = true;
    }
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
          const feature = props.features.find(
            (f) => String(f.id) === String(featureId),
          );
          if (feature)
            editingComposable.updateFeaturePosition(feature, dLat, dLng);
        });

        justFinishedDrag.value = true;
        setTimeout(() => {
          justFinishedDrag.value = false;
        }, 100);
      } else {
        // NEW: In RESIZE_SHAPE, clicking a feature may not fire Leaflet "click".
        // So we handle selection here and suppress the next feature-click handler.
        if (props.activeEditMode === "RESIZE_SHAPE") {
          suppressNextFeatureClick.value = true;
          setTimeout(() => {
            suppressNextFeatureClick.value = false;
          }, 0);

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

      editingComposable.deleteSelectedFeatures(
        selectedFeatures.value,
        layersComposable.featureLayerManager,
        map,
        emit,
      );

      selectedFeatures.value.clear();
      if (props.activeEditMode === "RESIZE_SHAPE") {
        emit("resize-selection", {
          featureId: null,
          widthMeters: null,
          heightMeters: null,
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
        });
      }
    }
  }

  // =======================
  // Cleanup functions
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

  // =======================
  // Resize handlers (existing)
  // =======================
  function handleResizeMouseDown(e, map) {
    if (!props.editMode || props.activeEditMode !== "RESIZE_SHAPE") return;

    e.originalEvent?.preventDefault();
    e.originalEvent?.stopPropagation();

    const point = e.latlng;
    let clickedFeature = null;
    let clickedFeatureId = null;

    layersComposable.featureLayerManager.layers.forEach((layer, featureId) => {
      if (layer.getBounds && layer.getBounds().contains(point)) {
        if (layer.feature?.properties?.resizable) {
          clickedFeature = layer.feature;
          clickedFeatureId = featureId;
        }
      }
    });

    if (!clickedFeature) return;

    const success = editingComposable.startResizeShape(
      clickedFeatureId,
      clickedFeature,
      layersComposable.featureLayerManager,
      map,
    );

    if (success) map.dragging.disable();
  }

  function handleResizeMouseMove(e, map) {
    if (
      !editingComposable.isResizeMode.value ||
      !editingComposable.resizingShape.value
    )
      return;

    editingComposable.updateResizeShape(
      L.latLng(editingComposable.resizingShape.value.feature.properties.center),
      e.latlng,
      map,
      layersComposable,
    );

    const rs = editingComposable.resizingShape.value;
    const rid = rs?.featureId ?? rs?.id ?? rs?.feature?.id;

    if (rid && selectedFeatures.value.has(String(rid))) {
      upsertSelectionBBox(rid, map, layersComposable.featureLayerManager);
      upsertSelectionAnchors(rid, map, layersComposable.featureLayerManager);
    }
  }

  function handleResizeMouseUp(e, map) {
    if (
      !editingComposable.isResizeMode.value ||
      !editingComposable.resizingShape.value
    )
      return;

    e.originalEvent?.preventDefault();
    e.originalEvent?.stopPropagation();

    editingComposable.finishResizeShape(e.latlng, map, layersComposable);
    const rs = editingComposable.resizingShape.value;
    const rid = rs?.featureId ?? rs?.id ?? rs?.feature?.id;

    if (rid && selectedFeatures.value.has(String(rid))) {
      upsertSelectionBBox(rid, map, layersComposable.featureLayerManager);
      upsertSelectionAnchors(rid, map, layersComposable.featureLayerManager);
    }
    map.dragging.enable();
  }

  // =======================
  // Exports
  // =======================
  return {
    // State
    selectedFeatures,
    isDraggingFeatures,
    currentPolygonPoints,
    isDrawingLine,
    isDrawingFree,
    justFinishedDrag,
    suppressNextFeatureClick,

    // Event handlers
    handleMouseDown,
    handleMouseMove,
    handleMouseUp,
    handleShapeMouseDown,
    handleShapeMouseMove,
    handleShapeMouseUp,
    handleResizeMouseDown,
    handleResizeMouseMove,
    handleResizeMouseUp,
    handleMapClick,
    handlePolygonClick,
    handleRightClick,
    handleMapDoubleClick,
    handleMoveMouseDown,
    handleMoveMouseMove,
    handleMoveMouseUp,
    handleKeyDown,

    // Utility
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
  };
}
