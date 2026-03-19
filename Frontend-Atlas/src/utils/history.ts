import type { Feature } from "../typescript/feature";
import {
  type AtomicHistoryAction,
  type HistoryAction,
  type UpdateFeatureHistoryAction,
  isBatchHistoryAction,
} from "../typescript/history";

export function cloneFeature(feature: Feature): Feature {
  return JSON.parse(JSON.stringify(feature)) as Feature;
}

export function cloneHistoryAction(action: HistoryAction): HistoryAction {
  if (isBatchHistoryAction(action)) {
    return {
      ...action,
      actions: action.actions.map(
        (child) => cloneHistoryAction(child) as AtomicHistoryAction,
      ),
    };
  }

  if (action.type === "update") {
    return {
      ...action,
      before: cloneFeature(action.before),
      after: cloneFeature(action.after),
    };
  }

  return {
    ...action,
    feature: cloneFeature(action.feature),
  };
}

export function replaceFeature(
  features: Feature[],
  nextFeature: Feature,
): Feature[] {
  const index = features.findIndex((feature) => feature.id === nextFeature.id);
  if (index === -1) {
    return [...features, cloneFeature(nextFeature)];
  }

  const next = [...features];
  next[index] = cloneFeature(nextFeature);
  return next;
}

export function removeFeatureById(
  features: Feature[],
  featureId: string,
): Feature[] {
  return features.filter((feature) => feature.id !== featureId);
}

function applyAtomicAction(
  features: Feature[],
  action: AtomicHistoryAction,
): Feature[] {
  if (action.type === "create") {
    return replaceFeature(features, action.feature);
  }

  if (action.type === "delete") {
    return removeFeatureById(features, action.feature.id);
  }

  return replaceFeature(features, action.after);
}

function applyAtomicInverse(
  features: Feature[],
  action: AtomicHistoryAction,
): Feature[] {
  if (action.type === "create") {
    return removeFeatureById(features, action.feature.id);
  }

  if (action.type === "delete") {
    return replaceFeature(features, action.feature);
  }

  return replaceFeature(features, action.before);
}

export function applyHistoryAction(
  features: Feature[],
  action: HistoryAction,
): Feature[] {
  if (!isBatchHistoryAction(action)) {
    return applyAtomicAction(features, action);
  }

  return action.actions.reduce<Feature[]>(
    (currentFeatures, childAction) =>
      applyAtomicAction(currentFeatures, childAction),
    features,
  );
}

export function applyHistoryInverseAction(
  features: Feature[],
  action: HistoryAction,
): Feature[] {
  if (!isBatchHistoryAction(action)) {
    return applyAtomicInverse(features, action);
  }

  return [...action.actions]
    .reverse()
    .reduce<
      Feature[]
    >((currentFeatures, childAction) => applyAtomicInverse(currentFeatures, childAction), features);
}

export function validateUpdateHistoryAction(
  action: UpdateFeatureHistoryAction,
): boolean {
  return (
    action.featureId === action.before.id &&
    action.featureId === action.after.id
  );
}
