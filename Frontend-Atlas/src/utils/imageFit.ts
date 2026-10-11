// Where an `object-contain` image actually sits inside its box.
export interface ContainRect {
  offsetX: number;
  offsetY: number;
  width: number;
  height: number;
  // Rendered pixels per natural image pixel.
  scale: number;
}

export function containRect(
  boxWidth: number,
  boxHeight: number,
  naturalWidth: number,
  naturalHeight: number,
): ContainRect | null {
  if (!boxWidth || !boxHeight || !naturalWidth || !naturalHeight) return null;
  const scale = Math.min(boxWidth / naturalWidth, boxHeight / naturalHeight);
  const width = naturalWidth * scale;
  const height = naturalHeight * scale;
  return {
    offsetX: (boxWidth - width) / 2,
    offsetY: (boxHeight - height) / 2,
    width,
    height,
    scale,
  };
}
