export interface CustomLabelStyle {
  id: string;
  name: string;
  sizePx: number;
  fontStyle: "normal" | "italic";
  textTransform: "none" | "uppercase";
  color: string;
  priority: number;
  minZoom: number;
}

export type NewCustomLabelStyle = Omit<CustomLabelStyle, "id">;
