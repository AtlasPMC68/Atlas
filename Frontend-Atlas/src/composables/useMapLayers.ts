import { ref } from "vue";
import type { Ref } from "vue";
import L from "leaflet";
import {
  toArray,
  getRadiusForZoom,
  transformNormalizedToWorld,
} from "../utils/mapUtils";
import { MAP_CONFIG } from "./useMapConfig.js";
import { getMapElementType } from "../utils/featureTypes.js";

type MapLayersProps = {
  editMode?: boolean;
  activeEditMode?: string | null;
  featureVisibility?: Map<string | number, boolean>;
};

type EmitFn = (event: string, ...args: unknown[]) => void;

type Feature = {
  id?: string | number;
  name?: string;
  geometry?: any;
  properties?: any;
  color?: string;
  opacity?: number;
  stroke_width?: number;
};

type FeatureLayer = L.Layer & {
  options?: any;
  __atlas_originalStyle?: L.PathOptions;
  __atlas_onDown?: L.LeafletEventHandlerFn;
  __atlas_onPointerDown?: L.LeafletEventHandlerFn;
  __atlas_onClick?: L.LeafletEventHandlerFn;
  arrowheads?: (options: any) => void;
};

type EditingComposable = {
  applyAngleToLayerFromCanonical: (
    layer: L.Layer,
    map: L.Map,
    geometry: any,
    angleDeg: number,
    pivot: L.LatLng,
  ) => void;
};

type ClickHandler = (featureId: string, isCtrlPressed: boolean) => void;

class FeatureLayerManager {
  public layers = new Map<string, FeatureLayer>();
  private clickHandler: ClickHandler | null = null;
  private map: L.Map | null = null;

  constructor(
    private props: MapLayersProps,
    private allCircles: Ref<Set<any>>,
  ) {}

  setMap(map: L.Map) {
    this.map = map;
  }

  setClickHandler(handler: ClickHandler) {
    this.clickHandler = handler;
  }

  addFeatureLayer(
    featureId: string | number,
    layer: FeatureLayer,
    feature: any,
  ) {
    const fid = String(featureId);

    if (this.layers.has(fid)) {
      const oldLayer = this.layers.get(fid);
      if (oldLayer instanceof L.CircleMarker) {
        this.allCircles.value.delete(oldLayer);
      }
      if (this.map && oldLayer && this.map.hasLayer(oldLayer)) {
        this.map.removeLayer(oldLayer);
      }
    }

    this.layers.set(fid, layer);

    if ((layer as any).setStyle && feature) {
      layer.__atlas_originalStyle = {
        color: feature.color || MAP_CONFIG.DEFAULT_STYLES.borderColor,
        weight: 2,
        fillColor: feature.color || MAP_CONFIG.DEFAULT_STYLES.fillColor,
        fillOpacity: feature.opacity ?? MAP_CONFIG.DEFAULT_STYLES.opacity,
      };
    }

    if (layer instanceof L.CircleMarker) {
      this.allCircles.value.add(layer);
    }

    if (this.props.editMode) {
      this.makeLayerClickable(fid, layer);
    }

    const visible =
      this.props.featureVisibility?.get(fid) ??
      this.props.featureVisibility?.get(featureId);
    const shouldShow = visible === undefined ? true : Boolean(visible);

    if (shouldShow && this.map && !this.map.hasLayer(layer)) {
      this.map.addLayer(layer);
    }
    if (!shouldShow && this.map && this.map.hasLayer(layer)) {
      this.map.removeLayer(layer);
    }
  }

