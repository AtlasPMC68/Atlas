import { defineStore } from "pinia";
import type { Feature } from "../typescript/feature";
import {
  cloneFeatureSnapshot,
  buildFeatureSnapshotSignature,
  trimFeatureHistoryStack,
} from "../utils/featureHistory";

export interface ProjectHistoryEntry {
  features: Feature[];
  label?: string;
  timestamp: number;
}

export const useProjectHistoryStore = defineStore("projectHistory", {
  state: () => ({
    undoStack: [] as ProjectHistoryEntry[],
    redoStack: [] as ProjectHistoryEntry[],
    trackingEnabled: true,
    maxLimit: 30,
    currentSignature: "",
  }),

  getters: {
    canUndo: (state): boolean => state.undoStack.length > 0,
    canRedo: (state): boolean => state.redoStack.length > 0,
    undoCount: (state): number => state.undoStack.length,
    redoCount: (state): number => state.redoStack.length,
    lastActionLabel: (state): string | null =>
      state.undoStack.length > 0 ? (state.undoStack[0].label ?? null) : null,
  },

  actions: {
    /**
     * Records a new state in the history stack.
     * Skips recording if tracking is disabled or if content has not changed.
     */
    commit(currentFeatures: Feature[], nextFeatures: Feature[], label?: string): Feature[] {
      if (!this.trackingEnabled) {
        return cloneFeatureSnapshot(nextFeatures);
      }

      const currentSig = buildFeatureSnapshotSignature(currentFeatures);
      const nextSig = buildFeatureSnapshotSignature(nextFeatures);

      // If content is identical, do not pollute the history stack
      if (currentSig === nextSig) {
        return cloneFeatureSnapshot(currentFeatures);
      }

      const entry: ProjectHistoryEntry = {
        features: cloneFeatureSnapshot(currentFeatures),
        label,
        timestamp: Date.now(),
      };

      this.undoStack = trimFeatureHistoryStack([entry, ...this.undoStack], this.maxLimit);
      this.redoStack = [];
      this.currentSignature = nextSig;

      return cloneFeatureSnapshot(nextFeatures);
    },

    /**
     * Reverts the last action and returns the previous state.
     */
    undo(currentFeatures: Feature[]): Feature[] {
      if (!this.canUndo) {
        return cloneFeatureSnapshot(currentFeatures);
      }

      const previousEntry = this.undoStack[0];
      this.undoStack = this.undoStack.slice(1);

      const currentEntry: ProjectHistoryEntry = {
        features: cloneFeatureSnapshot(currentFeatures),
        label: previousEntry.label,
        timestamp: Date.now(),
      };

      this.redoStack = trimFeatureHistoryStack([currentEntry, ...this.redoStack], this.maxLimit);
      this.currentSignature = buildFeatureSnapshotSignature(previousEntry.features);

      return cloneFeatureSnapshot(previousEntry.features);
    },

    /**
     * Reapplies the last undone action and returns the next state.
     */
    redo(currentFeatures: Feature[]): Feature[] {
      if (!this.canRedo) {
        return cloneFeatureSnapshot(currentFeatures);
      }

      const nextEntry = this.redoStack[0];
      this.redoStack = this.redoStack.slice(1);

      const currentEntry: ProjectHistoryEntry = {
        features: cloneFeatureSnapshot(currentFeatures),
        label: nextEntry.label,
        timestamp: Date.now(),
      };

      this.undoStack = trimFeatureHistoryStack([currentEntry, ...this.undoStack], this.maxLimit);
      this.currentSignature = buildFeatureSnapshotSignature(nextEntry.features);

      return cloneFeatureSnapshot(nextEntry.features);
    },

    /**
     * Resets history stacks (e.g. on active map or project switch).
     */
    reset(initialFeatures: Feature[] = []): Feature[] {
      this.undoStack = [];
      this.redoStack = [];
      this.currentSignature = buildFeatureSnapshotSignature(initialFeatures);
      return cloneFeatureSnapshot(initialFeatures);
    },

    /**
     * Executes an operation without recording any action in the history.
     */
    withoutTracking<T>(callback: () => T): T {
      const prev = this.trackingEnabled;
      this.trackingEnabled = false;
      try {
        return callback();
      } finally {
        queueMicrotask(() => {
          this.trackingEnabled = prev;
        });
      }
    },

    setTrackingEnabled(enabled: boolean) {
      this.trackingEnabled = enabled;
    },

    setMaxLimit(limit: number) {
      this.maxLimit = Math.max(1, limit);
    },
  },
});
