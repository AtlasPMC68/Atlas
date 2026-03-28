export interface MapData {
  id: string;
  userId: string;
  username: string;
  title: string;
  description?: string;
  isPrivate: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface MapSaveAsPayload
  extends Omit<MapData, "id" | "userId" | "createdAt" | "updatedAt"> {}

export interface MapDisplay extends MapData {
  image: string;
}
