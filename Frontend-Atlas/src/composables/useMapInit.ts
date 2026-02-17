import L from "leaflet";

type MapInitProps = {
  editMode?: boolean;
  activeEditMode?: string | null;
};

type EmitFn = (event: string, ...args: unknown[]) => void;

type FeatureLayerManager = {
  layers: Map<string, any>;
  makeLayerClickable: (id: string, layer: any) => void;
};

type LayersComposable = {
  featureLayerManager: FeatureLayerManager;
  drawnItems: { value: L.FeatureGroup | null };
  allCircles: { value: Set<L.CircleMarker> };
};

type EventsComposable = Record<string, any> & {
  selectedFeatures: { value: Set<string> };
  isDraggingFeatures: { value: boolean };
  justFinishedDrag: { value: boolean };
  clearSelectionBBoxes: (map: L.Map) => void;
  clearSelectionAnchors: (map: L.Map) => void;
};

type EditingComposable = Record<string, any> & {
  isDeleteMode?: { value: boolean };
  deleteFeature: (
    featureId: string,
    featureLayerManager: FeatureLayerManager,
    map: L.Map,
    emit: EmitFn,
  ) => void;
};

type HandlerName =
  | "mousedown"
  | "mousemove"
  | "mouseup"
  | "keydown"
  | "click"
  | "dblclick"
  | "contextmenu"
  | "dragstart";

