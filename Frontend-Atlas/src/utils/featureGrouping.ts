import {
  type Feature,
  type FeatureVisibilityGroup,
} from "../typescript/feature";
import type { MapPeriod } from "../typescript/map";
import { isVisibleInMainLayers } from "./featureValidationState";
import { getMapElementType } from "./featureHelpers";

export { isVisibleInMainLayers } from "./featureValidationState";

export interface MapGroupItem {
  id: string | null;
  title: string;
  startDate?: string | null;
  features: Feature[];
}

/**
 * Group features into standard display categories (point, zone, shape, image, drawing).
 */
export function groupFeaturesByType(features: Feature[]): FeatureVisibilityGroup[] {
  const pointGroup: FeatureVisibilityGroup = { type: "point", label: "Texte", features: [] };
  const zoneGroup: FeatureVisibilityGroup = { type: "zone", label: "Zone(s)", features: [] };
  const shapeGroup: FeatureVisibilityGroup = { type: "shape", label: "Forme(s)", features: [] };
  const imageGroup: FeatureVisibilityGroup = { type: "image", label: "Image(s)", features: [] };
  const drawingGroup: FeatureVisibilityGroup = { type: "drawing", label: "Dessins", features: [] };

  const groupsByType: Record<string, FeatureVisibilityGroup> = {
    point: pointGroup,
    label: pointGroup,
    zone: zoneGroup,
    shape: shapeGroup,
    image: imageGroup,
    polyline: drawingGroup,
    arrow: drawingGroup,
    drawing: drawingGroup,
  };

  features.forEach((feature: Feature) => {
    if (!isVisibleInMainLayers(feature)) return;

    const featureType = getMapElementType(feature);
    if (!featureType) return;

    const targetGroup = groupsByType[featureType] ?? drawingGroup;
    targetGroup.features.push(feature);
  });

  return [pointGroup, zoneGroup, shapeGroup, imageGroup, drawingGroup];
}

/**
 * Group a list of features by their associated mapId / mapPeriod.
 */
export function groupFeaturesByMap(
  features: Feature[],
  mapPeriods?: MapPeriod[],
): MapGroupItem[] {
  const mapGroups = new Map<string | null, MapGroupItem>();
  const periodByNormalizedId = mapPeriods
    ? new Map<string, MapPeriod>(
        mapPeriods.map((p) => [String(p.id).trim().toLowerCase(), p]),
      )
    : null;

  features.forEach((feature: Feature) => {
    const rawMapId =
      feature.mapId ??
      (feature as any).map_id ??
      (feature.properties as any)?.mapId ??
      (feature.properties as any)?.map_id ??
      null;
    const mapId = rawMapId ? String(rawMapId).trim() : null;
    if (!mapGroups.has(mapId)) {
      let title = "Éléments généraux";
      let startDate: string | null = null;
      if (mapId && periodByNormalizedId) {
        const period = periodByNormalizedId.get(mapId.toLowerCase());
        if (period) {
          title = period.title;
          startDate = period.startDate;
        }
      }
      if (title === "Éléments généraux" && mapId) {
        const customTitle = (feature as any).mapTitle || (feature.properties as any)?.mapTitle;
        if (customTitle) {
          title = customTitle;
        }
      }
      mapGroups.set(mapId, { id: mapId, title, startDate, features: [] });
    }
    mapGroups.get(mapId)!.features.push(feature);
  });

  return Array.from(mapGroups.values())
    .map((group) => {
      group.features.sort((a, b) => {
        const nameA = a.properties?.name || "! Nom manquant";
        const nameB = b.properties?.name || "! Nom manquant";
        return nameA.localeCompare(nameB);
      });
      return group;
    })
    .sort((a, b) => {
      if (a.id === null) return -1;
      if (b.id === null) return 1;

      if (a.startDate && b.startDate) {
        if (a.startDate < b.startDate) return -1;
        if (a.startDate > b.startDate) return 1;
      } else if (a.startDate) {
        return -1;
      } else if (b.startDate) {
        return 1;
      }

      return a.title.localeCompare(b.title);
    });
}
