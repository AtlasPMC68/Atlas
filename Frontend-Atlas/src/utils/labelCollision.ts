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

const COLLISION_GRID_SIZE = 64;
const MAX_GRID_CELLS_PER_LABEL = 256;

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
  occupiedIndexes: Iterable<number>,
): boolean {
  for (const index of occupiedIndexes) {
    const box = occupied[index];
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

function getGridCells(rect: LabelRectangle): string[] | null {
  const minX = Math.floor(rect.left / COLLISION_GRID_SIZE);
  const maxX = Math.floor(rect.right / COLLISION_GRID_SIZE);
  const minY = Math.floor(rect.top / COLLISION_GRID_SIZE);
  const maxY = Math.floor(rect.bottom / COLLISION_GRID_SIZE);
  const cellCount = (maxX - minX + 1) * (maxY - minY + 1);
  if (cellCount > MAX_GRID_CELLS_PER_LABEL) return null;

  const cells: string[] = [];
  for (let x = minX; x <= maxX; x++) {
    for (let y = minY; y <= maxY; y++) {
      cells.push(`${x}:${y}`);
    }
  }
  return cells;
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
  const occupiedByCell = new Map<string, number[]>();
  const largeOccupiedIndexes: number[] = [];

  for (const candidate of sorted) {
    const isSelected = candidate.id === selectedId;
    if (zoom < candidate.minZoom && !isSelected) continue;
    if (isOutsideBounds(candidate.rectangle, bounds)) continue;

    const candidateCells = getGridCells(candidate.rectangle);
    if (!isSelected) {
      let nearbyIndexes: Iterable<number>;
      if (candidateCells) {
        const indexSet = new Set<number>(largeOccupiedIndexes);
        for (const cell of candidateCells) {
          const indexes = occupiedByCell.get(cell);
          if (indexes) {
            for (const idx of indexes) {
              indexSet.add(idx);
            }
          }
        }
        nearbyIndexes = indexSet;
      } else {
        nearbyIndexes = occupied.keys();
      }

      if (
        overlapsByThreshold(
          candidate.rectangle,
          occupied,
          nearbyIndexes,
        )
      ) {
        continue;
      }
    }

    visible.add(candidate.id);
    const occupiedIndex = occupied.length;
    occupied.push(candidate.rectangle);
    if (candidateCells) {
      candidateCells.forEach((cell) => {
        const indexes = occupiedByCell.get(cell) ?? [];
        indexes.push(occupiedIndex);
        occupiedByCell.set(cell, indexes);
      });
    } else {
      largeOccupiedIndexes.push(occupiedIndex);
    }
  }

  return visible;
}


