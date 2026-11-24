/**
 * Utility functions for continuous range selection and multi-selection across the application.
 */

/**
 * Calculates continuous range selection between an anchor item and a target item in an ordered list.
 *
 * @param orderedIds Array of IDs in the current visual/list order.
 * @param anchorId The ID of the element previously selected (starting anchor).
 * @param targetId The ID of the element clicked with modifier (Ctrl/Shift/Cmd).
 * @returns Array of IDs from anchorId to targetId inclusive in list order.
 *          If anchorId is missing, invalid, or not in orderedIds, returns [targetId].
 *          If targetId is not in orderedIds, returns [targetId] if targetId is valid, or empty array.
 */
export function getContinuousRangeSelection(
  orderedIds: (string | number)[],
  anchorId: string | number | null | undefined,
  targetId: string | number | null | undefined,
): string[] {
  if (targetId == null || targetId === "") return [];
  const targetStr = String(targetId).trim();
  if (!targetStr) return [];

  const stringList = orderedIds.map((id) => String(id).trim());

  if (anchorId == null || anchorId === "") {
    return [targetStr];
  }

  const anchorStr = String(anchorId).trim();

  const targetIndex = stringList.indexOf(targetStr);
  const anchorIndex = stringList.indexOf(anchorStr);

  if (targetIndex === -1 || anchorIndex === -1) {
    return [targetStr];
  }

  const start = Math.min(anchorIndex, targetIndex);
  const end = Math.max(anchorIndex, targetIndex);

  return stringList.slice(start, end + 1);
}

/**
 * Checks whether an event has Shift modifier active (range selection).
 */
export function isRangeSelectModifier(
  event:
    | MouseEvent
    | KeyboardEvent
    | { ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean }
    | null
    | undefined,
): boolean {
  if (!event) return false;
  return Boolean(event.shiftKey);
}

/**
 * Checks whether an event has Ctrl or Meta (Cmd on Mac) modifier active (toggle selection).
 */
export function isToggleSelectModifier(
  event:
    | MouseEvent
    | KeyboardEvent
    | { ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean }
    | null
    | undefined,
): boolean {
  if (!event) return false;
  return Boolean(event.ctrlKey || event.metaKey);
}

/**
 * Checks whether an event has any multi-select modifier active (Ctrl, Cmd or Shift).
 */
export function isMultiSelectModifier(
  event:
    | MouseEvent
    | KeyboardEvent
    | { ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean }
    | null
    | undefined,
): boolean {
  if (!event) return false;
  return Boolean(event.ctrlKey || event.metaKey || event.shiftKey);
}

/**
 * Deduplicates features by their unique ID to prevent duplicate Leaflet layer
 * instantiations and visual stacking artifacts. Never drops features solely
 * based on identical coordinates (e.g. across multiple maps or coincident points).
 */
export function deduplicateFeatures<T extends { id?: string | number; properties?: any }>(
  features: T[],
): T[] {
  const seenIds = new Set<string>();
  const result: T[] = [];

  for (const f of features) {
    const fid = f.id != null ? String(f.id).trim() : (f.properties?.id != null ? String(f.properties.id).trim() : "");
    if (fid) {
      if (seenIds.has(fid)) {
        continue;
      }
      seenIds.add(fid);
    }
    result.push(f);
  }

  return result;
}

/**
 * Checks whether a Leaflet layer (Marker, Path, Polygon, Polyline, or LayerGroup/FeatureGroup)
 * intersects with or is contained inside the given bounding box.
 * Recursively inspects child layers in L.LayerGroup to properly select points, cities and labels.
 */
