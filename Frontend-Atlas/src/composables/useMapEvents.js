import { ref } from "vue";
import L from "leaflet";
import { getPixelDistance } from "../utils/mapUtils.js";
import { MAP_CONFIG } from "./useMapConfig.js";

// Composable for managing map events (mouse, keyboard, etc.)
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

  // Shape drawing state
  let shapeState = null; // 'drawing' | 'adjusting_height' | 'adjusting_width' | null
  let shapeStartPoint = null; // Starting point (corner of square or center for circle/triangle)
  let shapeEndPoint = null; // End point (opposite corner or point for size adjustment)
  let tempShape = null;
  let lastMousePos = null; // Last known mouse position
  let isDrawingShape = false; // Global indicator to prevent dragging

  // Polygon drawing
  const currentPolygonPoints = ref([]);
  let tempPolygon = null;

  // ==============================
  // Selection and movement state
  // ==============================
  const selectedFeatures = ref(new Set()); // Set of selected feature IDs
  const isDraggingFeatures = ref(false); // If currently dragging shapes
  const originalPositions = ref(new Map()); // Original positions before dragging
  const justFinishedDrag = ref(false); // Flag to avoid deselection after drag

  // Movement internals (for "drag object / click empty = deselect / drag empty = pan")
  let moveDownClient = null; // L.point(clientX, clientY)
  let moveDownLatLng = null; // e.latlng at mousedown
  let downFeatureId = null; // feature under cursor at mousedown (or null)
  let cancelDeselect = false; // set true when user actually drags on empty map

  // =======================
  // Resize state (existing)
  // =======================
  // Resize handles (kept for compatibility with your resize mode composable)
  // Note: This file doesn't implement handles directly; editingComposable does.
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
  function getFeatureIdFromDomTarget(domTarget) {
    let el = domTarget;
    for (let i = 0; i < 6 && el; i += 1, el = el.parentElement) {
      if (el._atlasFeatureId) return String(el._atlasFeatureId);
    }
    return null;
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
      const layer = layersComposable.featureLayerManager.layers.get(String(featureId));
      if (!layer) return;

      // Circle / Marker-like (getLatLng but not getLatLngs)
      if (layer.getLatLng && typeof layer.setLatLng === "function" && !layer.getLatLngs) {
        const ll = layer.getLatLng();
        originalPositions.value.set(featureId, L.latLng(ll.lat, ll.lng));
        return;
      }

      // Polyline / Polygon / Rectangle
      if (layer.getLatLngs && typeof layer.setLatLngs === "function") {
        originalPositions.value.set(featureId, cloneLatLngs(layer.getLatLngs()));
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
    // If you're clicking a feature (layer-level), let selection/move logic handle it.
    // Note: this depends on your layer wiring; if you keep _isFeatureClick somewhere else,
    // it won't break anything because we also gate by activeEditMode below.
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
          {
            color: "#000000",
            weight: 2,
            fillColor: "#cccccc",
            fillOpacity: 0.5,
          }
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
          tempShape = editingComposable.updateTempSquareFromCenter(
            shapeStartPoint,
            e.latlng,
            map,
            layersComposable,
            tempShape
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
            tempShape
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
            tempShape
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
            tempShape
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
            tempShape
          );
        } else if (shapeState === "adjusting_width" && shapeStartPoint && shapeEndPoint) {
          tempShape = editingComposable.updateTempOvalWidth(
            shapeStartPoint,
            shapeEndPoint,
            e.latlng,
            map,
            layersComposable,
            tempShape
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
      lines.push(currentPolygonPoints.value[i], currentPolygonPoints.value[i + 1]);
    }

    if (currentPolygonPoints.value.length >= 3) {
      lines.push(
        currentPolygonPoints.value[currentPolygonPoints.value.length - 1],
        currentPolygonPoints.value[0]
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
    // Move is only valid when editMode ON and no active tool (selection mode)
    if (!props.editMode) return;
    if (props.activeEditMode) return;

    justFinishedDrag.value = false;

    const oe = e.originalEvent;
    moveDownClient = oe ? L.point(oe.clientX, oe.clientY) : null;
    moveDownLatLng = e.latlng;
    cancelDeselect = false;

    downFeatureId = getFeatureIdFromDomTarget(oe?.target);

    if (downFeatureId) {
      // Disable map pan for object drag
      map.dragging.disable();

      // Prepare drag
      isDraggingFeatures.value = false;

      if (selectedFeatures.value.has(downFeatureId)) {
        snapshotSelectedOriginalPositions();
      } else {
        originalPositions.value.clear();
      }
      return;
    }

    // Click on empty map: don't deselect yet (could be a pan).
    // We'll decide on mouseup if it's a real click or a drag-pan.
    isDraggingFeatures.value = false;
    originalPositions.value.clear();
  }

  function handleMoveMouseMove(e, map) {
    if (!props.editMode) return;
    if (props.activeEditMode) return;
    if (!moveDownClient || !moveDownLatLng) return;

    const oe = e.originalEvent;
    const cur = oe ? L.point(oe.clientX, oe.clientY) : null;
    const distPx = cur ? moveDownClient.distanceTo(cur) : 0;

    // Case 1: started on a feature -> move objects
    if (downFeatureId) {
      // Start drag only after threshold
      if (!isDraggingFeatures.value && distPx > MAP_CONFIG.DRAG_THRESHOLD) {
        isDraggingFeatures.value = true;

        const isCtrl = !!(oe?.ctrlKey || oe?.metaKey);

        // If user starts dragging a non-selected feature, select it NOW (not on mousedown)
        if (!selectedFeatures.value.has(downFeatureId)) {
          if (!isCtrl) selectedFeatures.value.clear();
          selectedFeatures.value.add(downFeatureId);

          editingComposable.updateFeatureSelectionVisual(
            map,
            layersComposable.featureLayerManager,
            selectedFeatures.value
          );
        }

        // Ensure we have a snapshot for the current selection
        snapshotSelectedOriginalPositions();
      }

      // If we are dragging, apply delta to layers
      if (isDraggingFeatures.value) {
        const dLat = e.latlng.lat - moveDownLatLng.lat;
        const dLng = e.latlng.lng - moveDownLatLng.lng;

        selectedFeatures.value.forEach((featureId) => {
          const layer = layersComposable.featureLayerManager.layers.get(String(featureId));
          const orig = originalPositions.value.get(featureId);
          if (!layer || !orig) return;

          // Circle / Marker-like (getLatLng but not getLatLngs)
          if (layer.getLatLng && typeof layer.setLatLng === "function" && !layer.getLatLngs) {
            layer.setLatLng(L.latLng(orig.lat + dLat, orig.lng + dLng));
            return;
          }

          // Polyline / Polygon / Rectangle
          if (layer.getLatLngs && typeof layer.setLatLngs === "function") {
            layer.setLatLngs(translateLatLngs(orig, dLat, dLng));
          }
        });
      }

      return;
    }

    // Case 2: started on empty map -> if user drags, it's a pan (cancel deselect)
    if (distPx > MAP_CONFIG.DRAG_THRESHOLD) {
      cancelDeselect = true;
    }
  }

  function handleMoveMouseUp(e, map) {
    if (!props.editMode) return;
    if (props.activeEditMode) return;
    if (!moveDownClient || !moveDownLatLng) return;

    // Started on a feature: finish object drag
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
        setTimeout(() => {
          justFinishedDrag.value = false;
        }, 100);
      }

      isDraggingFeatures.value = false;
      originalPositions.value.clear();
    } else {
      // Started on empty map: if it was a click (not a pan), deselect
      if (!cancelDeselect && selectedFeatures.value.size > 0) {
        selectedFeatures.value.clear();
        editingComposable.updateFeatureSelectionVisual(
          map,
          layersComposable.featureLayerManager,
          selectedFeatures.value
        );
      }
    }

    // Reset movement internals
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
      editingComposable.deleteSelectedFeatures(
        selectedFeatures.value,
        layersComposable.featureLayerManager,
        map,
        emit
      );
      return;
    }

    if (key === "Escape") {
      selectedFeatures.value.clear();
      editingComposable.updateFeatureSelectionVisual(
        map,
        layersComposable.featureLayerManager,
        selectedFeatures.value
      );
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
    // Polygon not cleaned here intentionally
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
      map
    );

    if (success) map.dragging.disable();
  }

  function handleResizeMouseMove(e, map) {
    if (!editingComposable.isResizeMode.value || !editingComposable.resizingShape.value) return;

    editingComposable.updateResizeShape(
      L.latLng(editingComposable.resizingShape.value.feature.properties.center),
      e.latlng,
      map,
      layersComposable
    );
  }

  function handleResizeMouseUp(e, map) {
    if (!editingComposable.isResizeMode.value || !editingComposable.resizingShape.value) return;

    e.originalEvent?.preventDefault();
    e.originalEvent?.stopPropagation();

    editingComposable.finishResizeShape(e.latlng, map, layersComposable);
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
  };
}
