export interface PickedColor {
  hex: string;
  rgb: [number, number, number];
  name: string;
  stageX: number;
  stageY: number;
  normalizedX: number;
  normalizedY: number;
  sampleRadiusPx: number;
}

export interface PendingClick {
  id: number;
  stageX: number;
  stageY: number;
  sampleRadiusPx: number;
}

export interface SampleColorResponse {
  hex: string;
  rgb: [number, number, number];
  lab: [number, number, number];
  name: string;
}

export type DialogCloseReason = "cancel" | "success" | "programmatic";
