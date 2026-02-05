import L from "leaflet";

export function useMapInit(props, emit, layersComposable, eventsComposable, editingComposable, timelineComposable) {
  const boundHandlers = {
    mousedown: null,
    mousemove: null,
    mouseup: null,
    keydown: null,
    click: null,
    dblclick: null,
    contextmenu: null,
    dragstart: null,
  };

  // État d’origine des interactions map pour pouvoir les restaurer
  const uiState = {
    saved: false,
    doubleClickZoom: null,
    boxZoom: null,
    keyboard: null,
    touchZoom: null,
    tap: null,
  };

  function initializeEditControls(map) {
    if (!props.editMode || !map) return;

    setLeafletUiSuppression(map, true);

    updateMapCursor(map);
    makeFeaturesClickable(map);
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
    detachEditEventHandlers(map);

    const container = map.getContainer();
    if (container && !container.hasAttribute("tabindex")) {
      container.setAttribute("tabindex", "0");
    }

    const bind = (name, fn) => {
      boundHandlers[name] = fn;
      map.on(name, fn);
    };

    if (props.activeEditMode === "CREATE_LINE" || props.activeEditMode === "CREATE_FREE_LINE") {
      bind("mousedown", (e) => eventsComposable.handleMouseDown(e, map));
      bind("mousemove", (e) => eventsComposable.handleMouseMove(e, map));
      bind("mouseup", (e) => eventsComposable.handleMouseUp(e, map));
    } else if (props.activeEditMode === "CREATE_SHAPES") {
      bind("mousedown", (e) => eventsComposable.handleShapeMouseDown(e, map));
      bind("mousemove", (e) => eventsComposable.handleShapeMouseMove(e, map));
      bind("mouseup", (e) => eventsComposable.handleShapeMouseUp(e, map));
      bind("dragstart", (e) => eventsComposable.preventDragDuringShapeDrawing(e));
    } else if (props.activeEditMode === "RESIZE_SHAPE") {
      bind("mousedown", (e) => eventsComposable.handleMoveMouseDown(e, map));
      bind("mousemove", (e) => eventsComposable.handleMoveMouseMove(e, map));
      bind("mouseup", (e) => eventsComposable.handleMoveMouseUp(e, map));
    } else if (props.activeEditMode === "CREATE_POLYGON") {
      bind("contextmenu", (e) => eventsComposable.handleRightClick(e, map));
      bind("click", (e) => eventsComposable.handleMapClick(e, map));
      bind("dblclick", (e) => eventsComposable.handleMapDoubleClick(e, map));
    } else if (props.activeEditMode === "CREATE_POINT") {
      bind("click", (e) => eventsComposable.handleMapClick(e, map));
    } else if (props.editMode && !props.activeEditMode) {
      bind("mousedown", (e) => eventsComposable.handleMoveMouseDown(e, map));
      bind("mousemove", (e) => eventsComposable.handleMoveMouseMove(e, map));
      bind("mouseup", (e) => eventsComposable.handleMoveMouseUp(e, map));
    }

    if (props.editMode) {
      bind("keydown", (e) => eventsComposable.handleKeyDown(e, map));

      const focusOnMouseDown = () => container && container.focus();
      container?.addEventListener("mousedown", focusOnMouseDown, { once: true });
    }
  }

  function detachEditEventHandlers(map) {
    if (!map) return;

    const offIf = (name) => {
      if (boundHandlers[name]) {
        map.off(name, boundHandlers[name]);
        boundHandlers[name] = null;
      }
    };

    offIf("mousedown");
    offIf("mousemove");
    offIf("mouseup");
    offIf("keydown");
    offIf("click");
    offIf("dblclick");
    offIf("contextmenu");
    offIf("dragstart");
  }

  // Ne casse pas les clicks Leaflet sur les layers.
  // Désactive seulement des interactions "gênantes" + strip popups/tooltips.
  // IMPORTANT: on garde scrollWheelZoom actif (molette) en mode édition.
  function setLeafletUiSuppression(map, enabled) {
    if (!map) return;

    if (!uiState.saved) {
      uiState.saved = true;
      uiState.doubleClickZoom = map.doubleClickZoom?.enabled?.() ?? null;
      uiState.boxZoom = map.boxZoom?.enabled?.() ?? null;
      uiState.keyboard = map.keyboard?.enabled?.() ?? null;
      uiState.touchZoom = map.touchZoom?.enabled?.() ?? null;
      uiState.tap = map.tap ? true : null;
    }

    const toggle = (handler, shouldEnable) => {
      if (!handler) return;
      if (shouldEnable) handler.enable?.();
      else handler.disable?.();
    };

    if (enabled) {
      toggle(map.doubleClickZoom, false);
      toggle(map.boxZoom, false);
      toggle(map.keyboard, false);

      // On garde la molette active
      map.scrollWheelZoom?.enable?.();

      toggle(map.touchZoom, false);
      if (map.tap) map.tap.disable?.();

      stripLayerUi(layersComposable.featureLayerManager);
      if (layersComposable.drawnItems.value) stripGroupUi(layersComposable.drawnItems.value);
    } else {
      if (uiState.doubleClickZoom != null) toggle(map.doubleClickZoom, uiState.doubleClickZoom);
      if (uiState.boxZoom != null) toggle(map.boxZoom, uiState.boxZoom);
      if (uiState.keyboard != null) toggle(map.keyboard, uiState.keyboard);
      if (uiState.touchZoom != null) toggle(map.touchZoom, uiState.touchZoom);
      if (map.tap && uiState.tap != null) map.tap.enable?.();

      // On laisse scrollWheelZoom tel qu’il était (on l’a forcé enable en édition),
      // si tu veux restaurer strictement l’état initial, ajoute-le à uiState.
    }
  }

  function stripLayerUi(featureLayerManager) {
    if (!featureLayerManager?.layers) return;
    featureLayerManager.layers.forEach((layer) => {
      stripOneLayerUi(layer);
      if (layer && typeof layer.eachLayer === "function") {
        layer.eachLayer((kid) => stripOneLayerUi(kid));
      }
    });
  }

  function stripGroupUi(group) {
    if (!group || typeof group.eachLayer !== "function") return;
    group.eachLayer((layer) => stripOneLayerUi(layer));
  }

  function stripOneLayerUi(layer) {
    if (!layer) return;

    if (typeof layer.unbindTooltip === "function") layer.unbindTooltip();
    if (typeof layer.closeTooltip === "function") layer.closeTooltip();

    if (typeof layer.unbindPopup === "function") layer.unbindPopup();
    if (typeof layer.closePopup === "function") layer.closePopup();
  }

  // À appeler après renderAllFeatures() aussi (sinon les nouveaux layers réintroduisent des popups)
  function makeFeaturesClickable(map) {
    if (!map) return;

    layersComposable.featureLayerManager.layers.forEach((layer, featureId) => {
      stripOneLayerUi(layer);
      layersComposable.featureLayerManager.makeLayerClickable(featureId, layer);
    });

    if (layersComposable.drawnItems.value) {
      layersComposable.drawnItems.value.eachLayer((layer) => {
        const tempId = "temp_" + Math.random();
        stripOneLayerUi(layer);
        layersComposable.featureLayerManager.makeLayerClickable(tempId, layer);
      });
    }
  }

  function handleFeatureClick(featureId, isCtrlPressed, map) {
    const fid = String(featureId);

    if (eventsComposable.justFinishedDrag?.value) {
      eventsComposable.justFinishedDrag.value = false;
      return;
    }

    if (editingComposable.isDeleteMode?.value) {
      editingComposable.deleteFeature(fid, layersComposable.featureLayerManager, map, emit);
      return;
    }

    eventsComposable.applySelectionClick(fid, isCtrlPressed, map);
  }

  function cleanupEditMode(map) {
    setLeafletUiSuppression(map, false);

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
  }

  return {
    initializeEditControls,
    updateMapCursor,
    attachEditEventHandlers,
    detachEditEventHandlers,
    makeFeaturesClickable,
    handleFeatureClick,
    cleanupEditMode,
    setLeafletUiSuppression,
  };
}
