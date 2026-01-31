import L from "leaflet";

// Composable for map initialization and cleanup
export function useMapInit(props, emit, layersComposable, eventsComposable, editingComposable, timelineComposable) {
  function initializeEditControls(map) {
    if (!props.editMode) return;

    updateMapCursor(map);
    makeFeaturesClickable();
    attachEditEventHandlers(map);
  }

  function updateMapCursor(map) {
    if (!map) return;
    const mapContainer = map.getContainer();

    if (props.editMode && props.activeEditMode && props.activeEditMode !== "RESIZE_SHAPE") {
      mapContainer.style.cursor = "crosshair";
    } else {
      mapContainer.style.cursor = "";
    }
  }

  function attachEditEventHandlers(map) {
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
      map.on("mousedown", (e) => eventsComposable.handleMoveMouseDown(e, map));
      map.on("mousemove", (e) => eventsComposable.handleMoveMouseMove(e, map));
      map.on("mouseup", (e) => eventsComposable.handleMoveMouseUp(e, map));
    } else if (props.activeEditMode === "CREATE_POLYGON") {
      map.on("contextmenu", (e) => eventsComposable.handleRightClick(e, map));
      map.on("click", (e) => eventsComposable.handleMapClick(e, map));
      map.on("dblclick", (e) => eventsComposable.handleMapDoubleClick(e, map));
    } else if (props.activeEditMode === "CREATE_POINT") {
      map.on("click", (e) => eventsComposable.handleMapClick(e, map));
    } else if (props.editMode && !props.activeEditMode) {
      map.on("mousedown", (e) => eventsComposable.handleMoveMouseDown(e, map));
      map.on("mousemove", (e) => eventsComposable.handleMoveMouseMove(e, map));
      map.on("mouseup", (e) => eventsComposable.handleMoveMouseUp(e, map));
    }

    if (props.editMode) {
      map.on("keydown", (e) => eventsComposable.handleKeyDown(e, map));
    }
  }

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

  function makeFeaturesClickable() {
    layersComposable.featureLayerManager.layers.forEach((layer, featureId) => {
      layersComposable.featureLayerManager.makeLayerClickable(featureId, layer);
    });

    if (layersComposable.drawnItems.value) {
      layersComposable.drawnItems.value.eachLayer((layer) => {
        const tempId = "temp_" + Math.random();
        layersComposable.featureLayerManager.makeLayerClickable(tempId, layer);
      });
    }
  }

  function handleFeatureClick(featureId, isCtrlPressed, map) {
    const fid = String(featureId);

    // NEW: avoid double toggle if mouseup already handled selection
    if (eventsComposable.suppressNextFeatureClick?.value) {
      eventsComposable.suppressNextFeatureClick.value = false;
      return;
    }

    if (editingComposable.isDeleteMode.value) {
      editingComposable.deleteFeature(fid, layersComposable.featureLayerManager, map, emit);
      return;
    }

    if (eventsComposable.justFinishedDrag.value) {
      eventsComposable.justFinishedDrag.value = false;
      return;
    }

    eventsComposable.applySelectionClick(fid, isCtrlPressed, map);
  }

  function cleanupEditMode(map) {
    if (layersComposable.drawnItems.value) {
      layersComposable.drawnItems.value.eachLayer((layer) => {
        if (layer instanceof L.CircleMarker) {
          layersComposable.allCircles.value.delete(layer);
        }
      });
      map.removeLayer(layersComposable.drawnItems.value);
      layersComposable.drawnItems.value = null;
    }

    detachEditEventHandlers(map);

    eventsComposable.cleanupCurrentDrawing();
    eventsComposable.cleanupTempLine();
    eventsComposable.cleanupTempShape();

    eventsComposable.selectedFeatures.value.clear();
    eventsComposable.isDraggingFeatures.value = false;
    eventsComposable.justFinishedDrag.value = false;
    eventsComposable.clearSelectionBBoxes(map);
    eventsComposable.clearSelectionAnchors(map);

    updateMapCursor(map);

    setTimeout(() => {}, 100);
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
