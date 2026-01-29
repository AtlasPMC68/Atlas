import { ref } from "vue";
import L from "leaflet";
import { smoothFreeLinePoints } from "../utils/mapUtils.js";
import { MAP_CONFIG } from "./useMapConfig.js";

// Composable for map editing functionality (creating shapes, managing selection, etc.)
export function useMapEditing(props, emit) {
  const isDeleteMode = ref(false);

  // IMPORTANT:
  // On garde ces refs pour compatibilité avec ton code existant,
  // mais le redimensionnement par drag est désactivé (resize via inputs seulement).
  const isResizeMode = ref(false);
  const resizingShape = ref(null);

  // ===== SHAPE CREATION FUNCTIONS =====

  function createSquare(center, sizePoint, map, layersComposable) {
    const centerPixel = map.latLngToContainerPoint(center);
    const sizePixel = map.latLngToContainerPoint(sizePoint);

    const pixelDistance = centerPixel.distanceTo(sizePixel);
    const halfSidePixels = pixelDistance / Math.sqrt(2);

    const topLeftPixel = L.point(centerPixel.x - halfSidePixels, centerPixel.y - halfSidePixels);
    const bottomRightPixel = L.point(centerPixel.x + halfSidePixels, centerPixel.y + halfSidePixels);

    const topLeft = map.containerPointToLatLng(topLeftPixel);
    const bottomRight = map.containerPointToLatLng(bottomRightPixel);

    const square = L.rectangle(
      [
        [topLeft.lat, topLeft.lng],
        [bottomRight.lat, bottomRight.lng],
      ],
      { color: "#000000", weight: 2, fillColor: "#cccccc", fillOpacity: 0.5 }
    );

    layersComposable.drawnItems.value.addLayer(square);

    const feature = squareToFeatureFromCenter(center, sizePoint, map);

    const tempFeature = {
      ...feature,
      id: `temp_${Date.now()}_${Math.random()}`,
      _isTemporary: true,
    };

    square.feature = tempFeature;

    layersComposable.featureLayerManager.layers.set(tempFeature.id, square);
    layersComposable.featureLayerManager.makeLayerClickable(tempFeature.id, square);
  }

  function createRectangle(startCorner, endCorner, map, layersComposable) {
    const minLat = Math.min(startCorner.lat, endCorner.lat);
    const maxLat = Math.max(startCorner.lat, endCorner.lat);
    const minLng = Math.min(startCorner.lng, endCorner.lng);
    const maxLng = Math.max(startCorner.lng, endCorner.lng);

    const rectangle = L.rectangle(
      [
        [minLat, minLng],
        [maxLat, maxLng],
      ],
      { color: "#000000", weight: 2, fillColor: "#cccccc", fillOpacity: 0.5 }
    );

    layersComposable.drawnItems.value.addLayer(rectangle);

    const feature = rectangleToFeatureFromCorners(startCorner, endCorner);

    const tempFeature = {
      ...feature,
      id: `temp_${Date.now()}_${Math.random()}`,
      _isTemporary: true,
    };

    rectangle.feature = tempFeature;

    layersComposable.featureLayerManager.layers.set(tempFeature.id, rectangle);
    layersComposable.featureLayerManager.makeLayerClickable(tempFeature.id, rectangle);
  }

  function createCircle(center, edgePoint, map, layersComposable) {
    const radius = map.distance(center, edgePoint);

    const circle = L.circle(center, {
      radius,
      color: "#000000",
      weight: 2,
      fillColor: "#cccccc",
      fillOpacity: 0.5,
    });

    layersComposable.drawnItems.value.addLayer(circle);

    const feature = circleToFeatureFromCenter(center, edgePoint, map);

    const tempFeature = {
      ...feature,
      id: `temp_${Date.now()}_${Math.random()}`,
      _isTemporary: true,
    };

    circle.feature = tempFeature;

    layersComposable.featureLayerManager.layers.set(tempFeature.id, circle);
    layersComposable.featureLayerManager.makeLayerClickable(tempFeature.id, circle);
  }

  function createTriangle(center, sizePoint, map, layersComposable) {
    const distance = map.distance(center, sizePoint);

    const points = [];
    for (let i = 0; i < 3; i++) {
      const angle = ((i * 120 + 90) * Math.PI) / 180;
      const lat = center.lat + (distance / 111320) * Math.sin(angle);
      const lng =
        center.lng +
        ((distance / 111320) * Math.cos(angle)) /
          Math.cos((center.lat * Math.PI) / 180);
      points.push([lat, lng]);
    }

    const triangle = L.polygon(points, {
      color: "#000000",
      weight: 2,
      fillColor: "#cccccc",
      fillOpacity: 0.5,
    });

    layersComposable.drawnItems.value.addLayer(triangle);

    const feature = triangleToFeatureFromCenter(center, sizePoint, map);

    const tempFeature = {
      ...feature,
      id: `temp_${Date.now()}_${Math.random()}`,
      _isTemporary: true,
    };

    triangle.feature = tempFeature;

    layersComposable.featureLayerManager.layers.set(tempFeature.id, triangle);
    layersComposable.featureLayerManager.makeLayerClickable(tempFeature.id, triangle);
  }

  function createOval(center, heightPoint, widthPoint, map, layersComposable) {
    const heightRadius = Math.abs(center.lat - heightPoint.lat) * 111320;
    const widthRadius =
      Math.abs(center.lng - widthPoint.lng) *
      111320 *
      Math.cos((center.lat * Math.PI) / 180);

    const points = [];
    const steps = 32;
    for (let i = 0; i < steps; i++) {
      const angle = (i / steps) * 2 * Math.PI;
      const lat = center.lat + (heightRadius / 111320) * Math.sin(angle);
      const lng =
        center.lng +
        ((widthRadius / 111320) * Math.cos(angle)) /
          Math.cos((center.lat * Math.PI) / 180);
      points.push([lat, lng]);
    }

    const oval = L.polygon(points, {
      color: "#000000",
      weight: 2,
      fillColor: "#cccccc",
      fillOpacity: 0.5,
    });

    layersComposable.drawnItems.value.addLayer(oval);

    const feature = ovalToFeatureFromCenter(center, heightPoint, widthPoint);

    const tempFeature = {
      ...feature,
      id: `temp_${Date.now()}_${Math.random()}`,
      _isTemporary: true,
    };

    oval.feature = tempFeature;

    layersComposable.featureLayerManager.layers.set(tempFeature.id, oval);
    layersComposable.featureLayerManager.makeLayerClickable(tempFeature.id, oval);
  }

  function createPointAt(latlng, map, layersComposable) {
    const currentZoom = map.getZoom();
    const radius = getRadiusForZoom(currentZoom);

    const circle = L.circleMarker(latlng, {
      radius,
      fillColor: "#000000",
      color: "#333333",
      weight: 1,
      opacity: 0.8,
      fillOpacity: 0.8,
      draggable: true,
    });

    layersComposable.allCircles.value.add(circle);
    layersComposable.drawnItems.value.addLayer(circle);

    const feature = {
      map_id: props.mapId,
      type: "point",
      geometry: { type: "Point", coordinates: [latlng.lng, latlng.lat] },
      color: "#000000",
      opacity: 0.8,
      z_index: 1,
    };

    const tempFeature = {
      ...feature,
      id: `temp_${Date.now()}_${Math.random()}`,
      _isTemporary: true,
    };

    layersComposable.featureLayerManager.layers.set(tempFeature.id, circle);
    layersComposable.featureLayerManager.makeLayerClickable(tempFeature.id, circle);
  }

  function createLine(startLatLng, endLatLng, map, layersComposable) {
    const line = L.polyline([startLatLng, endLatLng], {
      color: "#000000",
      weight: 2,
      opacity: 1.0,
    });

    layersComposable.drawnItems.value.addLayer(line);

    const feature = {
      map_id: props.mapId,
      type: "polyline",
      geometry: {
        type: "LineString",
        coordinates: [
          [startLatLng.lng, startLatLng.lat],
          [endLatLng.lng, endLatLng.lat],
        ],
      },
      color: "#000000",
      stroke_width: 2,
      opacity: 1.0,
      z_index: 1,
    };

    const tempFeature = {
      ...feature,
      id: `temp_${Date.now()}_${Math.random()}`,
      _isTemporary: true,
    };

    layersComposable.featureLayerManager.layers.set(tempFeature.id, line);
    layersComposable.featureLayerManager.makeLayerClickable(tempFeature.id, line);
  }

  function createPolygon(points, map, layersComposable) {
    const polygon = L.polygon(points, {
      color: "#000000",
      weight: 2,
      fillColor: "#cccccc",
      fillOpacity: 0.5,
    });

    layersComposable.drawnItems.value.addLayer(polygon);

    const feature = {
      map_id: props.mapId,
      type: "polygon",
      geometry: {
        type: "Polygon",
        coordinates: [points.map((p) => [p.lng, p.lat])],
      },
      color: "#cccccc",
      opacity: 0.5,
      z_index: 1,
    };

    const tempFeature = {
      ...feature,
      id: `temp_${Date.now()}_${Math.random()}`,
      _isTemporary: true,
    };

    layersComposable.featureLayerManager.layers.set(tempFeature.id, polygon);
    layersComposable.featureLayerManager.makeLayerClickable(tempFeature.id, polygon);
  }

  function finishFreeLine(freeLinePoints, tempFreeLine, map, layersComposable) {
    if (freeLinePoints.length < 2) return;

    const smoothedPoints = smoothFreeLinePoints(freeLinePoints);

    if (tempFreeLine) layersComposable.drawnItems.value.removeLayer(tempFreeLine);

    const freeLine = L.polyline(smoothedPoints, {
      color: "#000000",
      weight: 2,
      opacity: 1.0,
    });

    layersComposable.drawnItems.value.addLayer(freeLine);

    const feature = {
      map_id: props.mapId,
      type: "polyline",
      geometry: {
        type: "LineString",
        coordinates: smoothedPoints.map((point) => [point.lng, point.lat]),
      },
      color: "#000000",
      stroke_width: 2,
      opacity: 1.0,
      z_index: 1,
    };

    const tempId = `temp_freeline_${Date.now()}_${Math.random()}`;
    const tempFeature = { ...feature, id: tempId, _isTemporary: true };

    layersComposable.featureLayerManager.layers.set(tempId, freeLine);
    if (props.editMode) {
      layersComposable.featureLayerManager.makeLayerClickable(tempId, freeLine);
    }
  }

  // ===== TEMPORARY SHAPE UPDATE FUNCTIONS =====

  function updateTempSquareFromCenter(center, sizePoint, map, layersComposable, tempShape) {
    if (tempShape) layersComposable.drawnItems.value.removeLayer(tempShape);

    const centerPixel = map.latLngToContainerPoint(center);
    const sizePixel = map.latLngToContainerPoint(sizePoint);
    const pixelDistance = centerPixel.distanceTo(sizePixel);
    const halfSidePixels = pixelDistance / Math.sqrt(2);

    const topLeftPixel = L.point(centerPixel.x - halfSidePixels, centerPixel.y - halfSidePixels);
    const bottomRightPixel = L.point(centerPixel.x + halfSidePixels, centerPixel.y + halfSidePixels);

    const topLeft = map.containerPointToLatLng(topLeftPixel);
    const bottomRight = map.containerPointToLatLng(bottomRightPixel);

    const newTempShape = L.rectangle(
      [
        [topLeft.lat, topLeft.lng],
        [bottomRight.lat, bottomRight.lng],
      ],
      { color: "#000000", weight: 2, fillColor: "#cccccc", fillOpacity: 0.5 }
    );

    layersComposable.drawnItems.value.addLayer(newTempShape);
    return newTempShape;
  }

  function updateTempRectangleFromCorners(startCorner, endCorner, map, layersComposable, tempShape) {
    if (tempShape) layersComposable.drawnItems.value.removeLayer(tempShape);

    const minLat = Math.min(startCorner.lat, endCorner.lat);
    const maxLat = Math.max(startCorner.lat, endCorner.lat);
    const minLng = Math.min(startCorner.lng, endCorner.lng);
    const maxLng = Math.max(startCorner.lng, endCorner.lng);

    const newTempShape = L.rectangle(
      [
        [minLat, minLng],
        [maxLat, maxLng],
      ],
      { color: "#000000", weight: 2, fillColor: "#cccccc", fillOpacity: 0.5 }
    );

    layersComposable.drawnItems.value.addLayer(newTempShape);
    return newTempShape;
  }

  function updateTempCircleFromCenter(center, edgePoint, map, layersComposable, tempShape) {
    if (tempShape) layersComposable.drawnItems.value.removeLayer(tempShape);

    const radius = map.distance(center, edgePoint);

    const newTempShape = L.circle(center, {
      radius,
      color: "#000000",
      weight: 2,
      fillColor: "#cccccc",
      fillOpacity: 0.5,
    });

    layersComposable.drawnItems.value.addLayer(newTempShape);
    return newTempShape;
  }

  function updateTempTriangleFromCenter(center, sizePoint, map, layersComposable, tempShape) {
    if (tempShape) layersComposable.drawnItems.value.removeLayer(tempShape);

    const distance = map.distance(center, sizePoint);

    const points = [];
    for (let i = 0; i < 3; i++) {
      const angle = ((i * 120 + 90) * Math.PI) / 180;
      const lat = center.lat + (distance / 111320) * Math.sin(angle);
      const lng =
        center.lng +
        ((distance / 111320) * Math.cos(angle)) /
          Math.cos((center.lat * Math.PI) / 180);
      points.push([lat, lng]);
    }

    const newTempShape = L.polygon(points, {
      color: "#000000",
      weight: 2,
      fillColor: "#cccccc",
      fillOpacity: 0.5,
    });

    layersComposable.drawnItems.value.addLayer(newTempShape);
    return newTempShape;
  }

  function updateTempOvalHeight(center, heightPoint, map, layersComposable, tempShape) {
    if (tempShape) layersComposable.drawnItems.value.removeLayer(tempShape);

    const radius = Math.abs(center.lat - heightPoint.lat) * 111320;

    const newTempShape = L.circle(center, {
      radius,
      color: "#000000",
      weight: 2,
      fillColor: "#cccccc",
      fillOpacity: 0.5,
    });

    layersComposable.drawnItems.value.addLayer(newTempShape);
    return newTempShape;
  }

  function updateTempOvalWidth(center, heightPoint, widthPoint, map, layersComposable, tempShape) {
    if (tempShape) layersComposable.drawnItems.value.removeLayer(tempShape);

    const heightRadius = Math.abs(center.lat - heightPoint.lat) * 111320;
    const widthRadius =
      Math.abs(center.lng - widthPoint.lng) *
      111320 *
      Math.cos((center.lat * Math.PI) / 180);

    const points = [];
    const steps = 32;
    for (let i = 0; i < steps; i++) {
      const angle = (i / steps) * 2 * Math.PI;
      const lat = center.lat + (heightRadius / 111320) * Math.sin(angle);
      const lng =
        center.lng +
        ((widthRadius / 111320) * Math.cos(angle)) /
          Math.cos((center.lat * Math.PI) / 180);
      points.push([lat, lng]);
    }

    const newTempShape = L.polygon(points, {
      color: "#000000",
      weight: 2,
      fillColor: "#cccccc",
      fillOpacity: 0.5,
    });

    layersComposable.drawnItems.value.addLayer(newTempShape);
    return newTempShape;
  }

  // ===== FEATURE CONVERSION FUNCTIONS =====

  function squareToFeatureFromCenter(center, sizePoint, map) {
    const distance = map.distance(center, sizePoint);
    const halfSide = distance / Math.sqrt(2);

    const latOffset = halfSide / 111320;
    const lngOffset = halfSide / (111320 * Math.cos((center.lat * Math.PI) / 180));

    const geometry = {
      type: "Polygon",
      coordinates: [
        [
          [center.lng - lngOffset, center.lat + latOffset],
          [center.lng + lngOffset, center.lat + latOffset],
          [center.lng + lngOffset, center.lat - latOffset],
          [center.lng - lngOffset, center.lat - latOffset],
          [center.lng - lngOffset, center.lat + latOffset],
        ],
      ],
    };

    return {
      map_id: props.mapId,
      type: "square",
      geometry,
      color: "#cccccc",
      opacity: 0.5,
      z_index: 1,
      properties: {
        shapeType: "square",
        center: { lat: center.lat, lng: center.lng },
        size: distance,
        resizable: true,
      },
    };
  }

  function rectangleToFeatureFromCorners(startCorner, endCorner) {
    const minLat = Math.min(startCorner.lat, endCorner.lat);
    const maxLat = Math.max(startCorner.lat, endCorner.lat);
    const minLng = Math.min(startCorner.lng, endCorner.lng);
    const maxLng = Math.max(startCorner.lng, endCorner.lng);

    const geometry = {
      type: "Polygon",
      coordinates: [
        [
          [minLng, maxLat],
          [maxLng, maxLat],
          [maxLng, minLat],
          [minLng, minLat],
          [minLng, maxLat],
        ],
      ],
    };

    return {
      map_id: props.mapId,
      type: "rectangle",
      geometry,
      color: "#cccccc",
      opacity: 0.5,
      z_index: 1,
    };
  }

  function circleToFeatureFromCenter(center, edgePoint, map) {
    const radius = map.distance(center, edgePoint);

    const points = [];
    const steps = 32;
    for (let i = 0; i < steps; i++) {
      const angle = (i / steps) * 2 * Math.PI;
      const lat = center.lat + (radius / 111320) * Math.sin(angle);
      const lng =
        center.lng +
        ((radius / 111320) * Math.cos(angle)) /
          Math.cos((center.lat * Math.PI) / 180);
      points.push([lng, lat]);
    }
    points.push(points[0]);

    const geometry = { type: "Polygon", coordinates: [points] };

    return {
      map_id: props.mapId,
      type: "circle",
      geometry,
      color: "#cccccc",
      opacity: 0.5,
      z_index: 1,
      properties: {
        shapeType: "circle",
        center: { lat: center.lat, lng: center.lng },
        size: radius,
        resizable: true,
      },
    };
  }

  function triangleToFeatureFromCenter(center, sizePoint, map) {
    const distance = map.distance(center, sizePoint);

    const points = [];
    for (let i = 0; i < 3; i++) {
      const angle = ((i * 120 + 90) * Math.PI) / 180;
      const lat = center.lat + (distance / 111320) * Math.sin(angle);
      const lng =
        center.lng +
        ((distance / 111320) * Math.cos(angle)) /
          Math.cos((center.lat * Math.PI) / 180);
      points.push([lng, lat]);
    }
    points.push(points[0]);

    const geometry = { type: "Polygon", coordinates: [points] };

    return {
      map_id: props.mapId,
      type: "triangle",
      geometry,
      color: "#cccccc",
      opacity: 0.5,
      z_index: 1,
      properties: {
        shapeType: "triangle",
        center: { lat: center.lat, lng: center.lng },
        size: distance,
        resizable: true,
      },
    };
  }

  function ovalToFeatureFromCenter(center, heightPoint, widthPoint) {
    const heightRadius = Math.abs(center.lat - heightPoint.lat) * 111320;
    const widthRadius =
      Math.abs(center.lng - widthPoint.lng) *
      111320 *
      Math.cos((center.lat * Math.PI) / 180);

    const points = [];
    const steps = 32;
    for (let i = 0; i < steps; i++) {
      const angle = (i / steps) * 2 * Math.PI;
      const lat = center.lat + (heightRadius / 111320) * Math.sin(angle);
      const lng =
        center.lng +
        ((widthRadius / 111320) * Math.cos(angle)) /
          Math.cos((center.lat * Math.PI) / 180);
      points.push([lng, lat]);
    }
    points.push(points[0]);

    const geometry = { type: "Polygon", coordinates: [points] };

    return {
      map_id: props.mapId,
      type: "oval",
      geometry,
      color: "#cccccc",
      opacity: 0.5,
      z_index: 1,
    };
  }

  // ===== SELECTION AND VISUAL MANAGEMENT =====

  function updateFeatureSelectionVisual(map, layerManager, selectedFeatures) {
    if (!map || !layerManager) return;

    layerManager.layers.forEach((layer, featureId) => {
      const fid = String(featureId);

      if (selectedFeatures.has(fid)) {
        if (layer instanceof L.CircleMarker) {
          layer.setStyle({ color: "#ff6b6b", weight: 3, fillColor: "#ff6b6b", fillOpacity: 0.8 });
        } else if (layer instanceof L.Polygon || layer instanceof L.Rectangle) {
          layer.setStyle({
            color: "#ff6b6b",
            weight: 3,
            fillColor: layer.options.fillColor,
            fillOpacity: layer.options.fillOpacity,
          });
        } else if (layer instanceof L.Polyline) {
          layer.setStyle({ color: "#ff6b6b", weight: 4 });
        }
      } else {
        if (layer.__atlas_originalStyle && layer.setStyle) {
          layer.setStyle(layer.__atlas_originalStyle);
        } else if (layer.setStyle) {
          const feature = props.features.find((f) => String(f.id) === fid);
          const defaultBorderColor = "#000000";
          const defaultFillColor = "#cccccc";
          const defaultOpacity = 0.5;
          const defaultStrokeWidth = 2;

          if (layer instanceof L.CircleMarker) {
            layer.setStyle({
              color: feature?.color || defaultBorderColor,
              weight: 1,
              fillColor: feature?.color || defaultBorderColor,
              fillOpacity: feature?.opacity ?? 0.8,
            });
          } else if (layer instanceof L.Polygon || layer instanceof L.Rectangle) {
            layer.setStyle({
              color: feature?.color || defaultBorderColor,
              weight: 2,
              fillColor: feature?.color || defaultFillColor,
              fillOpacity: feature?.opacity ?? defaultOpacity,
            });
          } else if (layer instanceof L.Polyline) {
            layer.setStyle({
              color: feature?.color || defaultBorderColor,
              weight: feature?.stroke_width ?? defaultStrokeWidth,
              opacity: feature?.opacity ?? 1,
            });
          }
        }
      }
    });
  }

  // ===== CRUD OPERATIONS =====

  async function updateFeaturePosition(feature, deltaLat, deltaLng) {
    try {
      const updatedGeometry = updateGeometryCoordinates(feature.geometry, deltaLat, deltaLng);
      const updateData = { geometry: updatedGeometry };

      const response = await fetch(`http://localhost:8000/maps/features/${feature.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(updateData),
      });

      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const updatedFeature = await response.json();

      const featureIndex = props.features.findIndex((f) => f.id === feature.id);
      if (featureIndex !== -1) {
        const updatedFeatures = [...props.features];
        updatedFeatures[featureIndex] = updatedFeature;
        emit("features-loaded", updatedFeatures);
      }
    } catch (error) {
      console.error("Error updating feature position:", error);
    }
  }

  async function deleteSelectedFeatures(selectedFeatures, featureLayerManager, map, emit) {
    if (selectedFeatures.size === 0) return;

    const featuresToDelete = Array.from(selectedFeatures);

    for (const featureId of featuresToDelete) {
      const layer = featureLayerManager.layers.get(String(featureId));
      if (layer) {
        map.removeLayer(layer);
        featureLayerManager.layers.delete(String(featureId));
      }
    }

    for (const featureId of featuresToDelete) {
      try {
        const response = await fetch(`http://localhost:8000/maps/features/${featureId}`, {
          method: "DELETE",
        });
        if (!response.ok) console.error(`Failed to delete feature ${featureId}`);
      } catch (error) {
        console.error(`Error deleting feature ${featureId}:`, error);
      }
    }

    const remainingFeatures = props.features.filter((f) => !featuresToDelete.includes(f.id));
    emit("features-loaded", remainingFeatures);

    selectedFeatures.clear();
    updateFeatureSelectionVisual(map, featureLayerManager, selectedFeatures);
  }

  async function deleteFeature(featureId, featureLayerManager, map, emit) {
    const fid = String(featureId);

    const layer = featureLayerManager.layers.get(fid);
    if (layer) {
      map.removeLayer(layer);
      featureLayerManager.layers.delete(fid);
    }

    if (!fid.startsWith("temp_")) {
      try {
        const response = await fetch(`http://localhost:8000/maps/features/${featureId}`, {
          method: "DELETE",
        });
        if (!response.ok) console.error(`Failed to delete feature ${featureId}`);
      } catch (error) {
        console.error(`Error deleting feature ${featureId}:`, error);
      }

      const remainingFeatures = props.features.filter((f) => f.id !== featureId);
      emit("features-loaded", remainingFeatures);
    }
  }

  function updateGeometryCoordinates(geometry, deltaLat, deltaLng) {
    if (!geometry || !geometry.coordinates) return geometry;

    const updatedGeometry = { ...geometry };

    switch (geometry.type) {
      case "Point":
        updatedGeometry.coordinates = [geometry.coordinates[0] + deltaLng, geometry.coordinates[1] + deltaLat];
        break;
      case "LineString":
        updatedGeometry.coordinates = geometry.coordinates.map((coord) => [coord[0] + deltaLng, coord[1] + deltaLat]);
        break;
      case "Polygon":
        updatedGeometry.coordinates = geometry.coordinates.map((ring) =>
          ring.map((coord) => [coord[0] + deltaLng, coord[1] + deltaLat])
        );
        break;
      default:
        return geometry;
    }

    return updatedGeometry;
  }

  function toggleDeleteMode() {
    if (props.activeEditMode === "DELETE_FEATURE") emit("mode-change", null);
    else emit("mode-change", "DELETE_FEATURE");
  }

  // ===== RESIZE (DISABLED / LEGACY STUBS) =====
  // Ces fonctions existent juste pour ne pas casser le code qui les appelle,
  // mais ne font rien. Le resize doit être fait via les input box.
  function startResizeShape() {
    isResizeMode.value = false;
    resizingShape.value = null;
    return false;
  }

  function updateResizeShape() {
    return null;
  }

  async function finishResizeShape() {
    isResizeMode.value = false;
    resizingShape.value = null;
    return;
  }

  function cancelResizeShape() {
    isResizeMode.value = false;
    resizingShape.value = null;
    return;
  }

  return {
    // State
    isDeleteMode,
    isResizeMode,
    resizingShape,

    // Shape creation functions
    createSquare,
    createRectangle,
    createCircle,
    createTriangle,
    createOval,
    createPointAt,
    createLine,
    createPolygon,
    finishFreeLine,

    // Temporary shape updates
    updateTempSquareFromCenter,
    updateTempRectangleFromCorners,
    updateTempCircleFromCenter,
    updateTempTriangleFromCenter,
    updateTempOvalHeight,
    updateTempOvalWidth,

    // Feature conversion functions
    squareToFeatureFromCenter,
    rectangleToFeatureFromCorners,
    circleToFeatureFromCenter,
    triangleToFeatureFromCenter,
    ovalToFeatureFromCenter,

    // Selection and visual management
    updateFeatureSelectionVisual,

    // CRUD operations
    updateFeaturePosition,
    deleteSelectedFeatures,
    deleteFeature,
    updateGeometryCoordinates,

    // Mode management
    toggleDeleteMode,

    // Resize functions (disabled but kept for compatibility)
    startResizeShape,
    updateResizeShape,
    finishResizeShape,
    cancelResizeShape,

    // Utility functions
    smoothFreeLinePoints,
  };
}

function getRadiusForZoom(currentZoom) {
  const BASE_ZOOM = 5;
  const BASE_RADIUS = 3;
  const ZOOM_FACTOR = 1.5;
  const zoomDiff = currentZoom - BASE_ZOOM;
  return Math.max(BASE_RADIUS, BASE_RADIUS * Math.pow(ZOOM_FACTOR, zoomDiff));
}
