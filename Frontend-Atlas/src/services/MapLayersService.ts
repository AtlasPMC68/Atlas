import { ref } from "vue";
import L from "leaflet";
import { getRadiusForZoom } from "../utils/map.ts";
import { toArray } from "../utils/utils";
import { getFeatureRgbColor, getMapElementType } from "../utils/featureHelpers";
import type { Feature } from "../typescript/feature";
import { FeatureLayerManager } from "./FeatureLayerManagerService.ts";
import type {
  FeatureLayer,
  MapLayersProps,
  RadiusAdjustable,
} from "../typescript/mapLayers";

function isAxisAlignedRectangle(latLngs: L.LatLngTuple[], tolerance = 1e-6) {
  if (!Array.isArray(latLngs) || latLngs.length < 4) return false;

  const normalized = latLngs.slice();
  const first = normalized[0];
  const last = normalized[normalized.length - 1];
  if (
    first &&
    last &&
    Math.abs(first[0] - last[0]) <= tolerance &&
    Math.abs(first[1] - last[1]) <= tolerance
  ) {
    normalized.pop();
  }

  if (normalized.length !== 4) return false;

  const roundToTolerance = (v: number) => Math.round(v / tolerance);
  const lats = new Set(normalized.map((p) => roundToTolerance(p[0])));
  const lngs = new Set(normalized.map((p) => roundToTolerance(p[1])));
  return lats.size === 2 && lngs.size === 2;
}

function rectangleFromLatLngs(
  latLngs: L.LatLngTuple[],
  options: L.PathOptions,
) {
  const lats = latLngs.map((p) => p[0]);
  const lngs = latLngs.map((p) => p[1]);
  const bounds = L.latLngBounds(
    [Math.min(...lats), Math.min(...lngs)],
    [Math.max(...lats), Math.max(...lngs)],
  );
  return L.rectangle(bounds, options);
}

export class MapLayersService {
  public drawnItems = ref<L.FeatureGroup | null>(null);
  public allCircles = ref<Set<RadiusAdjustable>>(new Set());
  public previousFeatureIds = ref(new Set<string>());
  public featureLayerManager: FeatureLayerManager;

  constructor(private mapLayersProps: MapLayersProps) {
    this.featureLayerManager = new FeatureLayerManager(
      mapLayersProps,
      this.allCircles,
    );
  }

  updateCircleSizes(map: L.Map) {
    const currentZoom = map.getZoom();
    const newRadius = getRadiusForZoom(currentZoom);

    this.allCircles.value.forEach((circle) => {
      circle.setRadius(newRadius);
    });
  }

  renderCities(features: Feature[], map: L.Map) {
    const safeFeatures = toArray(features) as Feature[];
    const radius = getRadiusForZoom(map.getZoom());

    for (const feature of safeFeatures) {
      if (!feature.geometry || !Array.isArray(feature.geometry.coordinates))
        continue;

      const [lng, lat] = feature.geometry.coordinates as [number, number];
      const coord = [lat, lng] as L.LatLngTuple;

      const featureProperties = feature.properties || {};
      const colorFromRgb = getFeatureRgbColor(feature);
      const color = colorFromRgb || "#000";

      const circle = L.circleMarker(coord, {
        radius,
        fillColor: color,
        color,
        weight: 1,
        opacity: feature.opacity ?? 0.8,
        fillOpacity: feature.opacity ?? 0.8,
      });

      const labelText = featureProperties.name || feature.name || "";
      if (labelText) {
        circle.bindTooltip(labelText, {
          permanent: false,
          direction: "top",
          offset: [0, -5],
        });
      }

      this.featureLayerManager.addFeatureLayer(feature.id, circle, feature);
    }
  }

  renderZones(features: Feature[], map: L.Map) {
    void map;
    const safeFeatures = toArray(features) as Feature[];

    for (const feature of safeFeatures) {
      if (!feature.geometry || !Array.isArray(feature.geometry.coordinates))
        continue;

      const featureProperties = feature.properties || {};
      const colorFromRgb = getFeatureRgbColor(feature);
      const fillColor = colorFromRgb || "#ccc";

      const targetGeometry = feature.geometry;

      let latLngs: L.LatLngTuple[] | null = null;

      if (targetGeometry.type === "Polygon") {
        const outer = targetGeometry.coordinates?.[0];
        if (Array.isArray(outer) && outer.length >= 4) {
          latLngs = outer.map(
            (pair) => [pair[1], pair[0]] as L.LatLngTuple,
          );
        }
      } else if (targetGeometry.type === "MultiPolygon") {
        const outer = targetGeometry.coordinates?.[0]?.[0];
        if (Array.isArray(outer) && outer.length >= 4) {
          latLngs = outer.map(
            (pair) => [pair[1], pair[0]] as L.LatLngTuple,
          );
        }
      } else {
        continue;
      }

      if (!latLngs) continue;

      const styleOptions = {
        color: "#333",
        weight: 1,
        fillColor,
        fillOpacity: 0.5,
        interactive: true,
      };
      const canUseRectangle = isAxisAlignedRectangle(latLngs);

      const poly = canUseRectangle
        ? rectangleFromLatLngs(latLngs, styleOptions)
        : L.polygon(latLngs, styleOptions);

      const name = featureProperties.name || feature.name;
      if (name) poly.bindPopup(name);

      this.featureLayerManager.addFeatureLayer(feature.id, poly, feature);
    }
  }

