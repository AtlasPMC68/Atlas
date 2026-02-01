import { ref, computed } from 'vue';
import L from 'leaflet';
import { toArray, getRadiusForZoom, transformNormalizedToWorld } from '../utils/mapUtils.js';
import { MAP_CONFIG } from './useMapConfig.js';

export function useMapLayers(props, emit) {
  let citiesLayer = null;
  let zonesLayer = null;
  let arrowsLayer = null;
  const drawnItems = ref(null);
  let currentRegionsLayer = null;
  let baseTileLayer = null;
  let labelLayer = null;

  const allCircles = ref(new Set());

  const previousFeatureIds = ref(new Set());

  const featureLayerManager = {
    layers: new Map(),
    clickHandler: null,

    setClickHandler(handler) {
      this.clickHandler = handler;
    },

    addFeatureLayer(featureId, layer, feature) {
      const fid = String(featureId);
      
      if (this.layers.has(fid)) {
        const oldLayer = this.layers.get(fid);
        if (oldLayer instanceof L.CircleMarker) {
          allCircles.value.delete(oldLayer);
        }
        if (oldLayer._map) {
          oldLayer._map.removeLayer(oldLayer);
        }
      }
      this.layers.set(fid, layer);

      if (layer.setStyle && feature) {
        layer.__atlas_originalStyle = {
          color: feature.color || MAP_CONFIG.DEFAULT_STYLES.borderColor,
          weight: 2,
          fillColor: feature.color || MAP_CONFIG.DEFAULT_STYLES.fillColor,
          fillOpacity: feature.opacity ?? MAP_CONFIG.DEFAULT_STYLES.opacity,
        };
      }

      if (layer instanceof L.CircleMarker) {
        allCircles.value.add(layer);
      }

      if (props.editMode) {
        this.makeLayerClickable(fid, layer);
      }

      if (props.featureVisibility.get(fid)) {
      }
    },

    makeLayerClickable(featureId, layer) {
      const fid = String(featureId);

      layer.options.interactive = true;

      layer.options.bubblingMouseEvents = true;

      if (layer.__atlas_onDown) layer.off("mousedown", layer.__atlas_onDown);
      if (layer.__atlas_onClick) layer.off("click", layer.__atlas_onClick);
      if (layer.__atlas_onPointerDown) layer.off("pointerdown", layer.__atlas_onPointerDown);

      const markDom = (oe) => {
        const t = oe?.target;
        if (!t) return;
        t._atlasFeatureId = fid;
        if (t.parentElement) t.parentElement._atlasFeatureId = fid;
      };

      layer.__atlas_onDown = (e) => {
        const oe = e.originalEvent;
        markDom(oe);

        if (props.activeEditMode) {
          oe?.preventDefault();
          oe?.stopPropagation();
          oe?.stopImmediatePropagation?.();
        }
      };

      layer.__atlas_onPointerDown = (e) => {
        const oe = e.originalEvent;
        markDom(oe);

        if (props.activeEditMode) {
          oe?.preventDefault();
          oe?.stopPropagation();
          oe?.stopImmediatePropagation?.();
        }
      };

      layer.__atlas_onClick = (e) => {
        e.originalEvent?.stopPropagation();

        if (this.clickHandler) {
          const isCtrlPressed = e.originalEvent?.ctrlKey || e.originalEvent?.metaKey;
          this.clickHandler(fid, isCtrlPressed);
        }
      };

      layer.on("mousedown", layer.__atlas_onDown);
      layer.on("pointerdown", layer.__atlas_onPointerDown);
      layer.on("click", layer.__atlas_onClick);
    },

    toggleFeature(featureId, visible) {
      const fid = String(featureId);
      const layer = this.layers.get(fid);
      if (layer) {
      }
    },

    clearAllFeatures(map) {
      this.layers.forEach((layer) => {
        if (layer instanceof L.CircleMarker) {
          allCircles.value.delete(layer);
        }
        if (layer._map) {
          map.removeLayer(layer);
        }
      });
      this.layers.clear();
    },
  };

  function updateCircleSizes(map) {
    const currentZoom = map.getZoom();
    const newRadius = getRadiusForZoom(currentZoom);

    allCircles.value.forEach((circle) => {
      circle.setRadius(newRadius);
    });
  }

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

      const circle = L.circleMarker(coord, {
        radius: radius,
        fillColor: feature.color || "#000000",
        color: feature.color || "#333333",
        weight: 1,
        opacity: feature.opacity ?? 0.8,
        fillOpacity: feature.opacity ?? 0.8,
      });

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

      if (props.is_normalized) {
        const fc = {
          type: "FeatureCollection",
          features: [feature],
        };

        const anchorLat = -80 + Math.random() * 160;
        const anchorLng = -170 + Math.random() * 340;

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

  function renderShapes(features, map) {
    const safeFeatures = toArray(features);

    safeFeatures.forEach((feature) => {
      if (!feature.geometry || !Array.isArray(feature.geometry.coordinates) || !feature.geometry.coordinates[0]) {
        return;
      }

      const latLngs = feature.geometry.coordinates[0].map((coord) => [coord[1], coord[0]]);

      const shape = L.polygon(latLngs, {
        color: feature.color || "#000000",
        weight: 2,
        fillColor: feature.color || "#cccccc",
        fillOpacity: feature.opacity ?? 0.5,
        interactive: true,
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

  function renderAllFeatures(filteredFeatures, map) {
    const currentIds = new Set(filteredFeatures.map((f) => String(f.id)));
    const previousIds = previousFeatureIds.value;

    previousIds.forEach((oldId) => {
      if (!currentIds.has(oldId)) {
        const layer = featureLayerManager.layers.get(oldId);
        if (layer) {
          map.removeLayer(layer);
          featureLayerManager.layers.delete(oldId);
        }
      }
    });

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

  function initializeBaseLayers(map) {
    baseTileLayer = L.tileLayer(
      "https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png",
      {
        attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
        subdomains: "abcd",
        maxZoom: 19,
      }
    ).addTo(map);

    drawnItems.value = new L.FeatureGroup();
    map.addLayer(drawnItems.value);

    map.on("zoomend", () => updateCircleSizes(map));
  }

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
