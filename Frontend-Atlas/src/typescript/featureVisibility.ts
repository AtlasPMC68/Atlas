import type { Feature } from "./feature";

export type FeatureGroupType = "point" | "zone" | "arrow" | "shape";

export type FeatureGroup = {
  type: FeatureGroupType;
  label: string;
  aliases?: string[];
  features: Feature[];
};
