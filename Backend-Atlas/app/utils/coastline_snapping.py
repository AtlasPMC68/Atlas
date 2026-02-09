import json
import logging
import math
from typing import List, Dict, Any, Tuple

from shapely.geometry import LineString, MultiLineString, shape, mapping, Point, Polygon, MultiPolygon
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points


logger = logging.getLogger(__name__)

R_EARTH = 6378137.0  # Earth radius in meters for WebMercator


def _lonlat_to_webmercator(lon: float, lat: float) -> Tuple[float, float]:
    """Convert WGS84 lon/lat to WebMercator (EPSG:3857)."""
    x = math.radians(lon) * R_EARTH
    lat = max(min(lat, 89.9), -89.9)
    y = math.log(math.tan(math.pi / 4.0 + math.radians(lat) / 2.0)) * R_EARTH
    return x, y


def _webmercator_to_lonlat(x: float, y: float) -> Tuple[float, float]:
    """Convert WebMercator (EPSG:3857) to WGS84 lon/lat."""
    lon = math.degrees(x / R_EARTH)
    lat = math.degrees(2.0 * math.atan(math.exp(y / R_EARTH)) - math.pi / 2.0)
    return lon, lat


def load_reference_coastline(geojson_path: str) -> MultiLineString:
    """Load reference coastline from GeoJSON file.
    
    Args:
        geojson_path: Path to Natural Earth coastline GeoJSON
        
    Returns:
        MultiLineString containing all reference coastline segments
    """
    try:
        with open(geojson_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        coastline_segments = []
        for feature in data.get('features', []):
            geom = shape(feature['geometry'])
            if isinstance(geom, LineString):
                coastline_segments.append(geom)
            elif isinstance(geom, MultiLineString):
                coastline_segments.extend(list(geom.geoms))
        
        reference_coastline = MultiLineString(coastline_segments)
        logger.info(f"Loaded reference coastline with {len(coastline_segments)} segments")
        return reference_coastline
        
    except Exception as e:
        logger.error(f"Failed to load reference coastline: {e}", exc_info=True)
        raise


def snap_point_to_coastline(
    point: Tuple[float, float],
    reference_coastline: MultiLineString,
    max_snap_distance_km: float = 10.0
) -> Tuple[float, float]:
    """Snap a single point to the nearest reference coastline if close enough.
    
    Args:
        point: (lon, lat) coordinate
        reference_coastline: Reference coastline to snap to
        max_snap_distance_km: Maximum distance in km to snap (beyond this, keep original)
        
    Returns:
        Snapped (lon, lat) coordinate, or original if too far
    """
    point_geom = Point(point)
    
    # Find nearest point on reference coastline
    _, nearest_on_ref = nearest_points(point_geom, reference_coastline)
    
    # Convert to WebMercator for accurate distance calculation
    point_merc = _lonlat_to_webmercator(point[0], point[1])
    nearest_merc = _lonlat_to_webmercator(nearest_on_ref.x, nearest_on_ref.y)
    
    # Calculate Euclidean distance in meters
    distance_m = math.sqrt(
        (point_merc[0] - nearest_merc[0])**2 + 
        (point_merc[1] - nearest_merc[1])**2
    )
    distance_km = distance_m / 1000.0
    
    if distance_km <= max_snap_distance_km:
        logger.debug(f"Snapped point (distance: {distance_km:.2f} km)")
        return (nearest_on_ref.x, nearest_on_ref.y)
    else:
        logger.debug(f"Point too far from reference ({distance_km:.2f} km), keeping original")
        return point


def _is_point_actually_on_coastline(
    coord: Tuple[float, float],
    reference_coastline: MultiLineString,
    max_distance_km: float
) -> bool:
    """Check if a point is actually ON or very near the reference coastline.
    
    This identifies coastline points vs inland border points.
    Only points already near the coastline should be snapped.
    
    Args:
        coord: (lon, lat) coordinate to check
        reference_coastline: Reference coastline geometry
        max_distance_km: Maximum distance to consider "on coastline"
        
    Returns:
        True if point is on coastline, False if inland border
    """
    point_geom = Point(coord)
    _, nearest_on_ref = nearest_points(point_geom, reference_coastline)
    
    # Calculate distance in WebMercator
    point_merc = _lonlat_to_webmercator(coord[0], coord[1])
    nearest_merc = _lonlat_to_webmercator(nearest_on_ref.x, nearest_on_ref.y)
    
    distance_m = math.sqrt(
        (point_merc[0] - nearest_merc[0])**2 + 
        (point_merc[1] - nearest_merc[1])**2
    )
    distance_km = distance_m / 1000.0
    
    return distance_km <= max_distance_km


def _remove_duplicate_consecutive_points(coords: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Remove duplicate consecutive points that can cause invalid geometries.
    
    Args:
        coords: List of (lon, lat) coordinates
        
    Returns:
        Cleaned list without duplicate consecutive points
    """
    if not coords:
        return coords
    
    cleaned = [coords[0]]
    for coord in coords[1:]:
        # Only add if different from previous point (with small tolerance)
        prev = cleaned[-1]
        if abs(coord[0] - prev[0]) > 1e-9 or abs(coord[1] - prev[1]) > 1e-9:
            cleaned.append(coord)
    
    return cleaned


def _snap_linestring_coordinates_selective(
    coords: List[Tuple[float, float]],
    reference_coastline: MultiLineString,
    sift_control_points: List[Point],
    max_snap_distance_km: float,
    sift_proximity_km: float
) -> Tuple[List[Tuple[float, float]], int, int]:
    """Selectively snap only coastline points, preserving inland borders.
    
    Strategy:
    1. Check if point is near a SIFT control point (indicates coastline region)
    2. Check if point is actually near the reference coastline (not inland border)
    3. Only snap if BOTH conditions are true
    
    This preserves inland borders (Quebec-Ontario) while snapping coastal borders (Quebec-Atlantic).
    
    Args:
        coords: List of (lon, lat) coordinates
        reference_coastline: Reference coastline geometry
        sift_control_points: SIFT points marking coastline regions
        max_snap_distance_km: Maximum distance to snap
        sift_proximity_km: Distance to SIFT point to consider coastline region
        
    Returns:
        Tuple of (snapped_coords, num_snapped, num_coastline_points)
    """
    snapped_coords = []
    num_snapped = 0
    num_coastline_points = 0
    
    for coord in coords:
        # First check: Is this point in a coastline region (near SIFT marker)?
        is_near_sift = False
        coord_merc = _lonlat_to_webmercator(coord[0], coord[1])
        
        for control_point in sift_control_points:
            control_merc = _lonlat_to_webmercator(control_point.x, control_point.y)
            
            distance_m = math.sqrt(
                (coord_merc[0] - control_merc[0])**2 + 
                (coord_merc[1] - control_merc[1])**2
            )
            distance_km = distance_m / 1000.0
            
            if distance_km <= sift_proximity_km:
                is_near_sift = True
                break
        
        # Second check: Is this point actually on the coastline (vs inland border)?
        is_on_coastline = False
        if is_near_sift:
            is_on_coastline = _is_point_actually_on_coastline(
                coord, 
                reference_coastline, 
                max_snap_distance_km * 2  # More lenient for detection than snapping
            )
        
        # Only snap if it's a coastline point in a coastline region
        if is_near_sift and is_on_coastline:
            num_coastline_points += 1
            snapped_coord = snap_point_to_coastline(
                coord,
                reference_coastline,
                max_snap_distance_km
            )
            snapped_coords.append(snapped_coord)
            
            if snapped_coord != coord:
                num_snapped += 1
        else:
            # Keep original for inland borders
            snapped_coords.append(coord)
    
    # Clean up duplicate consecutive points that can cause invalid geometries
    snapped_coords = _remove_duplicate_consecutive_points(snapped_coords)
    
    return snapped_coords, num_snapped, num_coastline_points


def refine_coastline_features(
    georeferenced_collections: List[Dict[str, Any]],
    reference_geojson_path: str,
    sift_control_points: List[Tuple[float, float]] = None,
    max_snap_distance_km: float = 10.0,
    sift_proximity_km: float = 25.0
) -> List[Dict[str, Any]]:
    """Refine georeferenced coastlines by snapping to reference data.
    
    Smart selective snapping: Only snaps points that are BOTH:
    1. Near a SIFT control point (coastline region marker)
    2. Actually close to the reference coastline (not inland borders)
    
    This preserves inland borders (e.g., Quebec-Ontario border) while fixing 
    coastal borders (e.g., Quebec-Atlantic coast).
    
    Args:
        georeferenced_collections: Output from georeference_features_with_sift_points
        reference_geojson_path: Path to ne_coastline.geojson
        sift_control_points: List of (lon, lat) SIFT control points placed on coastlines
        max_snap_distance_km: Maximum distance to snap points to reference (default 10 km)
        sift_proximity_km: Distance to SIFT point to consider coastline region (default 25 km)
        
    Returns:
        Refined FeatureCollections with selectively snapped coastlines
    """
    try:
        # Load reference coastline
        reference_coastline = load_reference_coastline(reference_geojson_path)
        
        # If no control points provided, don't snap anything
        if not sift_control_points:
            logger.info("No SIFT control points provided, skipping coastline snapping")
            return georeferenced_collections
        
        # Create Points from control points for distance checking
        control_point_geoms = [Point(lon, lat) for lon, lat in sift_control_points]
        logger.info(f"Using {len(control_point_geoms)} SIFT control points to identify coastlines")
        
        refined_collections = []
        total_snapped = 0
        total_points = 0
        features_snapped = 0
        features_skipped = 0
        
        for fc in georeferenced_collections:
            if fc.get("type") != "FeatureCollection":
                continue
                
            refined_features = []
            
            for feature in fc.get("features", []):
                try:
                    geom = shape(feature.get("geometry"))
                    props = feature.get("properties", {})
                    
                    # Only process polygon/line geometries
                    if geom.geom_type not in ['Polygon', 'MultiPolygon', 'LineString']:
                        refined_features.append(feature)
                        features_skipped += 1
                        continue
                    
                    # Handle different geometry types with SELECTIVE snapping
                    # (only snap points that are near SIFT markers AND near reference coastline)
                    points_snapped = 0
                    coastline_points = 0
                    
                    if geom.geom_type == 'LineString':
                        coords = list(geom.coords)
                        snapped_coords, points_snapped, coastline_points = _snap_linestring_coordinates_selective(
                            coords, reference_coastline, control_point_geoms,
                            max_snap_distance_km, sift_proximity_km
                        )
                        total_points += len(coords)
                        total_snapped += points_snapped
                        refined_geom = LineString(snapped_coords)
                        
                    elif geom.geom_type == 'Polygon':
                        # Selectively snap exterior ring (preserves inland borders!)
                        exterior_coords = list(geom.exterior.coords)
                        snapped_exterior, points_snapped, coastline_points = _snap_linestring_coordinates_selective(
                            exterior_coords, reference_coastline, control_point_geoms,
                            max_snap_distance_km, sift_proximity_km
                        )
                        total_points += len(exterior_coords)
                        total_snapped += points_snapped
                        
                        # Preserve interior rings (holes) without snapping
                        interiors = [list(interior.coords) for interior in geom.interiors]
                        refined_geom = Polygon(snapped_exterior, interiors)
                        
                    elif geom.geom_type == 'MultiPolygon':
                        # Process all polygons in MultiPolygon
                        snapped_polygons = []
                        total_snapped_multi = 0
                        total_coastline_multi = 0
                        
                        for polygon in geom.geoms:
                            exterior_coords = list(polygon.exterior.coords)
                            snapped_exterior, pts_snapped, pts_coastline = _snap_linestring_coordinates_selective(
                                exterior_coords, reference_coastline, control_point_geoms,
                                max_snap_distance_km, sift_proximity_km
                            )
                            total_points += len(exterior_coords)
                            total_snapped_multi += pts_snapped
                            total_coastline_multi += pts_coastline
                            
                            # Preserve interior rings
                            interiors = [list(interior.coords) for interior in polygon.interiors]
                            snapped_polygons.append(Polygon(snapped_exterior, interiors))
                        
                        total_snapped += total_snapped_multi
                        points_snapped = total_snapped_multi
                        coastline_points = total_coastline_multi
                        refined_geom = MultiPolygon(snapped_polygons)
                    
                    # Only save if we actually modified something
                    if points_snapped > 0:
                        # Validate and repair geometry if needed
                        if not refined_geom.is_valid:
                            logger.debug(f"Geometry invalid after snapping, attempting repair...")
                            try:
                                # buffer(0) is a common trick to fix invalid geometries
                                refined_geom = refined_geom.buffer(0)
                                
                                if not refined_geom.is_valid:
                                    logger.warning(
                                        f"Could not repair invalid geometry for {geom.geom_type}, "
                                        f"keeping original (snapped {points_snapped} points)"
                                    )
                                    refined_features.append(feature)
                                    features_skipped += 1
                                    continue
                                else:
                                    logger.debug(f"Successfully repaired geometry using buffer(0)")
                            except Exception as e:
                                logger.warning(f"Geometry repair failed: {e}, keeping original")
                                refined_features.append(feature)
                                features_skipped += 1
                                continue
                        
                        # Update properties
                        refined_props = dict(props)
                        refined_props["coastline_snapped"] = True
                        refined_props["points_snapped"] = points_snapped
                        refined_props["coastline_points_detected"] = coastline_points
                        refined_props["snap_distance_km"] = max_snap_distance_km
                        
                        refined_features.append({
                            "type": "Feature",
                            "properties": refined_props,
                            "geometry": mapping(refined_geom)
                        })
                        
                        logger.info(
                            f"Snapped {geom.geom_type}: {points_snapped}/{coastline_points} coastline points adjusted"
                        )
                        features_snapped += 1
                    else:
                        # No coastal points found, keep original
                        refined_features.append(feature)
                        features_skipped += 1
                        
                except Exception as e:
                    logger.warning(f"Failed to refine feature: {e}", exc_info=True)
                    # Keep original feature on error
                    refined_features.append(feature)
                    features_skipped += 1
            
            if refined_features:
                refined_collections.append({
                    "type": "FeatureCollection",
                    "features": refined_features
                })
        
        snap_percentage = (total_snapped / total_points * 100) if total_points > 0 else 0
        logger.info(
            f"Coastline refinement complete: {features_snapped} coastline features snapped, "
            f"{features_skipped} non-coastline features preserved. "
            f"{total_snapped}/{total_points} points snapped ({snap_percentage:.1f}%)"
        )
        
        return refined_collections
        
    except Exception as e:
        logger.error(f"Error in coastline refinement: {e}", exc_info=True)
        # Return original data on error
        return georeferenced_collections