  makeLayerClickable(featureId: string, layer: FeatureLayer) {
    const fid = String(featureId);

    if (layer.options) {
      layer.options.interactive = true;
      layer.options.bubblingMouseEvents = true;
    }

    if (layer.__atlas_onDown) layer.off("mousedown", layer.__atlas_onDown);
    if (layer.__atlas_onClick) layer.off("click", layer.__atlas_onClick);
    if (layer.__atlas_onPointerDown)
      layer.off("pointerdown", layer.__atlas_onPointerDown);

    const markDom = (oe: any) => {
      const t = oe?.target;
      if (!t) return;
      t._atlasFeatureId = fid;
      if (t.parentElement) t.parentElement._atlasFeatureId = fid;
    };

    layer.__atlas_onDown = (e) => {
      const oe = (e as any).originalEvent;
      markDom(oe);

      if (this.props.editMode && this.props.activeEditMode) {
        oe?.stopPropagation();
        oe?.stopImmediatePropagation?.();
      }
    };

    layer.__atlas_onPointerDown = (e) => {
      const oe = (e as any).originalEvent;
      markDom(oe);

      if (this.props.editMode && this.props.activeEditMode) {
        oe?.stopPropagation();
        oe?.stopImmediatePropagation?.();
      }
    };

    layer.__atlas_onClick = (e) => {
      (e as any).originalEvent?.stopPropagation();

      if (this.clickHandler) {
        const isCtrlPressed =
          (e as any).originalEvent?.ctrlKey ||
          (e as any).originalEvent?.metaKey;
        this.clickHandler(fid, isCtrlPressed);
      }
    };

    layer.on("mousedown", layer.__atlas_onDown);
    layer.on("pointerdown", layer.__atlas_onPointerDown);
    layer.on("click", layer.__atlas_onClick);
  }

  toggleFeature(featureId: string | number, visible: boolean) {
    const fid = String(featureId);
    const layer = this.layers.get(fid);
    if (!layer || !this.map) return;

    if (visible) {
      if (!this.map.hasLayer(layer)) this.map.addLayer(layer);
    } else {
      if (this.map.hasLayer(layer)) this.map.removeLayer(layer);
    }
  }

  clearAllFeatures(map: L.Map | null) {
    this.layers.forEach((layer) => {
      if (layer instanceof L.CircleMarker) {
        this.allCircles.value.delete(layer);
      }
      if (map && map.hasLayer(layer)) {
        map.removeLayer(layer);
      }
    });
    this.layers.clear();
  }
}

class MapLayersService {
  public drawnItems = ref<L.FeatureGroup | null>(null);
  public allCircles = ref<Set<any>>(new Set());
  public previousFeatureIds = ref(new Set<string>());
  public featureLayerManager: FeatureLayerManager;

