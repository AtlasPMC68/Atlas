import L from 'leaflet';

// Composable for map initialization and cleanup
export function useMapInit(props, emit, layersComposable, eventsComposable, editingComposable, timelineComposable) {
  
  // Initialize edit controls
  function initializeEditControls(map) {
    if (!props.editMode) return;

    // Layer for drawn items (already initialized in layersComposable)
    
    // Update cursor
    updateMapCursor(map);

    // Render existing features as clickable
    makeFeaturesClickable();

    // Setup event handlers based on active edit mode
    attachEditEventHandlers(map);
  }

  // Update map cursor based on edit mode
  function updateMapCursor(map) {
    if (!map) return;

    const mapContainer = map.getContainer();

    if (props.editMode && props.activeEditMode) {
      // In edit mode with active mode, use crosshair cursor
      mapContainer.style.cursor = "crosshair";
    } else if (props.editMode) {
      // In edit mode but no active mode (selection/movement), normal cursor
      mapContainer.style.cursor = "";
    } else {
      // Not in edit mode, normal cursor
      mapContainer.style.cursor = "";
    }
  }

  // Attach edit event handlers based on mode
  function attachEditEventHandlers(map) {
    // Attach mode-specific handlers first
    if (props.activeEditMode === "CREATE_LINE" || props.activeEditMode === "CREATE_FREE_LINE") {
      map.on("mousedown", (e) => eventsComposable.handleMouseDown(e, map));
      map.on("mousemove", (e) => eventsComposable.handleMouseMove(e, map));
      map.on("mouseup", (e) => eventsComposable.handleMouseUp(e, map));
    } else if (props.activeEditMode === "CREATE_SHAPES") {
      map.on("mousedown", (e) => eventsComposable.handleShapeMouseDown(e, map));
      map.on("mousemove", (e) => eventsComposable.handleShapeMouseMove(e, map));
      map.on("mouseup", (e) => eventsComposable.handleShapeMouseUp(e, map));
      map.on("dragstart", (e) => eventsComposable.preventDragDuringShapeDrawing(e));
    } else if (props.activeEditMode === "RESIZE_SHAPE") {
      map.on("mousedown", (e) => eventsComposable.handleResizeMouseDown(e, map));
      map.on("mousemove", (e) => eventsComposable.handleResizeMouseMove(e, map));
      map.on("mouseup", (e) => eventsComposable.handleResizeMouseUp(e, map));
    } else if (props.activeEditMode === "CREATE_POLYGON") {
      map.on("contextmenu", (e) => eventsComposable.handleRightClick(e, map));
      // Map click handler for polygon creation
      map.on("click", (e) => eventsComposable.handleMapClick(e, map));
      map.on("dblclick", (e) => eventsComposable.handleMapDoubleClick(e, map));
    } else if (props.activeEditMode === "CREATE_POINT") {
      // Map click handler for point creation
      map.on("click", (e) => eventsComposable.handleMapClick(e, map));
    } else if (props.editMode && !props.activeEditMode) {
      // Only attach selection/move events when NOT in an active drawing mode
      map.on("mousedown", (e) => eventsComposable.handleMoveMouseDown(e, map));
      map.on("mousemove", (e) => eventsComposable.handleMoveMouseMove(e, map));
      map.on("mouseup", (e) => eventsComposable.handleMoveMouseUp(e, map));
    }

    // Always attach keyboard events in edit mode
    if (props.editMode) {
      map.on("keydown", (e) => eventsComposable.handleKeyDown(e, map));
    }
  }

  // Detach all edit event handlers
  function detachEditEventHandlers(map) {
    map.off("mousedown");
    map.off("mousemove");
    map.off("mouseup");
    map.off("keydown");
    map.off("click");
    map.off("dblclick");
    map.off("contextmenu");
    map.off("dragstart");
  }

  // Make existing features clickable
  function makeFeaturesClickable() {
    // For each existing layer in featureLayerManager, make it clickable
    layersComposable.featureLayerManager.layers.forEach((layer, featureId) => {
      layersComposable.featureLayerManager.makeLayerClickable(featureId, layer);
    });

    // Also make drawn items clickable
    if (layersComposable.drawnItems.value) {
      layersComposable.drawnItems.value.eachLayer((layer) => {
        // For temporary layers, use a temporary ID
        const tempId = "temp_" + Math.random();
        layersComposable.featureLayerManager.makeLayerClickable(tempId, layer);
      });
    }
  }

  // Handle feature click (for selection/deselection/deletion)
  function handleFeatureClick(featureId, isCtrlPressed, map) {
    const fid = String(featureId);

    // If in delete mode, delete the clicked item
    if (editingComposable.isDeleteMode.value) {
      editingComposable.deleteFeature(fid, layersComposable.featureLayerManager, map, emit);
      return;
    }

    // If just finished drag, ignore this click to prevent accidental deselection
    if (eventsComposable.justFinishedDrag.value) {
      eventsComposable.justFinishedDrag.value = false;
      return;
    }

    if (isCtrlPressed) {
      // Multiple selection: toggle selection
      if (eventsComposable.selectedFeatures.value.has(fid)) {
        eventsComposable.selectedFeatures.value.delete(fid);
      } else {
        eventsComposable.selectedFeatures.value.add(fid);
      }
    } else {
      // Simple click: logic based on number of selected items
      if (eventsComposable.selectedFeatures.value.size === 1 && eventsComposable.selectedFeatures.value.has(fid)) {
        // Single item selected and it's this one: deselect
        eventsComposable.selectedFeatures.value.clear();
      } else {
        // Multiple items selected OR click on unselected item:
        // Deselect all and select only this item
        eventsComposable.selectedFeatures.value.clear();
        eventsComposable.selectedFeatures.value.add(fid);
      }
    }

    editingComposable.updateFeatureSelectionVisual(map, layersComposable.featureLayerManager, eventsComposable.selectedFeatures.value);
  }

  // Cleanup edit mode
  function cleanupEditMode(map) {
    if (layersComposable.drawnItems.value) {
      // Clean circles from drawnItems collection
      layersComposable.drawnItems.value.eachLayer((layer) => {
        if (layer instanceof L.CircleMarker) {
          layersComposable.allCircles.value.delete(layer);
        }
      });
      map.removeLayer(layersComposable.drawnItems.value);
      layersComposable.drawnItems.value = null;
    }

    // Clean all events
    detachEditEventHandlers(map);

    // Clean up temporary drawing state
    eventsComposable.cleanupCurrentDrawing();
    eventsComposable.cleanupTempLine();
    eventsComposable.cleanupTempShape();

    // Clean selection and movement
    eventsComposable.selectedFeatures.value.clear();
    eventsComposable.isDraggingFeatures.value = false;
    eventsComposable.justFinishedDrag.value = false;
    editingComposable.updateFeatureSelectionVisual(map, layersComposable.featureLayerManager, eventsComposable.selectedFeatures.value);

    // Update cursor
    updateMapCursor(map);

    // Reload all features when leaving edit mode
    setTimeout(() => {
      if (timelineComposable && timelineComposable.selectedYear) {
        // Fetch features will be handled by parent component
      }
    }, 100);
  }

  return {
    initializeEditControls,
    updateMapCursor,
    attachEditEventHandlers,
    detachEditEventHandlers,
    makeFeaturesClickable,
    handleFeatureClick,
    cleanupEditMode,
  };
}
