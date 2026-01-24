// Configuration constants for the map component
export const MAP_CONFIG = {
  // Smoothing configuration
  SMOOTHING_MIN_DISTANCE: 3, // Distance minimale entre points en pixels

  // Zoom-adaptive circles configuration
  BASE_ZOOM: 5, // Zoom de départ où le rayon est de 3px
  BASE_RADIUS: 3, // Rayon de base
  ZOOM_FACTOR: 1.5, // Facteur de croissance (1.5 = croissance modérée)

  // Available years for timeline
  AVAILABLE_YEARS: [
    1400, 1500, 1530, 1600, 1650, 1700, 1715, 1783, 1800, 1815, 1880, 1900, 1914,
    1920, 1930, 1938, 1945, 1960, 1994, 2000, 2010,
  ],

  // Default styles
  DEFAULT_STYLES: {
    borderColor: "#000000",
    fillColor: "#cccccc",
    opacity: 0.5,
    strokeWidth: 2,
  },

  // Selection styles
  SELECTION_STYLES: {
    borderColor: "#ff6b6b",
    weight: 3,
  },

  // Drawing tolerance
  DRAWING_TOLERANCE: 5, // Minimum distance in pixels to consider a valid drawing
  DRAG_THRESHOLD: 5, // Minimum movement in pixels to start dragging
};