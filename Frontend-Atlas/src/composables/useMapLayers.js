import { ref } from "vue";
import L from "leaflet";
import {
  toArray,
  getRadiusForZoom,
  transformNormalizedToWorld,
} from "../utils/mapUtils.js";
import { MAP_CONFIG } from "./useMapConfig.js";
import { getMapElementType } from "../utils/featureTypes.js";

export function useMapLayers(props, emit, editingComposable) {
  const drawnItems = ref(null);

  const allCircles = ref(new Set());
  const previousFeatureIds = ref(new Set());

  const featureLayerManager = {
    layers: new Map(),
    clickHandler: null,
    map: null,

    setMap(map) {
      this.map = map;
    },

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
        if (this.map && this.map.hasLayer(oldLayer)) {
          this.map.removeLayer(oldLayer);
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

      const visible = props.featureVisibility?.get(fid);
      const shouldShow = visible === undefined ? true : Boolean(visible);

      if (shouldShow && this.map && !this.map.hasLayer(layer)) {
        this.map.addLayer(layer);
      }
      if (!shouldShow && this.map && this.map.hasLayer(layer)) {
        this.map.removeLayer(layer);
      }
    },

    makeLayerClickable(featureId, layer) {
      const fid = String(featureId);

      layer.options.interactive = true;
      layer.options.bubblingMouseEvents = true;

      if (layer.__atlas_onDown) layer.off("mousedown", layer.__atlas_onDown);
      if (layer.__atlas_onClick) layer.off("click", layer.__atlas_onClick);
      if (layer.__atlas_onPointerDown)
        layer.off("pointerdown", layer.__atlas_onPointerDown);

      const markDom = (oe) => {
        const t = oe?.target;
        if (!t) return;
        t._atlasFeatureId = fid;
        if (t.parentElement) t.parentElement._atlasFeatureId = fid;
      };

      layer.__atlas_onDown = (e) => {
        const oe = e.originalEvent;
        markDom(oe);

        if (props.editMode && props.activeEditMode) {
          oe?.stopPropagation();
          oe?.stopImmediatePropagation?.();
        }
      };

      layer.__atlas_onPointerDown = (e) => {
        const oe = e.originalEvent;
        markDom(oe);

        if (props.editMode && props.activeEditMode) {
          oe?.stopPropagation();
          oe?.stopImmediatePropagation?.();
        }
      };

      layer.__atlas_onClick = (e) => {
        e.originalEvent?.stopPropagation();

        if (this.clickHandler) {
          const isCtrlPressed =
            e.originalEvent?.ctrlKey || e.originalEvent?.metaKey;
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
      if (!layer || !this.map) return;

      if (visible) {
        if (!this.map.hasLayer(layer)) this.map.addLayer(layer);
      } else {
        if (this.map.hasLayer(layer)) this.map.removeLayer(layer);
      }
    },

    clearAllFeatures(map) {
      this.layers.forEach((layer) => {
        if (layer instanceof L.CircleMarker) {
          allCircles.value.delete(layer);
        }
        if (map && map.hasLayer(layer)) {
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
    const radius = getRadiusForZoom(map.getZoom());

    safeFeatures.forEach((feature) => {
      if (!feature.geometry || !Array.isArray(feature.geometry.coordinates))
        return;

      const [lng, lat] = feature.geometry.coordinates;
      const coord = [lat, lng];

      const fprops = feature.properties || {};
      const rgb = Array.isArray(fprops.color_rgb) ? fprops.color_rgb : null;
      const colorFromRgb =
        rgb && rgb.length === 3 ? `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})` : null;
      const color = feature.color || colorFromRgb || "#000";

      const circle = L.circleMarker(coord, {
        radius,
        fillColor: color,
        color,
        weight: 1,
        opacity: feature.opacity ?? 0.8,
        fillOpacity: feature.opacity ?? 0.8,
      });

      const labelText = fprops.name || feature.name || "";
      if (labelText) {
        circle.bindTooltip(labelText, {
          permanent: false,
          direction: "top",
          offset: [0, -5],
        });
      }

      featureLayerManager.addFeatureLayer(feature.id, circle, feature);
    });
  }

  function renderZones(features, map) {
    const safeFeatures = toArray(features);

    safeFeatures.forEach((feature) => {
      if (!feature.geometry || !Array.isArray(feature.geometry.coordinates))
        return;

      const fprops = feature.properties || {};
      const rgb = Array.isArray(fprops.color_rgb) ? fprops.color_rgb : null;
      const colorFromRgb =
        rgb && rgb.length === 3 ? `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})` : null;
      const fillColor = feature.color || colorFromRgb || "#ccc";

      let targetGeometry = feature.geometry;

      if (fprops.is_normalized) {
        const fc = { type: "FeatureCollection", features: [feature] };
        const anchorLat = -80 + Math.random() * 160;
        const anchorLng = -170 + Math.random() * 340;
        const sizeMeters = 2_000_000;

        const worldFc = transformNormalizedToWorld(
          fc,
          anchorLat,
          anchorLng,
          sizeMeters,
        );
        if (worldFc?.features?.[0]?.geometry) {
          targetGeometry = worldFc.features[0].geometry;
        }
      }

      let latLngs = null;

      if (targetGeometry.type === "Polygon") {
        const outer = targetGeometry.coordinates?.[0];
        if (Array.isArray(outer) && outer.length >= 4) {
          latLngs = outer.map(([lng, lat]) => [lat, lng]);
        }
      } else if (targetGeometry.type === "MultiPolygon") {
        const outer = targetGeometry.coordinates?.[0]?.[0];
        if (Array.isArray(outer) && outer.length >= 4) {
          latLngs = outer.map(([lng, lat]) => [lat, lng]);
        }
      } else {
        return;
      }

      if (!latLngs) return;

      const poly = L.polygon(latLngs, {
        color: "#333",
        weight: 1,
        fillColor,
        fillOpacity: 0.5,
        interactive: true,
      });

      const angleDeg = feature.properties?.rotationDeg ?? 0;
      if (Math.abs(angleDeg) > 1e-6) {
        const pivot = feature.properties?.center
          ? L.latLng(
              feature.properties.center.lat,
              feature.properties.center.lng,
            )
          : poly.getBounds().getCenter();

        if (targetGeometry?.type === "Polygon") {
          editingComposable.applyAngleToLayerFromCanonical(
            poly,
            map,
            targetGeometry,
            angleDeg,
            pivot,
          );
        }
      }

      const name = fprops.name || feature.name;
      if (name) poly.bindPopup(name);

      featureLayerManager.addFeatureLayer(feature.id, poly, feature);
    });
  }

  function renderArrows(features, map) {
    const safeFeatures = toArray(features);

    safeFeatures.forEach((feature) => {
      if (!feature.geometry || !Array.isArray(feature.geometry.coordinates))
        return;

      const latLngs = feature.geometry.coordinates.map(([lng, lat]) => [
        lat,
        lng,
      ]);

      const fprops = feature.properties || {};
      const rgb = Array.isArray(fprops.color_rgb) ? fprops.color_rgb : null;
      const colorFromRgb =
        rgb && rgb.length === 3 ? `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})` : null;
      const color = feature.color || colorFromRgb || "#000";

      const line = L.polyline(latLngs, {
        color,
        weight: feature.stroke_width ?? 2,
        opacity: feature.opacity ?? 1,
      });

      const name = fprops.name || feature.name;
      if (name) line.bindPopup(name);

      const elementType = getMapElementType(feature);
      const visible = props.featureVisibility?.get(String(feature.id));
      const shouldShow = visible === undefined ? true : Boolean(visible);

      if (
        shouldShow &&
        elementType === "arrow" &&
        typeof line.arrowheads === "function"
      ) {
        line.arrowheads({
          size: "10px",
          frequency: "endonly",
          fill: true,
        });
      }

      featureLayerManager.addFeatureLayer(feature.id, line, feature);
    });
  }

  function renderShapes(features, map) {
    const safeFeatures = toArray(features);

    safeFeatures.forEach((feature) => {
      if (
        !feature.geometry ||
        !Array.isArray(feature.geometry.coordinates) ||
        !feature.geometry.coordinates[0]
      )
        return;

      const latLngs = feature.geometry.coordinates[0].map((coord) => [
        coord[1],
        coord[0],
      ]);

      const shape = L.polygon(latLngs, {
        color: feature.color || "#000000",
        weight: 2,
        fillColor: feature.color || "#cccccc",
        fillOpacity: feature.opacity ?? 0.5,
        interactive: true,
      });

      const angleDeg = feature.properties?.rotationDeg ?? 0;

      if (Math.abs(angleDeg) > 1e-6) {
        const pivot = feature.properties?.center
          ? L.latLng(
              feature.properties.center.lat,
              feature.properties.center.lng,
            )
          : shape.getBounds().getCenter();

        editingComposable.applyAngleToLayerFromCanonical(
          shape,
          map,
          feature.geometry,
          angleDeg,
          pivot,
        );
      }

      if (feature.name) shape.bindPopup(feature.name);

      featureLayerManager.addFeatureLayer(feature.id, shape, feature);
    });
  }

  function renderAllFeatures(filteredFeatures, map) {
    const currentIds = new Set(filteredFeatures.map((f) => String(f.id)));
    const previousIds = previousFeatureIds.value;

    previousIds.forEach((oldId) => {
      if (!currentIds.has(oldId)) {
        const layer = featureLayerManager.layers.get(oldId);
        if (layer && map.hasLayer(layer)) {
          map.removeLayer(layer);
        }
        featureLayerManager.layers.delete(oldId);
      }
    });

    const newFeatures = filteredFeatures.filter(
      (f) => !previousIds.has(String(f.id)),
    );

    const featuresByType = {
      point: newFeatures.filter((f) => getMapElementType(f) === "point"),
      zone: newFeatures.filter((f) => getMapElementType(f) === "zone"),
      polyline: newFeatures.filter((f) => getMapElementType(f) === "polyline"),
      arrow: newFeatures.filter((f) => getMapElementType(f) === "arrow"),
      shape: newFeatures.filter((f) => getMapElementType(f) === "shape"),
    };

    renderCities(featuresByType.point, map);
    renderShapes(featuresByType.shape, map);
    renderZones(featuresByType.zone, map);
    renderArrows([...featuresByType.polyline, ...featuresByType.arrow], map);

    previousFeatureIds.value = currentIds;
  }

  function initializeBaseLayers(map) {
    featureLayerManager.setMap(map);

    L.tileLayer(
      "https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png",
      {
        attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
        subdomains: "abcd",
        maxZoom: 19,
      },
    ).addTo(map);

    drawnItems.value = new L.FeatureGroup();
    map.addLayer(drawnItems.value);

    map.on("zoomend", () => updateCircleSizes(map));
  }

  function clearAllLayers(map) {
    featureLayerManager.clearAllFeatures(map);
  }

  return {
    allCircles,
    featureLayerManager,
    previousFeatureIds,

    drawnItems,

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
