import type { Ref } from "vue";

export type BaseStage = {
  containerW: number;
  containerH: number;
  renderedW: number;
  renderedH: number;
  offsetX: number;
  offsetY: number;
  naturalW: number;
  naturalH: number;
};

export type ZoomableStageOptions = {
  containerRef?: Ref<HTMLElement | null>;
  imageRef?: Ref<HTMLImageElement | null>;
  zoomMin?: number;
  zoomMax?: number;
  zoomStepFactor?: number;
};

export type StagePosition = {
  normalized: { x: number; y: number };
  stage: { x: number; y: number };
};
