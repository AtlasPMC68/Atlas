import type { Feature } from "../typescript/feature";
import {
  DEFAULT_HISTORY_LIMIT,
  type FeatureHistoryConfig,
  type FeatureHistoryState,
  type HistoryApplyResult,
  type HistoryAction,
  normalizeHistoryLimit,
} from "../typescript/history";
import {
  applyHistoryAction,
  applyHistoryInverseAction,
  cloneHistoryAction,
  validateUpdateHistoryAction,
} from "../utils/history";

export class FeatureHistoryService {
  private readonly limit: number;
  private readonly state: FeatureHistoryState = {
    undoStack: [],
    redoStack: [],
  };

  constructor(config?: Partial<FeatureHistoryConfig>) {
    this.limit = normalizeHistoryLimit(config?.limit ?? DEFAULT_HISTORY_LIMIT);
  }

  get canUndo(): boolean {
    return this.state.undoStack.length > 0;
  }

  get canRedo(): boolean {
    return this.state.redoStack.length > 0;
  }

  get historyLimit(): number {
    return this.limit;
  }

  getState(): FeatureHistoryState {
    return {
      undoStack: this.state.undoStack.map(cloneHistoryAction),
      redoStack: this.state.redoStack.map(cloneHistoryAction),
    };
  }

  clear(): void {
    this.state.undoStack = [];
    this.state.redoStack = [];
  }

  record(action: HistoryAction): void {
    const actionToRecord = cloneHistoryAction(action);

    if (
      actionToRecord.type === "update" &&
      !validateUpdateHistoryAction(actionToRecord)
    ) {
      throw new Error("Invalid update action: featureId must match before/after ids");
    }

    this.state.undoStack.push(actionToRecord);
    if (this.state.undoStack.length > this.limit) {
      this.state.undoStack.shift();
    }

    this.state.redoStack = [];
  }

  undo(features: Feature[]): HistoryApplyResult {
    const action = this.state.undoStack.pop();
    if (!action) {
      return {
        features,
        appliedAction: null,
      };
    }

    const nextFeatures = applyHistoryInverseAction(features, action);
    this.state.redoStack.push(cloneHistoryAction(action));

    return {
      features: nextFeatures,
      appliedAction: cloneHistoryAction(action),
    };
  }

  redo(features: Feature[]): HistoryApplyResult {
    const action = this.state.redoStack.pop();
    if (!action) {
      return {
        features,
        appliedAction: null,
      };
    }

    const nextFeatures = applyHistoryAction(features, action);
    this.state.undoStack.push(cloneHistoryAction(action));
    if (this.state.undoStack.length > this.limit) {
      this.state.undoStack.shift();
    }

    return {
      features: nextFeatures,
      appliedAction: cloneHistoryAction(action),
    };
  }
}
