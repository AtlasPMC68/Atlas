export interface MapData {
  id: string;
  userId: string;
  title: string;
  description?: string;
  isPrivate: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface MapSaveAsPayload
  extends Omit<MapData, "id" | "userId" | "createdAt" | "updatedAt"> {}

export interface MapDisplay {
  id: string;
  title: string;
  userId: string;
  image?: string;
}
