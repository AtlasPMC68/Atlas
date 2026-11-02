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

export function isReviewStatus(status: unknown): boolean {
  return (
    status === ValidationStatus.REJECTED ||
    status === ValidationStatus.MANUAL_REVIEW
  );
}

export function isTextValidationReviewCandidate(feature: Feature): boolean {
  return (
    isReviewStatus(getFeatureValidationStatus(feature)) ||
    isUnrecognizedOcrFeature(feature)
  );
}

export function isUnrecognizedOcrFeature(feature: Feature): boolean {
  if (!feature.properties?.isOcrText) return false;

  const status = getFeatureValidationStatus(feature);
  return (
    isReviewStatus(status) ||
    (!feature.properties.recognized && feature.properties.show === false)
  );
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
