import { ValidationStatus, type Feature } from "../typescript/feature";

type ValidationProperties = Record<string, unknown>;

type SynchronizedValidationProperties = {
  validationStatus?: unknown;
  validation_status?: unknown;
  show?: boolean;
  recognized?: boolean;
};

export function getFeatureValidationStatus(
  feature: Feature,
): ValidationStatus | `${ValidationStatus}` | undefined {
  return (
    feature.properties?.validationStatus ??
    feature.properties?.validation_status
  );
}

export type FeatureReviewState = ValidationStatus | "unreviewed";

export function getFeatureReviewState(feature: Feature): FeatureReviewState {
  const status = getFeatureValidationStatus(feature);
  if (
    status === ValidationStatus.ACCEPTED ||
    status === ValidationStatus.REJECTED ||
    status === ValidationStatus.MANUAL_REVIEW
  ) {
    return status;
  }

  if (feature.properties?.isOcrText && !feature.properties.recognized) {
    return ValidationStatus.MANUAL_REVIEW;
  }

  return "unreviewed";
}

export function isReviewStatus(status: unknown): boolean {
  return (
    status === ValidationStatus.REJECTED ||
    status === ValidationStatus.MANUAL_REVIEW
  );
}

export function isTextValidationReviewCandidate(feature: Feature): boolean {
  const state = getFeatureReviewState(feature);
  return (
    state === ValidationStatus.REJECTED ||
    state === ValidationStatus.MANUAL_REVIEW
  );
}

export function isUnrecognizedOcrFeature(feature: Feature): boolean {
  if (!feature.properties?.isOcrText) return false;

  const state = getFeatureReviewState(feature);
  return state !== ValidationStatus.ACCEPTED && state !== "unreviewed";
}

export function isFeatureSelectedForValidation(
  feature: Feature,
  defaultSelected = true,
): boolean {
  const state = getFeatureReviewState(feature);
  if (state === ValidationStatus.ACCEPTED) return true;
  if (state === ValidationStatus.REJECTED) return false;

  const isUnrecognizedOcr =
    feature.properties?.isOcrText &&
    state === ValidationStatus.MANUAL_REVIEW;
  if (isUnrecognizedOcr) {
    return feature.properties?.userSelected !== undefined
      ? Boolean(feature.properties.userSelected)
      : defaultSelected;
  }

  return feature.properties?.show !== undefined
    ? Boolean(feature.properties.show)
    : defaultSelected;
}

export function isVisibleInMainLayers(feature: Feature): boolean {
  return !isUnrecognizedOcrFeature(feature);
}

export function synchronizeValidationState<T extends ValidationProperties>(
  properties: T,
  status = properties.validationStatus ?? properties.validation_status,
): T & SynchronizedValidationProperties {
  const next = { ...properties } as T & SynchronizedValidationProperties;
  if (status === undefined) return next;

  next.validationStatus = status;
  next.validation_status = status;

  if (status === ValidationStatus.ACCEPTED) {
    next.show = true;
    next.recognized = true;
  } else if (isReviewStatus(status)) {
    next.show = false;
    next.recognized = false;
  }

  return next;
}
