import { ref } from 'vue';
import L from 'leaflet';
import { getPixelDistance } from '../utils/mapUtils.js';
import { MAP_CONFIG } from './useMapConfig.js';

// Composable for managing map events (mouse, keyboard, etc.)
export function useMapEvents(props, emit, layersComposable, editingComposable) {
  // Drawing state variables
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

  // Selection and movement state
  const selectedFeatures = ref(new Set()); // Set of selected feature IDs
  const isDraggingFeatures = ref(false); // If currently dragging shapes
  let dragStartPoint = null; // Starting point of drag
  const originalPositions = ref(new Map()); // Original positions before dragging
  const justFinishedDrag = ref(false); // Flag to avoid deselection after drag

  // Polygon drawing
  const currentPolygonPoints = ref([]);
  let tempPolygon = null;

  // Resize handles
  let resizeHandles = new Map();
  let isResizing = false;
  let resizeStartPoint = null;
  let resizeHandle = null;
  let originalGeometry = null;
  let originalBounds = null;
  let tempResizeShape = null;

  // ===== MOUSE EVENT HANDLERS =====

  // Line drawing mouse down
  function handleMouseDown(e, map) {
    if (!props.editMode) return;

    if (props.activeEditMode === "CREATE_LINE") {
      isDrawingLine.value = true;
      lineStartPoint.value = e.latlng;

      // Disable map dragging during drawing
      map.dragging.disable();

      // Create temporary line (invisible at first)
      tempLine = L.polyline([lineStartPoint.value, lineStartPoint.value], {
        color: "#000000",
        weight: 2,
        opacity: 0.7,
      });
      layersComposable.drawnItems.addLayer(tempLine);
    } else if (props.activeEditMode === "CREATE_FREE_LINE") {
      isDrawingFree.value = true;
      freeLinePoints.value = [e.latlng];

      // Disable map dragging during drawing
      map.dragging.disable();

      // Create temporary free line
      tempFreeLine = L.polyline([e.latlng], {
        color: "#000000",
        weight: 2,
        opacity: 0.7,
      });
      layersComposable.drawnItems.addLayer(tempFreeLine);
    }
  }

  // Mouse move handler
  function handleMouseMove(e, map) {
    if (isDrawingLine.value && lineStartPoint.value && tempLine) {
      // Update temporary straight line coordinates
      tempLine.setLatLngs([lineStartPoint.value, e.latlng]);
    } else if (isDrawingFree.value && tempFreeLine) {
      // Add current point to free line
      freeLinePoints.value.push(e.latlng);

      // Apply smoothing in real-time (optional, can be commented if too slow)
      const smoothedPoints = editingComposable.smoothFreeLinePoints(freeLinePoints.value);
      tempFreeLine.setLatLngs(smoothedPoints);
    }
  }

  // Mouse up handler
  function handleMouseUp(e, map) {
    // Handle straight line finish
    if (isDrawingLine.value && lineStartPoint.value) {
      isDrawingLine.value = false;

      // Re-enable map dragging
      map.dragging.enable();

      // Calculate distance between start and end points
      const distance = getPixelDistance(map, lineStartPoint.value, e.latlng);

      // If distance is too small, cancel
      if (distance < MAP_CONFIG.DRAWING_TOLERANCE) {
        cleanupTempLine();
        lineStartPoint.value = null;
        return;
      }

      // Remove temporary line
      if (tempLine) {
        layersComposable.drawnItems.removeLayer(tempLine);
        tempLine = null;
      }

      // Create final line
      editingComposable.createLine(lineStartPoint.value, e.latlng, map, layersComposable);
      lineStartPoint.value = null;
    }

    // Handle free line finish
    else if (isDrawingFree.value) {
      isDrawingFree.value = false;

      // Re-enable map dragging
      map.dragging.enable();

      // Finalize free line
      editingComposable.finishFreeLine(freeLinePoints.value, tempFreeLine, map, layersComposable);

      // Clean up
      freeLinePoints.value = [];
      tempFreeLine = null;
    }
  }

  // Shape mouse down
  function handleShapeMouseDown(e, map) {
    // Check if it's a click on an existing shape
    if (e.target && e.target._isFeatureClick) {
      return;
    }

    if (props.activeEditMode !== "CREATE_SHAPES" || !props.selectedShape) {
      return;
    }

    // Mark that we're starting to draw
    isDrawingShape = true;

    // Disable map dragging during drawing
    map.dragging.disable();

    // Prevent dragging completely
    e.originalEvent.preventDefault();
    e.originalEvent.stopPropagation();
    e.originalEvent.stopImmediatePropagation();

    const shapeType = props.selectedShape;

    // Logic according to shape type
    switch (shapeType) {
      case "square":
        // Approach: center + size (like circle, but perfect square)
        shapeState = "drawing";
        shapeStartPoint = e.latlng;
        // We'll create the temporary shape on mouse move
        break;

      case "rectangle":
        // Approach: two opposite corners
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
        layersComposable.drawnItems.addLayer(tempShape);
        break;

      case "circle":
      case "triangle":
        // Approach: center + size
        shapeState = "drawing";
        shapeStartPoint = e.latlng;
        // We'll create the temporary shape on mouse move
        break;

      case "oval":
        // Approach: center + height first, then width
        if (shapeState === null) {
          // First step: define center
          shapeState = "adjusting_height";
          shapeStartPoint = e.latlng;
        }
        break;

      default:
        isDrawingShape = false;
        map.dragging.enable();
        return;
    }
  }

  // Shape mouse move
  function handleShapeMouseMove(e, map) {
    lastMousePos = e.latlng; // Store last position

    if (!props.activeEditMode === "CREATE_SHAPES" || !props.selectedShape) return;

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

  // Shape mouse up
  function handleShapeMouseUp(e, map) {
    if (!shapeStartPoint || !props.selectedShape) {
      return;
    }

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
            layersComposable.drawnItems.removeLayer(tempShape);
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
            layersComposable.drawnItems.removeLayer(tempShape);
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
          // For circle, mouseup finalizes the shape (not like others)
          isDrawingShape = false;
          map.dragging.enable();

          const distance = getPixelDistance(map, shapeStartPoint, e.latlng);
          if (distance < MAP_CONFIG.DRAWING_TOLERANCE) {
            cleanupTempShape();
            return;
          }

          if (tempShape) {
            layersComposable.drawnItems.removeLayer(tempShape);
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
            layersComposable.drawnItems.removeLayer(tempShape);
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
          // First step completed: height defined, move to width
          shapeState = "adjusting_width";
          shapeEndPoint = e.latlng;
        } else if (shapeState === "adjusting_width") {
          // Second step completed: create final oval
          isDrawingShape = false;
          map.dragging.enable();

          if (tempShape) {
            layersComposable.drawnItems.removeLayer(tempShape);
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

  // Map click handler
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
        // Shapes are handled by mouse mousedown/mousemove/mouseup events
        break;
    }
  }

  // Polygon click handler
  function handlePolygonClick(latlng, map) {
    currentPolygonPoints.value.push(latlng);
    updatePolygonLines(map);
  }

  // Update polygon lines
  function updatePolygonLines(map) {
    // Remove existing temporary lines
    if (tempPolygon) {
      layersComposable.drawnItems.removeLayer(tempPolygon);
    }

    if (currentPolygonPoints.value.length < 2) return;

    // Create lines between consecutive points
    const lines = [];

    // Lines between consecutive points
    for (let i = 0; i < currentPolygonPoints.value.length - 1; i++) {
      lines.push(currentPolygonPoints.value[i], currentPolygonPoints.value[i + 1]);
    }

    // Temporary closing line (last point to first)
    if (currentPolygonPoints.value.length >= 3) {
      lines.push(
        currentPolygonPoints.value[currentPolygonPoints.value.length - 1],
        currentPolygonPoints.value[0]
      );
    }

    // Create polyline with all segments
    if (lines.length > 0) {
      tempPolygon = L.polyline(lines, {
        color: "#000000",
        weight: 2,
        opacity: 1.0,
      });
      layersComposable.drawnItems.addLayer(tempPolygon);
    }
  }

  // Finish polygon
  function finishPolygon(map) {
    if (currentPolygonPoints.value.length < 3) return;

    // Close the polygon
    const points = [...currentPolygonPoints.value, currentPolygonPoints.value[0]];

    // Clean up ONLY temporary lines (keep previous polygons)
    if (tempPolygon) {
      layersComposable.drawnItems.removeLayer(tempPolygon);
      tempPolygon = null;
    }

    // Create final polygon
    editingComposable.createPolygon(points, map, layersComposable);

    // RESET to allow new polygon
    currentPolygonPoints.value = [];
  }

  // Right click handler for polygons
  function handleRightClick(e, map) {
    if (!props.editMode || props.activeEditMode !== "CREATE_POLYGON") return;

    // Prevent default context menu
    e.originalEvent.preventDefault();

    if (currentPolygonPoints.value.length >= 3) {
      finishPolygon(map);
    }
  }

  // Double click handler for polygons
  function handleMapDoubleClick(e, map) {
    if (!props.editMode || props.activeEditMode !== "CREATE_POLYGON") return;

    if (currentPolygonPoints.value.length >= 3) {
      finishPolygon(map);
    }
  }

  // Movement mouse down
  function handleMoveMouseDown(e, map) {
    // Reset drag finished flag at start of new action
    justFinishedDrag.value = false;

    // Check if it's a click on an existing shape (via layer events)
    const isFeatureClick = e.originalEvent && e.originalEvent.target && 
                           (e.originalEvent.target._isFeatureClick || 
                            e.originalEvent.target.parentElement?._isFeatureClick);

    if (isFeatureClick) {
      // Clicking on a feature - prepare for potential drag
      if (selectedFeatures.value.size > 0) {
        dragStartPoint = e.latlng;
      }
    } else {
      // Clicking on empty space
      if (selectedFeatures.value.size > 0) {
        // Deselect all
        selectedFeatures.value.clear();
        editingComposable.updateFeatureSelectionVisual(map, layersComposable.featureLayerManager, selectedFeatures.value);
      }
      dragStartPoint = null;
    }
  }

  // Movement mouse move
  function handleMoveMouseMove(e, map) {
    // If not yet dragging but we have a starting point
    if (!isDraggingFeatures.value && dragStartPoint && selectedFeatures.value.size > 0) {
      // Check if moved enough to start drag
      const distance = getPixelDistance(map, dragStartPoint, e.latlng);
      if (distance > MAP_CONFIG.DRAG_THRESHOLD) {
        // Start drag
        isDraggingFeatures.value = true;

        // Disable ALL map interactions
        map.dragging.disable();
        map.doubleClickZoom.disable();
        map.scrollWheelZoom.disable();
        map.keyboard.disable();
        map.touchZoom.disable();
        map.boxZoom.disable();

        // Save original positions
        originalPositions.value.clear();
        selectedFeatures.value.forEach((featureId) => {
          const layer = layersComposable.featureLayerManager.layers.get(String(featureId));
          if (layer) {
            // For polygons, save coordinates
            if (layer instanceof L.Polygon || layer instanceof L.Rectangle) {
              originalPositions.value.set(featureId, layer.getBounds());
            } else if (layer instanceof L.CircleMarker) {
              originalPositions.value.set(featureId, layer.getLatLng());
            } else if (layer instanceof L.Polyline) {
              originalPositions.value.set(featureId, layer.getLatLngs());
            }
          }
        });
      }
    }

    // If dragging
    if (isDraggingFeatures.value && dragStartPoint) {
      // Calculate delta movement
      const deltaLat = e.latlng.lat - dragStartPoint.lat;
      const deltaLng = e.latlng.lng - dragStartPoint.lng;

      // Apply movement to all selected shapes
      selectedFeatures.value.forEach((featureId) => {
        const layer = layersComposable.featureLayerManager.layers.get(String(featureId));
        if (layer && originalPositions.value.has(featureId)) {
          if (layer instanceof L.Polygon || layer instanceof L.Rectangle) {
            const originalBounds = originalPositions.value.get(featureId);
            const newBounds = L.latLngBounds([
              [
                originalBounds.getSouthWest().lat + deltaLat,
                originalBounds.getSouthWest().lng + deltaLng,
              ],
              [
                originalBounds.getNorthEast().lat + deltaLat,
                originalBounds.getNorthEast().lng + deltaLng,
              ],
            ]);
            layer.setBounds(newBounds);
          } else if (layer instanceof L.CircleMarker) {
            const originalPos = originalPositions.value.get(featureId);
            const newPos = L.latLng(
              originalPos.lat + deltaLat,
              originalPos.lng + deltaLng
            );
            layer.setLatLng(newPos);
          } else if (layer instanceof L.Polyline) {
            const originalLatLngs = originalPositions.value.get(featureId);
            const newLatLngs = originalLatLngs.map((latLng) =>
              L.latLng(latLng.lat + deltaLat, latLng.lng + deltaLng)
            );
            layer.setLatLngs(newLatLngs);
          }
        }
      });
    }
  }

  // Movement mouse up
  function handleMoveMouseUp(e, map) {
    if (isDraggingFeatures.value && dragStartPoint) {
      // Re-enable ALL map interactions
      map.dragging.enable();
      map.doubleClickZoom.enable();
      map.scrollWheelZoom.enable();
      map.keyboard.enable();
      map.touchZoom.enable();
      map.boxZoom.enable();

      // Calculate final delta
      const deltaLat = e.latlng.lat - dragStartPoint.lat;
      const deltaLng = e.latlng.lng - dragStartPoint.lng;

      // Save new positions in database
      selectedFeatures.value.forEach((featureId) => {
        const feature = props.features.find((f) => String(f.id) === String(featureId));
        if (feature) {
          editingComposable.updateFeaturePosition(feature, deltaLat, deltaLng);
        }
      });

      // Reset state
      isDraggingFeatures.value = false;
      dragStartPoint = null;
      originalPositions.value.clear();

      // Mark that we just finished a drag to avoid deselection
      justFinishedDrag.value = true;

      // Reset flag after short delay
      setTimeout(() => {
        justFinishedDrag.value = false;
      }, 100);
    } else if (dragStartPoint) {
      // We prepared a drag but didn't move enough, just clean up
      dragStartPoint = null;
    }
  }

  // Keyboard handler
  function handleKeyDown(e, map) {
    if (e.originalEvent.key === "Delete" && selectedFeatures.value.size > 0) {
      editingComposable.deleteSelectedFeatures(selectedFeatures.value, layersComposable.featureLayerManager, map, emit);
    } else if (e.originalEvent.key === "Escape") {
      selectedFeatures.value.clear();
      editingComposable.updateFeatureSelectionVisual(map, layersComposable.featureLayerManager, selectedFeatures.value);
    }
  }

  // ===== CLEANUP FUNCTIONS =====

  function cleanupTempLine() {
    if (tempLine) {
      layersComposable.drawnItems.removeLayer(tempLine);
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
      layersComposable.drawnItems.removeLayer(tempShape);
      tempShape = null;
    }
  }

  function cleanupCurrentDrawing() {
    // Clean up line drawing
    if (tempLine) {
      layersComposable.drawnItems.removeLayer(tempLine);
      tempLine = null;
    }
    
    // Clean up free line drawing
    freeLinePoints.value = [];
    isDrawingFree.value = false;
    if (tempFreeLine) {
      layersComposable.drawnItems.removeLayer(tempFreeLine);
      tempFreeLine = null;
    }

    // Don't clean up polygon here to allow persistence when switching modes
  }

  function preventDragDuringShapeDrawing(e) {
    if (isDrawingShape) {
      if (e.originalEvent) {
        e.originalEvent.preventDefault();
        e.originalEvent.stopPropagation();
      }
      return false;
    }
  }

  // ===== EXPORTS =====

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
    handleMapClick,
    handlePolygonClick,
    handleRightClick,
    handleMapDoubleClick,
    handleMoveMouseDown,
    handleMoveMouseMove,
    handleMoveMouseUp,
    handleKeyDown,

    // Utility functions
    finishPolygon,
    cleanupTempLine,
    cleanupTempShape,
    cleanupCurrentDrawing,
    preventDragDuringShapeDrawing,
  };
}
