export interface MapPeriod {
  id: string;
  title: string;
  startDate: string | null;
  endDate: string | null;
  exactDate: boolean;
  color: string;
}

export type SliderPeriod = MapPeriod & {
  startYear: number;
  endYear: number;
};

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