export function useMapInit(
  props: MapInitProps,
  emit: EmitFn,
  layersComposable: LayersComposable,
  eventsComposable: EventsComposable,
  editingComposable: EditingComposable,
) {
  const boundHandlers: Record<HandlerName, L.LeafletEventHandlerFn | null> = {
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
  const uiState: {
    saved: boolean;
    doubleClickZoom: boolean | null;
    boxZoom: boolean | null;
    keyboard: boolean | null;
    touchZoom: boolean | null;
    tap: boolean | null;
  } = {
    saved: false,
    doubleClickZoom: null,
    boxZoom: null,
    keyboard: null,
    touchZoom: null,
    tap: null,
  };

  function initializeEditControls(map: L.Map | null) {
    if (!props.editMode || !map) return;

    setLeafletUiSuppression(map, true);

    updateMapCursor(map);
    makeFeaturesClickable(map);
    attachEditEventHandlers(map);
  }

  function updateMapCursor(map: L.Map | null) {
    if (!map) return;
    const mapContainer = map.getContainer();

    if (
      props.editMode &&
      props.activeEditMode &&
      props.activeEditMode !== "RESIZE_SHAPE"
    ) {
      mapContainer.style.cursor = "crosshair";
    } else {
      mapContainer.style.cursor = "";
    }
  }

  function attachEditEventHandlers(map: L.Map) {
    detachEditEventHandlers(map);

    const container = map.getContainer();
    if (container && !container.hasAttribute("tabindex")) {
      container.setAttribute("tabindex", "0");
    }

    const bind = (name: HandlerName, fn: L.LeafletEventHandlerFn) => {
      boundHandlers[name] = fn;
      map.on(name, fn);
    };

    if (
      props.activeEditMode === "CREATE_LINE" ||
      props.activeEditMode === "CREATE_FREE_LINE"
    ) {
      bind("mousedown", (e) => eventsComposable.handleMouseDown(e, map));
      bind("mousemove", (e) => eventsComposable.handleMouseMove(e, map));
      bind("mouseup", (e) => eventsComposable.handleMouseUp(e, map));
    } else if (props.activeEditMode === "CREATE_SHAPES") {
      bind("mousedown", (e) => eventsComposable.handleShapeMouseDown(e, map));
      bind("mousemove", (e) => eventsComposable.handleShapeMouseMove(e, map));
      bind("mouseup", (e) => eventsComposable.handleShapeMouseUp(e, map));
      bind("dragstart", (e) =>
        eventsComposable.preventDragDuringShapeDrawing(e),
      );
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
      container?.addEventListener("mousedown", focusOnMouseDown, {
        once: true,
      });
    }
  }

  function detachEditEventHandlers(map: L.Map | null) {
    if (!map) return;

    const offIf = (name: HandlerName) => {
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
  function setLeafletUiSuppression(map: L.Map | null, enabled: boolean) {
    if (!map) return;

    if (!uiState.saved) {
      uiState.saved = true;
      uiState.doubleClickZoom = map.doubleClickZoom?.enabled?.() ?? null;
      uiState.boxZoom = map.boxZoom?.enabled?.() ?? null;
      uiState.keyboard = map.keyboard?.enabled?.() ?? null;
      uiState.touchZoom = map.touchZoom?.enabled?.() ?? null;
      uiState.tap = (map as any).tap ? true : null;
    }

    const toggle = (handler: any, shouldEnable: boolean) => {
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
      if ((map as any).tap) (map as any).tap.disable?.();

      stripLayerUi(layersComposable.featureLayerManager);
      if (layersComposable.drawnItems.value)
        stripGroupUi(layersComposable.drawnItems.value);
    } else {
      if (uiState.doubleClickZoom != null)
        toggle(map.doubleClickZoom, uiState.doubleClickZoom);
      if (uiState.boxZoom != null) toggle(map.boxZoom, uiState.boxZoom);
      if (uiState.keyboard != null) toggle(map.keyboard, uiState.keyboard);
      if (uiState.touchZoom != null) toggle(map.touchZoom, uiState.touchZoom);
      if ((map as any).tap && uiState.tap != null) (map as any).tap.enable?.();

      // On laisse scrollWheelZoom tel qu’il était (on l’a forcé enable en édition),
      // si tu veux restaurer strictement l’état initial, ajoute-le à uiState.
    }
  }

  function stripLayerUi(featureLayerManager: FeatureLayerManager | null) {
    if (!featureLayerManager?.layers) return;
    featureLayerManager.layers.forEach((layer) => {
      stripOneLayerUi(layer);
      if (layer && typeof layer.eachLayer === "function") {
        layer.eachLayer((kid: any) => stripOneLayerUi(kid));
      }
    });
  }

  function stripGroupUi(group: L.LayerGroup | null) {
    if (!group || typeof group.eachLayer !== "function") return;
    group.eachLayer((layer) => stripOneLayerUi(layer));
  }

  function stripOneLayerUi(layer: any) {
    if (!layer) return;

    if (typeof layer.unbindTooltip === "function") layer.unbindTooltip();
    if (typeof layer.closeTooltip === "function") layer.closeTooltip();

    if (typeof layer.unbindPopup === "function") layer.unbindPopup();
    if (typeof layer.closePopup === "function") layer.closePopup();
  }

  // À appeler après renderAllFeatures() aussi (sinon les nouveaux layers réintroduisent des popups)
  function makeFeaturesClickable(map: L.Map | null) {
    if (!map) return;

    layersComposable.featureLayerManager.layers.forEach((layer, featureId) => {
      stripOneLayerUi(layer);
      layersComposable.featureLayerManager.makeLayerClickable(featureId, layer);
    });

    if (layersComposable.drawnItems.value) {
      layersComposable.drawnItems.value.eachLayer((layer: any) => {
        const tempId = "temp_" + Math.random();
        stripOneLayerUi(layer);
        layersComposable.featureLayerManager.makeLayerClickable(tempId, layer);
      });
    }
  }

  function handleFeatureClick(
    featureId: string | number,
    isCtrlPressed: boolean,
    map: L.Map,
  ) {
    const fid = String(featureId);

    if (eventsComposable.justFinishedDrag?.value) {
      eventsComposable.justFinishedDrag.value = false;
      return;
    }

    if (editingComposable.isDeleteMode?.value) {
      editingComposable.deleteFeature(
        fid,
        layersComposable.featureLayerManager,
        map,
        emit,
      );
      return;
    }

    eventsComposable.applySelectionClick(fid, isCtrlPressed, map);
  }

  function cleanupEditMode(map: L.Map) {
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
