import { ref, computed } from "vue";
import L from "leaflet";

/**
 * Composable for managing multi-selection of map features
 * Supports Ctrl+Click to select/deselect multiple layers
 */
export function useMultiSelect() {
  const selectedLayers = ref<Set<string>>(new Set());
  const layerMap = ref<Map<string, L.Layer>>(new Map());
  const decoratorMap = ref<Map<string, L.Layer>>(new Map()); // Store decorator layers
  const preSelectionStyles = ref<Map<string, any>>(new Map()); // Store styles before selection

  const hasSelection = computed(() => selectedLayers.value.size > 0);
  const selectionCount = computed(() => selectedLayers.value.size);

  /**
   * Register a layer for potential selection
   */
  function registerLayer(featureId: string, layer: L.Layer) {
    layerMap.value.set(featureId, layer);
  }

  /**
   * Unregister a layer
   */
  function unregisterLayer(featureId: string) {
    // Remove decorator if exists
    const decorator = decoratorMap.value.get(featureId);
    if (decorator) {
      const map = (decorator as any)._map;
      if (map && map.hasLayer(decorator)) {
        map.removeLayer(decorator);
      }
      decoratorMap.value.delete(featureId);
    }

    // Clean up saved styles
    preSelectionStyles.value.delete(featureId);

    layerMap.value.delete(featureId);
    selectedLayers.value.delete(featureId);
  }

  /**
   * Handle click on a feature
   * @param featureId - ID of the clicked feature
   * @param isCtrlPressed - Whether Ctrl/Cmd key is pressed
   */
  function handleFeatureClick(featureId: string, isCtrlPressed: boolean) {
    if (!isCtrlPressed) {
      // Single selection - clear others and select this one
      clearSelection();
      selectLayer(featureId);
    } else {
      // Multi-selection - toggle this layer
      if (selectedLayers.value.has(featureId)) {
        deselectLayer(featureId);
      } else {
        selectLayer(featureId);
      }
    }
  }

  /**
   * Select a layer
   */
  function selectLayer(featureId: string) {
    const layer = layerMap.value.get(featureId);
    if (!layer) return;

    selectedLayers.value.add(featureId);
    highlightLayer(layer, true);
  }

  /**
   * Deselect a layer
   */
  function deselectLayer(featureId: string) {
    const layer = layerMap.value.get(featureId);
    if (!layer) return;

    selectedLayers.value.delete(featureId);
    highlightLayer(layer, false);
  }

  /**
   * Clear all selections
   */
  function clearSelection() {
    selectedLayers.value.forEach((featureId) => {
      const layer = layerMap.value.get(featureId);
      if (layer) {
        highlightLayer(layer, false);
      }

      // Clean up decorator
      const decorator = decoratorMap.value.get(featureId);
      if (decorator) {
        const map = (decorator as any)._map;
        if (map && map.hasLayer(decorator)) {
          map.removeLayer(decorator);
        }
        decoratorMap.value.delete(featureId);
      }

      // Clean up saved style
      preSelectionStyles.value.delete(featureId);
    });
    selectedLayers.value.clear();
  }

  /**
   * Apply/remove selection highlight to a layer
   * Creates a double-border effect like Geoman.io
   */
  function highlightLayer(layer: any, selected: boolean) {
    if (!layer.setStyle) return;

    const featureId = getFeatureIdFromLayer(layer);
    if (!featureId) return;

    if (selected) {
      // Save current style BEFORE modifying it
      const currentStyle = {
        color: layer.options?.color,
        weight: layer.options?.weight,
        fillColor: layer.options?.fillColor,
        fillOpacity: layer.options?.fillOpacity,
        opacity: layer.options?.opacity,
        dashArray: layer.options?.dashArray,
      };
      preSelectionStyles.value.set(featureId, currentStyle);

      // Create outer white border decorator
      const decorator = createDecoratorLayer(layer);
      if (decorator) {
        decoratorMap.value.set(featureId, decorator);

        // Add decorator to map (below the original layer)
        const map = (layer as any)._map;
        if (map) {
          decorator.addTo(map);
          if ((decorator as any).bringToBack) {
            (decorator as any).bringToBack();
          }
        }
      }

      // Apply blue selection border on top
      layer.setStyle({
        color: "#3388ff", // Blue border
        weight: 3,
      });

      // Bring selected layer to front
      if (layer.bringToFront) {
        layer.bringToFront();
      }
    } else {
      // Remove decorator
      const decorator = decoratorMap.value.get(featureId);
      if (decorator) {
        const map = (decorator as any)._map;
        if (map && map.hasLayer(decorator)) {
          map.removeLayer(decorator);
        }
        decoratorMap.value.delete(featureId);
      }

      // Restore saved style (from before selection)
      const savedStyle = preSelectionStyles.value.get(featureId);
      if (savedStyle) {
        layer.setStyle(savedStyle);
        preSelectionStyles.value.delete(featureId);
      }
    }
  }

  /**
   * Create a decorator layer for double-border effect
   */
  function createDecoratorLayer(layer: any): L.Layer | null {
    try {
      if (layer instanceof L.Polyline || layer instanceof L.Polygon) {
        const latlngs = layer.getLatLngs();
        const decorator =
          layer instanceof L.Polygon
            ? L.polygon(latlngs as any, {
                color: "#ffffff",
                weight: 7,
                fillOpacity: 0,
                interactive: false,
              })
            : L.polyline(latlngs as any, {
                color: "#ffffff",
                weight: 7,
                interactive: false,
              });
        return decorator;
      } else if (layer instanceof L.Circle) {
        const center = layer.getLatLng();
        const radius = layer.getRadius();
        return L.circle(center, {
          radius,
          color: "#ffffff",
          weight: 7,
          fillOpacity: 0,
          interactive: false,
        });
      } else if (layer instanceof L.CircleMarker) {
        const center = layer.getLatLng();
        const radius = (layer as any).options?.radius || 6;
        return L.circleMarker(center, {
          radius: radius + 2,
          color: "#ffffff",
          weight: 7,
          fillOpacity: 0,
          interactive: false,
        });
      }
    } catch (e) {
      console.warn("Failed to create decorator layer:", e);
    }
    return null;
  }

  /**
   * Get feature ID from a layer
   */
  function getFeatureIdFromLayer(layer: any): string | null {
    for (const [id, l] of layerMap.value.entries()) {
      if (l === layer) return id;
    }
    return null;
  }

  /**
   * Update decorator positions to match their parent layers
   * Called during drag to keep decorators synchronized
   */
  function updateDecorators() {
    decoratorMap.value.forEach((decorator, featureId) => {
      const layer = layerMap.value.get(featureId);
      if (!layer) return;

      try {
        if (
          (layer instanceof L.Polyline || layer instanceof L.Polygon) &&
          (decorator instanceof L.Polyline || decorator instanceof L.Polygon)
        ) {
          const latlngs = (layer as any).getLatLngs();
          (decorator as any).setLatLngs(latlngs);
        } else if (
          (layer instanceof L.Circle || layer instanceof L.CircleMarker) &&
          (decorator instanceof L.Circle || decorator instanceof L.CircleMarker)
        ) {
          const center = (layer as any).getLatLng();
          (decorator as any).setLatLng(center);

          if (layer instanceof L.Circle && decorator instanceof L.Circle) {
            const radius = (layer as any).getRadius();
            (decorator as any).setRadius(radius);
          }
        }
      } catch (e) {
        console.warn("Failed to update decorator:", e);
      }
    });
  }

  /**
   * Get all selected feature IDs
   */
  function getSelectedIds(): string[] {
    return Array.from(selectedLayers.value);
  }

  /**
   * Get all selected layers
   */
  function getSelectedLayers(): L.Layer[] {
    return getSelectedIds()
      .map((id) => layerMap.value.get(id))
      .filter((layer): layer is L.Layer => layer !== undefined);
  }

  /**
   * Check if a layer is selected
   */
  function isSelected(featureId: string): boolean {
    return selectedLayers.value.has(featureId);
  }

  /**
   * Move all selected layers by a delta
   */
  function moveSelectedLayers(deltaLat: number, deltaLng: number) {
    getSelectedLayers().forEach((layer: any) => {
      if (layer instanceof L.Marker || layer instanceof L.CircleMarker) {
        const current = layer.getLatLng();
        layer.setLatLng([current.lat + deltaLat, current.lng + deltaLng]);
      } else if (layer instanceof L.Polyline || layer instanceof L.Polygon) {
        const latlngs = layer.getLatLngs();
        const shifted = shiftLatLngs(latlngs, deltaLat, deltaLng);
        layer.setLatLngs(shifted);
      } else if (layer instanceof L.Circle) {
        const current = layer.getLatLng();
        layer.setLatLng([current.lat + deltaLat, current.lng + deltaLng]);
      }
    });
  }

  /**
   * Recursively shift LatLngs by delta (handles nested arrays)
   */
  function shiftLatLngs(latlngs: any, deltaLat: number, deltaLng: number): any {
    if (Array.isArray(latlngs)) {
      return latlngs.map((item) => {
        if (
          item &&
          typeof item === "object" &&
          "lat" in item &&
          "lng" in item
        ) {
          return L.latLng(item.lat + deltaLat, item.lng + deltaLng);
        } else if (Array.isArray(item)) {
          return shiftLatLngs(item, deltaLat, deltaLng);
        }
        return item;
      });
    }
    return latlngs;
  }

  return {
    // State
    selectedLayers: computed(() => Array.from(selectedLayers.value)),
    hasSelection,
    selectionCount,

    // Methods
    registerLayer,
    unregisterLayer,
    handleFeatureClick,
    selectLayer,
    deselectLayer,
    clearSelection,
    getSelectedIds,
    getSelectedLayers,
    isSelected,
    moveSelectedLayers,
    getFeatureIdFromLayer,
    updateDecorators,
  };
}
