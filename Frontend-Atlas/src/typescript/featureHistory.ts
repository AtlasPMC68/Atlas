import type { Feature } from "./feature";

export type FeatureSnapshot = Feature[];
export type FeatureHistoryStack = FeatureSnapshot[];

export type FeatureTrackingCallback<T> = () => T;