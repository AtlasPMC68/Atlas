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

export interface MapDisplay extends MapData {
  image: string;
}
