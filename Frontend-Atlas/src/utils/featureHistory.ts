import { toRaw } from "vue";
import type { Feature } from "../typescript/feature";
import type {
  FeatureHistoryStack,
  FeatureSnapshot,
} from "../typescript/feature";

// TODO: exclure ou normaliser les champs lourds comme image pour éviter les problèmes de performance et de taille de snapshot
function toPlainFeatureSnapshot(features: Feature[]): FeatureSnapshot {
  return JSON.parse(JSON.stringify(toRaw(features))) as FeatureSnapshot;
}

export function cloneFeatureSnapshot(features: Feature[]): FeatureSnapshot {
  return toPlainFeatureSnapshot(features);
}

export function buildFeatureSnapshotSignature(features: Feature[]): string {
  const normalizedFeatures = toPlainFeatureSnapshot(features);

  const sortedFeatures = [...normalizedFeatures].sort((a, b) =>
    String(a.id).localeCompare(String(b.id)),
  );

  return JSON.stringify(
    sortedFeatures.map((feature) => ({
      ...feature,
      id: String(feature.id),
    })),
  );
}

export function trimFeatureHistoryStack(
  stack: FeatureHistoryStack,
  limit: number,
): FeatureHistoryStack {
  return stack.slice(0, limit);
}