  constructor(
    private props: MapLayersProps,
    private editingComposable: EditingComposable,
  ) {
    this.featureLayerManager = new FeatureLayerManager(props, this.allCircles);
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

      this.featureLayerManager.addFeatureLayer(
        feature.id ?? "",
        circle,
        feature,
      );
    }
  }

  renderZones(features: Feature[], map: L.Map) {
    const safeFeatures = toArray(features) as Feature[];

    for (const feature of safeFeatures) {
      if (!feature.geometry || !Array.isArray(feature.geometry.coordinates))
        continue;

      const fprops = feature.properties || {};
      const rgb = Array.isArray(fprops.color_rgb) ? fprops.color_rgb : null;
      const colorFromRgb =
        rgb && rgb.length === 3 ? `rgb(${rgb[0]}, ${rgb[1]}, ${rgb[2]})` : null;
      const fillColor = feature.color || colorFromRgb || "#ccc";

      let targetGeometry = feature.geometry;

      if (fprops.is_normalized) {
        const fc = { type: "FeatureCollection", features: [feature] } as any;
        const anchorLat = -80 + Math.random() * 160;
        const anchorLng = -170 + Math.random() * 340;
        const sizeMeters = 2_000_000;

        const worldFc = transformNormalizedToWorld(
          fc,
          anchorLat,
          anchorLng,
          sizeMeters,
        ) as any;
        if (worldFc?.features?.[0]?.geometry) {
          targetGeometry = worldFc.features[0].geometry;
        }
      }

      let latLngs: L.LatLngTuple[] | null = null;

      if (targetGeometry.type === "Polygon") {
        const outer = targetGeometry.coordinates?.[0];
        if (Array.isArray(outer) && outer.length >= 4) {
          latLngs = outer.map((pair: any) => [pair[1], pair[0]]);
        }
      } else if (targetGeometry.type === "MultiPolygon") {
        const outer = targetGeometry.coordinates?.[0]?.[0];
        if (Array.isArray(outer) && outer.length >= 4) {
          latLngs = outer.map((pair: any) => [pair[1], pair[0]]);
        }
      } else {
        continue;
      }

      if (!latLngs) continue;

      const poly = L.polygon(latLngs, {
        color: "#333",
        weight: 1,
        fillColor,
        fillOpacity: 0.5,
        interactive: true,
      });

      const angleDeg = feature.properties?.rotation_deg ?? 0;
      if (Math.abs(angleDeg) > 1e-6) {
        const pivot = feature.properties?.center
          ? L.latLng(
              feature.properties.center.lat,
              feature.properties.center.lng,
            )
          : poly.getBounds().getCenter();

        if (targetGeometry?.type === "Polygon") {
          this.editingComposable.applyAngleToLayerFromCanonical(
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

      this.featureLayerManager.addFeatureLayer(feature.id ?? "", poly, feature);
    }
  }

  renderArrows(features: Feature[], map: L.Map) {
    void map;
    const safeFeatures = toArray(features) as Feature[];

    for (const feature of safeFeatures) {
      if (!feature.geometry || !Array.isArray(feature.geometry.coordinates))
        continue;

      const latLngs = feature.geometry.coordinates.map((pair: any) => [
        pair[1],
        pair[0],
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
      }) as FeatureLayer;

      const name = fprops.name || feature.name;
      if (name) line.bindPopup(name);

      const elementType = getMapElementType(feature);
      const visible = this.props.featureVisibility?.get(String(feature.id));
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

      this.featureLayerManager.addFeatureLayer(feature.id ?? "", line, feature);
    }
  }

  renderShapes(features: Feature[], map: L.Map) {
    const safeFeatures = toArray(features) as Feature[];

    for (const feature of safeFeatures) {
      if (
        !feature.geometry ||
        !Array.isArray(feature.geometry.coordinates) ||
        !feature.geometry.coordinates[0]
      )
        continue;

      const latLngs = feature.geometry.coordinates[0].map((coord: any) => [
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

      const angleDeg = feature.properties?.rotation_deg ?? 0;

      if (Math.abs(angleDeg) > 1e-6) {
        const pivot = feature.properties?.center
          ? L.latLng(
              feature.properties.center.lat,
              feature.properties.center.lng,
            )
          : shape.getBounds().getCenter();

        this.editingComposable.applyAngleToLayerFromCanonical(
          shape,
          map,
          feature.geometry,
          angleDeg,
          pivot,
        );
      }

      if (feature.name) shape.bindPopup(feature.name);

      this.featureLayerManager.addFeatureLayer(
        feature.id ?? "",
        shape,
        feature,
      );
    }
  }

  renderAllFeatures(filteredFeatures: Feature[], map: L.Map) {
    const currentIds = new Set(filteredFeatures.map((f) => String(f.id)));
    const previousIds = this.previousFeatureIds.value;

    previousIds.forEach((oldId) => {
      if (!currentIds.has(oldId)) {
        const layer = this.featureLayerManager.layers.get(oldId);
        if (layer && map.hasLayer(layer)) {
          map.removeLayer(layer);
        }
        this.featureLayerManager.layers.delete(oldId);
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

  getApi() {
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

export function useMapLayers(
  props: MapLayersProps,
  _emit: EmitFn,
  editingComposable: EditingComposable,
) {
  void _emit;
  const service = new MapLayersService(props, editingComposable);
  return service.getApi();
}
