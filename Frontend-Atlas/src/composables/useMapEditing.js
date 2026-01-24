import { ref } from 'vue';
import L from 'leaflet';
import { smoothFreeLinePoints } from '../utils/mapUtils.js';

// Composable for map editing functionality (creating shapes, managing selection, etc.)
export function useMapEditing(props, emit) {
  const isDeleteMode = ref(false);

  // ===== SHAPE CREATION FUNCTIONS =====

  // Create a square with center and size (like a circle)
  function createSquare(center, sizePoint, map, emit) {
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

    // Add to drawn items
    if (window.drawnItems) {
      window.drawnItems.addLayer(square);
    }

    // Create feature
    const feature = squareToFeatureFromCenter(center, sizePoint);

    // Generate temporary ID for local feature
    const tempFeature = {
      ...feature,
      id: `temp_${Date.now()}_${Math.random()}`,
      _isTemporary: true,
    };

    // Add to features list locally (for display)
    if (!props.features.some((f) => f.id === tempFeature.id)) {
      const updatedFeatures = [...props.features, tempFeature];
      emit("features-loaded", updatedFeatures);
    }

    // Make shape clickable immediately
    const layerKey = tempFeature.id;
    // This will be handled by the layers composable

    // Try to save (but don't block if it fails)
    saveFeature(tempFeature).catch(() => {
      // API not available
    });
  }

  // Create a rectangle between two opposite corners
  function createRectangle(startCorner, endCorner, map, emit) {
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

    // Add to drawn items
    if (window.drawnItems) {
      window.drawnItems.addLayer(rectangle);
    }

    const feature = rectangleToFeatureFromCorners(startCorner, endCorner);

    // Generate temporary ID for local feature
    const tempFeature = {
      ...feature,
      id: `temp_${Date.now()}_${Math.random()}`,
      _isTemporary: true,
    };

    // Add to features list locally (for display)
    if (!props.features.some((f) => f.id === tempFeature.id)) {
      const updatedFeatures = [...props.features, tempFeature];
      emit("features-loaded", updatedFeatures);
    }

    // Make shape clickable immediately
    const layerKey = tempFeature.id;

    // Try to save (but don't block if it fails)
    saveFeature(tempFeature).catch(() => {
      // API not available
    });
  }

  // Create a circle with center and edge point
  function createCircle(center, edgePoint, map, emit) {
    const radius = center.distanceTo(edgePoint);

    const circle = L.circle(center, {
      radius: radius,
      color: "#000000",
      weight: 2,
      fillColor: "#cccccc",
      fillOpacity: 0.5,
    });

    // Add to drawn items
    if (window.drawnItems) {
      window.drawnItems.addLayer(circle);
    }

    const feature = circleToFeatureFromCenter(center, edgePoint);

    // Generate temporary ID for local feature
    const tempFeature = {
      ...feature,
      id: `temp_${Date.now()}_${Math.random()}`,
      _isTemporary: true,
    };

    // Add to features list locally (for display)
    if (!props.features.some((f) => f.id === tempFeature.id)) {
      const updatedFeatures = [...props.features, tempFeature];
      emit("features-loaded", updatedFeatures);
    }

    // Make shape clickable immediately
    const layerKey = tempFeature.id;

    // Try to save (but don't block if it fails)
    saveFeature(tempFeature).catch(() => {
      // API not available
    });
  }

  // Create a triangle with center and size
  function createTriangle(center, sizePoint, map, emit) {
    const distance = center.distanceTo(sizePoint);

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

    // Add to drawn items
    if (window.drawnItems) {
      window.drawnItems.addLayer(triangle);
    }

    const feature = triangleToFeatureFromCenter(center, sizePoint);

    // Generate temporary ID for local feature
    const tempFeature = {
      ...feature,
      id: `temp_${Date.now()}_${Math.random()}`,
      _isTemporary: true,
    };

    // Add to features list locally (for display)
    if (!props.features.some((f) => f.id === tempFeature.id)) {
      const updatedFeatures = [...props.features, tempFeature];
      emit("features-loaded", updatedFeatures);
    }

    // Make shape clickable immediately
    const layerKey = tempFeature.id;

    // Try to save (but don't block if it fails)
    saveFeature(tempFeature).catch(() => {
      // API not available
    });
  }

  // Create an oval with center, height and width
  function createOval(center, heightPoint, widthPoint, map, emit) {
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

    // Add to drawn items
    if (window.drawnItems) {
      window.drawnItems.addLayer(oval);
    }

    const feature = ovalToFeatureFromCenter(center, heightPoint, widthPoint);

    // Generate temporary ID for local feature
    const tempFeature = {
      ...feature,
      id: `temp_${Date.now()}_${Math.random()}`,
      _isTemporary: true,
    };

    // Add to features list locally (for display)
    if (!props.features.some((f) => f.id === tempFeature.id)) {
      const updatedFeatures = [...props.features, tempFeature];
      emit("features-loaded", updatedFeatures);
    }

    // Make shape clickable immediately
    const layerKey = tempFeature.id;

    // Try to save (but don't block if it fails)
    saveFeature(tempFeature).catch(() => {
      // API not available
    });
  }

  // Create a point at position
  function createPointAt(latlng, map, emit) {
    const currentZoom = map.getZoom();
    const radius = (3 * Math.pow(1.5, currentZoom - 5)); // Adaptive size

    // Use circleMarker with adaptive size
    const circle = L.circleMarker(latlng, {
      radius: radius, // Size adapts to zoom
      fillColor: "#000000",
      color: "#333333",
      weight: 1,
      opacity: 0.8,
      fillOpacity: 0.8,
      draggable: true,
    });

    // Add to drawn items
    if (window.drawnItems) {
      window.drawnItems.addLayer(circle);
    }

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

    // Add to features list locally (for display)
    if (!props.features.some((f) => f.id === tempFeature.id)) {
      const updatedFeatures = [...props.features, tempFeature];
      emit("features-loaded", updatedFeatures);
    }

    // Make shape clickable immediately
    const layerKey = tempFeature.id;

    // Try to save (but don't block if it fails)
    saveFeature(tempFeature).catch(() => {
      // API not available
    });
  }

  // Create a line between two points
  function createLine(startLatLng, endLatLng, map, emit) {
    const line = L.polyline([startLatLng, endLatLng], {
      color: "#000000",
      weight: 2,
      opacity: 1.0,
    });

    // Add to drawn items
    if (window.drawnItems) {
      window.drawnItems.addLayer(line);
    }

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

    // Add to features list locally (for display)
    if (!props.features.some((f) => f.id === tempFeature.id)) {
      const updatedFeatures = [...props.features, tempFeature];
      emit("features-loaded", updatedFeatures);
    }

    // Make shape clickable immediately
    const layerKey = tempFeature.id;

    // Try to save (but don't block if it fails)
    saveFeature(tempFeature).catch(() => {
      // API not available
    });
  }

  // Create a polygon
  function createPolygon(points, map, emit) {
    const polygon = L.polygon(points, {
      color: "#000000",
      weight: 2,
      fillColor: "#cccccc",
      fillOpacity: 0.5,
    });

    // Add to drawn items
    if (window.drawnItems) {
      window.drawnItems.addLayer(polygon);
    }

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

    // Add to features list locally (for display)
    if (!props.features.some((f) => f.id === tempFeature.id)) {
      const updatedFeatures = [...props.features, tempFeature];
      emit("features-loaded", updatedFeatures);
    }

    // Make shape clickable immediately
    const layerKey = tempFeature.id;

    // Try to save (but don't block if it fails)
    saveFeature(tempFeature).catch(() => {
      // API not available
    });
  }

  // Finalize free line
  function finishFreeLine(map, emit) {
    if (!window.freeLinePoints || window.freeLinePoints.length < 2) return;

    // Apply final smoothing
    const smoothedPoints = smoothFreeLinePoints(window.freeLinePoints);

    // Remove temporary line
    if (window.tempFreeLine) {
      if (window.drawnItems) {
        window.drawnItems.removeLayer(window.tempFreeLine);
      }
      window.tempFreeLine = null;
    }

    // Create final smoothed line
    const freeLine = L.polyline(smoothedPoints, {
      color: "#000000",
      weight: 2,
      opacity: 1.0,
    });

    // Add to drawn items
    if (window.drawnItems) {
      window.drawnItems.addLayer(freeLine);
    }

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
    // This will be handled by layers composable

    saveFeature(feature);
  }

  // ===== TEMPORARY SHAPE UPDATE FUNCTIONS =====

  // Update temporary square from center and size (like circle)
  function updateTempSquareFromCenter(center, sizePoint, map) {
    // Clean previous shape
    if (window.tempShape) {
      if (window.drawnItems) {
        window.drawnItems.removeLayer(window.tempShape);
      }
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

    window.tempShape = L.rectangle(bounds, {
      color: "#000000",
      weight: 2,
      fillColor: "#cccccc",
      fillOpacity: 0.5,
    });

    if (window.drawnItems) {
      window.drawnItems.addLayer(window.tempShape);
    }
  }

  // Update temporary rectangle from two opposite corners
  function updateTempRectangleFromCorners(startCorner, endCorner, map) {
    // Clean previous shape
    if (window.tempShape) {
      if (window.drawnItems) {
        window.drawnItems.removeLayer(window.tempShape);
      }
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

    window.tempShape = L.rectangle(bounds, {
      color: "#000000",
      weight: 2,
      fillColor: "#cccccc",
      fillOpacity: 0.5,
    });

    if (window.drawnItems) {
      window.drawnItems.addLayer(window.tempShape);
    }
  }

  // Update temporary circle from center and edge point
  function updateTempCircleFromCenter(center, edgePoint, map) {
    // Clean previous shape
    if (window.tempShape) {
      if (window.drawnItems) {
        window.drawnItems.removeLayer(window.tempShape);
      }
    }

    // Calculate radius in meters
    const radius = center.distanceTo(edgePoint);

    window.tempShape = L.circle(center, {
      radius: radius,
      color: "#000000",
      weight: 2,
      fillColor: "#cccccc",
      fillOpacity: 0.5,
    });

    if (window.drawnItems) {
      window.drawnItems.addLayer(window.tempShape);
    }
  }

  // Update temporary triangle from center and size
  function updateTempTriangleFromCenter(center, sizePoint, map) {
    // Clean previous shape
    if (window.tempShape) {
      if (window.drawnItems) {
        window.drawnItems.removeLayer(window.tempShape);
      }
    }

    // Calculate distance from center
    const distance = center.distanceTo(sizePoint);

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

    window.tempShape = L.polygon(points, {
      color: "#000000",
      weight: 2,
      fillColor: "#cccccc",
      fillOpacity: 0.5,
    });

    if (window.drawnItems) {
      window.drawnItems.addLayer(window.tempShape);
    }
  }

  // Update temporary oval - height
  function updateTempOvalHeight(center, heightPoint, map) {
    // Clean previous shape
    if (window.tempShape) {
      if (window.drawnItems) {
        window.drawnItems.removeLayer(window.tempShape);
      }
    }

    // For now, create temporary circle to visualize height
    const radius = Math.abs(center.lat - heightPoint.lat) * 111320; // Distance in meters

    window.tempShape = L.circle(center, {
      radius: radius,
      color: "#000000",
      weight: 2,
      fillColor: "#cccccc",
      fillOpacity: 0.5,
    });

    if (window.drawnItems) {
      window.drawnItems.addLayer(window.tempShape);
    }
  }

  // Update temporary oval - width
  function updateTempOvalWidth(center, heightPoint, widthPoint, map) {
    // Clean previous shape
    if (window.tempShape) {
      if (window.drawnItems) {
        window.drawnItems.removeLayer(window.tempShape);
      }
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

    window.tempShape = L.polygon(points, {
      color: "#000000",
      weight: 2,
      fillColor: "#cccccc",
      fillOpacity: 0.5,
    });

    if (window.drawnItems) {
      window.drawnItems.addLayer(window.tempShape);
    }
  }

  // ===== FEATURE CONVERSION FUNCTIONS =====

  // Convert square defined by center and size to GeoJSON feature
  function squareToFeatureFromCenter(center, sizePoint) {
    const distance = center.distanceTo(sizePoint);
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
  function circleToFeatureFromCenter(center, edgePoint) {
    const radius = center.distanceTo(edgePoint);

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
      points.push([lng, lat]); // GeoJSON order = [lng, lat]
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
  function triangleToFeatureFromCenter(center, sizePoint) {
    const distance = center.distanceTo(sizePoint);

    const points = [];
    for (let i = 0; i < 3; i++) {
      const angle = ((i * 120 + 90) * Math.PI) / 180; // Triangle pointing up
      const lat = center.lat + (distance / 111320) * Math.sin(angle);
      const lng =
        center.lng +
        ((distance / 111320) * Math.cos(angle)) /
          Math.cos((center.lat * Math.PI) / 180);
      points.push([lng, lat]); // GeoJSON order = [lng, lat]
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
      points.push([lng, lat]); // GeoJSON order = [lng, lat]
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
    
    // Reset all layers to normal style
    layerManager.layers.forEach((layer, featureId) => {
      if (layer.setStyle) {
        // Get original color from feature data
        const feature = props.features.find(f => f.id === featureId);
        const originalColor = feature?.color || '#000000';
        
        layer.setStyle({
          color: originalColor,
          weight: 2,
        });
      }
    });
    
    // Apply red border to selected features
    selectedFeatures.forEach((featureId) => {
      const layer = layerManager.layers.get(featureId);
      if (layer && layer.setStyle) {
        layer.setStyle({
          color: '#FF0000',
          weight: 3,
        });
      }
    });
  }

  // ===== CRUD OPERATIONS =====

  // Save feature automatically
  async function saveFeature(featureData) {
    try {
      // Restructure data for backend API
      const { id, _isTemporary, map_id, geometry, type, color, stroke_width, opacity, z_index, start_date, end_date, ...rest } = featureData;
      
      const payload = {
        map_id: map_id,
        name: rest.name || null,
        type: type,  // "line", "square", "circle", etc.
        geometry: geometry,  // GeoJSON geometry object
        color: color || "#000000",
        stroke_width: stroke_width || 2,
        opacity: opacity !== undefined ? opacity : 1.0,
        z_index: z_index || 1,
        tags: rest.tags || {},
        start_date: start_date || null,
        end_date: end_date || null,
        precision: rest.precision || null,
        source: rest.source || null,
      };

      const response = await fetch("http://localhost:8000/maps/features", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const errorText = await response.text();
        console.error("Backend error:", errorText);
        throw new Error(`Failed to save feature: ${errorText}`);
      }

      const savedFeature = await response.json();

      // Add saved feature to current features list immediately
      // so it's visible even in edit mode
      const updatedFeatures = [...props.features, savedFeature];

      // Update display according to feature type
      // This will be handled by the layers composable

      // Notify parent to update complete list
      emit("features-loaded", updatedFeatures);

      // Make new shape clickable immediately if in edit mode
      if (props.editMode) {
        // This will be handled by the layers composable
      }
    } catch (error) {
      console.error("Error saving feature automatically:", error);
    }
  }

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
      console.error("❌ Error updating feature position:", error);
      // In case of error, we could reload features from server
      // or display error message to user
    }
  }

  // Delete selected features
  async function deleteSelectedFeatures(selectedFeatures, featureLayerManager, map, emit) {
    if (selectedFeatures.size === 0) return;

    const featuresToDelete = Array.from(selectedFeatures);

    // Remove from map first
    for (const featureId of featuresToDelete) {
      const layer = featureLayerManager.layers.get(featureId);
      if (layer) {
        // Remove circles from collection
        if (layer instanceof L.CircleMarker) {
          // This will be handled by layers composable
        }
        map.removeLayer(layer);
        featureLayerManager.layers.delete(featureId);
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
          // Failed to delete feature
        }
      } catch (error) {
        // Error deleting feature
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
    saveFeature,
    updateFeaturePosition,
    deleteSelectedFeatures,
    updateGeometryCoordinates,

    // Mode management
    toggleDeleteMode,
    
    // Utility functions
    smoothFreeLinePoints,
  };
}