export function doesLayerIntersectBounds(
  layer: any,
  selBounds: { intersects?: (b: any) => boolean; contains?: (latlng: any) => boolean } | null | undefined,
): boolean {
  if (!layer || !selBounds) return false;

  // 1. Direct getBounds (e.g. Polygon, Polyline, FeatureGroup)
  try {
    if (typeof layer.getBounds === "function") {
      const b = layer.getBounds();
      if (b && typeof selBounds.intersects === "function" && selBounds.intersects(b)) {
        return true;
      }
    }
  } catch {
    // Leaflet can throw when a layer has no geometry yet.
  }

  // 2. Direct getLatLng (e.g. Marker, CircleMarker)
  try {
    if (typeof layer.getLatLng === "function") {
      const latLng = layer.getLatLng();
      if (latLng && typeof selBounds.contains === "function" && selBounds.contains(latLng)) {
        return true;
      }
    }
  } catch {
    // Leaflet can throw when a marker has no latlng yet.
  }

  // 3. LayerGroup / FeatureGroup child inspection (recursively check children)
  try {
    if (typeof layer.getLayers === "function") {
      const children = layer.getLayers();
      if (Array.isArray(children)) {
        for (const child of children) {
          if (doesLayerIntersectBounds(child, selBounds)) {
            return true;
          }
        }
      }
    }
  } catch {
    // Leaflet can throw when a group has no child layers yet.
  }

  return false;
}

export interface SelectionModifierState {
  selectedId?: string | number | null;
  multiSelectedIds?: (string | number)[];
  lastAnchorId?: string | number | null;
  orderedIds?: (string | number)[];
}

export interface SelectionModifierResult {
  selectedId: string | null;
  multiSelectedIds: string[];
  newAnchorId: string;
  isModified: boolean;
}

/**
 * Standardized handler for Shift (range selection) and Ctrl/Meta (toggle selection) modifiers
 * across map layers, sidebar lists, legend, and timeline popovers.
 */
export function applySelectionModifier(
  clickedId: string | number,
  isCtrl: boolean,
  isShift: boolean,
  state: SelectionModifierState,
): SelectionModifierResult {
  const targetId = String(clickedId);

  if (isCtrl) {
    const currentList = (state.multiSelectedIds ?? []).map(String);
    const next = new Set<string>(currentList);
    if (state.selectedId != null && state.selectedId !== "") {
      next.add(String(state.selectedId));
    } else if (state.lastAnchorId != null && state.lastAnchorId !== "") {
      next.add(String(state.lastAnchorId));
    }
    if (next.has(targetId)) {
      next.delete(targetId);
    } else {
      next.add(targetId);
    }
    return {
      selectedId: null,
      multiSelectedIds: Array.from(next),
      newAnchorId: targetId,
      isModified: true,
    };
  }

  if (isShift) {
    const orderedIds = (state.orderedIds ?? []).map(String);
    const multiSelected = new Set((state.multiSelectedIds ?? []).map(String));
    const selectedInOrder = orderedIds.find((id) => multiSelected.has(id));
    const anchorId =
      state.selectedId != null && state.selectedId !== ""
        ? String(state.selectedId)
        : state.lastAnchorId != null && state.lastAnchorId !== ""
          ? String(state.lastAnchorId)
          : selectedInOrder ?? null;
    const range = getContinuousRangeSelection(orderedIds, anchorId, targetId);
    return {
      selectedId: null,
      multiSelectedIds: range,
      newAnchorId: anchorId || targetId,
      isModified: true,
    };
  }

  return {
    selectedId: targetId,
    multiSelectedIds: [],
    newAnchorId: targetId,
    isModified: false,
  };
}

/**
 * Resolves targeted features from single or multi selection state.
 */
export function getSelectedTargetFeatures<T extends { id?: string | number }>(
  allFeatures: T[],
  selectedId: string | number | null | undefined,
  multiSelectedIds: (string | number)[] = [],
): T[] {
  const ids =
    multiSelectedIds.length > 0
      ? multiSelectedIds.map(String)
      : selectedId != null && selectedId !== ""
        ? [String(selectedId)]
        : [];
  if (ids.length === 0) return [];
  const idSet = new Set(ids);
  return allFeatures.filter((f) => f.id != null && idSet.has(String(f.id)));
}

export function getNudgeDelta(
  key: string,
  isShift: boolean,
  baseNudgePx = 1,
  shiftNudgePx = 10,
): { dx: number; dy: number } | null {
  const lower = key.toLowerCase();
  const step = isShift ? shiftNudgePx : baseNudgePx;
  switch (lower) {
    case "arrowright":
      return { dx: step, dy: 0 };
    case "arrowleft":
      return { dx: -step, dy: 0 };
    case "arrowdown":
      return { dx: 0, dy: step };
    case "arrowup":
      return { dx: 0, dy: -step };
    default:
      return null;
  }
}

