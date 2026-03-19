import type { Feature } from "./feature";

export const DEFAULT_HISTORY_LIMIT = 20;
export const MAX_HISTORY_LIMIT = 50;

export type HistoryActionType = "create" | "update" | "delete" | "batch";

export interface BaseHistoryAction {
  type: HistoryActionType;
  timestamp: number;
}

export interface CreateFeatureHistoryAction extends BaseHistoryAction {
  type: "create";
  feature: Feature;
}

export interface UpdateFeatureHistoryAction extends BaseHistoryAction {
  type: "update";
  featureId: string;
  before: Feature;
  after: Feature;
}

export interface DeleteFeatureHistoryAction extends BaseHistoryAction {
  type: "delete";
  feature: Feature;
}

export type AtomicHistoryAction =
  | CreateFeatureHistoryAction
  | UpdateFeatureHistoryAction
  | DeleteFeatureHistoryAction;

export interface BatchHistoryAction extends BaseHistoryAction {
  type: "batch";
  actions: AtomicHistoryAction[];
}

export type HistoryAction = AtomicHistoryAction | BatchHistoryAction;

export interface FeatureHistoryState {
  undoStack: HistoryAction[];
  redoStack: HistoryAction[];
}

export interface FeatureHistoryConfig {
  limit: number;
}

export interface HistoryApplyResult {
  features: Feature[];
  appliedAction: HistoryAction | null;
}

export function normalizeHistoryLimit(limit: number): number {
  if (!Number.isFinite(limit) || limit <= 0) {
    return DEFAULT_HISTORY_LIMIT;
  }

  return Math.min(Math.floor(limit), MAX_HISTORY_LIMIT);
}

export function isBatchHistoryAction(
  action: HistoryAction,
): action is BatchHistoryAction {
  return action.type === "batch";
}

/*
 * Invariants for the upcoming history manager implementation:
 * 1) Every recorded action must be invertible.
 * 2) redoStack must be cleared when a new user action is recorded.
 * 3) undoStack size must never exceed config.limit.
 */
