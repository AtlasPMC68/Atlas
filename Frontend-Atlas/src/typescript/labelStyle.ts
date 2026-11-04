export interface CustomLabelStyle {
  id: string;
  name: string;
  sizePx: number;
  fontStyle: "normal" | "italic";
  fontWeight?: "normal" | "bold";
  bold?: boolean;
  textTransform: "none" | "uppercase";
  color: string;
  priority: number;
  minZoom: number;
}

export type NewCustomLabelStyle = Omit<CustomLabelStyle, "id">;


export function getCustomStyleObject(style: CustomLabelStyle) {
  const isBold = style.fontWeight === "bold" || Boolean(style.bold);
  
  return {
    color: style.color || "inherit",
    fontWeight: isBold ? "bold" : "normal",
    fontStyle: style.fontStyle || "normal",
    textTransform: style.textTransform || "none",
  };
}

export function formatCustomStyleOptionLabel(style: CustomLabelStyle): string {
  return style.name; 
}