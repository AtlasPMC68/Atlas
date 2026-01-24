import { ref, computed } from 'vue';
import L from 'leaflet';
import { toArray, getRadiusForZoom, transformNormalizedToWorld } from '../utils/mapUtils.js';
import { MAP_CONFIG } from './useMapConfig.js';

// Composable for managing map layers and feature rendering
export function useMapLayers(props, emit) {
  // Layer collections
  let citiesLayer = null;
  let zonesLayer = null;
  let arrowsLayer = null;
  let drawnItems = null;
  let currentRegionsLayer = null;
  let baseTileLayer = null;
  let labelLayer = null;

  // Circle management
  const allCircles = ref(new Set());

  // Track previous feature IDs for rendering optimization
  const previousFeatureIds = ref(new Set());

  // Feature layer manager
  const featureLayerManager = {
    layers: new Map(),
    clickHandler: null,

    setClickHandler(handler) {
      this.clickHandler = handler;
    },

    addFeatureLayer(featureId, layer, feature) {
      const fid = String(featureId);
      
      if (this.layers.has(fid)) {
        // If it was a circle, remove it from the collection
        const oldLayer = this.layers.get(fid);
        if (oldLayer instanceof L.CircleMarker) {
          allCircles.value.delete(oldLayer);
        }
        // Remove from map if exists
        if (oldLayer._map) {
          oldLayer._map.removeLayer(oldLayer);
        }
      }
      this.layers.set(fid, layer);

      // Store original style on the layer for reliable reset
      if (layer.setStyle && feature) {
        layer.__atlas_originalStyle = {
          color: feature.color || MAP_CONFIG.DEFAULT_STYLES.borderColor,
          weight: 2,
          fillColor: feature.color || MAP_CONFIG.DEFAULT_STYLES.fillColor,
          fillOpacity: feature.opacity ?? MAP_CONFIG.DEFAULT_STYLES.opacity,
        };
      }

      // Add to collection if it's a circle
      if (layer instanceof L.CircleMarker) {
        allCircles.value.add(layer);
      }

      // Make layer clickable if in edit mode
      if (props.editMode) {
        this.makeLayerClickable(fid, layer);
      }

      // Add only if visible
      if (props.featureVisibility.get(fid)) {
        // Will be added to map in render functions
      }
    },

    makeLayerClickable(featureId, layer) {
      const fid = String(featureId);
      
      // Force interactivity
      layer.options.interactive = true;

      // Remove only OUR handlers (not all handlers)
      if (layer.__atlas_onDown) layer.off("mousedown", layer.__atlas_onDown);
      if (layer.__atlas_onClick) layer.off("click", layer.__atlas_onClick);

      // Store our handlers on the layer
      layer.__atlas_onDown = (e) => {
        e.originalEvent?.stopPropagation();
        // Mark that this is a click on a shape
        e.target._isFeatureClick = true;
        e.target._featureId = fid;
      };

      layer.__atlas_onClick = (e) => {
        e.originalEvent?.stopPropagation();
        // Don't preventDefault on click - it can interfere with other interactions
        // Call the handler if available
        if (this.clickHandler) {
          const isCtrlPressed = e.originalEvent?.ctrlKey || e.originalEvent?.metaKey;
          this.clickHandler(fid, isCtrlPressed);
        }
      };

      // Attach our handlers
      layer.on("mousedown", layer.__atlas_onDown);
      layer.on("click", layer.__atlas_onClick);
    },

    toggleFeature(featureId, visible) {
      const fid = String(featureId);
      const layer = this.layers.get(fid);
      if (layer) {
        // This will be called by the map instance
      }
    },

    clearAllFeatures(map) {
      this.layers.forEach((layer) => {
        // Remove circles from collection
        if (layer instanceof L.CircleMarker) {
          allCircles.value.delete(layer);
        }
        // Remove from map if exists
        if (layer._map) {
          map.removeLayer(layer);
        }
      });
      this.layers.clear();
    },
  };

  // Update all existing circles when zoom changes
  function updateCircleSizes(map) {
    const currentZoom = map.getZoom();
    const newRadius = getRadiusForZoom(currentZoom);

    // Update all circles in the collection
    allCircles.value.forEach((circle) => {
      circle.setRadius(newRadius);
    });
  }

  // Render cities (points)
  function renderCities(features, map) {
    const safeFeatures = toArray(features);
    const currentZoom = map.getZoom();
    const radius = getRadiusForZoom(currentZoom);

    safeFeatures.forEach((feature) => {
      if (!feature.geometry || !Array.isArray(feature.geometry.coordinates)) {
        return;
      }

      const [lng, lat] = feature.geometry.coordinates;
      const coord = [lat, lng];

      const props = feature.properties || {};
      const rgb = Array.isArray(props.color_rgb) ? props.color_rgb : null;
      const colorFromRgb = rgb && rgb.length === 3 ? `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})` : null;
      const color = feature.color || colorFromRgb || "#000";

      // Use circleMarker with zoom-adaptive size
      const circle = L.circleMarker(coord, {
        radius: radius, // Size adapts to zoom
        fillColor: feature.color || "#000000",
        color: feature.color || "#333333",
        weight: 1,
        opacity: feature.opacity ?? 0.8,
        fillOpacity: feature.opacity ?? 0.8,
      });

      // Add discrete tooltip on hover if name exists
      if (feature.name) {
        circle.bindTooltip(feature.name, {
          permanent: false,
          direction: "top",
          offset: [0, -5],
        });
      }

      featureLayerManager.addFeatureLayer(feature.id, circle, feature);
      if (props.featureVisibility.get(String(feature.id))) {
        map.addLayer(circle);
      }
    });
  }

  // Render zones (polygons)
  function renderZones(features, map) {
    const safeFeatures = toArray(features);

    safeFeatures.forEach((feature) => {
      if (!feature.geometry || !Array.isArray(feature.geometry.coordinates)) {
        return;
      }

      const props = feature.properties || {};
      const rgb = Array.isArray(props.color_rgb) ? props.color_rgb : null;
      const colorFromRgb = rgb && rgb.length === 3 ? `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})` : null;
      const fillColor = feature.color || colorFromRgb || "#ccc";
      let targetGeometry = feature.geometry;

      // If the geometry is normalized ([0,1] space), project it onto the world
      if (props.is_normalized) {
        const fc = {
          type: "FeatureCollection",
          features: [feature],
        };

        // Pick a random anchor on earth so shapes are visible but not overlapping deterministically
        const anchorLat = -80 + Math.random() * 160; // between -80 and 80
        const anchorLng = -170 + Math.random() * 340; // between -170 and 170

        // Use a large size so the zone is easy to spot (e.g. ~2000km)
        const sizeMeters = 2_000_000;

        const worldFc = transformNormalizedToWorld(fc, anchorLat, anchorLng, sizeMeters);

        if (worldFc && Array.isArray(worldFc.features) && worldFc.features[0]?.geometry) {
          targetGeometry = worldFc.features[0].geometry;
        }
      }

      const layer = L.geoJSON(targetGeometry, {
        style: {
          fillColor,
          fillOpacity: 0.5,
          color: "#333",
          weight: 1,
        },
      });

      const name = props.name || feature.name;
      if (name) {
        layer.bindPopup(name);
      }

      featureLayerManager.addFeatureLayer(feature.id, layer, feature);
      if (props.featureVisibility.get(String(feature.id))) {
        map.addLayer(layer);
      }
    });
  }

  // Render arrows (polylines - NO arrowheads as per user request)
  function renderArrows(features, map) {
    const safeFeatures = toArray(features);

    safeFeatures.forEach((feature) => {
      if (!feature.geometry || !Array.isArray(feature.geometry.coordinates)) {
        return;
      }
      const latLngs = feature.geometry.coordinates.map(([lng, lat]) => [lat, lng]);

      const props = feature.properties || {};
      const rgb = Array.isArray(props.color_rgb) ? props.color_rgb : null;
      const colorFromRgb = rgb && rgb.length === 3 ? `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})` : null;
      const color = feature.color || colorFromRgb || "#000";

      const line = L.polyline(latLngs, {
        color,
        weight: feature.stroke_width ?? 2,
        opacity: feature.opacity ?? 1,
      });

      // NO arrowheads - user explicitly requested to remove them
      // line.arrowheads({
      //   size: "10px",
      //   frequency: "endonly",
      //   fill: true,
      // });

      const name = props.name || feature.name;
      if (name) {
        line.bindPopup(name);
      }

      featureLayerManager.addFeatureLayer(feature.id, line, feature);
      if (props.featureVisibility.get(String(feature.id))) {
        map.addLayer(line);
      }
    });
  }

  // Render shapes (squares, rectangles, circles, triangles, ovals)
  function renderShapes(features, map) {
    const safeFeatures = toArray(features);

    safeFeatures.forEach((feature) => {
      if (!feature.geometry || !Array.isArray(feature.geometry.coordinates) || !feature.geometry.coordinates[0]) {
        return;
      }

      // Convert GeoJSON coordinates to LatLng
      const latLngs = feature.geometry.coordinates[0].map((coord) => [coord[1], coord[0]]);

      const shape = L.polygon(latLngs, {
        color: feature.color || "#000000",
        weight: 2,
        fillColor: feature.color || "#cccccc",
        fillOpacity: feature.opacity ?? 0.5,
        interactive: true, // Make interactive by default
      });

      if (feature.name) {
        shape.bindPopup(feature.name);
      }

      featureLayerManager.addFeatureLayer(feature.id, shape, feature);
      if (props.featureVisibility.get(String(feature.id))) {
        map.addLayer(shape);
      }
    });
  }

  // Render all features with optimization
  function renderAllFeatures(filteredFeatures, map) {
    const currentIds = new Set(filteredFeatures.map((f) => String(f.id)));
    const previousIds = previousFeatureIds.value;

    // Remove old features that are no longer in the current list
    previousIds.forEach((oldId) => {
      if (!currentIds.has(oldId)) {
        const layer = featureLayerManager.layers.get(oldId);
        if (layer) {
          map.removeLayer(layer);
          featureLayerManager.layers.delete(oldId);
        }
      }
    });

    // Render only new features (not already rendered)
    const newFeatures = filteredFeatures.filter((f) => !previousIds.has(String(f.id)));
    const featuresByType = {
      point: newFeatures.filter((f) => f.type === "point"),
      polygon: newFeatures.filter((f) => f.type === "zone"),
      arrow: newFeatures.filter((f) => f.type === "arrow" || f.type === "polyline"),
      square: newFeatures.filter((f) => f.type === "square"),
      rectangle: newFeatures.filter((f) => f.type === "rectangle"),
      circle: newFeatures.filter((f) => f.type === "circle"),
      triangle: newFeatures.filter((f) => f.type === "triangle"),
      oval: newFeatures.filter((f) => f.type === "oval"),
    };

    renderCities(featuresByType.point, map);
    renderZones(featuresByType.polygon, map);
    renderArrows(featuresByType.arrow, map);
    renderShapes(featuresByType.square, map);
    renderShapes(featuresByType.rectangle, map);
    renderShapes(featuresByType.circle, map);
    renderShapes(featuresByType.triangle, map);
    renderShapes(featuresByType.oval, map);

    previousFeatureIds.value = currentIds;

    emit("features-loaded", filteredFeatures);
  }

  // Initialize base layers
  function initializeBaseLayers(map) {
    // Background map
    baseTileLayer = L.tileLayer(
      "https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png",
      {
        attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
        subdomains: "abcd",
        maxZoom: 19,
      }
    ).addTo(map);

    // Initialize drawnItems layer group
    drawnItems = new L.FeatureGroup();
    map.addLayer(drawnItems);

    // Add zoom event for adaptive circle sizes
    map.on("zoomend", () => updateCircleSizes(map));
  }

  // Clear all layers
  function clearAllLayers(map) {
    if (currentRegionsLayer) {
      map.removeLayer(currentRegionsLayer);
      currentRegionsLayer = null;
    }
    featureLayerManager.clearAllFeatures(map);
  }

  return {
    // State
    allCircles,
    featureLayerManager,
    previousFeatureIds,

    // Layer collections (for external access)
    drawnItems,
    currentRegionsLayer,
    baseTileLayer,
    labelLayer,

    // Functions
    renderCities,
    renderZones,
    renderArrows,
    renderShapes,
    renderAllFeatures,
    updateCircleSizes,
    initializeBaseLayers,
    clearAllLayers,
  };
}
