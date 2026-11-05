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
  const groups: FeatureVisibilityGroup[] = [
    { type: "point", label: "Texte", features: [] },
    { type: "zone", label: "Zone(s)", features: [] },
    { type: "shape", label: "Forme(s)", features: [] },
    { type: "image", label: "Image(s)", features: [] },
    { type: "drawing", label: "Dessins", features: [] },
  ];

  features.forEach((feature: Feature) => {
    if (!isVisibleInMainLayers(feature)) return;

    const featureType = getMapElementType(feature);
    if (!featureType) return;

    const targetGroup =
      groups.find((currentGroup) => {
        if (featureType === "label" || featureType === "point") {
          return currentGroup.type === "point";
        }
        if (featureType === "polyline" || featureType === "arrow") {
          return currentGroup.type === "drawing";
        }
        return currentGroup.type === featureType;
      }) ?? groups.find((currentGroup) => currentGroup.type === "drawing");

    if (targetGroup) targetGroup.features.push(feature);
  });

  return groups;
}

/**
 * Group a list of features by their associated mapId / mapPeriod.
 */
export function groupFeaturesByMap(
  features: Feature[],
  mapPeriods?: MapPeriod[],
): MapGroupItem[] {
  const mapGroups = new Map<string | null, MapGroupItem>();

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
      if (mapId && mapPeriods) {
        const period = mapPeriods.find(
          (p: MapPeriod) => String(p.id).trim().toLowerCase() === mapId.toLowerCase(),
        );
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
        const nameA = a.properties?.name || "Élément sans nom";
        const nameB = b.properties?.name || "Élément sans nom";
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
