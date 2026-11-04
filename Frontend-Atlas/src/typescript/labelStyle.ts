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

export function formatCustomStyleOptionLabel(style: CustomLabelStyle): string {
  const parts: string[] = [];

  if (style.color) {
    parts.push(style.color);
  }

  const isBold = style.fontWeight === "bold" || Boolean(style.bold);
  const isItalic = style.fontStyle === "italic";
  const isUppercase = style.textTransform === "uppercase";

  if (isBold) {
    parts.push("gras");
  }
  if (isItalic) {
    parts.push("italique");
  }
  if (isUppercase) {
    parts.push("majuscules");
  }

  if (parts.length === 0) {
    return `${style.name} (personnalisé)`;
  }

  return `${style.name} (${parts.join(", ")})`;
}
