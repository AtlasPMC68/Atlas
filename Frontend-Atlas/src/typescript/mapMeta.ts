export type MapMeta = {
  id: string;
  userId: string;
  title: string;
  description: string;
  isPrivate: boolean;
  createdAt?: string;
  updatedAt?: string;
};

export type CreateMapInput = {
  userId: string;
  title: string;
  description: string;
  isPrivate: boolean;
};

export type CreateMapResponse = {
  mapId: string;
};