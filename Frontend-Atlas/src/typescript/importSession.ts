import type { ControlPointInput, ImposedColor, WorldBounds } from "./georef";
import type { LegendAnswer } from "./legend";

// The three top-level phases of an import.
export type ImportPhase = "import" | "saisie" | "extraction";

export interface ImportOptions {
  textExtraction: boolean;
  shapesExtraction: boolean;
}

// What the user has entered so far, as the backend stores it
// (map_imports.inputs). Every key is absent until its step is confirmed.
export interface ImportInputs {
  frameBounds?: WorldBounds;
  legend?: LegendAnswer;
  controlPoints?: ControlPointInput[];
  colors?: ImposedColor[];
  options?: ImportOptions;
}

// A partial update: a value sets the key, null clears it.
export type ImportInputsPatch = {
  [K in keyof ImportInputs]?: ImportInputs[K] | null;
};

export type OcrState = "pending" | "running" | "done" | "failed";

export type ExtractionState =
  | "idle"
  | "waiting_for_text"
  | "queued"
  | "running"
  | "cancelling"
  | "cancelled"
  | "failed";

export interface ExtractionStatus {
  state: ExtractionState;
  taskId: string | null;
  error: string | null;
  progress: number;
  status: string;
}

// GET /imports/{mapId}
export interface ImportSessionResponse {
  mapId: string;
  projectId: string;
  mapTitle: string;
  filename: string;
  inputs: ImportInputs;
  ocr: { state: OcrState };
  extraction: ExtractionStatus;
}

export type StepId = "zone" | "legend" | "sift" | "cities" | "colors";

// locked: waiting on another step. available: can be done. done: can be redone.
export type StepStatus = "locked" | "available" | "done";

export interface StepState {
  id: StepId;
  status: StepStatus;
  required: boolean;
}

export type ApiResult<T> =
  | { success: true; data: T }
  | { success: false; error: string; status?: number };
