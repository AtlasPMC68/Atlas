export interface PickedColor {
  hex: string;
  rgb: [number, number, number];
  name: string;
  displayX: number;
  displayY: number;
  normalizedX: number;
  normalizedY: number;
}

export interface PendingClick {
  id: number;
  displayX: number;
  displayY: number;
}

export interface SampleColorResponse {
  hex: string;
  rgb: [number, number, number];
  lab: [number, number, number];
  name: string;
}
