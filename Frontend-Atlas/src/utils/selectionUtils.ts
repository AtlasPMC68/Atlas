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
