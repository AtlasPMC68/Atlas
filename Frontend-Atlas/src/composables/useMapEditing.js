import { ref } from 'vue';
import L from 'leaflet';
import { smoothFreeLinePoints } from '../utils/mapUtils.js';
import { MAP_CONFIG } from './useMapConfig.js';

// Composable for map editing functionality (creating shapes, managing selection, etc.)
export function useMapEditing(props, emit) {
  const isDeleteMode = ref(false);

  // ===== SHAPE CREATION FUNCTIONS =====

  // Create a square with center and size (like a circle)
  function createSquare(center, sizePoint, map, layersComposable) {
    // Use pixel coordinates for a perfectly visual square
    const centerPixel = map.latLngToContainerPoint(center);
    const sizePixel = map.latLngToContainerPoint(sizePoint);

    // Calculate distance in pixels
    const pixelDistance = centerPixel.distanceTo(sizePixel);
    const halfSidePixels = pixelDistance / Math.sqrt(2);

    // Calculate square corners in pixels
    const topLeftPixel = L.point(
      centerPixel.x - halfSidePixels,
      centerPixel.y - halfSidePixels
    );
    const bottomRightPixel = L.point(
      centerPixel.x + halfSidePixels,
      centerPixel.y + halfSidePixels
    );

    // Convert to geographic coordinates
    const topLeft = map.containerPointToLatLng(topLeftPixel);
    const bottomRight = map.containerPointToLatLng(bottomRightPixel);

    const square = L.rectangle(
      [
        [topLeft.lat, topLeft.lng],
        [bottomRight.lat, bottomRight.lng],
      ],
      {
        color: "#000000",
        weight: 2,
        fillColor: "#cccccc",
        fillOpacity: 0.5,
      }
    );

    layersComposable.drawnItems.value.addLayer(square);

    // Create feature
    const feature = squareToFeatureFromCenter(center, sizePoint, map);

    // Generate temporary ID for local feature
    const tempFeature = {
      ...feature,
      id: `temp_${Date.now()}_${Math.random()}`,
      _isTemporary: true,
    };

    // Make shape clickable immediately
    layersComposable.featureLayerManager.layers.set(tempFeature.id, square);
    layersComposable.featureLayerManager.makeLayerClickable(tempFeature.id, square);
  }

  // Create a rectangle between two opposite corners
  function createRectangle(startCorner, endCorner, map, layersComposable) {
    // Same logic as square
    const minLat = Math.min(startCorner.lat, endCorner.lat);
    const maxLat = Math.max(startCorner.lat, endCorner.lat);
    const minLng = Math.min(startCorner.lng, endCorner.lng);
    const maxLng = Math.max(startCorner.lng, endCorner.lng);

    const rectangle = L.rectangle(
      [
        [minLat, minLng],
        [maxLat, maxLng],
      ],
      {
        color: "#000000",
        weight: 2,
        fillColor: "#cccccc",
        fillOpacity: 0.5,
      }
    );

    layersComposable.drawnItems.value.addLayer(rectangle);

    const feature = rectangleToFeatureFromCorners(startCorner, endCorner);

    // Generate temporary ID for local feature
    const tempFeature = {
      ...feature,
      id: `temp_${Date.now()}_${Math.random()}`,
      _isTemporary: true,
    };

    // Make shape clickable immediately
    layersComposable.featureLayerManager.layers.set(tempFeature.id, rectangle);
    layersComposable.featureLayerManager.makeLayerClickable(tempFeature.id, rectangle);
  }

  // Create a circle with center and edge point
  function createCircle(center, edgePoint, map, layersComposable) {
    const radius = map.distance(center, edgePoint);

    const circle = L.circle(center, {
      radius: radius,
      color: "#000000",
      weight: 2,
      fillColor: "#cccccc",
      fillOpacity: 0.5,
    });

    layersComposable.drawnItems.value.addLayer(circle);

    const feature = circleToFeatureFromCenter(center, edgePoint, map);

    // Generate temporary ID for local feature
    const tempFeature = {
      ...feature,
      id: `temp_${Date.now()}_${Math.random()}`,
      _isTemporary: true,
    };

    // Make shape clickable immediately
    layersComposable.featureLayerManager.layers.set(tempFeature.id, circle);
    layersComposable.featureLayerManager.makeLayerClickable(tempFeature.id, circle);
  }

  // Create a triangle with center and size
  function createTriangle(center, sizePoint, map, layersComposable) {
    const distance = map.distance(center, sizePoint);

    const points = [];
    for (let i = 0; i < 3; i++) {
      const angle = ((i * 120 + 90) * Math.PI) / 180; // Triangle pointing up
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

    // Generate temporary ID for local feature
    const tempFeature = {
      ...feature,
      id: `temp_${Date.now()}_${Math.random()}`,
      _isTemporary: true,
    };

    // Make shape clickable immediately
    layersComposable.featureLayerManager.layers.set(tempFeature.id, triangle);
    layersComposable.featureLayerManager.makeLayerClickable(tempFeature.id, triangle);
  }

  // Create an oval with center, height and width
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

    // Generate temporary ID for local feature
    const tempFeature = {
      ...feature,
      id: `temp_${Date.now()}_${Math.random()}`,
      _isTemporary: true,
    };

    // Make shape clickable immediately
    layersComposable.featureLayerManager.layers.set(tempFeature.id, oval);
    layersComposable.featureLayerManager.makeLayerClickable(tempFeature.id, oval);
  }

  // Create a point at position
  function createPointAt(latlng, map, layersComposable) {
    const currentZoom = map.getZoom();
    const radius = getRadiusForZoom(currentZoom);

    // Use circleMarker with adaptive size
    const circle = L.circleMarker(latlng, {
      radius: radius,
      fillColor: "#000000",
      color: "#333333",
      weight: 1,
      opacity: 0.8,
      fillOpacity: 0.8,
      draggable: true,
    });

    // Add to circle collection
    layersComposable.allCircles.value.add(circle);

    layersComposable.drawnItems.value.addLayer(circle);

    // Create feature
    const feature = {
      map_id: props.mapId,
      type: "point",
      geometry: {
        type: "Point",
        coordinates: [latlng.lng, latlng.lat],
      },
      color: "#000000",
      opacity: 0.8,
      z_index: 1,
    };

    // Generate temporary ID for local feature
    const tempFeature = {
      ...feature,
      id: `temp_${Date.now()}_${Math.random()}`,
      _isTemporary: true,
    };

    // Make shape clickable immediately
    layersComposable.featureLayerManager.layers.set(tempFeature.id, circle);
    layersComposable.featureLayerManager.makeLayerClickable(tempFeature.id, circle);
  }

  // Create a line between two points
  function createLine(startLatLng, endLatLng, map, layersComposable) {
    // NO arrowheads - user explicitly requested to remove them
    const line = L.polyline([startLatLng, endLatLng], {
      color: "#000000",
      weight: 2,
      opacity: 1.0,
    });

    layersComposable.drawnItems.value.addLayer(line);

    // Create feature
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

    // Generate temporary ID for local feature
    const tempFeature = {
      ...feature,
      id: `temp_${Date.now()}_${Math.random()}`,
      _isTemporary: true,
    };

    // Make shape clickable immediately
    layersComposable.featureLayerManager.layers.set(tempFeature.id, line);
    layersComposable.featureLayerManager.makeLayerClickable(tempFeature.id, line);
  }

  // Create a polygon
  function createPolygon(points, map, layersComposable) {
    const polygon = L.polygon(points, {
      color: "#000000",
      weight: 2,
      fillColor: "#cccccc",
      fillOpacity: 0.5,
    });

    layersComposable.drawnItems.value.addLayer(polygon);

    // Create feature
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

    // Generate temporary ID for local feature
    const tempFeature = {
      ...feature,
      id: `temp_${Date.now()}_${Math.random()}`,
      _isTemporary: true,
    };

    // Make shape clickable immediately
    layersComposable.featureLayerManager.layers.set(tempFeature.id, polygon);
    layersComposable.featureLayerManager.makeLayerClickable(tempFeature.id, polygon);
  }

  // Finalize free line
  function finishFreeLine(freeLinePoints, tempFreeLine, map, layersComposable) {
    if (freeLinePoints.length < 2) return;

    // Apply final smoothing
    const smoothedPoints = smoothFreeLinePoints(freeLinePoints);

    // Remove temporary line
    if (tempFreeLine) {
      layersComposable.drawnItems.value.removeLayer(tempFreeLine);
    }

    // Create final smoothed line WITHOUT arrowheads
    const freeLine = L.polyline(smoothedPoints, {
      color: "#000000",
      weight: 2,
      opacity: 1.0,
    });

    layersComposable.drawnItems.value.addLayer(freeLine);

    // Create and save feature automatically
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

    // Generate temporary ID to make line clickable immediately
    const tempId = `temp_freeline_${Date.now()}_${Math.random()}`;
    const tempFeature = {
      ...feature,
      id: tempId,
      _isTemporary: true,
    };
    
    layersComposable.featureLayerManager.layers.set(tempId, freeLine);
    if (props.editMode) {
      layersComposable.featureLayerManager.makeLayerClickable(tempId, freeLine);
    }
  }

  // ===== TEMPORARY SHAPE UPDATE FUNCTIONS =====

  // Update temporary square from center and size (like circle)
  function updateTempSquareFromCenter(center, sizePoint, map, layersComposable, tempShape) {
    // Clean previous shape
    if (tempShape) {
      layersComposable.drawnItems.value.removeLayer(tempShape);
    }

    // Use pixel coordinates to create perfect square
    const centerPixel = map.latLngToContainerPoint(center);
    const sizePixel = map.latLngToContainerPoint(sizePoint);

    // Calculate distance in pixels
    const pixelDistance = centerPixel.distanceTo(sizePixel);

    // Create perfect square: side = distance / √2
    const halfSidePixels = pixelDistance / Math.sqrt(2);

    // Calculate square corners in pixels
    const topLeftPixel = L.point(
      centerPixel.x - halfSidePixels,
      centerPixel.y - halfSidePixels
    );
    const bottomRightPixel = L.point(
      centerPixel.x + halfSidePixels,
      centerPixel.y + halfSidePixels
    );

    // Convert pixel coordinates to geographic coordinates
    const topLeft = map.containerPointToLatLng(topLeftPixel);
    const bottomRight = map.containerPointToLatLng(bottomRightPixel);

    // Create square corners
    const bounds = [
      [topLeft.lat, topLeft.lng],
      [bottomRight.lat, bottomRight.lng],
    ];

    const newTempShape = L.rectangle(bounds, {
      color: "#000000",
      weight: 2,
      fillColor: "#cccccc",
      fillOpacity: 0.5,
    });

    layersComposable.drawnItems.value.addLayer(newTempShape);
    return newTempShape;
  }

  // Update temporary rectangle from two opposite corners
  function updateTempRectangleFromCorners(startCorner, endCorner, map, layersComposable, tempShape) {
    // Clean previous shape
    if (tempShape) {
      layersComposable.drawnItems.value.removeLayer(tempShape);
    }

    // Calculate four rectangle corner coordinates
    const minLat = Math.min(startCorner.lat, endCorner.lat);
    const maxLat = Math.max(startCorner.lat, endCorner.lat);
    const minLng = Math.min(startCorner.lng, endCorner.lng);
    const maxLng = Math.max(startCorner.lng, endCorner.lng);

    // Create rectangle with these bounds
    const bounds = [
      [minLat, minLng],
      [maxLat, maxLng],
    ];

    const newTempShape = L.rectangle(bounds, {
      color: "#000000",
      weight: 2,
      fillColor: "#cccccc",
      fillOpacity: 0.5,
    });

    layersComposable.drawnItems.value.addLayer(newTempShape);
    return newTempShape;
  }

  // Update temporary circle from center and edge point
  function updateTempCircleFromCenter(center, edgePoint, map, layersComposable, tempShape) {
    // Clean previous shape
    if (tempShape) {
      layersComposable.drawnItems.value.removeLayer(tempShape);
    }

    // Calculate radius in meters
    const radius = map.distance(center, edgePoint);

    const newTempShape = L.circle(center, {
      radius: radius,
      color: "#000000",
      weight: 2,
      fillColor: "#cccccc",
      fillOpacity: 0.5,
    });

    layersComposable.drawnItems.value.addLayer(newTempShape);
    return newTempShape;
  }

  // Update temporary triangle from center and size
  function updateTempTriangleFromCenter(center, sizePoint, map, layersComposable, tempShape) {
    // Clean previous shape
    if (tempShape) {
      layersComposable.drawnItems.value.removeLayer(tempShape);
    }

    // Calculate distance from center
    const distance = map.distance(center, sizePoint);

    // Create equilateral triangle pointing up
    // Calculate three triangle points
    const points = [];
    for (let i = 0; i < 3; i++) {
      const angle = ((i * 120 + 90) * Math.PI) / 180; // Start with top point (90°)
      const lat = center.lat + (distance / 111320) * Math.sin(angle); // Approximation in degrees
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

  // Update temporary oval - height
  function updateTempOvalHeight(center, heightPoint, map, layersComposable, tempShape) {
    // Clean previous shape
    if (tempShape) {
      layersComposable.drawnItems.value.removeLayer(tempShape);
    }

    // For now, create temporary circle to visualize height
    const radius = Math.abs(center.lat - heightPoint.lat) * 111320; // Distance in meters

    const newTempShape = L.circle(center, {
      radius: radius,
      color: "#000000",
      weight: 2,
      fillColor: "#cccccc",
      fillOpacity: 0.5,
    });

    layersComposable.drawnItems.value.addLayer(newTempShape);
    return newTempShape;
  }

  // Update temporary oval - width
  function updateTempOvalWidth(center, heightPoint, widthPoint, map, layersComposable, tempShape) {
    // Clean previous shape
    if (tempShape) {
      layersComposable.drawnItems.value.removeLayer(tempShape);
    }

    // Calculate radii
    const heightRadius = Math.abs(center.lat - heightPoint.lat) * 111320;
    const widthRadius =
      Math.abs(center.lng - widthPoint.lng) *
      111320 *
      Math.cos((center.lat * Math.PI) / 180);

    // Create ellipse approximation with polygon
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

  // Convert square defined by center and size to GeoJSON feature
  function squareToFeatureFromCenter(center, sizePoint, map) {
    const distance = map.distance(center, sizePoint);
    const halfSide = distance / Math.sqrt(2);

    // Convert to degrees
    const latOffset = halfSide / 111320;
    const lngOffset =
      halfSide / (111320 * Math.cos((center.lat * Math.PI) / 180));

    // Create square coordinates (clockwise)
    const geometry = {
      type: "Polygon",
      coordinates: [
        [
          [center.lng - lngOffset, center.lat + latOffset], // Top-left corner
          [center.lng + lngOffset, center.lat + latOffset], // Top-right corner
          [center.lng + lngOffset, center.lat - latOffset], // Bottom-right corner
          [center.lng - lngOffset, center.lat - latOffset], // Bottom-left corner
          [center.lng - lngOffset, center.lat + latOffset], // Back to start
        ],
      ],
    };

    return {
      map_id: props.mapId,
      type: "square",
      geometry: geometry,
      color: "#cccccc",
      opacity: 0.5,
      z_index: 1,
    };
  }

  // Convert rectangle defined by two opposite corners to GeoJSON feature
  function rectangleToFeatureFromCorners(startCorner, endCorner) {
    const minLat = Math.min(startCorner.lat, endCorner.lat);
    const maxLat = Math.max(startCorner.lat, endCorner.lat);
    const minLng = Math.min(startCorner.lng, endCorner.lng);
    const maxLng = Math.max(startCorner.lng, endCorner.lng);

    const geometry = {
      type: "Polygon",
      coordinates: [
        [
          [minLng, maxLat], // Top-left corner
          [maxLng, maxLat], // Top-right corner
          [maxLng, minLat], // Bottom-right corner
          [minLng, minLat], // Bottom-left corner
          [minLng, maxLat], // Back to start
        ],
      ],
    };

    return {
      map_id: props.mapId,
      type: "rectangle",
      geometry: geometry,
      color: "#cccccc",
      opacity: 0.5,
      z_index: 1,
    };
  }

  // Convert circle defined by center and edge point to GeoJSON feature
  function circleToFeatureFromCenter(center, edgePoint, map) {
    const radius = map.distance(center, edgePoint);

    // Create polygon approximating the circle
    const points = [];
    const steps = 32;
    for (let i = 0; i < steps; i++) {
      const angle = (i / steps) * 2 * Math.PI;
      const lat = center.lat + (radius / 111320) * Math.sin(angle);
      const lng =
        center.lng +
        ((radius / 111320) * Math.cos(angle)) /
          Math.cos((center.lat * Math.PI) / 180);
      points.push([lng, lat]); // GeoJSON format [lng, lat]
    }
    points.push(points[0]); // Close polygon

    const geometry = {
      type: "Polygon",
      coordinates: [points],
    };

    return {
      map_id: props.mapId,
      type: "circle",
      geometry: geometry,
      color: "#cccccc",
      opacity: 0.5,
      z_index: 1,
    };
  }

  // Convert triangle defined by center and size to GeoJSON feature
  function triangleToFeatureFromCenter(center, sizePoint, map) {
    const distance = map.distance(center, sizePoint);

    const points = [];
    for (let i = 0; i < 3; i++) {
      const angle = ((i * 120 + 90) * Math.PI) / 180; // Triangle pointing up
      const lat = center.lat + (distance / 111320) * Math.sin(angle);
      const lng =
        center.lng +
        ((distance / 111320) * Math.cos(angle)) /
          Math.cos((center.lat * Math.PI) / 180);
      points.push([lng, lat]); // GeoJSON format [lng, lat]
    }
    points.push(points[0]); // Close polygon

    const geometry = {
      type: "Polygon",
      coordinates: [points],
    };

    return {
      map_id: props.mapId,
      type: "triangle",
      geometry: geometry,
      color: "#cccccc",
      opacity: 0.5,
      z_index: 1,
    };
  }

  // Convert oval defined by center, height and width to GeoJSON feature
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
      points.push([lng, lat]); // GeoJSON format [lng, lat]
    }
    points.push(points[0]); // Close polygon

    const geometry = {
      type: "Polygon",
      coordinates: [points],
    };

    return {
      map_id: props.mapId,
      type: "oval",
      geometry: geometry,
      color: "#cccccc",
      opacity: 0.5,
      z_index: 1,
    };
  }

  // ===== SELECTION AND VISUAL MANAGEMENT =====

  // Update visual appearance of selected shapes
  function updateFeatureSelectionVisual(map, layerManager, selectedFeatures) {
    if (!map || !layerManager) return;
    
    layerManager.layers.forEach((layer, featureId) => {
      const fid = String(featureId);
      
      if (selectedFeatures.has(fid)) {
        // Style for selected shapes - RED BORDER
        if (layer instanceof L.CircleMarker) {
          layer.setStyle({
            color: "#ff6b6b",
            weight: 3,
            fillColor: "#ff6b6b",
            fillOpacity: 0.8,
          });
        } else if (layer instanceof L.Polygon || layer instanceof L.Rectangle) {
          layer.setStyle({
            color: "#ff6b6b",
            weight: 3,
            fillColor: layer.options.fillColor,
            fillOpacity: layer.options.fillOpacity,
          });
        } else if (layer instanceof L.Polyline) {
          layer.setStyle({
            color: "#ff6b6b",
            weight: 4,
          });
        }
      } else {
        // Reset to original style using stored __atlas_originalStyle
        if (layer.__atlas_originalStyle && layer.setStyle) {
          layer.setStyle(layer.__atlas_originalStyle);
        } else if (layer.setStyle) {
          // Fallback to default styles
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

  // Update feature position in database
  async function updateFeaturePosition(feature, deltaLat, deltaLng) {
    try {
      // Create updated coordinates copy
      const updatedGeometry = updateGeometryCoordinates(feature.geometry, deltaLat, deltaLng);

      // Prepare data for PUT request
      const updateData = {
        geometry: updatedGeometry,
      };

      // Send PUT request
      const response = await fetch(
        `http://localhost:8000/maps/features/${feature.id}`,
        {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify(updateData),
        }
      );

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const updatedFeature = await response.json();

      // Update feature in local list
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

  // Delete selected features
  async function deleteSelectedFeatures(selectedFeatures, featureLayerManager, map, emit) {
    if (selectedFeatures.size === 0) return;

    const featuresToDelete = Array.from(selectedFeatures);

    // Remove from map first
    for (const featureId of featuresToDelete) {
      const layer = featureLayerManager.layers.get(String(featureId));
      if (layer) {
        // Remove circles from collection
        if (layer instanceof L.CircleMarker) {
          // Will be handled by layers composable
        }
        map.removeLayer(layer);
        featureLayerManager.layers.delete(String(featureId));
      }
    }

    // Delete from database
    for (const featureId of featuresToDelete) {
      try {
        const response = await fetch(
          `http://localhost:8000/maps/features/${featureId}`,
          {
            method: "DELETE",
          }
        );

        if (!response.ok) {
          console.error(`Failed to delete feature ${featureId}`);
        }
      } catch (error) {
        console.error(`Error deleting feature ${featureId}:`, error);
      }
    }

    // Update features list in parent
    const remainingFeatures = props.features.filter(
      (f) => !featuresToDelete.includes(f.id)
    );
    emit("features-loaded", remainingFeatures);

    // Clear selection
    selectedFeatures.clear();
    updateFeatureSelectionVisual(map, featureLayerManager, selectedFeatures);
  }

  // Delete single feature
  async function deleteFeature(featureId, featureLayerManager, map, emit) {
    const fid = String(featureId);
    
    // Remove from map
    const layer = featureLayerManager.layers.get(fid);
    if (layer) {
      // Remove circles from collection
      if (layer instanceof L.CircleMarker) {
        // Will be handled by layers composable
      }
      map.removeLayer(layer);
      featureLayerManager.layers.delete(fid);
    }

    // Only delete from database if it's not a temporary feature
    if (!fid.startsWith('temp_')) {
      try {
        const response = await fetch(
          `http://localhost:8000/maps/features/${featureId}`,
          {
            method: "DELETE",
          }
        );

        if (!response.ok) {
          console.error(`Failed to delete feature ${featureId}`);
        }
      } catch (error) {
        console.error(`Error deleting feature ${featureId}:`, error);
      }

      // Update features list in parent (only for real features)
      const remainingFeatures = props.features.filter((f) => f.id !== featureId);
      emit("features-loaded", remainingFeatures);
    }
    // For temporary features, no need to update parent features list
  }

  // Update geometry coordinates
  function updateGeometryCoordinates(geometry, deltaLat, deltaLng) {
    if (!geometry || !geometry.coordinates) {
      return geometry;
    }

    const updatedGeometry = { ...geometry };

    switch (geometry.type) {
      case "Point":
        // Point: [lng, lat]
        updatedGeometry.coordinates = [
          geometry.coordinates[0] + deltaLng,
          geometry.coordinates[1] + deltaLat,
        ];
        break;

      case "LineString":
        // LineString: [[lng, lat], [lng, lat], ...]
        updatedGeometry.coordinates = geometry.coordinates.map((coord) => [
          coord[0] + deltaLng,
          coord[1] + deltaLat,
        ]);
        break;

      case "Polygon":
        // Polygon: [[[lng, lat], [lng, lat], ...]]
        updatedGeometry.coordinates = geometry.coordinates.map((ring) =>
          ring.map((coord) => [coord[0] + deltaLng, coord[1] + deltaLat])
        );
        break;

      default:
        return geometry;
    }

    return updatedGeometry;
  }

  // Toggle delete mode
  function toggleDeleteMode() {
    // Emit event to change mode
    if (props.activeEditMode === "DELETE_FEATURE") {
      emit("mode-change", null); // Return to default mode
    } else {
      emit("mode-change", "DELETE_FEATURE"); // Activate delete mode
    }
  }

  return {
    // State
    isDeleteMode,

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
    
    // Utility functions
    smoothFreeLinePoints,
  };
}

// Helper function for radius calculation
function getRadiusForZoom(currentZoom) {
  const BASE_ZOOM = 5;
  const BASE_RADIUS = 3;
  const ZOOM_FACTOR = 1.5;
  const zoomDiff = currentZoom - BASE_ZOOM;
  return Math.max(BASE_RADIUS, BASE_RADIUS * Math.pow(ZOOM_FACTOR, zoomDiff));
}
