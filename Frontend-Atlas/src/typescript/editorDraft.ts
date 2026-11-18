import type { Feature } from "./feature";

export interface FeatureEditFormDraft {
  featureId: string;
  name: string;
  labelText?: string;
  color?: string;
  strokeColor?: string;
  opacity?: number | string;
  strokeOpacity?: number | string;
  strokeWidth?: number | string;
}

export interface AddMapFormDraft {
  title: string;
  startYear: number | string | null;
  endYear: number | string | null;
  startDate: string;
  endDate: string;
  usePreciseDates: boolean;
}

export interface AddImageFormDraft {
  selectedFile: File | null;
}

export interface CreateProjectFormDraft {
  title?: string;
  description?: string;
  isPrivate: boolean;
}

// A present entry represents a form that should be reopened after reconnecting.
export interface EditorFormDrafts {
  featureEdit?: FeatureEditFormDraft;
  addMap?: AddMapFormDraft;
  addImage?: AddImageFormDraft;
  createProject?: CreateProjectFormDraft;
}

export interface EditorDraftScope {
  projectId: string;
  // The identity that owned the edits, retained when authentication expires.
  subject: string | null;
}

export interface EditorDraft extends EditorDraftScope {
  version: 1;
  id: string;
  updatedAt: number;
  features: Feature[];
  visibility: [string, boolean][];
  persistedFeatureIds: string[];
  pendingDeletions: string[];
  baseFeatures: Feature[];
  forms: EditorFormDrafts;
  intent: "resume" | "save" | null;
  // A pending phase survives a redirect or lost response; it must not be replayed blindly.
  savePhase: "idle" | "put-pending" | "delete-pending";
  targetProjectId?: string;
}
