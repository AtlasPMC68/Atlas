import type { Feature } from "../typescript/feature";

export interface FeatureInteractionOptions<T = Feature> {
  /** Maximum delay between two clicks to be considered a double-click (in ms). Default: 400 */
  thresholdMs?: number;
  /** Callback fired on a single click or selection */
  onSelect?: (item: T) => void;
  /** Callback fired on double click / edit request */
  onEdit?: (item: T) => void;
  /** Function to extract a unique ID from the item. Defaults to item.id */
  getId?: (item: T) => string | number | null | undefined;
}

export interface FeatureInteractionHandler<T = Feature> {
  handleClick: (item: T, event?: Event | unknown) => void;
  handleDblClick: (item: T, event?: Event | unknown) => void;
  reset: () => void;
}

/**
 * Creates a reusable handler for single and double click interactions on features.
 * Handles both native double-click events and consecutive fast clicks (which is critical
 * for map layers and elements where drag handlers intercept or suppress native dblclick).
 */
export function createFeatureDoubleClickHandler<T = Feature>(
  options: FeatureInteractionOptions<T>,
): FeatureInteractionHandler<T> {
  const thresholdMs = options.thresholdMs ?? 400;
  let lastClickTime = 0;
  let lastClickId: string | number | null = null;
  let lastEditTime = 0;
  let lastEditId: string | number | null = null;

  const getId = (item: T): string | number | null => {
    if (options.getId) {
      const id = options.getId(item);
      return id != null ? String(id) : null;
    }
    const anyItem = item as { id?: string | number | null };
    return anyItem?.id != null ? String(anyItem.id) : null;
  };

  const handleEdit = (item: T) => {
    const id = getId(item);
    const now = Date.now();
    // Guard against duplicated edit triggers within 300ms (e.g. if consecutive clicks and native dblclick both fire)
    if (lastEditId === id && now - lastEditTime < 300) {
      return;
    }
    lastEditTime = now;
    lastEditId = id;
    lastClickTime = 0;
    lastClickId = null;

    options.onSelect?.(item);
    options.onEdit?.(item);
  };

  const handleClick = (item: T) => {
    const id = getId(item);
    const now = Date.now();

    if (id != null && lastClickId === id && now - lastClickTime <= thresholdMs) {
      // Consecutive clicks on the same item within threshold -> trigger double-click/edit
      handleEdit(item);
    } else {
      lastClickTime = now;
      lastClickId = id;
      options.onSelect?.(item);
    }
  };

  const handleDblClick = (item: T) => {
    handleEdit(item);
  };

  const reset = () => {
    lastClickTime = 0;
    lastClickId = null;
    lastEditTime = 0;
    lastEditId = null;
  };

  return {
    handleClick,
    handleDblClick,
    reset,
  };
}
