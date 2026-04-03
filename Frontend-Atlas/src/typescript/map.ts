export interface MapData {
  id: string;
  userId: string;
  username: string;
  title: string;
  description?: string;
  isPrivate: boolean;
  createdAt: string;
  updatedAt: string;
  image?: string;
}

export interface MapSaveAsPayload extends Omit<
  MapData,
  "id" | "userId" | "createdAt" | "updatedAt" | "image"
> {}

export type CreatedMapRef = Pick<MapData, "id">;

export type CreateMapDialogPrefill = {
  title?: string;
  description?: string;
  isPrivate?: boolean;
};

export type CreateMapDialogExposed = {
  open: (prefill?: CreateMapDialogPrefill) => void;
  close: () => void;
};