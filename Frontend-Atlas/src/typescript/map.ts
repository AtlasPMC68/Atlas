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

export const PERIOD_COLORS: string[] = [
  "#0ea5e9",
  "#10b981",
  "#f59e0b",
  "#ef4444",
  "#8b5cf6",
  "#14b8a6",
  "#e11d48",
  "#84cc16",
];
