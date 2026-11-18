import type { MapData } from "./map";
import type { CreateProjectFormDraft } from "./editorDraft";

export type CreatedProjectRef = Pick<MapData, "id">;

export type CreateProjectDialogPrefill = {
  title?: string;
  description?: string;
  isPrivate?: boolean;
};

export type CreateProjectDialogExposed = {
  open: (prefill?: CreateProjectDialogPrefill) => void;
  close: () => void;
  getDraft: () => CreateProjectFormDraft | null;
  restoreDraft: (draft: CreateProjectFormDraft) => void;
};
