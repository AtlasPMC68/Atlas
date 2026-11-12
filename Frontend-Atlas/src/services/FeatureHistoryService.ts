import { computed, ref, type ComputedRef } from "vue";
import type { Feature } from "../typescript/feature";
import type {
  FeatureSnapshot,
  FeatureTrackingCallback,
} from "../typescript/feature";
import { useProjectHistoryStore } from "../stores/projectHistory";
import {
  buildFeatureSnapshotSignature,
  cloneFeatureSnapshot,
  trimFeatureHistoryStack,
} from "../utils/featureHistory";

export class FeatureHistoryService {
  private localUndoStack = ref<FeatureSnapshot[]>([]);
  private localRedoStack = ref<FeatureSnapshot[]>([]);
  private localTrackingEnabled = ref(true);

  private _undoStack?: ComputedRef<FeatureSnapshot[]>;
  private _redoStack?: ComputedRef<FeatureSnapshot[]>;
  private _trackingEnabled?: ComputedRef<boolean>;
  private _canUndo?: ComputedRef<boolean>;
  private _canRedo?: ComputedRef<boolean>;

  constructor(private readonly limit: number = 30) {}

  private get store() {
    try {
      return useProjectHistoryStore();
    } catch {
      return null;
    }
  }

  public get undoStack(): ComputedRef<FeatureSnapshot[]> {
    if (!this._undoStack) {
      this._undoStack = computed(() => {
        const s = this.store;
        return s ? s.undoStack.map((e) => e.features) : this.localUndoStack.value;
      });
    }
    return this._undoStack;
  }

  public get redoStack(): ComputedRef<FeatureSnapshot[]> {
    if (!this._redoStack) {
      this._redoStack = computed(() => {
        const s = this.store;
        return s ? s.redoStack.map((e) => e.features) : this.localRedoStack.value;
      });
    }
    return this._redoStack;
  }

  public get trackingEnabled(): ComputedRef<boolean> {
    if (!this._trackingEnabled) {
      this._trackingEnabled = computed(() => {
        const s = this.store;
        return s ? s.trackingEnabled : this.localTrackingEnabled.value;
      });
    }
    return this._trackingEnabled;
  }

  public get canUndo(): ComputedRef<boolean> {
    if (!this._canUndo) {
      this._canUndo = computed(() => {
        const s = this.store;
        return s ? s.canUndo : this.localUndoStack.value.length > 0;
      });
    }
    return this._canUndo;
  }

  public get canRedo(): ComputedRef<boolean> {
    if (!this._canRedo) {
      this._canRedo = computed(() => {
        const s = this.store;
        return s ? s.canRedo : this.localRedoStack.value.length > 0;
      });
    }
    return this._canRedo;
  }

  commit(current: Feature[], next: Feature[], label?: string): FeatureSnapshot {
    const s = this.store;
    if (s) {
      return s.commit(current, next, label);
    }

    if (!this.localTrackingEnabled.value) {
      return cloneFeatureSnapshot(next);
    }

    if (
      buildFeatureSnapshotSignature(current) ===
      buildFeatureSnapshotSignature(next)
    ) {
      return cloneFeatureSnapshot(current);
    }

    this.localUndoStack.value = trimFeatureHistoryStack(
      [cloneFeatureSnapshot(current), ...this.localUndoStack.value],
      this.limit,
    );
    this.localRedoStack.value = [];

    return cloneFeatureSnapshot(next);
  }

  undo(current: Feature[]): FeatureSnapshot {
    const s = this.store;
    if (s) {
      return s.undo(current);
    }

    const previous = this.localUndoStack.value[0];
    if (!previous) {
      return cloneFeatureSnapshot(current);
    }

    this.localUndoStack.value = this.localUndoStack.value.slice(1);
    this.localRedoStack.value = trimFeatureHistoryStack(
      [cloneFeatureSnapshot(current), ...this.localRedoStack.value],
      this.limit,
    );

    return cloneFeatureSnapshot(previous);
  }

  redo(current: Feature[]): FeatureSnapshot {
    const s = this.store;
    if (s) {
      return s.redo(current);
    }

    const next = this.localRedoStack.value[0];
    if (!next) {
      return cloneFeatureSnapshot(current);
    }

    this.localRedoStack.value = this.localRedoStack.value.slice(1);
    this.localUndoStack.value = trimFeatureHistoryStack(
      [cloneFeatureSnapshot(current), ...this.localUndoStack.value],
      this.limit,
    );

    return cloneFeatureSnapshot(next);
  }

  reset(initial: Feature[] = []): FeatureSnapshot {
    const s = this.store;
    if (s) {
      return s.reset(initial);
    }

    this.localUndoStack.value = [];
    this.localRedoStack.value = [];

    return cloneFeatureSnapshot(initial);
  }

  withoutTracking<T>(callback: FeatureTrackingCallback<T>): T {
    const s = this.store;
    if (s) {
      return s.withoutTracking(callback);
    }

    this.localTrackingEnabled.value = false;
    try {
      return callback();
    } finally {
      queueMicrotask(() => {
        this.localTrackingEnabled.value = true;
      });
    }
  }
}