  renderArrows(features: Feature[], map: L.Map) {
    void map;
    const safeFeatures = toArray(features) as Feature[];

    for (const feature of safeFeatures) {
      if (feature.geometry.type !== "LineString")
        continue;

      const latLngs = feature.geometry.coordinates.map(
        (pair) => [pair[1], pair[0]] as L.LatLngTuple,
      );

      const featureProperties = feature.properties || {};
      const colorFromRgb = getFeatureRgbColor(feature);
      const color = colorFromRgb || "#000";

      const line = L.polyline(latLngs, {
        color,
        weight: feature.strokeWidth ?? 2,
        opacity: feature.opacity ?? 1,
      }) as FeatureLayer;

      const name = featureProperties.name || feature.name;
      if (name) line.bindPopup(name);

      const elementType = getMapElementType(feature);
      const visible = this.mapLayersProps.featureVisibility.value.get(
        String(feature.id),
      );
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

      this.featureLayerManager.addFeatureLayer(feature.id, line, feature);
    }
  }

  renderShapes(features: Feature[], map: L.Map) {
    void map;
    const safeFeatures = toArray(features) as Feature[];

    for (const feature of safeFeatures) {
      if (feature.geometry.type !== "Polygon") continue;

      const featureProperties = feature.properties || {};
      const colorFromRgb = getFeatureRgbColor(feature);
      const shapeColor = colorFromRgb || "#000000";

      const outerRing = feature.geometry.coordinates[0];
      if (
        !Array.isArray(feature.geometry.coordinates) ||
        !Array.isArray(outerRing)
      )
        continue;

      const latLngs: L.LatLngTuple[] = outerRing.map(
        (coord) => [coord[1], coord[0]] as L.LatLngTuple,
      );

      const styleOptions = {
        color: shapeColor,
        weight: 2,
        fillColor: shapeColor,
        fillOpacity: feature.opacity ?? 0.5,
        interactive: true,
      };
      const canUseRectangle = isAxisAlignedRectangle(latLngs);

      const shape = canUseRectangle
        ? rectangleFromLatLngs(latLngs, styleOptions)
        : L.polygon(latLngs, styleOptions);

      const name = featureProperties.name || feature.name;
      if (name) shape.bindPopup(name);

      this.featureLayerManager.addFeatureLayer(feature.id, shape, feature);
    }
  }

  renderAllFeatures(filteredFeatures: Feature[], map: L.Map) {
    const currentIds = new Set(filteredFeatures.map((f) => String(f.id)));
    const previousIds = this.previousFeatureIds.value;

    previousIds.forEach((oldId) => {
      if (!currentIds.has(oldId)) {
        this.featureLayerManager.removeFeature(oldId, map);
      }
    });

    const featuresByType = {
      point: filteredFeatures.filter((f) => getMapElementType(f) === "point"),
      zone: filteredFeatures.filter((f) => getMapElementType(f) === "zone"),
      polyline: filteredFeatures.filter(
        (f) => getMapElementType(f) === "polyline",
      ),
      arrow: filteredFeatures.filter((f) => getMapElementType(f) === "arrow"),
      shape: filteredFeatures.filter((f) => getMapElementType(f) === "shape"),
    };

    this.renderCities(featuresByType.point, map);
    this.renderShapes(featuresByType.shape, map);
    this.renderZones(featuresByType.zone, map);
    this.renderArrows(
      [...featuresByType.polyline, ...featuresByType.arrow],
      map,
    );

    this.previousFeatureIds.value = currentIds;
  }

  initializeBaseLayers(map: L.Map) {
    this.featureLayerManager.setMap(map);

    L.tileLayer(
      "https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png",
      {
        attribution: '&copy; <a href="https://carto.com/">CARTO</a>',
        subdomains: "abcd",
        maxZoom: 19,
      },
    ).addTo(map);

    this.drawnItems.value = new L.FeatureGroup();
    map.addLayer(this.drawnItems.value as unknown as L.Layer);

    map.on("zoomend", () => this.updateCircleSizes(map));
  }

  clearAllLayers(map: L.Map) {
    this.featureLayerManager.clearAllFeatures(map);
  }

  createLayerTools() {
    return {
      allCircles: this.allCircles,
      featureLayerManager: this.featureLayerManager,
      previousFeatureIds: this.previousFeatureIds,
      drawnItems: this.drawnItems,
      renderCities: this.renderCities.bind(this),
      renderZones: this.renderZones.bind(this),
      renderArrows: this.renderArrows.bind(this),
      renderShapes: this.renderShapes.bind(this),
      renderAllFeatures: this.renderAllFeatures.bind(this),
      updateCircleSizes: this.updateCircleSizes.bind(this),
      initializeBaseLayers: this.initializeBaseLayers.bind(this),
      clearAllLayers: this.clearAllLayers.bind(this),
    };
  }
}
