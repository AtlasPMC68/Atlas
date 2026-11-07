import { toRaw } from "vue";
import type { Feature, FeatureSnapshot } from "../typescript/feature";

/**
 * Normalizes a feature for signature hashing without redundantly duplicating
 * bulky image payloads (data URI, base64) that degrade memory and hashing speed.
 */
function normalizeFeatureForSignature(feature: Feature) {
  const rawProps = (feature.properties || {}) as Record<string, any>;

  let imageDesc = undefined;
  if (typeof feature.image === "string") {
    imageDesc = feature.image.length > 120 ? `[img:${feature.image.length}]` : feature.image;
  }

  let propImageDesc = undefined;
  if (typeof rawProps.image === "string") {
    propImageDesc = rawProps.image.length > 120 ? `[img:${rawProps.image.length}]` : rawProps.image;
  }

  return {
    id: String(feature.id),
    name: feature.name,
    mapId: feature.mapId,
    geometry: feature.geometry,
    image: imageDesc,
    properties: {
      ...rawProps,
      image: propImageDesc,
    },
  };
}

export function cloneFeatureSnapshot(features: Feature[]): FeatureSnapshot {
  if (!features || !Array.isArray(features)) return [];
  const raw = toRaw(features);
  if (typeof structuredClone === "function") {
    try {
      return structuredClone(raw) as FeatureSnapshot;
    } catch {
      // Fallback in case raw contains non-cloneable values
    }
  }
  return JSON.parse(JSON.stringify(raw)) as FeatureSnapshot;
}

export function buildFeatureSnapshotSignature(features: Feature[]): string {
  if (!features || !Array.isArray(features)) return "[]";

  const sortedFeatures = [...features].sort((a, b) =>
    String(a.id).localeCompare(String(b.id)),
  );

  return JSON.stringify(sortedFeatures.map(normalizeFeatureForSignature));
}

export function trimFeatureHistoryStack<T>(
  stack: T[],
  limit: number,
): T[] {
  return stack.slice(0, Math.max(1, limit));
}
