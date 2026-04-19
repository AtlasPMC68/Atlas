import type { MapData } from "./map";

export type CreatedProjectRef = Pick<MapData, "id">;

export type CreateProjectDialogPrefill = {
  title?: string;
  description?: string;
  isPrivate?: boolean;
};

export type CreateProjectDialogExposed = {
  open: (prefill?: CreateProjectDialogPrefill) => void;
  close: () => void;
};