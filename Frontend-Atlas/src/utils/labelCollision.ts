export interface LabelRectangle {
  left: number;
  right: number;
  top: number;
  bottom: number;
  width: number;
  height: number;
}

export interface LabelCollisionCandidate {
  id: string;
  text: string;
  priority: number;
  minZoom: number;
  rectangle: LabelRectangle;
}

function isOutsideBounds(
  rect: LabelRectangle,
  bounds: LabelRectangle,
): boolean {
  return (
    rect.right < bounds.left ||
    rect.left > bounds.right ||
    rect.bottom < bounds.top ||
    rect.top > bounds.bottom
  );
}

function overlapsByThreshold(
  rect: LabelRectangle,
  occupied: LabelRectangle[],
): boolean {
  for (const box of occupied) {
    const width = Math.max(
      0,
      Math.min(rect.right, box.right) - Math.max(rect.left, box.left),
    );
    const height = Math.max(
      0,
      Math.min(rect.bottom, box.bottom) - Math.max(rect.top, box.top),
    );
    const overlapArea = width * height;
    const smallestArea = Math.min(rect.width * rect.height, box.width * box.height);
    if (smallestArea > 0 && overlapArea / smallestArea >= 0.7) return true;
  }
  return false;
}

export function selectVisibleLabels(
  candidates: LabelCollisionCandidate[],
  bounds: LabelRectangle,
  zoom: number,
  selectedId: string | null,
): Set<string> {
  const sorted = [...candidates].sort(
    (a, b) => b.priority - a.priority || a.text.localeCompare(b.text),
  );
  const visible = new Set<string>();
  const occupied: LabelRectangle[] = [];

  for (const candidate of sorted) {
    const isSelected = candidate.id === selectedId;
    if (zoom < candidate.minZoom && !isSelected) continue;
    if (isOutsideBounds(candidate.rectangle, bounds)) continue;
    if (
      !isSelected &&
      overlapsByThreshold(candidate.rectangle, occupied)
    ) {
      continue;
    }

    visible.add(candidate.id);
    occupied.push(candidate.rectangle);
  }

  return visible;
}
